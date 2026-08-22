from inventory import Item, low_stock, total_value


def summary(items: list[Item]) -> dict[str, float | int]:
    return {
        "count": len(items),
        "value": total_value(items),
        "low_stock": len(low_stock(items)),
    }
