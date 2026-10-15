
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from invoice_ai.ingestion import extract_document
from invoice_ai.extraction import extract_invoice

PDF = ROOT / "data" / "raw" / "sample_invoice.pdf"
OUTPUT = ROOT / "data" / "processed" / "extracted_invoice.json"

document = extract_document(str(PDF))
invoice = extract_invoice(document["markdown"])

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(
    json.dumps(
        invoice.model_dump(mode="json"),
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

print(invoice.model_dump_json(indent=2))
print(f"\nSaved to: {OUTPUT}")
