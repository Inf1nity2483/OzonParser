import json
from datetime import datetime

import pytest

from src.config import Settings
from src.crm.amocrm_client import AmoCRMClient
from src.crm.task_selector import TaskSelector
from src.models.product import CRMTask, PriceSegment, Product


@pytest.fixture
def settings(tmp_path):
    return Settings(
        crm_mock=True,
        crm_task_limit=5,
        data_dir=tmp_path / "data",
    )


@pytest.fixture
def sample_products():
    return [
        Product(
            id="1", name="Budget", price=8000, url="https://ozon.ru/1",
            category="Смартфоны", collected_at=datetime.now(),
            segment=PriceSegment.ECONOMY.value, reviews_count=100,
        ),
        Product(
            id="2", name="Standard A", price=30000, url="https://ozon.ru/2",
            category="Смартфоны", collected_at=datetime.now(),
            segment=PriceSegment.STANDARD.value, rating=4.8, reviews_count=200,
        ),
        Product(
            id="3", name="Standard B", price=35000, url="https://ozon.ru/3",
            category="Смартфоны", collected_at=datetime.now(),
            segment=PriceSegment.STANDARD.value, rating=4.2,
        ),
        Product(
            id="4", name="Premium Cheap", price=70000, url="https://ozon.ru/4",
            category="Смартфоны", collected_at=datetime.now(),
            segment=PriceSegment.PREMIUM.value,
        ),
        Product(
            id="5", name="Premium Flagship", price=150000, url="https://ozon.ru/5",
            category="Смартфоны", collected_at=datetime.now(),
            segment=PriceSegment.PREMIUM.value,
        ),
    ]


class TestTaskSelector:
    def test_select_returns_products(self, sample_products):
        selector = TaskSelector(task_limit=3)
        selected = selector.select(sample_products)
        assert len(selected) <= 3
        assert len(selected) >= 2

    def test_select_at_least_two(self, sample_products):
        selector = TaskSelector(task_limit=10)
        selected = selector.select(sample_products[:2])
        assert len(selected) == 2

    def test_build_tasks(self, sample_products):
        selector = TaskSelector()
        selected = selector.select(sample_products)
        tasks = selector.build_tasks(selected)
        assert len(tasks) == len(selected)
        assert all("[Ozon]" in t.text for t in tasks)
        assert all(t.complete_till > 0 for t in tasks)


class TestAmoCRMClient:
    @pytest.mark.asyncio
    async def test_mock_create_tasks(self, settings):
        client = AmoCRMClient(settings)
        tasks = [
            CRMTask(product_id="1", text="Test task", complete_till=1700000000),
            CRMTask(product_id="2", text="Another task", complete_till=1700000000),
        ]
        created, errors = await client.create_tasks(tasks)
        assert created == 2
        assert errors == 0

        tasks_file = settings.data_dir / "tasks.json"
        assert tasks_file.exists()
        data = json.loads(tasks_file.read_text(encoding="utf-8"))
        assert len(data) == 2
