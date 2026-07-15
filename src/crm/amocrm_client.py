import json
import logging

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import Settings
from src.http.rate_limit import RateLimitError, raise_for_rate_limit
from src.models.product import CRMTask

logger = logging.getLogger(__name__)


class AmoCRMClient:
    """AmoCRM API v4 client for task creation."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._access_token = settings.amocrm_access_token

    async def _refresh_token(self) -> str:
        url = f"{self.settings.amocrm_base_url}/oauth2/access_token"
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={
                    "client_id": self.settings.amocrm_client_id,
                    "client_secret": self.settings.amocrm_client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": self.settings.amocrm_refresh_token,
                    "redirect_uri": self.settings.amocrm_redirect_uri,
                },
            )
            await raise_for_rate_limit(
                response.status_code,
                response.headers,
                context="amocrm oauth refresh",
            )
            response.raise_for_status()
            data = response.json()
            self._access_token = data["access_token"]
            return self._access_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    @retry(
        retry=retry_if_exception_type((RateLimitError, httpx.TransportError)),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def _post_tasks_batch(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: list[dict],
    ) -> httpx.Response:
        """POST a batch of tasks; retries on 429 with Retry-After + exponential backoff."""
        response = await client.post(url, json=payload, headers=self._headers())

        await raise_for_rate_limit(
            response.status_code,
            response.headers,
            context="amocrm create tasks",
        )

        if response.status_code == 401:
            await self._refresh_token()
            response = await client.post(url, json=payload, headers=self._headers())
            await raise_for_rate_limit(
                response.status_code,
                response.headers,
                context="amocrm create tasks (after refresh)",
            )

        return response

    async def create_tasks(self, tasks: list[CRMTask]) -> tuple[int, int]:
        """
        Create tasks in AmoCRM.

        Returns:
            Tuple of (created_count, error_count)
        """
        if not tasks:
            return 0, 0

        if self.settings.crm_mock:
            return await self._mock_create_tasks(tasks)

        created = 0
        errors = 0
        batch_size = 50

        async with httpx.AsyncClient() as client:
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i : i + batch_size]
                payload = []
                for t in batch:
                    item: dict = {"text": t.text, "complete_till": t.complete_till}
                    if t.entity_id:
                        item["entity_type"] = t.entity_type
                        item["entity_id"] = t.entity_id
                    payload.append(item)

                url = f"{self.settings.amocrm_base_url}/api/v4/tasks"
                try:
                    response = await self._post_tasks_batch(client, url, payload)
                except RateLimitError:
                    errors += len(batch)
                    logger.error(
                        "AmoCRM rate limit exceeded after retries for batch of %d",
                        len(batch),
                    )
                    continue

                if response.status_code in (200, 201):
                    data = response.json()
                    embedded = data.get("_embedded", {})
                    created += len(embedded.get("tasks", batch))
                    logger.info("Created %d AmoCRM tasks", len(batch))
                else:
                    errors += len(batch)
                    logger.error(
                        "AmoCRM error %d: %s",
                        response.status_code,
                        response.text[:200],
                    )

        return created, errors

    async def _mock_create_tasks(self, tasks: list[CRMTask]) -> tuple[int, int]:
        """Save tasks to JSON file in mock mode."""
        output_path = self.settings.data_dir / "tasks.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        existing: list[dict] = []
        if output_path.exists():
            existing = json.loads(output_path.read_text(encoding="utf-8"))

        new_tasks = [
            {
                "product_id": t.product_id,
                "text": t.text,
                "complete_till": t.complete_till,
                "status": "created",
            }
            for t in tasks
        ]
        existing.extend(new_tasks)
        output_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info("Mock CRM: saved %d tasks to %s", len(tasks), output_path)
        return len(tasks), 0
