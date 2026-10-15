# Demo Script

This repository does not contain a real customer screenshot or recorded video. Do not fabricate one. Capture only synthetic fixtures or redacted documents with permission.

## 60–90 seconds

1. Start FastAPI and the React dev server, then show the clearly labelled live/demo indicator.
2. Open Invoice workspace and upload `data/samples/INV-003.pdf` or a generated image fixture.
3. Show extracted identity fields, line items, invoice totals, validation warnings, and source evidence.
4. Open Review center and explain that missing GST evidence and unsupported line tax allocations remain human decisions.
5. Open Extractor comparison and show the INV-003 regression: 34 fields, 0 substantive differences, 7 formatting-only differences. State that agreement is not correctness.
6. Open Batch processing and show per-file statuses and isolated failures.
7. Open Evaluation lab and show sample sizes, arithmetic failures, skipped semantics, and provenance limitations.

## Recording checklist

- Run `.venv/bin/uvicorn api:app --port 8000`.
- Run `cd frontend && npm run dev`.
- Use only synthetic samples under `data/samples/`.
- Do not capture `.env`, private source Markdown, credentials, or real invoice identifiers.
- Store approved captures under `docs/screenshots/`; store videos under `docs/demo/`.
