from datetime import date
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class LineItem(BaseModel):
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


class InvoiceData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    vendor_name: str | None = None
    vendor_tax_id: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    currency: str | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    # Explicit accounting-system mappings; never infer IDs from display names.
    quickbooks_vendor_id: str | None = None
    quickbooks_expense_account_id: str | None = None

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value):
        return value.upper().strip() if value else value


class ReviewPatch(BaseModel):
    corrected_fields: dict
    notes: str | None = None


class ReviewDecision(BaseModel):
    notes: str | None = None
