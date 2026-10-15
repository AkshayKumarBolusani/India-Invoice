from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evaluation"
DATA = ROOT / "data" / "samples"
EVAL.mkdir(exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)

# Synthetic references for testing evaluation logic.
records = [
    {
        "document_id": "INV-001",
        "document_type": "gst_invoice",
        "vendor_name": "Sri Lakshmi Office Supplies",
        "vendor_gstin": "36ABCDE1234F1Z5",
        "invoice_number": "INV-2026-001",
        "invoice_date": "14/10/2026",
        "buyer_name": "Example Technologies Pvt Ltd",
        "subtotal": "2200.00",
        "total_cgst": "198.00",
        "total_sgst": "198.00",
        "total_igst": "0.00",
        "grand_total": "2596.00",
        "items": [
            {"description": "Office Paper", "quantity": "2",
             "unit_price": "500.00", "taxable_value": "1000.00"},
            {"description": "Printer Cartridge", "quantity": "1",
             "unit_price": "1200.00", "taxable_value": "1200.00"},
        ],
    },
    {
        "document_id": "INV-002",
        "document_type": "gst_invoice",
        "vendor_name": "Deccan Tech Supplies",
        "vendor_gstin": "29ABCDE1234F1Z5",
        "invoice_number": "ITS-204",
        "invoice_date": "15/10/2026",
        "buyer_name": "Example Systems Ltd",
        "subtotal": "1000.00",
        "total_cgst": "0.00",
        "total_sgst": "0.00",
        "total_igst": "180.00",
        "grand_total": "1180.00",
        "items": [
            {"description": "USB Keyboard", "quantity": "2",
             "unit_price": "500.00", "taxable_value": "1000.00"},
        ],
    },
    {
        "document_id": "INV-003",
        "document_type": "gst_invoice",
        "vendor_name": "Metro Business Mart",
        "vendor_gstin": "27ABCDE1234F1Z5",
        "invoice_number": "MBM-882",
        "invoice_date": "12/10/2026",
        "buyer_name": "Example Retail Pvt Ltd",
        "subtotal": "1500.00",
        "total_cgst": "45.00",
        "total_sgst": "45.00",
        "total_igst": "0.00",
        "grand_total": "1590.00",
        "items": [
            {"description": "Notebook", "quantity": "5",
             "unit_price": "100.00", "taxable_value": "500.00"},
            {"description": "Desk Organizer", "quantity": "2",
             "unit_price": "500.00", "taxable_value": "1000.00"},
        ],
    },
]

with (EVAL / "ground_truth.jsonl").open("w", encoding="utf-8") as f:
    for record in records:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

# These are references only, not actual generated PDFs.
(EVAL / "DATASET_README.txt").write_text(
    "Synthetic evaluation references.\n"
    "These records are not evidence of real-world extraction accuracy.\n"
    "INV-001 matches the existing sample invoice.\n"
    "INV-002 and INV-003 are evaluation cases for future fixtures.\n",
    encoding="utf-8",
)

print(f"Created {len(records)} synthetic references:")
print(EVAL / "ground_truth.jsonl")
print("Next: create matching prediction records before scoring all cases.")
