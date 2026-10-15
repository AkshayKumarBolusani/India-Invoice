from decimal import Decimal

from pydantic import ValidationError

from invoice_ai.schemas import Invoice, InvoiceItem


def test_valid_invoice_item():
    item = InvoiceItem(
        description="Office supplies",
        quantity=Decimal("2"),
        unit_price=Decimal("100"),
        taxable_value=Decimal("200"),
        gst_rate=Decimal("18"),
        cgst_amount=Decimal("18"),
        sgst_amount=Decimal("18"),
        total_amount=Decimal("236"),
    )

    assert item.taxable_value == Decimal("200")


def test_negative_tax_is_rejected():
    try:
        InvoiceItem(
            description="Office supplies",
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            taxable_value=Decimal("100"),
            gst_rate=Decimal("18"),
            cgst_amount=Decimal("-9"),
            total_amount=Decimal("100"),
        )
    except ValidationError:
        return

    raise AssertionError("Negative tax should be rejected")


def test_invoice_json_serialization():
    invoice = Invoice(
        document_type="gst_invoice",
        vendor_name="Example Traders",
        grand_total=Decimal("118"),
    )

    result = invoice.model_dump(mode="json")

    assert result["vendor_name"] == "Example Traders"
    assert result["grand_total"] == "118"