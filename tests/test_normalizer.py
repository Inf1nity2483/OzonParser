import json
from datetime import datetime
from pathlib import Path

import pytest

from src.models.product import Product, RawProduct
from src.normalizer.normalizer import Normalizer
from src.parser.ozon_parser import parse_widget_states

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def ozon_page_data():
    with open(FIXTURES_DIR / "ozon_page.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def sample_raw_products():
    return [
        RawProduct(
            id="100001",
            name="Смартфон Samsung Galaxy A15",
            price=12990.0,
            category="Смартфоны",
        ),
        RawProduct(
            id="100002",
            name="Apple iPhone 15 Pro Max",
            price=119990.0,
            category="Смартфоны",
        ),
        RawProduct(
            id="100003",
            name="Invalid product",
            price=0.0,
            category="Смартфоны",
        ),
    ]


class TestParser:
    def test_parse_widget_states(self, ozon_page_data):
        products = parse_widget_states(ozon_page_data)
        assert len(products) == 2
        assert products[0].id == "100001"
        assert products[0].price == 12990.0
        assert "Samsung" in products[0].name

    def test_parse_empty_widget_states(self):
        products = parse_widget_states({})
        assert products == []

    def test_parse_tile_with_tracking_info(self):
        data = {
            "widgetStates": {
                "tileGrid-1": json.dumps({
                    "tiles": [{
                        "cellTrackingInfo": {
                            "product": {
                                "id": "999",
                                "title": "Xiaomi Redmi Note 13",
                                "finalPrice": 15990,
                            }
                        }
                    }]
                })
            }
        }
        products = parse_widget_states(data)
        assert len(products) == 1
        assert products[0].id == "999"
        assert products[0].price == 15990.0


class TestNormalizer:
    def test_normalize_valid_product(self, sample_raw_products):
        normalizer = Normalizer()
        product = normalizer.normalize_one(sample_raw_products[0])
        assert product is not None
        assert product.id == "100001"
        assert product.price == 12990.0
        assert product.currency == "RUB"
        assert "ozon.ru/product/100001" in product.url

    def test_normalize_invalid_price_skipped(self, sample_raw_products):
        normalizer = Normalizer()
        product = normalizer.normalize_one(sample_raw_products[2])
        assert product is None

    def test_normalize_all(self, sample_raw_products):
        normalizer = Normalizer()
        products = normalizer.normalize_all(sample_raw_products)
        assert len(products) == 2

    def test_product_from_raw(self):
        raw = RawProduct(id="1", name="Test", price=1000.0)
        product = Product.from_raw(raw, collected_at=datetime(2025, 1, 1))
        assert product.collected_at == datetime(2025, 1, 1)
        assert product.segment is None
