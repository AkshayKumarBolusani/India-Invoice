import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from invoice_ai.ingestion import extract_document

INPUT = ROOT / "data" / "raw" / "sample_invoice.pdf"

result = extract_document(str(INPUT))

print(f"Method: {result['method']}")
print(f"Extracted characters: {result['text_length']}")
print("\n--- Extracted Markdown ---\n")
print(result["markdown"])