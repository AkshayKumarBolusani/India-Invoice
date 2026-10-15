
from decimal import Decimal

from invoice_ai.schemas import Invoice, InvoiceItem
from invoice_ai.validation import validate_invoice


def make_invoice(grand_total="2596.00"):
    return Invoice(
        document_type="gst_invoice",
        vendor_name="Example Traders",
        vendor_gstin="36ABCDE1234F1Z5",
        items=[
            InvoiceItem(
                description="Office Paper",
                quantity=Decimal("2"),
                unit_price=Decimal("500"),
                taxable_value=Decimal("1000"),
            ),
            InvoiceItem(
                description="Printer Cartridge",
                quantity=Decimal("1"),
                unit_price=Decimal("1200"),
                taxable_value=Decimal("1200"),
            ),
        ],
        subtotal=Decimal("2200"),
        total_cgst=Decimal("198"),
        total_sgst=Decimal("198"),
        grand_total=Decimal(grand_total),
    )


def test_consistent_invoice_requires_review_for_missing_line_tax():
    result = validate_invoice(make_invoice())

    assert result["status"] == "review_required"
    assert not result["errors"]


def test_inconsistent_grand_total_is_invalid():
    result = validate_invoice(make_invoice("2500"))

    assert result["status"] == "invalid"
    assert any("Grand total mismatch" in e for e in result["errors"])


def test_item_subtotal_mismatch_is_invalid():
    invoice = make_invoice()
    invoice.subtotal = Decimal("2300")

    result = validate_invoice(invoice)

    assert result["status"] == "invalid"
    assert any("Item taxable values total" in e for e in result["errors"])


def test_invalid_gstin_format_is_reported():
    invoice = make_invoice()
    invoice.vendor_gstin = "NOT-A-GSTIN"

    result = validate_invoice(invoice)

    assert result["status"] == "invalid"
    assert any("invalid GSTIN format" in e for e in result["errors"])

def test_duplicate_invoice_level_taxes_across_items_require_review():
    invoice = make_invoice()

    for item in invoice.items:
        item.cgst_amount = Decimal("198")
        item.sgst_amount = Decimal("198")

    result = validate_invoice(invoice)

    assert result["status"] == "review_required"
    assert any("likely duplicated allocation" in w for w in result["warnings"])
    assert any("differs from invoice-level tax total" in w for w in result["warnings"])
    assert not result["errors"]


def test_single_item_invoice_with_matching_igst_is_not_flagged_as_duplicate():
    invoice = make_invoice()
    invoice.items = [
        InvoiceItem(
            description="USB Keyboard",
            quantity=Decimal("2"),
            unit_price=Decimal("500"),
            taxable_value=Decimal("1000"),
            igst_amount=Decimal("180"),
        )
    ]
    invoice.subtotal = Decimal("1000")
    invoice.total_cgst = Decimal("0")
    invoice.total_sgst = Decimal("0")
    invoice.total_igst = Decimal("180")
    invoice.grand_total = Decimal("1180")

    result = validate_invoice(invoice)

    assert result["status"] == "review_required"
    assert not result["errors"]
    assert not any("likely duplicated allocation" in w for w in result["warnings"])
    assert not any("differs from invoice-level tax total" in w for w in result["warnings"])


def test_correct_line_level_tax_allocations_match_invoice_totals():
    invoice = make_invoice()

    invoice.items[0].cgst_amount = Decimal("90")
    invoice.items[0].sgst_amount = Decimal("90")
    invoice.items[1].cgst_amount = Decimal("108")
    invoice.items[1].sgst_amount = Decimal("108")

    result = validate_invoice(invoice)

    assert result["status"] == "review_required"
    assert not result["errors"]
    assert not any("likely duplicated allocation" in w for w in result["warnings"])
    assert not any("differs from invoice-level tax total" in w for w in result["warnings"])


def test_missing_buyer_gstin_requires_review_not_invalid():
    invoice = make_invoice()
    invoice.buyer_gstin = None

    result = validate_invoice(invoice)

    assert result["status"] == "review_required"
    assert not result["errors"]
    assert any("Buyer GSTIN is missing" in w for w in result["warnings"])
