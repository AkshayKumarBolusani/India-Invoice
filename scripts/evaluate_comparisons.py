#!/usr/bin/env python3
"""Evaluate saved extractor_comparison*.json files against manually checked JSONL ground truth."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from invoice_ai.comparison import flatten, normalize_value


def load_ground_truth(path):
    truth = {}
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        truth[row["filename"]] = row["invoice"]
    return truth


def score(prediction, expected):
    pred_flat, truth_flat = flatten(prediction), flatten(expected)
    fields = sorted(set(pred_flat) | set(truth_flat))
    mismatches = []
    for field in fields:
        pv, tv = pred_flat.get(field), truth_flat.get(field)
        if normalize_value(field, pv) != normalize_value(field, tv):
            mismatches.append({"field": field, "expected": tv, "predicted": pv})
    return {"fields_scored": len(fields), "correct_fields": len(fields) - len(mismatches),
            "mismatch_count": len(mismatches), "field_accuracy": round((len(fields) - len(mismatches)) / len(fields), 4) if fields else None,
            "mismatches": mismatches}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("comparisons", nargs="+", help="Saved extractor_comparison JSON files")
    parser.add_argument("--ground-truth", default="evaluation/ground_truth.jsonl")
    parser.add_argument("--output", default="evaluation/extractor_evaluation_report.json")
    args = parser.parse_args()
    truth = load_ground_truth(args.ground_truth)
    report = {"note": "Field accuracy is against the included synthetic fixtures only; not production accuracy or GST certification.", "invoices": {}}
    for comparison_path in args.comparisons:
        comparison = json.loads(Path(comparison_path).read_text(encoding="utf-8"))
        filename = comparison.get("filename")
        if filename not in truth:
            print(f"Skipping {comparison_path}: no ground truth for {filename!r}")
            continue
        invoice_result = {"rules": score(comparison["rules"], truth[filename]),
                          "ollama": score(comparison["ollama"], truth[filename]),
                          "reported_comparison": {
                              "fields_compared": comparison.get("fields_compared"),
                              "substantive_differences": comparison.get("difference_count"),
                              "formatting_only_differences": comparison.get("formatting_difference_count", 0),
                              "ollama_latency_seconds": comparison.get("ollama_metadata", {}).get("latency_seconds")}}
        report["invoices"][filename] = invoice_result
    if report["invoices"]:
        for extractor in ("rules", "ollama"):
            total_fields = sum(v[extractor]["fields_scored"] for v in report["invoices"].values())
            correct_fields = sum(v[extractor]["correct_fields"] for v in report["invoices"].values())
            report.setdefault("aggregate", {})[extractor] = {
                "fields_scored": total_fields, "correct_fields": correct_fields,
                "mismatch_count": total_fields - correct_fields,
                "field_accuracy": round(correct_fields / total_fields, 4) if total_fields else None}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report.get("aggregate", {}), indent=2))
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
