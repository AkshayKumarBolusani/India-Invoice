
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUND_TRUTH = ROOT / "evaluation" / "ground_truth.jsonl"
PREDICTION = ROOT / "data" / "processed" / "extracted_invoice.json"


def load_ground_truth(path: Path) -> dict:
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    if len(records) != 1:
        raise ValueError(
            f"Expected one ground-truth record for this baseline; "
            f"found {len(records)}"
        )

    return records[0]


def flatten(data: dict) -> dict:
    result = {key: value for key, value in data.items()
              if key not in {"items", "document_id", "file"}}

    items = data.get("items", [])
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


def main():
    if not GROUND_TRUTH.exists():
        raise FileNotFoundError(
            f"Ground truth not found: {GROUND_TRUTH}\n"
            "Create evaluation/ground_truth.jsonl first."
        )

    if not PREDICTION.exists():
        raise FileNotFoundError(
            f"Prediction not found: {PREDICTION}\n"
            "Run scripts/run_extraction.py first."
        )

    expected = flatten(load_ground_truth(GROUND_TRUTH))
    predicted = flatten(
        json.loads(PREDICTION.read_text(encoding="utf-8"))
    )

    results = []
    for field, expected_value in expected.items():
        predicted_value = predicted.get(field)
        correct = normalize(expected_value) == normalize(predicted_value)

        results.append({
            "field": field,
            "expected": expected_value,
            "predicted": predicted_value,
            "correct": correct,
        })

    correct_count = sum(row["correct"] for row in results)
    total_count = len(results)
    accuracy = correct_count / total_count if total_count else 0

    print("\n=== Invoice Extraction Evaluation ===\n")
    for row in results:
        status = "PASS" if row["correct"] else "FAIL"
        print(f"[{status}] {row['field']}")
        if not row["correct"]:
            print(f"  Expected:  {row['expected']}")
            print(f"  Predicted: {row['predicted']}")

    print(f"\nCorrect fields: {correct_count}/{total_count}")
    print(f"Field exact-match accuracy: {accuracy:.2%}")

    document_exact_match = all(row["correct"] for row in results)
    print(f"Document exact match: {document_exact_match}")

    report_path = ROOT / "evaluation" / "baseline_report.json"
    report_path.write_text(
        json.dumps({
            "correct_fields": correct_count,
            "total_fields": total_count,
            "field_exact_match_accuracy": accuracy,
            "document_exact_match": document_exact_match,
            "results": results,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Report saved to: {report_path}")


if __name__ == "__main__":
    main()
