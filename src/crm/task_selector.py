import logging
import time
from statistics import median

from src.models.product import CRMTask, PriceSegment, Product

logger = logging.getLogger(__name__)


class TaskSelector:
    """Selects interesting products for CRM task creation."""

    def __init__(self, task_limit: int = 10) -> None:
        self.task_limit = task_limit

    def select(self, products: list[Product]) -> list[Product]:
        """
        Select interesting products based on:
        1. Premium segment with price in lower quartile (niche affordable premium)
        2. Standard segment with high rating or price deviation from median
        """
        if not products:
            return []

        selected: list[Product] = []
        seen_ids: set[str] = set()

        # Rule 1: Affordable premium (lower quartile of premium prices)
        premium = [p for p in products if p.segment == PriceSegment.PREMIUM.value]
        if premium:
            prices = sorted(p.price for p in premium)
            q1_idx = len(prices) // 4
            q1_threshold = prices[q1_idx] if prices else 0
            affordable_premium = sorted(
                [p for p in premium if p.price <= q1_threshold],
                key=lambda p: p.price,
            )
            for p in affordable_premium[: max(1, self.task_limit // 2)]:
                if p.id not in seen_ids:
                    seen_ids.add(p.id)
                    selected.append(p)

        # Rule 2: Standard with high rating or price outlier
        standard = [p for p in products if p.segment == PriceSegment.STANDARD.value]
        if standard:
            all_prices = [p.price for p in products]
            med = median(all_prices) if all_prices else 0

            rated = [p for p in standard if p.rating and p.rating >= 4.5]
            rated.sort(key=lambda p: (-(p.rating or 0), -(p.reviews_count or 0)))

            outliers = sorted(
                standard,
                key=lambda p: abs(p.price - med),
                reverse=True,
            )

            candidates = rated + [p for p in outliers if p.id not in seen_ids]
            for p in candidates:
                if p.id not in seen_ids and len(selected) < self.task_limit:
                    seen_ids.add(p.id)
                    selected.append(p)

        # Rule 3: Fill remaining with economy top sellers (by reviews)
        if len(selected) < self.task_limit:
            economy = [p for p in products if p.segment == PriceSegment.ECONOMY.value]
            economy.sort(key=lambda p: -(p.reviews_count or 0))
            for p in economy:
                if p.id not in seen_ids and len(selected) < self.task_limit:
                    seen_ids.add(p.id)
                    selected.append(p)

        # Ensure at least 2 for demo
        if len(selected) < 2 and len(products) >= 2:
            for p in products:
                if p.id not in seen_ids:
                    selected.append(p)
                    if len(selected) >= 2:
                        break

        logger.info("Selected %d products for CRM tasks", len(selected))
        return selected[: self.task_limit]

    def build_tasks(self, products: list[Product], days_ahead: int = 7) -> list[CRMTask]:
        complete_till = int(time.time()) + days_ahead * 86400
        tasks: list[CRMTask] = []

        for product in products:
            text = (
                f"[Ozon] Проработать: {product.name} | "
                f"{product.segment} | {product.price:.0f} {product.currency} | {product.url}"
            )
            tasks.append(
                CRMTask(
                    product_id=product.id,
                    text=text,
                    complete_till=complete_till,
                )
            )

        return tasks
