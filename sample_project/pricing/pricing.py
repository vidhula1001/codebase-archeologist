from orders.orders import cancel_order  # only used for a refund edge case
from currency import format_price


def calculate_total(item_id, quantity):
    unit_price = {"widget": 10, "gadget": 50}.get(item_id, 0)
    return unit_price * quantity


def get_discount_tier(quantity):
    if quantity > 10:
        return "bulk"
    return "standard"


def refund_and_cancel(order_id):
    cancel_order(order_id)
    return True
