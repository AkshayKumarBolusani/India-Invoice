from decimal import Decimal

from invoice_ai.schemas import Invoice, InvoiceItem
from invoice_ai.workflow import compare_file, process_batch, process_file


def fake_llm(markdown):
    return Invoice(
        document_type="gst_invoice",
        invoice_number="LLM-1",
        vendor_name="Seller",
        items=[InvoiceItem(
            description="Paper",
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            taxable_value=Decimal("100"),
        )],
        subtotal=Decimal("100"),
        grand_total=Decimal("100"),
    ), {"model": "fake", "latency_seconds": 0}


def duplicate_tax_llm(markdown):
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
    ), {"model": "fake", "latency_seconds": 28.166}


def test_single_invoice_workflow_processes_text(tmp_path):
    path = tmp_path / "invoice.txt"
    path.write_text(
        "Vendor: Seller\nInvoice Number: INV-1\nInvoice Date: 01/01/2026\n"
        "Buyer: Buyer\n| Description | Quantity | Unit Price | Taxable Value |\n"
        "| Paper | 1 | 100 | 100 |\nSubtotal: 100\nGrand Total: 100",
        encoding="utf-8",
    )

    result = process_file(path)

    assert result["invoice"]["invoice_number"] == "INV-1"
    assert result["validation"]["status"] == "review_required"
    assert result["metadata"]["engine"] == "rules-based"


def test_batch_isolates_malformed_file(tmp_path):
    valid = tmp_path / "valid.txt"
    valid.write_text("Invoice Number: INV-1\n", encoding="utf-8")
    missing = tmp_path / "malformed.docx"
    missing.write_text("not a supported invoice format", encoding="utf-8")

    results = process_batch([valid, missing])

    assert results[0]["status"] in {"review_required", "invalid"}
    assert results[1]["status"] == "processing_failed"
    assert "Unsupported document format" in results[1]["error"]


def test_single_and_batch_workflows_preserve_tax_review_warnings(tmp_path):
    path = tmp_path / "inv-003.txt"
    path.write_text("Invoice Number: INV-003\n", encoding="utf-8")

    single = process_file(path, engine="llm", llm_extractor=duplicate_tax_llm)
    batch = process_batch([path], engine="llm", llm_extractor=duplicate_tax_llm)

    assert len(single["metadata"]["tax_review_warnings"]) == 3
    assert len(single["metadata"]["tax_review_changes"]) == 6
    assert len(batch[0]["metadata"]["tax_review_warnings"]) == 3
    assert len(batch[0]["metadata"]["tax_review_changes"]) == 6
    assert batch[0]["invoice"]["total_cgst"] == "45"
    assert all(item["cgst_amount"] is None for item in batch[0]["invoice"]["items"])


def test_comparison_uses_one_document_conversion_and_mocked_llm(tmp_path):
    path = tmp_path / "invoice.txt"
    path.write_text(
        "Vendor: Seller\nInvoice Number: INV-1\nInvoice Date: 01/01/2026\n"
        "| Description | Quantity | Unit Price | Taxable Value |\n"
        "| Paper | 1 | 100 | 100 |\nSubtotal: 100\nGrand Total: 100",
        encoding="utf-8",
    )

    result = compare_file(path, llm_extractor=fake_llm)

    assert result["comparison"]["fields_compared"] > 0
    assert result["llm_metadata"]["model"] == "fake"
    assert result["rules_validation"]["status"] in {"review_required", "invalid"}