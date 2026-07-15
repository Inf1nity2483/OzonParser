import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.config import Settings
from src.models.product import PriceSegment, Product, RawProduct
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.reporter import Reporter


@pytest.fixture
def settings(tmp_path):
    return Settings(
        demo_mode=True,
        demo_target_count=5,
        llm_mock=True,
        crm_mock=True,
        crm_task_limit=2,
        data_dir=tmp_path / "data",
        checkpoint_dir=tmp_path / "checkpoints",
        request_delay_ms=0,
    )


@pytest.fixture
def mock_raw_products():
    return [
        RawProduct(id=str(i), name=f"Phone {i}", price=10000.0 * i, category="Смартфоны")
        for i in range(1, 6)
    ]


class TestReporter:
    def test_build_report(self, settings):
        products = [
            Product(
                id="1", name="Phone", price=10000, url="https://ozon.ru/1",
                category="Смартфоны", collected_at=datetime.now(),
                segment=PriceSegment.ECONOMY.value,
            )
        ]
        from src.models.product import CRMTask

        tasks = [CRMTask(product_id="1", text="Task", complete_till=1700000000)]
        reporter = Reporter(settings.data_dir)
        report = reporter.build(products, tasks, collected=1, crm_created=1)

        assert report.collected == 1
        assert report.normalized == 1
        assert report.segments.get("Эконом") == 1
        assert (settings.data_dir / "report.json").exists()


class TestPipelineE2E:
    @pytest.mark.asyncio
    async def test_pipeline_with_mocks(self, settings, mock_raw_products):
        orchestrator = PipelineOrchestrator(settings)

        with patch.object(
            orchestrator.parser,
            "collect_category",
            new_callable=AsyncMock,
            return_value=(mock_raw_products, 0),
        ):
            report = await orchestrator.run()

        assert report.collected == 5
        assert report.normalized == 5
        assert report.llm_classified == 5
        assert report.crm_tasks_created >= 2
        assert (settings.data_dir / "enriched_products.json").exists()
        assert (settings.data_dir / "tasks.json").exists()

        enriched = json.loads(
            (settings.data_dir / "enriched_products.json").read_text(encoding="utf-8")
        )
        assert all(p.get("segment") for p in enriched)
