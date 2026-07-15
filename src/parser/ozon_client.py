import asyncio
import logging
from urllib.parse import quote, urlparse

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import Settings
from src.http.rate_limit import RateLimitError, raise_for_rate_limit

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.ozon.ru/",
}


class AccessForbiddenError(Exception):
    """Raised when Ozon returns 403 (antibot / access denied)."""


class OzonClient:
    """HTTP client for Ozon storefront composer-api."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "OzonClient":
        self._client = httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._client:
            await self._client.aclose()

    def _build_api_url(self, category_path: str, page: int) -> str:
        """Build composer-api URL for a category page."""
        parsed = urlparse(category_path)
        path = parsed.path.rstrip("/")
        page_url = f"{path}/?page={page}"
        encoded = quote(page_url, safe="")
        return f"{self.settings.ozon_api_base}?url={encoded}"

    def _extract_category_path(self, category_url: str) -> str:
        parsed = urlparse(category_url)
        return parsed.path

    @retry(
        retry=retry_if_exception_type((RateLimitError, httpx.TransportError)),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def fetch_page(self, category_url: str, page: int) -> dict:
        if not self._client:
            raise RuntimeError("Client not initialized. Use async with.")

        category_path = self._extract_category_path(category_url)
        url = self._build_api_url(category_path, page)

        logger.info("Fetching Ozon page %d: %s", page, url)

        response = await self._client.get(url)

        await raise_for_rate_limit(
            response.status_code,
            response.headers,
            context=f"ozon page {page}",
        )

        if response.status_code == 403:
            logger.warning("Access forbidden (antibot) on page %d", page)
            raise AccessForbiddenError(f"Access forbidden on page {page}")

        if response.status_code >= 500:
            logger.warning("Server error %d on page %d", response.status_code, page)
            response.raise_for_status()

        if response.status_code != 200:
            logger.error("Unexpected status %d on page %d", response.status_code, page)
            response.raise_for_status()

        delay = self.settings.request_delay_ms / 1000
        if delay > 0:
            await asyncio.sleep(delay)

        return response.json()
