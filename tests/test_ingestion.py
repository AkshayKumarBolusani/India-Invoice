from pathlib import Path

import pytest
from PIL import Image

import invoice_ai.ingestion as ingestion
from invoice_ai.ingestion import (
    DocumentIngestionError,
    extract_document,
    get_document_converter,
)
from invoice_ai.workflow import process_file


def test_txt_ingestion_returns_markdown_and_metadata(tmp_path):
    source = tmp_path / "invoice.txt"
    source.write_text("Invoice Number: INV-TEST-001", encoding="utf-8")

    result = extract_document(str(source))

    assert result["filename"] == "invoice.txt"
    assert result["markdown"] == "Invoice Number: INV-TEST-001"
    assert result["text_length"] == len(result["markdown"])
    assert result["method"] == "direct_text"


def test_missing_file_raises_file_not_found(tmp_path):
    missing = tmp_path / "missing.pdf"

    with pytest.raises(FileNotFoundError):
        extract_document(str(missing))


def test_unsupported_file_type_raises_value_error(tmp_path):
    source = tmp_path / "invoice.docx"
    source.write_text("test", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported document format"):
        extract_document(str(source))


def test_document_converter_is_cached():
    get_document_converter.cache_clear()


class FakeDocument:
    def __init__(self, markdown):
        self.markdown = markdown

    def export_to_markdown(self):
        return self.markdown


class FakeResult:
    def __init__(self, markdown):
        self.document = FakeDocument(markdown)


class FakeConverter:
    def __init__(self, markdown="Invoice Number: OCR-001"):
        self.markdown = markdown
        self.paths = []

    def convert(self, path, **kwargs):
        self.paths.append((path, kwargs))
        return FakeResult(self.markdown)


@pytest.mark.parametrize("extension, image_format", [(".png", "PNG"), (".jpg", "JPEG"), (".webp", "WEBP")])
def test_supported_image_formats_use_docling_and_validate_content(tmp_path, monkeypatch, extension, image_format):
    source = tmp_path / f"invoice{extension}"
    Image.new("RGB", (100, 80), "white").save(source, format=image_format)
    converter = FakeConverter()
    monkeypatch.setattr(ingestion, "get_document_converter", lambda: converter)
    monkeypatch.setattr(ingestion, "_ocr_backend", lambda: "rapidocr")

    result = extract_document(str(source))

    assert result["method"] == "docling_image_ocr"
    assert result["text_length"] > 0
    assert result["ocr_backend"] == "rapidocr"
    assert result["timings"]["ocr_seconds"] >= 0
    assert converter.paths[0][0] == str(source)


def test_corrupt_image_is_rejected_before_docling(tmp_path):
    source = tmp_path / "invoice.png"
    source.write_bytes(b"not an image")

    with pytest.raises(DocumentIngestionError, match="corrupt"):
        extract_document(str(source))


def test_oversized_document_is_rejected(tmp_path):
    source = tmp_path / "invoice.png"
    Image.new("RGB", (10, 10), "white").save(source, format="PNG")

    with pytest.raises(DocumentIngestionError, match="size limit"):
        extract_document(str(source), max_file_size=1)


def test_empty_ocr_text_is_actionable(tmp_path, monkeypatch):
    source = tmp_path / "invoice.png"
    Image.new("RGB", (100, 80), "white").save(source, format="PNG")
    monkeypatch.setattr(ingestion, "get_document_converter", lambda: FakeConverter("  \n"))
    monkeypatch.setattr(ingestion, "_ocr_backend", lambda: "rapidocr")

    with pytest.raises(DocumentIngestionError, match="OCR returned no readable text"):
        extract_document(str(source))


def test_image_requires_an_available_ocr_runtime(tmp_path, monkeypatch):
    source = tmp_path / "invoice.png"
    Image.new("RGB", (100, 80), "white").save(source, format="PNG")
    monkeypatch.setattr(ingestion, "_ocr_backend", lambda: None)

    with pytest.raises(DocumentIngestionError, match="No supported OCR runtime"):
        extract_document(str(source))


def test_ocr_markdown_flows_into_existing_invoice_extractor(tmp_path, monkeypatch):
    source = tmp_path / "invoice.png"
    Image.new("RGB", (100, 80), "white").save(source, format="PNG")
    markdown = (
        "Vendor: OCR Seller\nInvoice Number: OCR-001\nInvoice Date: 15/10/2026\n"
        "| Description | Quantity | Unit Price | Taxable Value |\n"
        "| Paper | 2 | 10 | 20 |\nSubtotal: 20\nGrand Total: 20"
    )
    monkeypatch.setattr(ingestion, "get_document_converter", lambda: FakeConverter(markdown))
    monkeypatch.setattr(ingestion, "_ocr_backend", lambda: "rapidocr")

    result = process_file(source)

    assert result["invoice"]["invoice_number"] == "OCR-001"
    assert result["invoice"]["vendor_name"] == "OCR Seller"
    assert result["metadata"]["ocr_backend"] == "rapidocr"
    assert result["metadata"]["ocr_seconds"] >= 0

    first = get_document_converter()
    second = get_document_converter()

    assert first is second

    get_document_converter.cache_clear()
