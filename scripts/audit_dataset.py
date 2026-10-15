"""Audit invoice parser records without writing invoice contents to reports."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


BOOLEAN_TEXT = {"true", "false"}
JSON_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def load_records(path: Path) -> list[dict]:
    """Load JSON/JSONL records or a Hugging Face dataset saved to disk."""
    if path.is_dir():
        try:
            from datasets import load_from_disk
        except ImportError as exc:
            raise RuntimeError(
                "Reading a saved Hugging Face dataset requires the optional "
                "'datasets' package; export JSONL or install the project dependencies."
            ) from exc

        dataset = load_from_disk(str(path))
        splits = dataset.items() if hasattr(dataset, "items") else [("default", dataset)]
        records = []
        for split_name, split in splits:
            for record in split:
                copied = dict(record)
                copied.setdefault("_split", split_name)
                records.append(copied)
        return records

    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    loaded = json.loads(text)
    if isinstance(loaded, list):
        return loaded
    if isinstance(loaded, dict):
        return [loaded]
    raise ValueError("Input must contain a JSON object, JSON array, or JSONL records.")


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content) if content is not None else ""


def extract_source_and_response(record: dict) -> tuple[str, Any]:
    """Extract source text and the final assistant response from common layouts."""
    source = record.get("source_text") or record.get("invoice_text") or record.get("raw_text") or ""
    response = record.get("invoice_gpt_parser_response")
    if response is None:
        response = record.get("parser_response")

    messages = record.get("messages")
    if isinstance(messages, list):
        user_parts = []
        assistant_parts = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = _content_text(message.get("content"))
            if message.get("role") == "user":
                user_parts.append(content)
            elif message.get("role") == "assistant":
                assistant_parts.append(content)
        source = source or "\n".join(user_parts)
        response = response if response is not None else (assistant_parts[-1] if assistant_parts else None)

    return source, response


def parse_response(response: Any) -> tuple[dict | None, str]:
    """Return a parsed object and a precise response-shape status."""
    if isinstance(response, dict):
        return response, "parsed"
    if not isinstance(response, str) or not response.strip():
        return None, "missing_response"

    candidate = response.strip()
    fenced = JSON_FENCE.match(candidate)
    if fenced:
        candidate = fenced.group(1)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None, "malformed_json"
    if not isinstance(parsed, dict):
        return None, "unexpected_json_shape"
    return parsed, "parsed"


def classify_flag(value) -> str:
    """Classify a flag without retaining its potentially sensitive value."""
    if isinstance(value, bool):
        return "boolean"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in BOOLEAN_TEXT:
            return "boolean_text"
        if not normalized:
            return "empty_text"
        if len(normalized) > 80 or any(char in normalized for char in "\n\r"):
            return "long_or_multiline_text"
        if re.fullmatch(r"[a-z0-9][a-z0-9_./:-]{2,}", normalized):
            return "identifier_like_text"
        return "other_text"
    return type(value).__name__


def _normalized_source(value) -> str:
    return " ".join(str(value).casefold().split())


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool) or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("₹", "").strip())
    except (InvalidOperation, TypeError, ValueError):
        return None


def _first_present(data: dict, fields: tuple[str, ...]) -> tuple[Any, str | None]:
    for field in fields:
        if field in data and data[field] is not None and data[field] != "":
            return data[field], field
    return None, None


def normalize_invoice_response(response: dict) -> tuple[dict, dict]:
    """Normalize aliases without assigning generic tax to a GST component."""
    items, item_source = _first_present(response, ("items", "line_items"))
    normalized_items = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                normalized_items.append({"_shape": type(item).__name__})
                continue
            normalized_item = {}
            aliases = {
                "description": ("description", "item_description", "name"),
                "quantity": ("quantity", "qty"),
                "unit_price": ("unit_price", "price", "rate"),
                "taxable_value": ("taxable_value", "taxable_amount", "line_total"),
                "hsn_sac": ("hsn_sac", "hsn", "sac"),
                "gst_rate": ("gst_rate", "tax_rate"),
                "cgst_amount": ("cgst_amount",),
                "sgst_amount": ("sgst_amount",),
                "igst_amount": ("igst_amount",),
                "total_amount": ("total_amount", "amount", "line_total"),
            }
            for target, names in aliases.items():
                value, source_field = _first_present(item, names)
                if source_field is not None:
                    normalized_item[target] = value
            normalized_items.append(normalized_item)

    normalized = {
        "invoice_number": response.get("invoice_number"),
        "invoice_date": response.get("invoice_date"),
        "vendor_name": response.get("vendor_name"),
        "buyer_name": response.get("buyer_name", response.get("customer_name")),
        "currency": response.get("currency"),
        "items": normalized_items,
        "subtotal": response.get("subtotal"),
        "generic_tax_amount": response.get("tax_amount"),
        "grand_total": response.get("grand_total", response.get("total_amount")),
        "shipping_fee": response.get("shipping_fee"),
        "discount": response.get("discount"),
        "round_off": response.get(
            "round_off",
            response.get("rounding_adjustment", response.get("rounding")),
        ),
        "order_id": response.get("order_id"),
    }
    provenance = {
        "item_source": item_source,
        "grand_total_source": "grand_total" if "grand_total" in response else (
            "total_amount" if "total_amount" in response else None
        ),
        "buyer_name_source": "buyer_name" if "buyer_name" in response else (
            "customer_name" if "customer_name" in response else None
        ),
    }
    return normalized, provenance


def source_evidence(source: str, invoice: dict) -> dict[str, int]:
    checks = {
        "core_fields_present": 0,
        "core_fields_not_found": 0,
        "item_descriptions_present": 0,
        "item_descriptions_not_found": 0,
    }
    searchable = _normalized_source(source)
    for field in ("invoice_number", "invoice_date", "vendor_name", "buyer_name"):
        value = invoice.get(field)
        if value and _normalized_source(value) in searchable:
            checks["core_fields_present"] += 1
        elif value:
            checks["core_fields_not_found"] += 1
    for item in invoice.get("items", []):
        value = item.get("description") if isinstance(item, dict) else None
        if value and _normalized_source(value) in searchable:
            checks["item_descriptions_present"] += 1
        elif value:
            checks["item_descriptions_not_found"] += 1
    return checks


def audit_arithmetic(invoice: dict) -> tuple[list[str], list[str]]:
    """Check generic invoice arithmetic, never relabeling tax as GST components.

    The checked equation is subtotal + generic tax + shipping - discount + round-off
    = total. Missing generic tax, subtotal, or total skips this check; absent optional
    adjustments are treated as zero, while a supplied round-off keeps its signed value.
    """
    failures = []
    skipped = []
    items = invoice.get("items", [])
    subtotal = _decimal(invoice.get("subtotal"))
    if items and all(_decimal(item.get("taxable_value")) is not None for item in items):
        if subtotal is None:
            skipped.append("item_taxable_values_vs_subtotal:missing_subtotal")
        elif abs(sum((_decimal(item["taxable_value"]) for item in items), Decimal("0")) - subtotal) > Decimal("0.01"):
            failures.append("item_taxable_values_vs_subtotal")
    else:
        skipped.append("item_taxable_values_vs_subtotal:missing_item_taxable_values")

    grand_total = _decimal(invoice.get("grand_total"))
    generic_tax = _decimal(invoice.get("generic_tax_amount"))
    shipping = _decimal(invoice.get("shipping_fee"))
    discount = _decimal(invoice.get("discount"))
    round_off = _decimal(invoice.get("round_off"))
    if subtotal is not None and grand_total is not None and generic_tax is not None:
        calculated = (
            subtotal
            + generic_tax
            + (shipping or Decimal("0"))
            - (discount or Decimal("0"))
            + (round_off or Decimal("0"))
        )
        if abs(calculated - grand_total) > Decimal("0.01"):
            failures.append("subtotal_plus_generic_tax_plus_adjustments_vs_total")
    else:
        skipped.append("subtotal_plus_generic_tax_plus_adjustments_vs_total:missing_semantic_fields")

    line_checked = False
    for item in items:
        quantity = _decimal(item.get("quantity"))
        unit_price = _decimal(item.get("unit_price"))
        taxable_value = _decimal(item.get("taxable_value"))
        if quantity is not None and unit_price is not None and taxable_value is not None:
            line_checked = True
            if abs(quantity * unit_price - taxable_value) > Decimal("0.01"):
                failures.append("line_quantity_times_unit_price")
    if not line_checked:
        skipped.append("line_quantity_times_unit_price:missing_semantic_fields")
    return failures, skipped


def audit_record(record: dict, index: int) -> dict:
    source, raw_response = extract_source_and_response(record)
    response, response_status = parse_response(raw_response)
    normalized = {}
    provenance = {}
    if response is not None:
        normalized, provenance = normalize_invoice_response(response)

    schema_issues = []
    missing_fields = []
    arithmetic_failures = []
    arithmetic_skipped = []
    if response is None:
        schema_issues.append(response_status)
    else:
        if not provenance.get("item_source"):
            schema_issues.append("missing_items_or_line_items")
        elif not isinstance(response.get(provenance["item_source"]), list):
            schema_issues.append("items_not_list")
        for field in ("invoice_number", "invoice_date", "vendor_name", "subtotal", "grand_total"):
            if normalized.get(field) in (None, ""):
                missing_fields.append(field)
        arithmetic_failures, arithmetic_skipped = audit_arithmetic(normalized)

    metadata = {
        field: classify_flag(record[field])
        for field in ("is_duplicate", "all_found", "current_format")
        if field in record
    }
    suspicious_values = sum(
        value not in {"boolean", "boolean_text", "missing"}
        for value in metadata.values()
    )
    evidence = source_evidence(source, normalized) if response is not None else {}
    row = {
        "record_index": index,
        "record_id_hash": hashlib.sha256(
            str(record.get("doc_id", index)).encode("utf-8")
        ).hexdigest()[:16],
        "split": record.get("_split", ""),
        "response_status": response_status,
        "item_source": provenance.get("item_source", ""),
        "grand_total_source": provenance.get("grand_total_source", ""),
        "generic_tax_semantics": "generic_tax_amount" if normalized.get("generic_tax_amount") is not None else "missing",
        "schema_issue_count": len(schema_issues),
        "missing_field_count": len(missing_fields),
        "recognized_item_count": len(normalized.get("items", [])),
        "arithmetic_failure_count": len(arithmetic_failures),
        "arithmetic_skipped_count": len(arithmetic_skipped),
        "source_core_fields_present": evidence.get("core_fields_present", 0),
        "source_core_fields_not_found": evidence.get("core_fields_not_found", 0),
        "source_item_descriptions_present": evidence.get("item_descriptions_present", 0),
        "source_item_descriptions_not_found": evidence.get("item_descriptions_not_found", 0),
        "suspicious_metadata_count": suspicious_values,
        "metadata_types": json.dumps(metadata, sort_keys=True),
        "schema_issues": "|".join(schema_issues),
        "missing_fields": "|".join(missing_fields),
        "arithmetic_failures": "|".join(arithmetic_failures),
        "arithmetic_skipped": "|".join(arithmetic_skipped),
        "manual_review_required": bool(
            schema_issues or missing_fields or arithmetic_failures or suspicious_values
        ),
    }
    return row


def choose_manual_sample(rows: list[dict], size: int) -> list[dict]:
    """Prefer flagged records, then low/high item counts, without exposing values."""
    if size <= 0:
        return []
    ranked = sorted(
        rows,
        key=lambda row: (
            not row["manual_review_required"],
            -row["suspicious_metadata_count"],
            -row["recognized_item_count"],
            row["record_index"],
        ),
        reverse=True,
    )
    selected = []
    for row in ranked:
        if row not in selected:
            selected.append(row)
        if len(selected) >= size:
            break
    return selected


def build_summary(rows: list[dict], sample_size: int = 10) -> dict:
    metadata_types = {
        field: dict(Counter(
            json.loads(row["metadata_types"]).get(field, "missing") for row in rows
        ))
        for field in ("is_duplicate", "all_found", "current_format")
    }
    skip_reasons = Counter(
        reason
        for row in rows
        for reason in row["arithmetic_skipped"].split("|")
        if reason
    )
    summary = {
        "records_audited": len(rows),
        "parsed_json_records": sum(row["response_status"] == "parsed" for row in rows),
        "malformed_json_records": sum(row["response_status"] == "malformed_json" for row in rows),
        "unexpected_response_records": sum(row["response_status"] == "unexpected_json_shape" for row in rows),
        "records_with_recognized_items": sum(row["recognized_item_count"] > 0 for row in rows),
        "recognized_item_count_total": sum(row["recognized_item_count"] for row in rows),
        "schema_issue_records": sum(row["schema_issue_count"] > 0 for row in rows),
        "records_with_missing_required_response_fields": sum(row["missing_field_count"] > 0 for row in rows),
        "records_with_source_evidence_gaps": sum(
            int(row["source_core_fields_not_found"]) > 0
            or int(row["source_item_descriptions_not_found"]) > 0
            for row in rows
        ),
        "source_core_field_not_found_total": sum(
            int(row["source_core_fields_not_found"]) for row in rows
        ),
        "source_item_description_not_found_total": sum(
            int(row["source_item_descriptions_not_found"]) for row in rows
        ),
        "arithmetic_failure_records": sum(row["arithmetic_failure_count"] > 0 for row in rows),
        "arithmetic_failure_checks": sum(row["arithmetic_failure_count"] for row in rows),
        "arithmetic_skipped_checks": sum(row["arithmetic_skipped_count"] for row in rows),
        "arithmetic_skipped_by_reason": dict(skip_reasons),
        "manual_review_records": sum(row["manual_review_required"] for row in rows),
        "suspicious_metadata_records": sum(row["suspicious_metadata_count"] > 0 for row in rows),
        "metadata_type_counts": metadata_types,
        "manual_review_sample": [
            {"record_index": row["record_index"], "record_id_hash": row["record_id_hash"]}
            for row in choose_manual_sample(rows, sample_size)
        ],
        "privacy": "Reports contain hashes, counts, types, and statuses only; invoice contents are omitted.",
    }
    return summary


def write_reports(rows: list[dict], output: Path, summary_output: Path, sample_size: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else ["record_index", "record_id_hash"]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    summary = build_summary(rows, sample_size)
    summary_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, nargs="?", help="JSON, JSONL, or saved Hugging Face dataset directory")
    parser.add_argument("--dataset-name", help="Optional Hugging Face dataset name")
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation" / "dataset_audit.csv")
    parser.add_argument("--summary-output", type=Path, default=ROOT / "evaluation" / "dataset_audit_summary.json")
    parser.add_argument("--sample-size", type=int, default=10)
    args = parser.parse_args()

    if args.dataset_name:
        from datasets import load_dataset
        dataset = load_dataset(args.dataset_name)
        records = []
        for split_name, split in dataset.items():
            for record in split:
                copied = dict(record)
                copied.setdefault("_split", split_name)
                records.append(copied)
    elif args.input is not None:
        records = load_records(args.input)
    else:
        parser.error("provide input or --dataset-name")
    rows = [audit_record(record, index) for index, record in enumerate(records)]
    write_reports(rows, args.output, args.summary_output, args.sample_size)
    print(f"Audited {len(rows)} records")
    print(f"CSV report: {args.output}")
    print(f"Summary: {args.summary_output}")


if __name__ == "__main__":
    main()