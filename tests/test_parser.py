import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Settings
from src.parser.ozon_client import OzonClient, RateLimitError
from src.parser.ozon_parser import OzonParser
from src.storage.checkpoint import CheckpointStore

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def settings(tmp_path):
    return Settings(
        demo_mode=True,
        demo_target_count=50,
        checkpoint_dir=tmp_path / "checkpoints",
        data_dir=tmp_path / "data",
        request_delay_ms=0,
    )


@pytest.fixture
def checkpoint(settings):
    return CheckpointStore(settings.checkpoint_dir)


@pytest.fixture
def ozon_page_data():
    with open(FIXTURES_DIR / "ozon_page.json", encoding="utf-8") as f:
        return json.load(f)


class TestOzonClient:
    @pytest.mark.asyncio
    async def test_fetch_page_success(self, settings, ozon_page_data):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = ozon_page_data

        async with OzonClient(settings) as client:
            client._client.get = AsyncMock(return_value=mock_response)
            data = await client.fetch_page(settings.ozon_category_url, 1)
        assert "widgetStates" in data

    @pytest.mark.asyncio
    async def test_fetch_page_rate_limit(self, settings):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "1"}

        async with OzonClient(settings) as client:
            client._client.get = AsyncMock(return_value=mock_response)
            with pytest.raises(RateLimitError):
                await client.fetch_page(settings.ozon_category_url, 1)

    def test_build_api_url(self, settings):
        client = OzonClient(settings)
        url = client._build_api_url("/category/smartfony-15502/", 2)
        assert "composer-api.bx" in url
        assert "page%3D2" in url or "page=2" in url


class TestCheckpoint:
    def test_save_and_load(self, checkpoint):
        from src.models.product import RawProduct

        products = [
            RawProduct(id="1", name="A", price=100.0),
            RawProduct(id="2", name="B", price=200.0),
        ]
        checkpoint.save_page(1, products)
        loaded = checkpoint.load_all()
        assert len(loaded) == 2
        assert loaded[0].id == "1"

    def test_deduplication(self, checkpoint):
        from src.models.product import RawProduct

        checkpoint.save_page(1, [RawProduct(id="1", name="A", price=100.0)])
        checkpoint.save_page(2, [RawProduct(id="1", name="A", price=100.0)])
        loaded = checkpoint.load_all()
        assert len(loaded) == 1

    def test_get_last_page(self, checkpoint):
        from src.models.product import RawProduct

        checkpoint.save_page(3, [RawProduct(id="1", name="A", price=100.0)])
        assert checkpoint.get_last_page() == 3


class TestOzonParserCollect:
    @pytest.mark.asyncio
    async def test_collect_with_mock(self, settings, checkpoint, ozon_page_data):
        parser = OzonParser(settings, checkpoint)

        async def mock_fetch(category_url, page):
            if page == 1:
                return ozon_page_data
            return {"widgetStates": {}}

        with patch.object(OzonClient, "fetch_page", side_effect=mock_fetch):
            products, errors = await parser.collect_category(target_count=2)

        assert len(products) >= 2
        assert errors == 0

    @pytest.mark.asyncio
    async def test_parser_mock_mode(self, settings, checkpoint):
        settings.parser_mock = True
        parser = OzonParser(settings, checkpoint)
        products, errors = await parser.collect_category(target_count=10)
        assert len(products) == 10
        assert errors == 0
