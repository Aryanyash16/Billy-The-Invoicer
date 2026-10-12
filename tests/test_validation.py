from datetime import date
from decimal import Decimal
from app.schemas import InvoiceData
from app.services.validation import validate_invoice


def test_total_mismatch_is_error():
    data = InvoiceData(
        vendor_name="Vendor", invoice_number="INV-1", invoice_date=date(2024, 1, 1),
        currency="USD", subtotal=Decimal("100"), tax=Decimal("10"), total=Decimal("120")
    )
    result = validate_invoice(data)
    assert result["valid"] is False
    assert any(e["code"] == "total_mismatch" for e in result["errors"])


def test_valid_minimal_invoice():
    data = InvoiceData(
        vendor_name="Vendor", invoice_number="INV-2", invoice_date=date(2024, 1, 1),
        currency="USD", subtotal=Decimal("100"), tax=Decimal("10"), total=Decimal("110")
    )
    assert validate_invoice(data)["valid"] is True


def test_duplicate_pair_is_flagged():
    data = InvoiceData(
        vendor_name="Vendor", invoice_number="INV-3", invoice_date=date(2024, 1, 1),
        currency="USD", subtotal=Decimal("10"), tax=Decimal("0"), total=Decimal("10")
    )
    result = validate_invoice(data, {("vendor", "inv-3")})
    assert any(e["code"] == "duplicate_vendor_invoice" for e in result["errors"])
