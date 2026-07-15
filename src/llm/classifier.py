import asyncio
import json
import logging

from openai import APIStatusError, AsyncOpenAI
from openai import RateLimitError as OpenAIRateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import Settings
from src.http.rate_limit import RateLimitError
from src.llm.cache import SegmentCache
from src.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from src.llm.schemas import CLASSIFICATION_SCHEMA, SegmentBatchResponse
from src.models.product import PriceSegment, Product

logger = logging.getLogger(__name__)


def _mock_classify(product: Product) -> str:
    """Rule-based classification for mock/CI mode."""
    if product.price < 15_000:
        return PriceSegment.ECONOMY.value
    if product.price < 60_000:
        return PriceSegment.STANDARD.value
    return PriceSegment.PREMIUM.value


class SegmentClassifier:
    """Batch LLM classifier with SQLite cache."""

    def __init__(self, settings: Settings, cache: SegmentCache) -> None:
        self.settings = settings
        self.cache = cache
        self._client: AsyncOpenAI | None = None
        self.api_calls = 0
        self.cache_hits = 0

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        return self._client

    async def classify_all(self, products: list[Product]) -> list[Product]:
        """Classify all products, using cache and batching."""
        result: list[Product] = []
        uncached: list[Product] = []

        for product in products:
            cached = self.cache.get(product.id, product.name, product.description)
            if cached:
                self.cache_hits += 1
                product.segment = cached
                result.append(product)
            else:
                uncached.append(product)

        if uncached:
            if self.settings.llm_mock:
                for product in uncached:
                    product.segment = _mock_classify(product)
                    self.cache.set(product.id, product.name, product.description, product.segment)
                    result.append(product)
            else:
                classified = await self._classify_batches(uncached)
                result.extend(classified)

        logger.info(
            "Classified %d products (cache hits: %d, API calls: %d)",
            len(result),
            self.cache_hits,
            self.api_calls,
        )
        return result

    async def _classify_batches(self, products: list[Product]) -> list[Product]:
        batch_size = self.settings.llm_batch_size
        classified: list[Product] = []

        for i in range(0, len(products), batch_size):
            batch = products[i : i + batch_size]
            try:
                segments = await self._classify_batch(batch)
                for product in batch:
                    segment = segments.get(product.id, PriceSegment.STANDARD.value)
                    product.segment = segment
                    self.cache.set(product.id, product.name, product.description, segment)
                    classified.append(product)
            except Exception as e:
                logger.error("Batch classification failed: %s, using mock fallback", e)
                for product in batch:
                    product.segment = _mock_classify(product)
                    self.cache.set(product.id, product.name, product.description, product.segment)
                    classified.append(product)

        return classified

    @retry(
        retry=retry_if_exception_type((OpenAIRateLimitError, RateLimitError)),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def _classify_batch(self, products: list[Product]) -> dict[str, str]:
        """Call OpenAI; retries on HTTP 429 with exponential backoff (1→2→4→8s)."""
        client = self._get_client()

        product_dicts = [
            {
                "id": p.id,
                "name": p.name,
                "price": p.price,
                "currency": p.currency,
                "description": p.description,
            }
            for p in products
        ]

        try:
            response = await client.chat.completions.create(
                model=self.settings.openai_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(product_dicts)},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "segment_classification",
                        "strict": True,
                        "schema": CLASSIFICATION_SCHEMA,
                    },
                },
                temperature=0.1,
            )
        except OpenAIRateLimitError as e:
            retry_after = None
            if e.response is not None:
                raw = e.response.headers.get("retry-after")
                if raw is not None:
                    try:
                        retry_after = float(raw)
                    except (TypeError, ValueError):
                        retry_after = None
            logger.warning(
                "OpenAI HTTP 429 Too Many Requests, retry_after=%s",
                retry_after,
            )
            if retry_after and retry_after > 0:
                await asyncio.sleep(retry_after)
            raise RateLimitError(retry_after) from e
        except APIStatusError as e:
            if e.status_code == 429:
                logger.warning("OpenAI HTTP 429 (APIStatusError)")
                raise RateLimitError(None) from e
            raise

        self.api_calls += 1
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty LLM response")

        parsed = SegmentBatchResponse.model_validate(json.loads(content))
        return {item.id: item.segment for item in parsed.classifications}
