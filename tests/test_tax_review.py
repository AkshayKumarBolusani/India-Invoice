from copy import deepcopy

from invoice_ai.tax_review import review_llm_tax_fields


def test_preserves_single_item_igst_from_inv002():
    invoice = {
        "total_cgst": "0", "total_sgst": "0", "total_igst": "180.00",
        "items": [{"description": "USB Keyboard", "gst_rate": "18", "igst_amount": "180.00"}],
    }
    reviewed, warnings = review_llm_tax_fields(invoice)
    assert reviewed["items"][0]["gst_rate"] == "18"
    assert reviewed["items"][0]["igst_amount"] == "180.00"
    assert reviewed["total_igst"] == "180.00"
    assert warnings == []


def test_clears_repeated_invoice_tax_totals_from_inv003():
    invoice = {
        "total_cgst": "45.00", "total_sgst": "45.00", "total_igst": "0",
        "items": [
            {"description": "Notebook", "gst_rate": "3", "cgst_amount": "45.00", "sgst_amount": "45.00"},
            {"description": "Desk Organizer", "gst_rate": "3", "cgst_amount": "45.00", "sgst_amount": "45.00"},
        ],
    }
    reviewed, warnings = review_llm_tax_fields(invoice)
    assert len(warnings) == 3
    assert reviewed["total_cgst"] == "45.00"
    assert reviewed["total_sgst"] == "45.00"
    assert all(item["cgst_amount"] is None for item in reviewed["items"])
    assert all(item["sgst_amount"] is None for item in reviewed["items"])
    assert all(item["gst_rate"] is None for item in reviewed["items"])
    # The helper must not mutate the caller's invoice.
    assert invoice["items"][0]["cgst_amount"] == "45.00"


def test_does_not_clear_line_taxes_when_sum_matches_invoice_total():
    invoice = {
        "total_cgst": "45", "total_sgst": "45", "total_igst": "0",
        "items": [
            {"gst_rate": "3", "cgst_amount": "15", "sgst_amount": "15"},
            {"gst_rate": "3", "cgst_amount": "30", "sgst_amount": "30"},
        ],
    }
    reviewed, warnings = review_llm_tax_fields(invoice)
    assert reviewed == invoice
    assert warnings == []
