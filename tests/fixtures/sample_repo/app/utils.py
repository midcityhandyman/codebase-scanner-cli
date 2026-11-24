"""Small helpers shared across the fixture app."""


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def format_cents(cents: int) -> str:
    return f"${cents // 100}.{cents % 100:02d}"
