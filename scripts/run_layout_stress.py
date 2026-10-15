import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from invoice_ai.ingestion import extract_document
from invoice_ai.extraction import extract_invoice

EVAL = ROOT / "evaluation"
OUT = ROOT / "data" / "samples" / "layout_stress"
OUT.mkdir(parents=True, exist_ok=True)

records = [
    json.loads(line)
    for line in (EVAL / "ground_truth.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    if line.strip()
]

def p(text, style):
    return Paragraph(text, style)

def create_variant(record, variant):
    path = OUT / f"{record['document_id']}_layout{variant}.pdf"
    styles = getSampleStyleSheet()

    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )

    story = []
    if variant == 1:
        # Same basic labels, but separated and reordered.
        story.extend([
            p("TAX INVOICE", styles["Title"]),
            Spacer(1, 8 * mm),
            p(f"Invoice Date: {record['invoice_date']}", styles["BodyText"]),
            p(f"Invoice Number: {record['invoice_number']}", styles["BodyText"]),
            Spacer(1, 4 * mm),
            p(f"Vendor: {record['vendor_name']}", styles["BodyText"]),
            p(f"GSTIN: {record['vendor_gstin']}", styles["BodyText"]),
            p(f"Buyer: {record['buyer_name']}", styles["BodyText"]),
        ])
    elif variant == 2:
        # Common alternative labels challenge our exact-label parser.
        story.extend([
            p("COMMERCIAL TAX INVOICE", styles["Title"]),
            Spacer(1, 8 * mm),
            p(f"Supplier: {record['vendor_name']}", styles["BodyText"]),
            p(f"GSTIN/UIN: {record['vendor_gstin']}", styles["BodyText"]),
            p(f"Bill No: {record['invoice_number']}", styles["BodyText"]),
            p(f"Date: {record['invoice_date']}", styles["BodyText"]),
            p(f"Billed To: {record['buyer_name']}", styles["BodyText"]),
        ])
    else:
        # Different table headers and invoice field ordering.
        story.extend([
            p("INVOICE", styles["Title"]),
            Spacer(1, 8 * mm),
            p(f"GSTIN: {record['vendor_gstin']}", styles["BodyText"]),
            p(f"Vendor: {record['vendor_name']}", styles["BodyText"]),
            p(f"Invoice Number: {record['invoice_number']}", styles["BodyText"]),
            p(f"Invoice Date: {record['invoice_date']}", styles["BodyText"]),
            p(f"Buyer: {record['buyer_name']}", styles["BodyText"]),
        ])

    story.append(Spacer(1, 6 * mm))
    rows = [["Item Description", "Quantity", "Unit Price", "Taxable Amount"]]
    for item in record["items"]:
        rows.append([
            item["description"], item["quantity"],
            item["unit_price"], item["taxable_value"],
        ])

    table = Table(
        rows, colWidths=[65 * mm, 22 * mm, 38 * mm, 46 * mm],
        repeatRows=1,
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([table, Spacer(1, 6 * mm)])

    subtotal = Decimal(record["subtotal"])
    cgst = Decimal(record["total_cgst"])
    sgst = Decimal(record["total_sgst"])
    igst = Decimal(record["total_igst"])

    story.append(p(f"Subtotal: INR {subtotal:.2f}", styles["BodyText"]))
    if igst:
        rate = igst / subtotal * 100 if subtotal else Decimal(0)
        story.append(p(
            f"IGST @ {rate.normalize()}%: INR {igst:.2f}",
            styles["BodyText"],
        ))
    else:
        cgst_rate = cgst / subtotal * 100 if subtotal else Decimal(0)
        sgst_rate = sgst / subtotal * 100 if subtotal else Decimal(0)
        story.append(p(
            f"CGST @ {cgst_rate.normalize()}%: INR {cgst:.2f}",
            styles["BodyText"],
        ))
        story.append(p(
            f"SGST @ {sgst_rate.normalize()}%: INR {sgst:.2f}",
            styles["BodyText"],
        ))

    story.append(p(
        f"Grand Total: INR {Decimal(record['grand_total']):.2f}",
        styles["BodyText"],
    ))
    doc.build(story)
    return path

def flatten(data):
    result = {
        k: v for k, v in data.items()
        if k not in {"items", "document_id", "file"}
    }
    result["item_count"] = len(data.get("items", []))
    for i, item in enumerate(data.get("items", [])):
        for k, v in item.items():
            result[f"items[{i}].{k}"] = v
    return result

def norm(value):
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

results = []
total_fields = 0
correct_fields = 0

for index, record in enumerate(records, start=1):
    pdf = create_variant(record, index)
    try:
        doc = extract_document(str(pdf))
        invoice = extract_invoice(doc["markdown"])
        prediction = invoice.model_dump(mode="json")

        expected = flatten(record)
        actual = flatten(prediction)
        matched = sum(
            norm(actual.get(key)) == norm(value)
            for key, value in expected.items()
        )
        count = len(expected)
        total_fields += count
        correct_fields += matched

        results.append({
            "document_id": record["document_id"],
            "layout": index,
            "pdf": str(pdf.relative_to(ROOT)),
            "correct_fields": matched,
            "total_fields": count,
            "accuracy": matched / count if count else 0,
            "prediction": prediction,
        })
        print(
            f"{record['document_id']} layout {index}: "
            f"{matched}/{count} fields correct"
        )
    except Exception as exc:
        results.append({
            "document_id": record["document_id"],
            "layout": index,
            "error": str(exc),
        })
        print(f"{record['document_id']} layout {index}: ERROR {exc}")

report = {
    "test_type": "synthetic_layout_stress",
    "documents": len(results),
    "correct_fields": correct_fields,
    "total_fields": total_fields,
    "field_accuracy": (
        correct_fields / total_fields if total_fields else 0
    ),
    "results": results,
}
report_path = EVAL / "layout_stress_report.json"
report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

print("\n=== LAYOUT STRESS RESULTS ===")
print(f"Field accuracy: {report['field_accuracy']:.2%}")
print(f"Report: {report_path}")
print("These are synthetic layout tests, not real-world accuracy.")
