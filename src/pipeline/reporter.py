import logging
import sys
from pathlib import Path

from src.models.product import CRMTask, PipelineReport, Product

logger = logging.getLogger(__name__)


class Reporter:
    """Builds pipeline execution report."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def build(
        self,
        products: list[Product],
        tasks: list[CRMTask],
        *,
        collected: int = 0,
        parse_errors: int = 0,
        llm_cache_hits: int = 0,
        llm_api_calls: int = 0,
        crm_created: int = 0,
        crm_errors: int = 0,
    ) -> PipelineReport:
        segments: dict[str, int] = {}
        for p in products:
            seg = p.segment or "Не определён"
            segments[seg] = segments.get(seg, 0) + 1

        sample_products = [
            p.model_dump(mode="json") for p in products[:5]
        ]
        sample_tasks = [
            {"product_id": t.product_id, "text": t.text} for t in tasks[:5]
        ]

        report = PipelineReport(
            collected=collected,
            normalized=len(products),
            parse_errors=parse_errors,
            llm_classified=sum(1 for p in products if p.segment),
            llm_cache_hits=llm_cache_hits,
            llm_api_calls=llm_api_calls,
            segments=segments,
            crm_tasks_created=crm_created,
            crm_errors=crm_errors,
            sample_products=sample_products,
            sample_tasks=sample_tasks,
        )

        self._save(report)
        self._print(report)
        return report

    def _save(self, report: PipelineReport) -> None:
        path = self.data_dir / "report.json"
        path.write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        logger.info("Report saved to %s", path)

    def _print(self, report: PipelineReport) -> None:
        seg_str = " | ".join(f"{k}: {v}" for k, v in report.segments.items())
        lines = [
            "=" * 60,
            "ОТЧЁТ О ВЫПОЛНЕНИИ ПАЙПЛАЙНА",
            "=" * 60,
            f"Собрано: {report.collected} | Нормализовано: {report.normalized} | "
            f"Ошибки парсинга: {report.parse_errors}",
            f"LLM: {report.llm_classified} классифицировано | "
            f"cache hit: {report.llm_cache_hits} | API calls: {report.llm_api_calls}",
            f"Сегменты: {seg_str}",
            f"CRM: {report.crm_tasks_created} задач создано | ошибок: {report.crm_errors}",
            "=" * 60,
        ]
        if report.sample_products:
            lines.append("\nПримеры товаров:")
            for p in report.sample_products[:3]:
                lines.append(
                    f"  - {p.get('name', '')[:50]} | {p.get('price')} RUB | "
                    f"segment={p.get('segment')}"
                )
        if report.sample_tasks:
            lines.append("\nПримеры задач CRM:")
            for t in report.sample_tasks[:2]:
                lines.append(f"  - {t.get('text', '')[:80]}")
        lines.append("=" * 60)

        print("\n".join(lines), file=sys.stdout, flush=True)
