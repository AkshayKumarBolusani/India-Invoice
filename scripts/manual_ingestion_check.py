import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from invoice_ai.ingestion import extract_document

INPUT = ROOT / "data" / "raw" / "sample_invoice.txt"
OUTPUT = ROOT / "data" / "processed" / "sample_invoice.json"

result = extract_document(str(INPUT))

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(
    json.dumps(result, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print(f"Processed: {result['filename']}")
print(f"Extracted characters: {result['text_length']}")
print(f"Saved to: {OUTPUT}")
print("\nExtracted content:\n")
print(result["markdown"])