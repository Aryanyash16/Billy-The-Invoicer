
from decimal import Decimal

from app.schemas import InvoiceData


def validate_invoice(
    data: InvoiceData,
    existing_vendor_invoice_pairs: set[tuple[str, str]] | None = None,
):
    errors = []
    warnings = []

    required = [
        "vendor_name",
        "invoice_number",
        "invoice_date",
        "currency",
        "total",
    ]

    for field in required:
        if getattr(data, field) is None:
            errors.append({
                "code": "missing_required_field",
                "field": field,
                "message": f"{field} is required",
            })

    if data.total is not None and data.total < 0:
        errors.append({
            "code": "negative_total",
            "field": "total",
            "message": "Total cannot be negative",
        })

    if data.subtotal is not None and data.subtotal < 0:
        errors.append({
            "code": "negative_subtotal",
            "field": "subtotal",
            "message": "Subtotal cannot be negative",
        })

    if data.tax is not None and data.tax < 0:
        errors.append({
            "code": "negative_tax",
            "field": "tax",
            "message": "Tax cannot be negative",
        })

    if (
        data.subtotal is not None
        and data.tax is not None
        and data.total is not None
    ):
        expected = data.subtotal + data.tax

        if abs(expected - data.total) > Decimal("0.02"):
            errors.append({
                "code": "total_mismatch",
                "field": "total",
                "message": (
                    f"Subtotal + tax ({expected}) differs from "
                    f"total ({data.total})"
                ),
            })
    elif data.total is not None:
        warnings.append({
            "code": "arithmetic_check_incomplete",
            "message": (
                "Subtotal/tax unavailable; cannot verify total."
            ),
        })

    # Check whether line-item amounts reconcile with the subtotal.
    # This is a warning because some invoices have separate credits,
    # shipping, fees, or other adjustments.
    if data.subtotal is not None and data.line_items:
        amounts = [
            item.amount
            for item in data.line_items
            if item.amount is not None
        ]

        if amounts:
            line_item_sum = sum(amounts, Decimal("0"))

            if abs(line_item_sum - data.subtotal) > Decimal("0.02"):
                warnings.append({
                    "code": "line_items_subtotal_mismatch",
                    "field": "subtotal",
                    "message": (
                        f"Line items sum to {line_item_sum}, but the "
                        f"extracted subtotal is {data.subtotal}. "
                        "Check discounts, credits, and other adjustments."
                    ),
                })

    if data.invoice_date and data.due_date:
        if data.due_date < data.invoice_date:
            warnings.append({
                "code": "due_before_invoice",
                "field": "due_date",
                "message": "Due date precedes invoice date",
            })

    if (
        existing_vendor_invoice_pairs
        and data.vendor_name
        and data.invoice_number
    ):
        key = (
            data.vendor_name.casefold().strip(),
            data.invoice_number.casefold().strip(),
        )

        if key in existing_vendor_invoice_pairs:
            errors.append({
                "code": "duplicate_vendor_invoice",
                "field": "invoice_number",
                "message": "Possible duplicate invoice",
            })

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }
