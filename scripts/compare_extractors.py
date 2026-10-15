import json
import os
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

from invoice_ai.extraction import extract_invoice
from invoice_ai.ingestion import extract_document
from invoice_ai.llm_extraction import extract_invoice_with_llm

EVAL_DIR = ROOT / "evaluation"
SAMPLES_DIR = ROOT / "data" / "samples"
REPORT_PATH = EVAL_DIR / "model_comparison.json"



def flatten(record):
    """Flatten invoice fields and line items for field-by-field scoring."""
    result = {
        key: value
        for key, value in record.items()
        if key not in {"items", "document_id", "file", "filename"}
    }

    items = record.get("items", [])
    result["item_count"] = len(items)

    for index, item in enumerate(items):
        for key, value in item.items():
            result[f"items[{index}].{key}"] = value

    return result



def normalize(value):
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).normalize()
    if isinstance(value, str):
        value = value.strip()
        try:
            return Decimal(value.replace(",", "")).normalize()
        except InvalidOperation:
            return " ".join(value.casefold().split())
    return value


def score(expected_record, prediction):
    expected = flatten(expected_record)
    actual = flatten(prediction)
    total = len(expected)
    correct = sum(normalize(actual.get(key)) == normalize(value)
                  for key, value in expected.items())
    mismatches = [
        {
            "field": key,
            "expected": value,
            "actual": actual.get(key),
        }
        for key, value in expected.items()
        if normalize(actual.get(key)) != normalize(value)
    ]
    return {
        "correct_fields": correct,
        "total_fields": total,
        "field_accuracy": correct / total if total else 0,
        "mismatches": mismatches,
    }


def main():
    gt_path = EVAL_DIR / "ground_truth.jsonl"
    records = [
        json.loads(line)
        for line in gt_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    if not os.getenv("LLM_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        raise SystemExit(
            "No API key configured. Copy .env.example to .env, add your API key/model, "
            "then rerun this script."
        )

    report = {
        "test_type": "synthetic_fixture_comparison",
        "note": "Synthetic fixtures only; this is not real-world accuracy.",
        "model": os.getenv("LLM_MODEL"),
        "documents": [],
        "totals": {
            "rules_correct_fields": 0,
            "rules_total_fields": 0,
            "llm_correct_fields": 0,
            "llm_total_fields": 0,
        },
        "llm_usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_seconds": [],
        },
    }

    input_rate = os.getenv("LLM_INPUT_USD_PER_1M")
    output_rate = os.getenv("LLM_OUTPUT_USD_PER_1M")
    cost_configured = input_rate is not None and output_rate is not None
    estimated_cost = 0.0

    for record in records:
        filename = record.get("filename")
        if not filename:
            raise SystemExit(
                "Invalid ground-truth record: missing 'filename'."
            )

        pdf = SAMPLES_DIR / filename
        if not pdf.exists():
            raise SystemExit(
                f"Missing {pdf}. Generate sample PDFs first with scripts/run_batch.py."
            )

        extracted = extract_document(str(pdf))
        markdown = extracted["markdown"]

        rules_prediction = extract_invoice(markdown).model_dump(mode="json")
        rules_score = score(record["invoice"], rules_prediction)

        llm_invoice, metadata = extract_invoice_with_llm(markdown)
        llm_prediction = llm_invoice.model_dump(mode="json")
        llm_score = score(record["invoice"], llm_prediction)

        report["totals"]["rules_correct_fields"] += rules_score["correct_fields"]
        report["totals"]["rules_total_fields"] += rules_score["total_fields"]
        report["totals"]["llm_correct_fields"] += llm_score["correct_fields"]
        report["totals"]["llm_total_fields"] += llm_score["total_fields"]

        report["llm_usage"]["latency_seconds"].append(metadata["latency_seconds"])
        for usage_key in ("input_tokens", "output_tokens"):
            amount = metadata.get(usage_key)
            if amount is not None:
                report["llm_usage"][usage_key] += amount

        if cost_configured:
            estimated_cost += (
                (metadata.get("input_tokens") or 0) * float(input_rate)
                + (metadata.get("output_tokens") or 0) * float(output_rate)
            ) / 1_000_000

        report["documents"].append({
            "document_id": Path(filename).stem,
            "rules": rules_score,
            "llm": llm_score,
            "llm_metadata": metadata,
            "llm_prediction": llm_prediction,
        })

        print(
            f"{Path(filename).stem}: rules {rules_score['correct_fields']}/"
            f"{rules_score['total_fields']} | LLM {llm_score['correct_fields']}/"
            f"{llm_score['total_fields']} | {metadata['latency_seconds']}s"
        )

    totals = report["totals"]
    report["summary"] = {
        "rules_field_accuracy": (
            totals["rules_correct_fields"] / totals["rules_total_fields"]
            if totals["rules_total_fields"] else 0
        ),
        "llm_field_accuracy": (
            totals["llm_correct_fields"] / totals["llm_total_fields"]
            if totals["llm_total_fields"] else 0
        ),
        "average_llm_latency_seconds": (
            sum(report["llm_usage"]["latency_seconds"])
            / len(report["llm_usage"]["latency_seconds"])
            if report["llm_usage"]["latency_seconds"] else None
        ),
        "estimated_cost_usd": round(estimated_cost, 8) if cost_configured else None,
        "cost_note": (
            "Estimated from rates configured in .env."
            if cost_configured else
            "Not calculated. Add LLM_INPUT_USD_PER_1M and LLM_OUTPUT_USD_PER_1M "
            "to .env for an estimate; verify rates with your provider."
        ),
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\n=== COMPARISON SUMMARY ===")
    print(f"Rules accuracy: {report['summary']['rules_field_accuracy']:.2%}")
    print(f"LLM accuracy:   {report['summary']['llm_field_accuracy']:.2%}")
    print(f"Average LLM latency: {report['summary']['average_llm_latency_seconds']}s")
    print(f"Estimated API cost: {report['summary']['estimated_cost_usd']}")
    print(f"Report saved to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
