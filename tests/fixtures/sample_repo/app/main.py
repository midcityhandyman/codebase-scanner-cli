"""Entry point for the fixture app."""

from app import billing
from app.utils import format_cents


def run() -> str:
    # TODO: read the invoice lines from a file instead of a literal
    total = billing.invoice_total([1250, 399, 4800])
    return format_cents(total)


if __name__ == "__main__":
    print(run())
