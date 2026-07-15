from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class PriceSegment(str, Enum):
    ECONOMY = "Эконом"
    STANDARD = "Стандарт"
    PREMIUM = "Премиум"


class RawProduct(BaseModel):
    """Raw product data extracted from Ozon API response."""

    id: str
    name: str
    price: float
    currency: str = "RUB"
    url: str = ""
    category: str = "Смартфоны"
    description: str = ""
    rating: float | None = None
    reviews_count: int | None = None


class Product(BaseModel):
    id: str
    name: str
    price: float
    currency: str = "RUB"
    url: str
    category: str
    description: str = ""
    collected_at: datetime
    segment: str | None = None
    rating: float | None = None
    reviews_count: int | None = None

    @field_validator("price")
    @classmethod
    def price_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Price must be positive")
        return v

    @classmethod
    def from_raw(cls, raw: RawProduct, collected_at: datetime | None = None) -> "Product":
        url = raw.url or f"https://www.ozon.ru/product/{raw.id}/"
        return cls(
            id=raw.id,
            name=raw.name,
            price=raw.price,
            currency=raw.currency,
            url=url,
            category=raw.category,
            description=raw.description,
            collected_at=collected_at or datetime.now(),
            rating=raw.rating,
            reviews_count=raw.reviews_count,
        )


class CRMTask(BaseModel):
    """Task to be created in CRM."""

    product_id: str
    text: str
    complete_till: int
    entity_type: str | None = None
    entity_id: int | None = None


class PipelineReport(BaseModel):
    collected: int = 0
    normalized: int = 0
    parse_errors: int = 0
    llm_classified: int = 0
    llm_cache_hits: int = 0
    llm_api_calls: int = 0
    segments: dict[str, int] = Field(default_factory=dict)
    crm_tasks_created: int = 0
    crm_errors: int = 0
    sample_products: list[dict[str, Any]] = Field(default_factory=list)
    sample_tasks: list[dict[str, Any]] = Field(default_factory=list)
