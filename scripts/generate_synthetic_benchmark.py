"""Generate and score a deterministic synthetic invoice benchmark."""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from invoice_ai.workflow import process_file


SCALAR_FIELDS = (
    "document_type", "invoice_number", "invoice_date", "vendor_name",
    "vendor_gstin", "buyer_name", "subtotal", "total_cgst", "total_sgst",
    "total_igst", "grand_total",
)
LAYOUTS = ("compact", "spaced", "wrapped")


def money(value: Decimal) -> str:
    return f"{value:.2f}"


def make_record(index: int, rng: random.Random) -> dict:
    tax_mode = "igst" if index % 2 else "cgst_sgst"
    layout = LAYOUTS[index % len(LAYOUTS)]
    item_count = 1 + (index % 5)
    items = []
    for item_index in range(item_count):
        quantity = Decimal(str(1 + ((index + item_index) % 5)))
        unit_price = Decimal(str(100 + ((index * 37 + item_index * 83) % 900)))
        items.append({
            "description": f"Synthetic Item {item_index + 1}",
            "quantity": money(quantity),
            "unit_price": money(unit_price),
            "taxable_value": money(quantity * unit_price),
        })
    subtotal = sum((Decimal(item["taxable_value"]) for item in items), Decimal("0"))
    if tax_mode == "igst":
        total_cgst = Decimal("0")
        total_sgst = Decimal("0")
        total_igst = (subtotal * Decimal("0.18")).quantize(Decimal("0.01"))
    else:
        total_cgst = (subtotal * Decimal("0.09")).quantize(Decimal("0.01"))
        total_sgst = total_cgst
        total_igst = Decimal("0")
    return {
        "document_id": f"SYN-{index:04d}",
        "document_type": "gst_invoice",
        "vendor_name": f"Synthetic Vendor {index:04d}",
        "vendor_gstin": "27ABCDE1234F1Z5",
        "invoice_number": f"SYN-{2026}-{index:04d}",
        "invoice_date": f"{1 + (index % 27):02d}/{10 + (index % 2):02d}/2026",
        "buyer_name": f"Synthetic Buyer {index:04d}",
        "buyer_gstin": "29ABCDE1234F1Z5",
        "currency": "INR",
        "items": items,
        "subtotal": money(subtotal),
        "total_cgst": money(total_cgst),
        "total_sgst": money(total_sgst),
        "total_igst": money(total_igst),
        "grand_total": money(subtotal + total_cgst + total_sgst + total_igst),
        "synthetic_metadata": {
            "layout": layout,
            "tax_mode": tax_mode,
            "language": "en",
            "item_count": item_count,
        },
    }


def render_text(record: dict) -> str:
    metadata = record["synthetic_metadata"]
    lines = [
        "TAX INVOICE",
        f"Vendor: {record['vendor_name']}",
        f"GSTIN: {record['vendor_gstin']}",
        f"Invoice Number: {record['invoice_number']}",
        f"Invoice Date: {record['invoice_date']}",
        f"Buyer: {record['buyer_name']}",
    ]
    if metadata["layout"] == "spaced":
        lines.insert(1, "")
        lines.insert(6, "")
    if metadata["layout"] == "wrapped":
        lines[3] = f"Invoice No.: {record['invoice_number']}"
        lines[5] = f"Billed To: {record['buyer_name']}"
    lines.extend([
        "| Description | Quantity | Unit Price | Taxable Value |",
    ])
    lines.extend(
        f"| {item['description']} | {item['quantity']} | {item['unit_price']} | {item['taxable_value']} |"
        for item in record["items"]
    )
    if metadata["tax_mode"] == "igst":
        lines.append(f"IGST @ 18%: INR {record['total_igst']}")
    else:
        lines.extend([
            f"CGST @ 9%: INR {record['total_cgst']}",
            f"SGST @ 9%: INR {record['total_sgst']}",
        ])
    lines.extend([
        f"Subtotal: INR {record['subtotal']}",
        f"Grand Total: INR {record['grand_total']}",
        "Currency: INR",
    ])
    return "\n".join(lines) + "\n"


def normalize(value):
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", "")).normalize()
    except Exception:
        return " ".join(str(value).casefold().split())


def score_items(expected: list[dict], actual: list[dict]) -> tuple[int, int, int]:
    expected_keys = Counter(
        (item["description"].casefold(), item["quantity"], item["unit_price"], item["taxable_value"])
        for item in expected
    )
    actual_keys = Counter(
        (str(item.get("description", "")).casefold(), str(item.get("quantity", "")), str(item.get("unit_price", "")), str(item.get("taxable_value", "")))
        for item in actual
    )
    matched = sum((expected_keys & actual_keys).values())
    return matched, len(actual), len(expected)


def run(output_dir: Path, count: int, seed: int) -> dict:
    rng = random.Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    documents_dir = output_dir / "documents"
    documents_dir.mkdir(exist_ok=True)
    records = [make_record(index, rng) for index in range(1, count + 1)]
    truth_path = output_dir / "ground_truth.jsonl"
    with truth_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    scalar_correct = 0
    scalar_total = 0
    matched_items = predicted_items = expected_items = 0
    arithmetic_consistent = 0
    review_required = 0
    latencies = []
    documents = []
    for record in records:
        path = documents_dir / f"{record['document_id']}.txt"
        path.write_text(render_text(record), encoding="utf-8")
        started = time.perf_counter()
        result = process_file(path)
        elapsed = time.perf_counter() - started
        prediction = result["invoice"] or {}
        for field in SCALAR_FIELDS:
            scalar_total += 1
            if normalize(record.get(field)) == normalize(prediction.get(field)):
                scalar_correct += 1
        matched, predicted_count, expected_count = score_items(record["items"], prediction.get("items", []))
        matched_items += matched
        predicted_items += predicted_count
        expected_items += expected_count
        arithmetic_consistent += not bool((result.get("validation") or {}).get("errors"))
        review_required += result["status"] == "review_required"
        latencies.append(elapsed)
        documents.append({
            "document_id": record["document_id"],
            "layout": record["synthetic_metadata"]["layout"],
            "tax_mode": record["synthetic_metadata"]["tax_mode"],
            "item_count": record["synthetic_metadata"]["item_count"],
            "status": result["status"],
        })

    precision = matched_items / predicted_items if predicted_items else 0
    recall = matched_items / expected_items if expected_items else 0
    report = {
        "dataset": "synthetic_generated_invoice_benchmark",
        "ground_truth": "constructed by generator",
        "seed": seed,
        "documents": count,
        "layouts": list(LAYOUTS),
        "tax_modes": ["cgst_sgst", "igst"],
        "item_count_range": [1, 5],
        "scalar_fields": list(SCALAR_FIELDS),
        "scalar_normalized_accuracy": scalar_correct / scalar_total if scalar_total else 0,
        "scalar_correct": scalar_correct,
        "scalar_total": scalar_total,
        "line_item_precision": precision,
        "line_item_recall": recall,
        "line_item_f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
        "line_items_matched": matched_items,
        "line_items_predicted": predicted_items,
        "line_items_expected": expected_items,
        "arithmetic_consistent_documents": arithmetic_consistent,
        "review_required_documents": review_required,
        "median_rules_pipeline_seconds": statistics.median(latencies) if latencies else None,
        "llm_metrics": "not measured; no live model was invoked",
        "documents_detail": documents,
    }
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output_dir / "REPORT.md").write_text(
        "# Synthetic Invoice Benchmark\n\n"
        f"Generated {count} labeled text invoices with seed `{seed}`.\n\n"
        f"- Normalized scalar accuracy: `{report['scalar_normalized_accuracy']:.2%}` ({scalar_correct}/{scalar_total})\n"
        f"- Line-item precision/recall/F1: `{precision:.2%}` / `{recall:.2%}` / `{report['line_item_f1']:.2%}`\n"
        f"- Arithmetic-consistent documents: `{arithmetic_consistent}/{count}`\n"
        f"- Median rules pipeline latency: `{report['median_rules_pipeline_seconds']:.4f}s`\n"
        "- LLM metrics: not measured; no live model was invoked.\n\n"
        "This is synthetic regression evidence, not real-world accuracy.\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--seed", type=int, default=20261015)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation" / "synthetic_benchmark")
    args = parser.parse_args()
    report = run(args.output_dir, args.count, args.seed)
    print(json.dumps({key: value for key, value in report.items() if key != "documents_detail"}, indent=2))
    print(f"Report: {args.output_dir / 'report.json'}")


if __name__ == "__main__":
    main()
