# Technical Write-up

## Problem

Invoice extraction is not trustworthy merely because a model returns valid JSON. Scans, tables, missing GST evidence, generic tax fields, and duplicated invoice-level taxes require a review-first design.

## Pipeline

PDFs and supported images are converted with Docling. Image inputs are validated with Pillow and require an installed OCR runtime; the current local environment uses RapidOCR on CPU. Empty OCR output raises an actionable ingestion error. Normalized Markdown then feeds the rules extractor or optional OpenAI-compatible local LLM path.

The Pydantic invoice schema uses Decimal-compatible monetary fields. Validation checks arithmetic and GSTIN shape but does not infer missing GSTINs, HSN/SAC codes, rates, or line tax allocations.

## Tax review

`tax_review.py` detects the strong unsupported pattern where every line repeats the complete invoice-level CGST, SGST, or IGST total. It clears the line values and associated unverified rates, preserves invoice-level totals, emits warnings, and records original/corrected fields in workflow metadata. Arithmetic reconciliation remains separate from tax-rate verification.

## Evaluation

Synthetic fixtures are regression tests, not production accuracy. Public datasets are audited for structure, semantics, arithmetic, skipped checks, and review needs; their parser responses are not ground truth. See [`EVALUATION.md`](EVALUATION.md) and [`scripts/audit_dataset.py`](../scripts/audit_dataset.py).

## Performance and deployment

Workflow metadata records ingestion, OCR/conversion, extraction, validation, and total processing timings where available. Docker Compose provides FastAPI plus a static frontend; Ollama remains external and is configured through environment variables. Docker configuration is statically validated, but the current environment lacks a running Docker daemon for image execution.

## Future work

Durable authenticated review history, source-region coordinates, authorized vendor-group evaluation splits, asynchronous large-batch jobs, and browser-level live API tests remain useful next steps.
