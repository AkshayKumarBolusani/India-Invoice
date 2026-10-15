"""Application workflows shared by the UI and offline tests."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from .comparison import compare_outputs
from .extraction import extract_invoice
from .ingestion import extract_document
from .schemas import Invoice
from .tax_review import review_llm_tax_fields
from .validation import validate_invoice


LLMExtractor = Callable[[str], tuple[Invoice, dict[str, Any]]]


def _serialize_invoice(invoice: Invoice) -> dict[str, Any]:
    return invoice.model_dump(mode="json")


def _tax_review_changes(
    original: dict[str, Any], reviewed: dict[str, Any]
) -> list[dict[str, Any]]:
    changes = []
    for index, (original_item, reviewed_item) in enumerate(
        zip(original.get("items", []), reviewed.get("items", []))
    ):
        for field in ("cgst_amount", "sgst_amount", "igst_amount", "gst_rate"):
            before = original_item.get(field)
            after = reviewed_item.get(field)
            if before != after:
                changes.append({
                    "field": f"items[{index}].{field}",
                    "original": before,
                    "corrected": after,
                    "reason": "duplicate invoice-level tax allocation was not source-supported",
                })
    return changes


def process_file(
    file_path: str | Path,
    engine: str = "rules-based",
    llm_extractor: LLMExtractor | None = None,
) -> dict[str, Any]:
    """Process one supported file and return payload, validation, and metadata."""
    path = Path(file_path)
    started = time.perf_counter()
    ingestion_started = time.perf_counter()
    document = extract_document(str(path))
    ingestion_seconds = time.perf_counter() - ingestion_started
    extraction_started = time.perf_counter()
    metadata: dict[str, Any]

    if engine == "rules-based":
        invoice = extract_invoice(document["markdown"])
        metadata = {"engine": "rules-based"}
    elif engine == "llm":
        if llm_extractor is None:
            from .llm_extraction import extract_invoice_with_llm

            llm_extractor = extract_invoice_with_llm
        invoice, metadata = llm_extractor(document["markdown"])
        original_payload = _serialize_invoice(invoice)
        reviewed_data, tax_warnings = review_llm_tax_fields(invoice)
        invoice = Invoice.model_validate(reviewed_data)
        metadata = dict(metadata)
        metadata["tax_review_warnings"] = tax_warnings
        metadata["tax_review_changes"] = _tax_review_changes(
            original_payload, _serialize_invoice(invoice)
        )
        metadata["engine"] = "llm"
    else:
        raise ValueError(f"Unsupported extraction engine: {engine}")

    extraction_seconds = time.perf_counter() - extraction_started
    payload = _serialize_invoice(invoice)
    validation_started = time.perf_counter()
    validation = validate_invoice(payload)
    validation_seconds = time.perf_counter() - validation_started
    metadata = dict(metadata)
    metadata.update({
        "ingestion_seconds": round(ingestion_seconds, 4),
        "extraction_seconds": round(extraction_seconds, 4),
        "validation_seconds": round(validation_seconds, 4),
        "processing_seconds": round(time.perf_counter() - started, 3),
    })
    metadata.update({
        key: value
        for key, value in document.get("timings", {}).items()
        if key.endswith("_seconds")
    })
    if document.get("ocr_backend"):
        metadata["ocr_backend"] = document["ocr_backend"]
    return {
        "filename": path.name,
        "status": validation["status"],
        "invoice": payload,
        "validation": validation,
        "metadata": metadata,
        "source_markdown": document["markdown"],
    }


def process_batch(
    file_paths: Iterable[str | Path],
    engine: str = "rules-based",
    llm_extractor: LLMExtractor | None = None,
) -> list[dict[str, Any]]:
    """Process every file independently; one failure does not abort the batch."""
    results = []
    for file_path in file_paths:
        path = Path(file_path)
        try:
            results.append(process_file(path, engine=engine, llm_extractor=llm_extractor))
        except Exception as exc:
            results.append({
                "filename": path.name,
                "status": "processing_failed",
                "invoice": None,
                "validation": None,
                "metadata": {},
                "error": str(exc),
            })
    return results


def compare_file(
    file_path: str | Path,
    llm_extractor: LLMExtractor | None = None,
) -> dict[str, Any]:
    """Run both extractors on one normalized document and validate independently."""
    path = Path(file_path)
    started = time.perf_counter()
    ingestion_started = time.perf_counter()
    document = extract_document(str(path))
    ingestion_seconds = time.perf_counter() - ingestion_started

    rules_started = time.perf_counter()
    rules_invoice = extract_invoice(document["markdown"])
    rules_payload = _serialize_invoice(rules_invoice)
    rules_seconds = time.perf_counter() - rules_started

    if llm_extractor is None:
        from .llm_extraction import extract_invoice_with_llm

        llm_extractor = extract_invoice_with_llm
    llm_started = time.perf_counter()
    llm_invoice, llm_metadata = llm_extractor(document["markdown"])
    llm_seconds = time.perf_counter() - llm_started
    original_llm_payload = _serialize_invoice(llm_invoice)
    reviewed_data, tax_warnings = review_llm_tax_fields(llm_invoice)
    llm_invoice = Invoice.model_validate(reviewed_data)
    llm_payload = _serialize_invoice(llm_invoice)

    validation_started = time.perf_counter()
    rules_validation = validate_invoice(rules_payload)
    llm_validation = validate_invoice(llm_payload)
    validation_seconds = time.perf_counter() - validation_started
    return {
        "filename": path.name,
        "rules": rules_payload,
        "rules_validation": rules_validation,
        "llm": llm_payload,
        "llm_validation": llm_validation,
        "llm_metadata": {
            **llm_metadata,
            "tax_review_warnings": tax_warnings,
            "tax_review_changes": _tax_review_changes(
                original_llm_payload, llm_payload
            ),
            "ingestion_seconds": round(ingestion_seconds, 4),
            "rules_extraction_seconds": round(rules_seconds, 4),
            "llm_inference_seconds": round(llm_seconds, 4),
            "validation_seconds": round(validation_seconds, 4),
            "processing_seconds": round(time.perf_counter() - started, 3),
        },
        "comparison": compare_outputs(rules_payload, llm_payload),
        "source_markdown": document["markdown"],
    }
