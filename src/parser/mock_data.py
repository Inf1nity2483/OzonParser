"""Generate synthetic smartphone catalog for demo/mock mode."""

import random

from src.models.product import RawProduct

BRANDS = [
    ("Samsung", "Galaxy"),
    ("Apple", "iPhone"),
    ("Xiaomi", "Redmi"),
    ("realme", ""),
    ("Honor", ""),
    ("POCO", ""),
    ("vivo", ""),
    ("OPPO", ""),
]

DESCRIPTIONS = [
    "Смартфон с хорошей камерой и ёмким аккумулятором.",
    "Бюджетный смартфон для повседневных задач.",
    "Флагманский смартфон с AMOLED-экраном и быстрой зарядкой.",
    "Смартфон среднего класса с NFC и хорошим дисплеем.",
]


def generate_mock_products(count: int) -> list[RawProduct]:
    """Generate realistic mock smartphone products."""
    products: list[RawProduct] = []
    for i in range(1, count + 1):
        brand, series = random.choice(BRANDS)
        name = f"Смартфон {brand} {series} {random.randint(10, 15)}".strip()
        tier = random.random()
        if tier < 0.35:
            price = random.uniform(5_000, 14_999)
        elif tier < 0.75:
            price = random.uniform(15_000, 59_999)
        else:
            price = random.uniform(60_000, 180_000)

        products.append(
            RawProduct(
                id=str(1_000_000 + i),
                name=name,
                price=round(price, 2),
                category="Смартфоны",
                description=random.choice(DESCRIPTIONS),
                rating=round(random.uniform(3.5, 5.0), 1),
                reviews_count=random.randint(10, 5000),
            )
        )
    return products
