import json
import logging

from src.config import Settings
from src.crm.amocrm_client import AmoCRMClient
from src.crm.task_selector import TaskSelector
from src.llm.cache import SegmentCache
from src.llm.classifier import SegmentClassifier
from src.models.product import PipelineReport
from src.normalizer.normalizer import Normalizer
from src.parser.ozon_parser import OzonParser
from src.pipeline.reporter import Reporter
from src.storage.checkpoint import CheckpointStore

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Orchestrates the full analytics pipeline."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        self.checkpoint = CheckpointStore(settings.checkpoint_dir)
        self.parser = OzonParser(settings, self.checkpoint)
        self.normalizer = Normalizer()
        self.cache = SegmentCache(settings.data_dir / "segment_cache.db")
        self.classifier = SegmentClassifier(settings, self.cache)
        self.selector = TaskSelector(settings.crm_task_limit)
        self.crm = AmoCRMClient(settings)
        self.reporter = Reporter(settings.data_dir)

    async def run(self, resume: bool = False) -> PipelineReport:
        logger.info(
            "Starting pipeline (demo=%s, target=%d)",
            self.settings.demo_mode,
            self.settings.effective_target_count,
        )

        # Step 1: Parse
        raw_products, parse_errors = await self.parser.collect_category(resume=resume)
        collected_count = len(raw_products)

        # Save raw products
        self._save_products(raw_products, "raw_products.json")

        # Step 2: Normalize
        products = self.normalizer.normalize_all(raw_products)
        self._save_products(products, "products.json")

        # Step 3: LLM classify
        enriched = await self.classifier.classify_all(products)
        self._save_products(enriched, "enriched_products.json")

        # Step 4: Select and create CRM tasks
        selected = self.selector.select(enriched)
        tasks = self.selector.build_tasks(selected)
        crm_created, crm_errors = await self.crm.create_tasks(tasks)

        # Step 5: Report
        return self.reporter.build(
            enriched,
            tasks,
            collected=collected_count,
            parse_errors=parse_errors,
            llm_cache_hits=self.classifier.cache_hits,
            llm_api_calls=self.classifier.api_calls,
            crm_created=crm_created,
            crm_errors=crm_errors,
        )

    def _save_products(self, products: list, filename: str) -> None:
        path = self.settings.data_dir / filename
        data = [
            p.model_dump(mode="json") if hasattr(p, "model_dump") else p
            for p in products
        ]
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("Saved %d items to %s", len(products), path)
