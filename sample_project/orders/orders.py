from inventory.inventory import check_stock
from pricing.pricing import calculate_total


def create_order(item_id, quantity):
    if not check_stock(item_id, quantity):
        raise ValueError("insufficient stock")
    total = calculate_total(item_id, quantity)
    return {"item_id": item_id, "quantity": quantity, "total": total}


def cancel_order(order_id):
    print(f"cancelling order {order_id}")
