# Release validation — India Invoice AI

This release contains the complete project tree from the supplied archive, with the evaluation and paper artifacts synchronized.

## Checks completed for this release

- Re-ran `scripts/evaluate_injection.py` with no command-line arguments from outside the repository. The script correctly resolved the repository from its own location and wrote `evaluation/injection_results.json` in this project.
- The injection study loaded 60 synthetic ground-truth invoices; all 60 clean records validated as `valid`.
- The six arithmetic/format/missing-field error classes retained their recorded outcomes: 60/60 intended signals for each class.
- Duplicated-allocation warning: 48/48 applicable records.
- Three controls: 0 false flags across 150 mutations (30 consistent invented splits, 60 thousands-separator mutations, 60 currency-symbol mutations).
- Explicit grand-total tolerance probes now execute in the script and are saved in JSON: +₹0.50 flagged 0/60; +₹2.00 triggered the intended grand-total mismatch on 60/60.
- The paper's tolerance description was corrected to say the +₹0.50 probe was *not flagged*, and the paper PDF was rebuilt from `paper/india_invoice_v2.tex`.
- Focused tests passed: `26 passed` across validation, schemas, tax review, and dataset audit tests.
- ZIP integrity and key-artifact checksum checks are recorded in the release handoff.

## Test environment limitation

The complete test suite could not be collected in this packaging environment because `docling` is not installed here. Collection fails in `tests/test_api.py`, `tests/test_comparison.py`, `tests/test_ingestion.py`, and `tests/test_workflow.py` on `ModuleNotFoundError: docling`. This is an environment/dependency limitation, not a passing full-suite result. Install `requirements.txt` in the intended Python environment and rerun the complete suite before making a final external submission.

## Scope note

All injection and tolerance figures are synthetic-fixture results. They are not real-world invoice accuracy estimates, and the paper correctly states that real-invoice evaluation has not yet been run.
