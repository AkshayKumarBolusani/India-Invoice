from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InvoiceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    hsn_sac: str | None = None
    quantity: Decimal = Field(ge=0)
    unit_price: Decimal = Field(ge=0)
    taxable_value: Decimal = Field(ge=0)
    gst_rate: Decimal | None = Field(default=None, ge=0, le=100)
    cgst_amount: Decimal | None = Field(default=None, ge=0)
    sgst_amount: Decimal | None = Field(default=None, ge=0)
    igst_amount: Decimal | None = Field(default=None, ge=0)
    total_amount: Decimal | None = Field(default=None, ge=0)


class Invoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: Literal[
        "gst_invoice", "purchase_order", "bill", "receipt"
    ]

    invoice_number: str | None = None
    invoice_date: str | None = None
    vendor_name: str | None = None
    vendor_gstin: str | None = None
    buyer_name: str | None = None
    buyer_gstin: str | None = None

    currency: str = "INR"
    items: list[InvoiceItem] = Field(default_factory=list)

    subtotal: Decimal | None = Field(default=None, ge=0)
    total_cgst: Decimal = Field(default=Decimal("0"), ge=0)
    total_sgst: Decimal = Field(default=Decimal("0"), ge=0)
    total_igst: Decimal = Field(default=Decimal("0"), ge=0)
    grand_total: Decimal | None = Field(default=None, ge=0)

    @field_validator("vendor_gstin", "buyer_gstin")
    @classmethod
    def normalize_gstin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        return value or None
