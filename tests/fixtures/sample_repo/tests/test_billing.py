from app.billing import invoice_total


def test_invoice_total_adds_tax():
    assert invoice_total([1000]) == 1080
