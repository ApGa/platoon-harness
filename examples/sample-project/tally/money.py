"""Amounts of money, held as whole cents, so that no sum is off by a fraction."""


def parse_amount(text: str) -> int:
    """The cents in an amount written as `12`, `12.50` or `-3.20`."""
    whole, _, cents = text.strip().partition(".")
    sign = -1 if whole.startswith("-") else 1
    return sign * (abs(int(whole)) * 100 + int(cents or 0))


def format_amount(cents: int) -> str:
    """An amount in cents as text, such as `12.50` or `-3.20`."""
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"
