import json
import logging
from pathlib import Path

from src.models.product import RawProduct

logger = logging.getLogger(__name__)


class CheckpointStore:
    """Persists raw products per page for graceful degradation and resume."""

    def __init__(self, checkpoint_dir: Path) -> None:
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save_page(self, page: int, products: list[RawProduct]) -> None:
        path = self.checkpoint_dir / f"raw_page_{page}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for product in products:
                f.write(product.model_dump_json() + "\n")
        logger.debug("Saved checkpoint page %d (%d products)", page, len(products))

    def load_all(self) -> list[RawProduct]:
        products: list[RawProduct] = []
        seen_ids: set[str] = set()

        for path in sorted(self.checkpoint_dir.glob("raw_page_*.jsonl")):
            with path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    product = RawProduct.model_validate_json(line)
                    if product.id not in seen_ids:
                        seen_ids.add(product.id)
                        products.append(product)

        logger.info("Loaded %d products from checkpoints", len(products))
        return products

    def get_last_page(self) -> int:
        pages = []
        for path in self.checkpoint_dir.glob("raw_page_*.jsonl"):
            try:
                page_num = int(path.stem.replace("raw_page_", ""))
                pages.append(page_num)
            except ValueError:
                continue
        return max(pages) if pages else 0

    def save_metadata(self, metadata: dict) -> None:
        path = self.checkpoint_dir / "metadata.json"
        path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_metadata(self) -> dict:
        path = self.checkpoint_dir / "metadata.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
