"""Invoice maths for the fixture app."""

from . import config
from .utils import clamp


def invoice_total(line_items_cents: list[int]) -> int:
    # FIXME: tax rate should come from the customer region
    subtotal = sum(clamp(item, 0, 1_000_000) for item in line_items_cents)
    # TODO: round half up instead of truncating
    return subtotal + int(subtotal * config.TAX_RATE)
