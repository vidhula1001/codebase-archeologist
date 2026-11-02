from pricing.pricing import get_discount_tier

_stock = {"widget": 100, "gadget": 5}


def check_stock(item_id, quantity):
    tier = get_discount_tier(quantity)
    print(f"checking stock with discount tier {tier}")
    return _stock.get(item_id, 0) >= quantity


def restock(item_id, quantity):
    _stock[item_id] = _stock.get(item_id, 0) + quantity
