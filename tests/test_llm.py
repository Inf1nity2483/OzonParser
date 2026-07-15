from datetime import datetime

import pytest

from src.config import Settings
from src.llm.cache import SegmentCache
from src.llm.classifier import SegmentClassifier, _mock_classify
from src.models.product import PriceSegment, Product


@pytest.fixture
def settings(tmp_path):
    return Settings(
        llm_mock=True,
        llm_batch_size=10,
        data_dir=tmp_path / "data",
    )


@pytest.fixture
def cache(tmp_path):
    return SegmentCache(tmp_path / "cache.db")


@pytest.fixture
def sample_products():
    return [
        Product(
            id="1",
            name="Budget phone",
            price=10000.0,
            url="https://ozon.ru/product/1/",
            category="Смартфоны",
            collected_at=datetime.now(),
        ),
        Product(
            id="2",
            name="Mid-range phone",
            price=35000.0,
            url="https://ozon.ru/product/2/",
            category="Смартфоны",
            collected_at=datetime.now(),
        ),
        Product(
            id="3",
            name="Flagship phone",
            price=120000.0,
            url="https://ozon.ru/product/3/",
            category="Смартфоны",
            collected_at=datetime.now(),
        ),
    ]


class TestMockClassify:
    def test_economy(self):
        p = Product(
            id="1", name="X", price=5000, url="", category="", collected_at=datetime.now()
        )
        assert _mock_classify(p) == PriceSegment.ECONOMY.value

    def test_standard(self):
        p = Product(
            id="1", name="X", price=30000, url="", category="", collected_at=datetime.now()
        )
        assert _mock_classify(p) == PriceSegment.STANDARD.value

    def test_premium(self):
        p = Product(
            id="1", name="X", price=100000, url="", category="", collected_at=datetime.now()
        )
        assert _mock_classify(p) == PriceSegment.PREMIUM.value


class TestSegmentCache:
    def test_set_and_get(self, cache):
        cache.set("1", "Phone A", "desc", "Эконом")
        assert cache.get("1", "Phone A", "desc") == "Эконом"

    def test_miss(self, cache):
        assert cache.get("1", "Unknown", "") is None


class TestSegmentClassifier:
    @pytest.mark.asyncio
    async def test_classify_mock_mode(self, settings, cache, sample_products):
        classifier = SegmentClassifier(settings, cache)
        result = await classifier.classify_all(sample_products)
        assert len(result) == 3
        assert all(p.segment for p in result)
        assert result[0].segment == PriceSegment.ECONOMY.value
        assert result[2].segment == PriceSegment.PREMIUM.value

    @pytest.mark.asyncio
    async def test_cache_hit(self, settings, cache, sample_products):
        cache.set("1", sample_products[0].name, "", PriceSegment.ECONOMY.value)
        classifier = SegmentClassifier(settings, cache)
        result = await classifier.classify_all([sample_products[0]])
        assert classifier.cache_hits == 1
        assert classifier.api_calls == 0
        assert result[0].segment == PriceSegment.ECONOMY.value
