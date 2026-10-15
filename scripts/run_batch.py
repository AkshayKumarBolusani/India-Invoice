import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)
from reportlab.lib.styles import getSampleStyleSheet

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evaluation"
PDF_DIR = ROOT / "data" / "samples"
PRED_PATH = EVAL / "predictions.jsonl"
REPORT_PATH = EVAL / "batch_report.json"

sys.path.insert(0, str(ROOT / "src"))
from invoice_ai.ingestion import extract_document
from invoice_ai.extraction import extract_invoice


def load_records(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def create_pdf(record):
    path = PDF_DIR / f"{record['document_id']}.pdf"
    styles = getSampleStyleSheet()

    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )

    story = [
        Paragraph("TAX INVOICE", styles["Title"]),
        Spacer(1, 6 * mm),
        Paragraph(f"Vendor: {record['vendor_name']}", styles["BodyText"]),
        Paragraph(f"GSTIN: {record['vendor_gstin']}", styles["BodyText"]),
        Paragraph(f"Invoice Number: {record['invoice_number']}", styles["BodyText"]),
        Paragraph(f"Invoice Date: {record['invoice_date']}", styles["BodyText"]),
        Spacer(1, 4 * mm),
        Paragraph(f"Buyer: {record['buyer_name']}", styles["BodyText"]),
        Spacer(1, 6 * mm),
    ]

    rows = [["Description", "Qty", "Rate (INR)", "Taxable Value (INR)"]]
    for item in record["items"]:
        rows.append([
            item["description"], item["quantity"],
            item["unit_price"], item["taxable_value"],
        ])

    table = Table(
        rows,
        colWidths=[65 * mm, 20 * mm, 38 * mm, 48 * mm],
        repeatRows=1,
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EDF5")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
    ]))
    story.extend([table, Spacer(1, 6 * mm)])

    subtotal = Decimal(record["subtotal"])
    cgst = Decimal(record["total_cgst"])
    sgst = Decimal(record["total_sgst"])
    igst = Decimal(record["total_igst"])

    if igst > 0:
        rate = (igst / subtotal * 100) if subtotal else Decimal("0")
        story.append(Paragraph(
            f"IGST @ {rate.normalize()}%: INR {igst:.2f}",
            styles["BodyText"],
        ))
    else:
        cgst_rate = (cgst / subtotal * 100) if subtotal else Decimal("0")
        sgst_rate = (sgst / subtotal * 100) if subtotal else Decimal("0")
        story.append(Paragraph(
            f"CGST @ {cgst_rate.normalize()}%: INR {cgst:.2f}",
            styles["BodyText"],
        ))
        story.append(Paragraph(
            f"SGST @ {sgst_rate.normalize()}%: INR {sgst:.2f}",
            styles["BodyText"],
        ))

    story.extend([
        Paragraph(f"Subtotal: INR {subtotal:.2f}", styles["BodyText"]),
        Paragraph(f"Grand Total: INR {Decimal(record['grand_total']):.2f}",
                  styles["BodyText"]),
        Paragraph("Currency: INR", styles["BodyText"]),
    ])

    doc.build(story)
    return path


def flatten(data):
    result = {
        key: value
        for key, value in data.items()
        if key not in {"items", "document_id", "file"}
    }
    result["item_count"] = len(data.get("items", []))
    for i, item in enumerate(data.get("items", [])):
        for key, value in item.items():
            result[f"items[{i}].{key}"] = value
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
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    records = load_records(EVAL / "ground_truth.jsonl")
    predictions = []
    failures = []

    for record in records:
        document_id = record["document_id"]
        try:
            pdf = create_pdf(record)
            extracted = extract_document(str(pdf))
            invoice = extract_invoice(extracted["markdown"])
            prediction = invoice.model_dump(mode="json")
            prediction["document_id"] = document_id
            predictions.append(prediction)
            print(f"[EXTRACTED] {document_id}: {pdf.name}")
        except Exception as exc:
            failures.append({"document_id": document_id, "error": str(exc)})
            print(f"[FAILED] {document_id}: {exc}")

    PRED_PATH.write_text(
        "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in predictions),
        encoding="utf-8",
    )

    pred_by_id = {p["document_id"]: p for p in predictions}
    total = correct = tp = fp = fn = 0
    per_document = []

    for record in records:
        doc_id = record["document_id"]
        prediction = pred_by_id.get(doc_id)

        if prediction is None:
            per_document.append({
                "document_id": doc_id, "status": "FAILED",
                "correct_fields": 0, "total_fields": 0,
            })
            continue

        expected_fields = flatten(record)
        predicted_fields = flatten(prediction)
        doc_correct = 0

        for field, expected in expected_fields.items():
            actual = predicted_fields.get(field)
            total += 1

            if normalize(expected) == normalize(actual):
                correct += 1
                doc_correct += 1
                tp += 1
            else:
                fn += 1
                if actual is not None:
                    fp += 1

        # Extra line items are false positives.
        expected_items = len(record.get("items", []))
        actual_items = len(prediction.get("items", []))
        if actual_items > expected_items:
            fp += actual_items - expected_items

        per_document.append({
            "document_id": doc_id,
            "status": "PASS" if doc_correct == len(expected_fields) else "REVIEW",
            "correct_fields": doc_correct,
            "total_fields": len(expected_fields),
        })

    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0

    report = {
        "dataset_size": len(records),
        "predictions_written": len(predictions),
        "extraction_failures": failures,
        "correct_fields": correct,
        "total_fields": total,
        "field_exact_match_accuracy": correct / total if total else 0,
        "field_precision": precision,
        "field_recall": recall,
        "field_f1": f1,
        "documents": per_document,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== BATCH EVALUATION ===")
    print(f"Documents: {len(records)}")
    print(f"Predictions: {len(predictions)}")
    print(f"Correct fields: {correct}/{total}")
    print(f"Field accuracy: {report['field_exact_match_accuracy']:.2%}")
    print(f"Field precision: {precision:.2%}")
    print(f"Field recall: {recall:.2%}")
    print(f"Field F1: {f1:.2%}")
    for result in per_document:
        print(
            f"{result['document_id']}: {result['status']} "
            f"({result['correct_fields']}/{result['total_fields']})"
        )
    print(f"\nPredictions: {PRED_PATH}")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
