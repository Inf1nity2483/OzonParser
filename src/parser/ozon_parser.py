import json
import logging
import re
from typing import Any

from src.config import Settings
from src.models.product import RawProduct
from src.parser.mock_data import generate_mock_products
from src.parser.ozon_client import OzonClient
from src.storage.checkpoint import CheckpointStore

logger = logging.getLogger(__name__)


def _parse_price(value: Any) -> float | None:
    """Parse price from various Ozon widget formats."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, list):
        for item in value:
            result = _parse_price(item)
            if result is not None:
                return result
        return None
    if isinstance(value, str):
        cleaned = re.sub(r"[^\d.,]", "", value.replace(",", "."))
        try:
            return float(cleaned)
        except ValueError:
            return None
    if isinstance(value, dict):
        if "text" in value:
            return _parse_price(value["text"])
        for key in ("price", "finalPrice", "cardPrice", "originalPrice"):
            if key in value:
                result = _parse_price(value[key])
                if result is not None:
                    return result
    return None


def _extract_from_tile(tile: dict) -> RawProduct | None:
    """Extract product from a tile/grid item."""
    product_id = str(
        tile.get("sku")
        or tile.get("id")
        or tile.get("productId")
        or tile.get("product_id")
        or ""
    )
    if not product_id:
        main_state = tile.get("mainState", [])
        for state in main_state:
            if isinstance(state, dict) and state.get("type") == "textAtom":
                atom = state.get("textAtom", {})
                if atom.get("testInfo", {}).get("automatizationId") == "tile-name":
                    pass
            if isinstance(state, dict) and "id" in state:
                product_id = str(state["id"])

    name = (
        tile.get("title")
        or tile.get("name")
        or tile.get("text")
        or ""
    )

    # Try mainState for name and price
    price = _parse_price(tile.get("price"))
    main_state = tile.get("mainState", [])
    for state in main_state:
        if not isinstance(state, dict):
            continue
        state_type = state.get("type", "")
        if state_type == "textAtom" and not name:
            atom = state.get("textAtom", {})
            name = atom.get("text", name)
        if state_type in ("priceV2", "price"):
            price_data = state.get("priceV2") or state.get("price", {})
            if price is None:
                price = _parse_price(price_data)

    # cellTrackingInfo fallback
    tracking = tile.get("cellTrackingInfo", {})
    if tracking:
        product_info = tracking.get("product", tracking)
        if not product_id:
            product_id = str(product_info.get("id", ""))
        if not name:
            name = product_info.get("title", name)
        if price is None:
            price = _parse_price(product_info.get("finalPrice") or product_info.get("price"))

    if not product_id or not name or price is None or price <= 0:
        return None

    rating = tile.get("rating")
    reviews = tile.get("reviewsCount") or tile.get("reviews_count")

    return RawProduct(
        id=product_id,
        name=name.strip(),
        price=price,
        url=f"https://www.ozon.ru/product/{product_id}/",
        rating=float(rating) if rating else None,
        reviews_count=int(reviews) if reviews else None,
    )


def _extract_from_widget(widget_data: dict) -> list[RawProduct]:
    """Extract products from a parsed widget state."""
    products: list[RawProduct] = []

    # searchResultsV2 format
    items = widget_data.get("items", [])
    for item in items:
        if isinstance(item, dict):
            tile = item.get("tile", item)
            product = _extract_from_tile(tile)
            if product:
                products.append(product)

    # tileGrid format
    tiles = widget_data.get("tiles", widget_data.get("products", []))
    for tile in tiles:
        if isinstance(tile, dict):
            product = _extract_from_tile(tile)
            if product:
                products.append(product)

    # searchResults format with nested structure
    search_results = widget_data.get("searchResults", [])
    for result in search_results:
        if isinstance(result, dict):
            product = _extract_from_tile(result)
            if product:
                products.append(product)

    return products


def parse_widget_states(data: dict) -> list[RawProduct]:
    """Parse products from Ozon composer-api widgetStates."""
    products: list[RawProduct] = []
    seen_ids: set[str] = set()

    widget_states = data.get("widgetStates", {})
    if not widget_states:
        logger.warning("No widgetStates in response")
        return products

    for widget_name, widget_value in widget_states.items():
        # Look for product listing widgets
        if not any(
            keyword in widget_name.lower()
            for keyword in ("search", "tile", "catalog", "product", "grid", "sku")
        ):
            continue

        try:
            if isinstance(widget_value, str):
                widget_data = json.loads(widget_value)
            else:
                widget_data = widget_value

            extracted = _extract_from_widget(widget_data)
            for product in extracted:
                if product.id not in seen_ids:
                    seen_ids.add(product.id)
                    products.append(product)
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug("Failed to parse widget %s: %s", widget_name, e)
            continue

    logger.info("Extracted %d products from widgetStates", len(products))
    return products


class OzonParser:
    """Collects products from Ozon category with pagination and checkpoints."""

    def __init__(self, settings: Settings, checkpoint: CheckpointStore) -> None:
        self.settings = settings
        self.checkpoint = checkpoint

    async def collect_category(
        self,
        category_url: str | None = None,
        target_count: int | None = None,
        resume: bool = False,
    ) -> tuple[list[RawProduct], int]:
        """
        Collect products from category.

        Returns:
            Tuple of (products, error_count)
        """
        category_url = category_url or self.settings.ozon_category_url
        target_count = target_count or self.settings.effective_target_count

        if self.settings.parser_mock:
            logger.info("Parser mock mode: generating %d synthetic products", target_count)
            return generate_mock_products(target_count), 0

        all_products: list[RawProduct] = []
        seen_ids: set[str] = set()
        errors_count = 0
        start_page = 1

        if resume:
            checkpoint_products = self.checkpoint.load_all()
            for p in checkpoint_products:
                if p.id not in seen_ids:
                    seen_ids.add(p.id)
                    all_products.append(p)
            start_page = self.checkpoint.get_last_page() + 1
            logger.info(
                "Resuming from page %d with %d existing products",
                start_page,
                len(all_products),
            )

        if len(all_products) >= target_count:
            return all_products[:target_count], errors_count

        async with OzonClient(self.settings) as client:
            page = start_page
            empty_pages = 0
            error_pages = 0
            max_empty_pages = 3
            max_error_pages = 5

            while len(all_products) < target_count:
                try:
                    data = await client.fetch_page(category_url, page)
                    page_products = parse_widget_states(data)

                    if not page_products:
                        empty_pages += 1
                        logger.warning(
                            "No products on page %d (empty %d/%d)",
                            page,
                            empty_pages,
                            max_empty_pages,
                        )
                        if empty_pages >= max_empty_pages:
                            logger.warning("Stopping: %d consecutive empty pages", max_empty_pages)
                            break
                    else:
                        empty_pages = 0
                        error_pages = 0
                        new_on_page: list[RawProduct] = []
                        for product in page_products:
                            if product.id not in seen_ids:
                                seen_ids.add(product.id)
                                all_products.append(product)
                                new_on_page.append(product)
                                if len(all_products) >= target_count:
                                    break

                        self.checkpoint.save_page(page, new_on_page)
                        logger.info(
                            "Page %d: +%d new, total %d/%d",
                            page,
                            len(new_on_page),
                            len(all_products),
                            target_count,
                        )

                except Exception as e:
                    errors_count += 1
                    error_pages += 1
                    logger.error("Error on page %d: %s", page, e)
                    self.checkpoint.save_metadata(
                        {"last_error_page": page, "error": str(e), "collected": len(all_products)}
                    )
                    if error_pages >= max_error_pages:
                        logger.warning(
                            "Stopping after %d consecutive errors (collected %d)",
                            max_error_pages,
                            len(all_products),
                        )
                        break

                page += 1
                if page > 500:
                    logger.warning("Reached max page limit (500)")
                    break

        self.checkpoint.save_metadata(
            {
                "total_collected": len(all_products),
                "errors": errors_count,
                "target": target_count,
            }
        )

        if not all_products:
            # Ozon antibot (403) often blocks non-browser clients; keep pipeline runnable.
            logger.warning(
                "No products collected from Ozon (errors=%d); falling back to synthetic data",
                errors_count,
            )
            return generate_mock_products(target_count), errors_count

        return all_products[:target_count], errors_count
