
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "raw" / "sample_invoice.pdf"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

doc = SimpleDocTemplate(
    str(OUTPUT),
    pagesize=A4,
    rightMargin=18 * mm,
    leftMargin=18 * mm,
    topMargin=18 * mm,
    bottomMargin=18 * mm,
)

styles = getSampleStyleSheet()
story = [
    Paragraph("TAX INVOICE", styles["Title"]),
    Spacer(1, 8 * mm),
    Paragraph("<b>Vendor:</b> Sri Lakshmi Office Supplies", styles["BodyText"]),
    Paragraph("<b>GSTIN:</b> 36ABCDE1234F1Z5", styles["BodyText"]),
    Paragraph("<b>Invoice Number:</b> INV-2026-001", styles["BodyText"]),
    Paragraph("<b>Invoice Date:</b> 14/10/2026", styles["BodyText"]),
    Spacer(1, 5 * mm),
    Paragraph("<b>Buyer:</b> Example Technologies Pvt Ltd", styles["BodyText"]),
    Spacer(1, 8 * mm),
]

rows = [
    ["Description", "Qty", "Rate (INR)", "Taxable Value (INR)"],
    ["Office Paper", "2", "500.00", "1,000.00"],
    ["Printer Cartridge", "1", "1,200.00", "1,200.00"],
]

table = Table(rows, colWidths=[65 * mm, 20 * mm, 38 * mm, 48 * mm])
table.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EDF5")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("PADDING", (0, 0), (-1, -1), 7),
    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
]))
story.extend([
    table,
    Spacer(1, 8 * mm),
    Paragraph("Subtotal: INR 2,200.00", styles["BodyText"]),
    Paragraph("CGST @ 9%: INR 198.00", styles["BodyText"]),
    Paragraph("SGST @ 9%: INR 198.00", styles["BodyText"]),
    Paragraph("<b>Grand Total: INR 2,596.00</b>", styles["BodyText"]),
    Paragraph("Currency: INR", styles["BodyText"]),
])

doc.build(story)
print(f"Created: {OUTPUT}")
