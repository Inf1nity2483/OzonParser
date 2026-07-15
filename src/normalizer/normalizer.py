import logging
from datetime import datetime

from src.models.product import Product, RawProduct

logger = logging.getLogger(__name__)


class Normalizer:
    """Normalizes raw Ozon products into unified Product schema."""

    def normalize_one(
        self, raw: RawProduct, collected_at: datetime | None = None
    ) -> Product | None:
        try:
            return Product.from_raw(raw, collected_at=collected_at or datetime.now())
        except ValueError as e:
            logger.warning("Skipping product %s: %s", raw.id, e)
            return None

    def normalize_all(
        self,
        raw_products: list[RawProduct],
        collected_at: datetime | None = None,
    ) -> list[Product]:
        collected_at = collected_at or datetime.now()
        products: list[Product] = []
        skipped = 0

        for raw in raw_products:
            product = self.normalize_one(raw, collected_at=collected_at)
            if product:
                products.append(product)
            else:
                skipped += 1

        logger.info("Normalized %d products, skipped %d", len(products), skipped)
        return products
