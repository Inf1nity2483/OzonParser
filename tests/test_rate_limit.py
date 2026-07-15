from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Settings
from src.crm.amocrm_client import AmoCRMClient
from src.http.rate_limit import RateLimitError, parse_retry_after, raise_for_rate_limit
from src.models.product import CRMTask
from src.parser.ozon_client import AccessForbiddenError, OzonClient


class TestRaiseForRateLimit:
    def test_parse_retry_after(self):
        assert parse_retry_after({"Retry-After": "2.5"}) == 2.5
        assert parse_retry_after({"retry-after": "1"}) == 1.0
        assert parse_retry_after({}) is None
        assert parse_retry_after({"Retry-After": "soon"}) is None

    @pytest.mark.asyncio
    async def test_raise_on_429(self):
        with pytest.raises(RateLimitError) as exc:
            await raise_for_rate_limit(429, {"Retry-After": "0"}, context="test")
        assert exc.value.retry_after == 0.0

    @pytest.mark.asyncio
    async def test_noop_on_other_status(self):
        await raise_for_rate_limit(200, {})
        await raise_for_rate_limit(500, {"Retry-After": "1"})


class TestOzon429:
    @pytest.mark.asyncio
    async def test_fetch_page_rate_limit(self, tmp_path):
        settings = Settings(
            demo_mode=True,
            checkpoint_dir=tmp_path / "checkpoints",
            data_dir=tmp_path / "data",
            request_delay_ms=0,
        )
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "0"}

        async with OzonClient(settings) as client:
            client._client.get = AsyncMock(return_value=mock_response)
            with pytest.raises(RateLimitError):
                await client.fetch_page(settings.ozon_category_url, 1)

    @pytest.mark.asyncio
    async def test_fetch_page_403_not_retried_as_rate_limit(self, tmp_path):
        settings = Settings(
            demo_mode=True,
            checkpoint_dir=tmp_path / "checkpoints",
            data_dir=tmp_path / "data",
            request_delay_ms=0,
        )
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.headers = {}

        async with OzonClient(settings) as client:
            client._client.get = AsyncMock(return_value=mock_response)
            with pytest.raises(AccessForbiddenError):
                await client.fetch_page(settings.ozon_category_url, 1)
            assert client._client.get.await_count == 1


class TestAmoCRM429:
    @pytest.mark.asyncio
    async def test_create_tasks_retries_then_counts_error(self, tmp_path):
        settings = Settings(
            crm_mock=False,
            amocrm_subdomain="test",
            amocrm_access_token="token",
            data_dir=tmp_path / "data",
        )
        client = AmoCRMClient(settings)
        tasks = [
            CRMTask(product_id="1", text="Task", complete_till=1700000000),
        ]

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "0"}
        mock_response.text = "rate limited"

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with patch("src.crm.amocrm_client.httpx.AsyncClient", return_value=mock_http):
            created, errors = await client.create_tasks(tasks)

        assert created == 0
        assert errors == 1
        assert mock_http.post.await_count == 5  # tenacity: 5 attempts
