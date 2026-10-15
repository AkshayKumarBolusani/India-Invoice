# Evaluation

Metrics in this repository are evidence-classified. Synthetic fixtures, public parser outputs, and authorized real-world labels are not interchangeable.

## Reproduce

```bash
.venv/bin/pytest -q
.venv/bin/python scripts/audit_dataset.py data/datasets/public/msduck_invoice_dataset
.venv/bin/python scripts/audit_dataset.py --dataset-name finvix/invoice
.venv/bin/python scripts/benchmark_pipeline.py
.venv/bin/python scripts/generate_synthetic_benchmark.py --count 60 --seed 20261015
```

## Verified results

- Full Python suite: 55 tests passed at the latest image-support validation.
- Synthetic batch report: 56/56 fields across 3 fixtures; regression evidence only ([`evaluation/batch_report.json`](../evaluation/batch_report.json)).
- Synthetic baseline: 20/20 fields and exact document match on one fixture ([`evaluation/baseline_report.json`](../evaluation/baseline_report.json)).
- Saved public audit: 1,348 records, 1,343 parsed responses, 1,343 recognized item records, 1,326 arithmetic-failure records, 2,686 skipped checks, and 1,331 manual-review records ([`evaluation/dataset_audit_summary.json`](../evaluation/dataset_audit_summary.json)).
- `finvix/invoice`: 100 sampled training records, 100 parsed responses, 524 recognized items, and 100 manual-review records.
- INV-003 comparison regression: 34 fields compared, zero substantive differences, seven formatting-only differences ([`tests/test_comparison.py`](../tests/test_comparison.py)).
- Rules pipeline warm medians: 0.58s, 0.45s, and 0.49s for INV-001/002/003; overall warm median 0.49s from [`scripts/benchmark_pipeline.py`](../scripts/benchmark_pipeline.py).
- Generated synthetic benchmark: 60 documents, 660/660 normalized scalar fields, 180/180 line items, precision/recall/F1 of 1.0, 60/60 arithmetic-consistent documents, and median rules latency of approximately 0.00014s on TXT input ([`evaluation/synthetic_benchmark/report.json`](../evaluation/synthetic_benchmark/report.json)).

Line-item precision/recall, language-level accuracy, and authorized real-world accuracy are **not yet measured**. Public parser outputs are not treated as ground truth. Extractor agreement does not establish source correctness or GST compliance.

The generated benchmark varies three text layouts, two GST modes, and one to five items per invoice. It is constructed-label regression evidence, not evidence of real-world generalization.
