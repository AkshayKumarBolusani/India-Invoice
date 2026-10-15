from pathlib import Path
from datasets import load_dataset

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data" / "datasets" / "public" / "msduck_invoice_dataset"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

dataset = load_dataset("Msduck/invoice_dataset")

print(dataset)
for split_name, split in dataset.items():
    print(f"{split_name}: {len(split)} rows")
    print("Columns:", split.column_names)

dataset.save_to_disk(str(OUTPUT))
print(f"Saved dataset to: {OUTPUT}")