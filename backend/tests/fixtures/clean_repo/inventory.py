"""Small, idiomatic module with no security issues and no vibe debt."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    sku: str
    quantity: int
    unit_price: float


def total_value(items: list[Item]) -> float:
    return sum(item.quantity * item.unit_price for item in items)


def low_stock(items: list[Item], threshold: int = 5) -> list[Item]:
    return [item for item in items if item.quantity < threshold]
