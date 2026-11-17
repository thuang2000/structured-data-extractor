"""Pydantic v2 schema and deterministic invoice reconciliation."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DraftLineItem(BaseModel):
    """Looser wire schema for structured output; checked again by LineItem."""
    model_config = ConfigDict(extra="forbid")
    description: str
    quantity: int
    unit_price: str
    line_total: str


class InvoiceDraft(BaseModel):
    """Provider-native JSON shape; business checks happen in InvoiceExtraction."""
    model_config = ConfigDict(extra="forbid")
    invoice_number: str
    vendor_name: str
    invoice_date: str
    line_items: list[DraftLineItem]
    subtotal: str
    tax_amount: str
    total_amount: str
    currency: str


def parse_money(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("money cannot be a boolean")
    if isinstance(value, str):
        value = value.strip().replace(",", "")
        value = re.sub(r"^(?:USD|EUR|GBP|\$|€|£)\s*", "", value, flags=re.I)
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid monetary amount") from exc
    if not amount.is_finite() or amount.as_tuple().exponent < -2:
        raise ValueError("money must be finite with at most two decimal places")
    return amount


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1)
    quantity: int = Field(gt=0, strict=True)
    unit_price: Decimal = Field(gt=0)
    line_total: Decimal = Field(ge=0)

    @field_validator("unit_price", "line_total", mode="before")
    @classmethod
    def normalize_money(cls, value: object) -> Decimal:
        return parse_money(value)

    @model_validator(mode="after")
    def verify_line_total(self):
        if abs(self.quantity * self.unit_price - self.line_total) > Decimal("0.02"):
            raise ValueError("line_total does not match quantity * unit_price")
        return self


class InvoiceExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invoice_number: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{2,39}$")
    vendor_name: str = Field(min_length=1)
    invoice_date: date
    line_items: list[LineItem] = Field(min_length=1)
    subtotal: Decimal = Field(ge=0)
    tax_amount: Decimal = Field(ge=0)
    total_amount: Decimal = Field(ge=0)
    currency: Literal["USD", "EUR", "GBP"]

    @field_validator("invoice_date", mode="before")
    @classmethod
    def normalize_date(cls, value: object):
        if not isinstance(value, str):
            return value
        value = value.strip()
        for fmt in ("%Y-%m-%d", "%B %d, %Y", "%d %B %Y", "%dth of %b, %Y",
                    "%dst of %b, %Y", "%dnd of %b, %Y", "%drd of %b, %Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                pass
        cleaned = re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", value, flags=re.I)
        cleaned = re.sub(r"\bof\b", "", cleaned, flags=re.I).strip()
        for fmt in ("%d %b, %Y", "%d %B, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(cleaned, fmt).date()
            except ValueError:
                pass
        return value

    @field_validator("subtotal", "tax_amount", "total_amount", mode="before")
    @classmethod
    def normalize_money(cls, value: object) -> Decimal:
        return parse_money(value)

    @model_validator(mode="after")
    def reconcile(self):
        items_total = sum((item.line_total for item in self.line_items), Decimal("0.00"))
        if abs(items_total - self.subtotal) > Decimal("0.02"):
            raise ValueError("subtotal does not match sum of line items")
        if abs(self.subtotal + self.tax_amount - self.total_amount) > Decimal("0.02"):
            raise ValueError("total_amount does not match subtotal + tax_amount")
        return self


class ExtractionResult(BaseModel):
    validated_data: InvoiceExtraction | None = None
    attempts_used: int
    error_log: list[str] = Field(default_factory=list)
    corrective_prompts: list[str] = Field(default_factory=list)
    execution_status: Literal["SUCCESS", "REPAIRED_VIA_REFLECTION", "DLQ_FAILED"]
    dlq_path: str | None = None
    events: list[str] = Field(default_factory=list)
