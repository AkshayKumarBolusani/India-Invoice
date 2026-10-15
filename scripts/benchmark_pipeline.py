import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from invoice_ai.ingestion import extract_document, get_document_converter
from invoice_ai.extraction import extract_invoice
from invoice_ai.validation import validate_invoice

FILES = sorted((ROOT / "data" / "samples").glob("*.pdf"))
REPEATS = 3


def run_pipeline(path):
    start = time.perf_counter()
    document = extract_document(str(path))
    ingestion = time.perf_counter() - start

    start = time.perf_counter()
    invoice = extract_invoice(document["markdown"])
    extraction = time.perf_counter() - start

    start = time.perf_counter()
    validate_invoice(invoice)
    validation = time.perf_counter() - start

    return ingestion, extraction, validation


def main():
    if not FILES:
        raise SystemExit("No PDFs found in data/samples/")

    get_document_converter.cache_clear()
    warm_times = {path.name: [] for path in FILES}

    print("=== Initial pass (includes converter initialization) ===")
    for path in FILES:
        ingestion, extraction, validation = run_pipeline(path)
        print(
            f"{path.name}: ingestion={ingestion:.2f}s | "
            f"rules={extraction:.4f}s | validation={validation:.4f}s | "
            f"total={ingestion + extraction + validation:.2f}s"
        )

    print(f"\n=== Warm pass ({REPEATS} repetitions per PDF) ===")
    for path in FILES:
        for _ in range(REPEATS):
            warm_times[path.name].append(run_pipeline(path))

        totals = [
            sum(result) for result in warm_times[path.name]
        ]
        ingestions = [
            result[0] for result in warm_times[path.name]
        ]
        print(
            f"{path.name}: median total={statistics.median(totals):.2f}s | "
            f"median ingestion={statistics.median(ingestions):.2f}s | "
            f"best total={min(totals):.2f}s"
        )

    all_totals = [
        sum(result)
        for results in warm_times.values()
        for result in results
    ]
    print(
        f"\nOverall warm median: {statistics.median(all_totals):.2f}s"
    )


if __name__ == "__main__":
    main()
