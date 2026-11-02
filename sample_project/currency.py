def to_cents(dollars):
    return int(dollars * 100)


def format_price(cents):
    return f"${cents / 100:.2f}"
