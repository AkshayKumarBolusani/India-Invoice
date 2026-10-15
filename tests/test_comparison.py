from decimal import Decimal

from invoice_ai.comparison import compare_outputs
from invoice_ai.schemas import Invoice, InvoiceItem
from invoice_ai.workflow import compare_file


def base_invoice():
    return {
        "subtotal": "1500.00",
        "total_cgst": "45.00",
        "total_sgst": "45.00",
        "total_igst": "0.00",
        "grand_total": "1590.00",
        "items": [{
            "description": "Notebook",
            "quantity": "5",
            "unit_price": "100.00",
            "taxable_value": "500.00",
        }],
    }


def test_decimal_formatting_is_formatting_only_across_invoice_and_tax_fields():
    rules = base_invoice()
    llm = {
        **rules,
        "subtotal": Decimal("1500"),
        "total_cgst": "45",
        "total_sgst": Decimal("45"),
        "grand_total": 1590,
        "items": [{**rules["items"][0], "unit_price": Decimal("100")}],
    }

    result = compare_outputs(rules, llm)

    assert result["difference_count"] == 0
    assert result["missing_field_count"] == 0
    assert result["formatting_difference_count"] >= 4
    assert result["formatting_difference_count"] == len(result["formatting_differences"])


def test_inv003_regression_counts_match_current_streamlit_case():
    rules = {
        "document_type": "gst_invoice",
        "invoice_number": "INV-003",
        "invoice_date": "12/10/2026",
        "vendor_name": "Metro Business Mart",
        "vendor_gstin": "27ABCDE1234F1Z5",
        "buyer_name": "Example Retail Pvt Ltd",
        "buyer_gstin": None,
        "currency": "INR",
        "items": [
            {"description": "Notebook", "hsn_sac": None, "quantity": "5", "unit_price": "100.00", "taxable_value": "500.00", "gst_rate": "3", "cgst_amount": None, "sgst_amount": None, "igst_amount": None, "total_amount": None},
            {"description": "Desk Organizer", "hsn_sac": None, "quantity": "2", "unit_price": "500.00", "taxable_value": "1000.00", "gst_rate": "3", "cgst_amount": None, "sgst_amount": None, "igst_amount": None, "total_amount": None},
        ],
        "subtotal": "1500.00",
        "total_cgst": "45.00",
        "total_sgst": "45.00",
        "total_igst": "0.00",
        "grand_total": "1590.00",
    }
    llm = {**rules, "items": [dict(item) for item in rules["items"]]}
    llm.update({
        "subtotal": "1500",
        "total_cgst": "45",
        "total_sgst": "45",
        "total_igst": "0.00",
        "grand_total": "1590",
    })
    llm["items"][0]["quantity"] = "5.0"
    llm["items"][0]["unit_price"] = "100"
    llm["items"][1]["taxable_value"] = "1000"

    result = compare_outputs(rules, llm)

    assert result["fields_compared"] == 34
    assert result["difference_count"] == 0
    assert result["missing_field_count"] == 0
    assert result["formatting_difference_count"] == 7
    assert len(result["formatting_differences"]) == 7


def test_missing_fields_are_reported_separately_from_mismatches():
    rules = {"subtotal": "100", "items": []}
    llm = {"subtotal": "100", "grand_total": "100", "items": []}

    result = compare_outputs(rules, llm)

    assert result["difference_count"] == 0
    assert result["missing_field_count"] == 1
    assert result["missing_fields"][0]["field"] == "grand_total"


def test_item_count_and_nested_item_fields_are_counted_as_differences():
    rules = base_invoice()
    llm = {
        **rules,
        "items": [
            rules["items"][0],
            {"description": "Organizer", "quantity": "1", "unit_price": "1000", "taxable_value": "1000"},
        ],
    }

    result = compare_outputs(rules, llm)
    fields = {difference["field"] for difference in result["differences"]}

    assert "items.__length__" in fields
    assert "items[1].description" in result["missing_fields"] or any(
        row["field"] == "items[1].description" for row in result["missing_fields"]
    )
    assert result["difference_count"] == len(result["differences"])
    assert result["missing_field_count"] == len(result["missing_fields"])


def test_inv003_duplicate_tax_review_warnings_survive_comparison(tmp_path):
    path = tmp_path / "inv-003.txt"
    path.write_text("Vendor: Seller\nInvoice Number: INV-003\n", encoding="utf-8")

    def fake_llm(_markdown):
        return Invoice(
            document_type="gst_invoice",
            invoice_number="INV-003",
            vendor_name="Seller",
            items=[
                InvoiceItem(description="Notebook", quantity=5, unit_price=100, taxable_value=500, gst_rate=3, cgst_amount=45, sgst_amount=45),
                InvoiceItem(description="Organizer", quantity=2, unit_price=500, taxable_value=1000, gst_rate=3, cgst_amount=45, sgst_amount=45),
            ],
            subtotal=1500,
            total_cgst=45,
            total_sgst=45,
            grand_total=1590,
        ), {"model": "mock", "latency_seconds": 28.166}

    result = compare_file(path, llm_extractor=fake_llm)

    assert len(result["llm_metadata"]["tax_review_warnings"]) == 3
    assert len(result["llm_metadata"]["tax_review_changes"]) == 6
    assert result["llm"]["total_cgst"] == "45"
    assert result["llm"]["total_sgst"] == "45"
    assert all(item["cgst_amount"] is None for item in result["llm"]["items"])
    assert all(item["sgst_amount"] is None for item in result["llm"]["items"])