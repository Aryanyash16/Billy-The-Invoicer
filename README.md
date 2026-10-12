# InvoiceAI — FDE-style invoice processing with human review

A portfolio-grade starter for turning messy invoice documents into validated, reviewable business records.

## What is implemented in this repository

- FastAPI endpoints for invoice ingestion, review, approval, rejection and metrics.
- PDF text extraction using PyMuPDF, with optional Tesseract OCR fallback for scanned pages.
- Groq structured extraction behind a service boundary.
- Deterministic business-rule validation.
- PostgreSQL persistence with SQLAlchemy; SQLite works for local smoke tests.
- Human corrections and audit events.
- Confidence-threshold evaluation and field-level evaluation metrics.
- QuickBooks Online sandbox adapter with OAuth callback/token refresh, bounded retries, QuickBooks request IDs, and a local idempotency ledger.
- Dataset conversion/evaluation utilities for SROIE/CORD/custom labelled JSONL.
- Tests, pilot checklist, case-study template and demo script.

## Honest scope boundaries

This is a runnable MVP scaffold, not a claim that an external QuickBooks company has been connected or that a customer pilot has occurred. Credentials, OAuth consent, dataset downloads, labelled ground truth and a real user test require your actions. QuickBooks sandbox payload requirements can vary by entity and API version; verify against the current Intuit docs before using beyond a sandbox.

The score is a heuristic field-completeness score, not a calibrated probability. Automatic approval is disabled by default and should remain disabled until a representative labelled evaluation supports the policy. Do not automatically pay invoices. This project creates accounting records only after explicit approval.

## Quick start (Mac)

```bash
cd invoice-ai-fde
uv sync
cp .env.example .env
# Add GROQ_API_KEY to .env if using LLM extraction.
uv run uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`.

For PostgreSQL, set `DATABASE_URL` in `.env`; for a quick local test, the default is SQLite.

## Configuration

- `DATABASE_URL`: SQLAlchemy URL. Default: `sqlite:///./invoice_ai.db`
- `GROQ_API_KEY`: optional for the deterministic demo fallback; required for Groq extraction.
- `GROQ_MODEL`: defaults to `openai/gpt-oss-120b`
- `AUTO_APPROVAL_ENABLED`: default `false`; keep disabled until evaluation on representative labelled data
- `AUTO_APPROVE_MIN_SCORE`: default `0.99`; current score is completeness, not calibrated confidence
- `QUICKBOOKS_CLIENT_ID`, `QUICKBOOKS_CLIENT_SECRET`, `QUICKBOOKS_REALM_ID`
- `QUICKBOOKS_ACCESS_TOKEN`, `QUICKBOOKS_REFRESH_TOKEN`
- `QUICKBOOKS_ENV`: `sandbox` by default
- `QUICKBOOKS_REDIRECT_URI`: must match the Intuit app configuration; connect through `/integrations/quickbooks/connect`

## API walkthrough

1. `POST /documents` with multipart field `file` and optional `vendor_allowlist` JSON.
2. `GET /documents` to list extracted invoices.
3. `GET /documents/{id}` for details and validation findings.
4. `GET /reviews/queue` to list cases requiring review.
5. `PATCH /reviews/{id}` with corrected invoice fields.
6. `POST /reviews/{id}/approve` or `/reject`.
7. `POST /integrations/quickbooks/sync/{invoice_id}` after approval.
8. `GET /metrics` for basic workflow metrics.

QuickBooks OAuth tokens are stored in the local database for this development scaffold; encrypt token storage and add a secret manager before production. OAuth state storage is process-local and requires a shared store for multi-worker deployment.

The review endpoints use a development-only reviewer identity header (`X-Reviewer`). Add proper authentication, authorization and CSRF protections before public deployment.

## Evaluation: public datasets and custom documents

This repo does not bundle SROIE or CORD. Download them from their official project pages under their respective terms, then convert the labelled records to the canonical JSONL format described in `data/README.md`. Keep source documents and annotations in a local ignored directory; do not commit private customer invoices.

```bash
uv run python scripts/evaluate_jsonl.py --predictions data/eval/predictions.jsonl --ground-truth data/eval/ground_truth.jsonl
uv run python scripts/threshold_analysis.py --input data/eval/threshold_records.jsonl
```

The scripts are dataset-agnostic. They do not claim performance until populated with actual model predictions and trusted labels. Report results separately for public datasets and any consented customer pilot.

## Tests

```bash
uv run pytest
```

## Roadmap to a credible 9–10/10 FDE portfolio project

1. Run the pipeline on public labelled samples and report per-field results.
2. Inspect false positives/negatives; add regression tests for each important failure.
3. Plot precision/coverage trade-offs for auto-approval thresholds; use a conservative threshold and deterministic checks.
4. Connect your own Intuit sandbox and verify one create/read round-trip.
5. Ask one small business or freelancer for permission to test a small, redacted batch. Do not upload their documents to external APIs without explicit informed consent.
6. Record the demo described in `docs/DEMO_SCRIPT.md`, and replace all placeholders in `docs/CASE_STUDY_TEMPLATE.md` with measured results.

## Security checklist before real customer use

- Authentication, roles and tenant isolation.
- Encryption in transit and at rest; secret manager in production.
- File size/type limits, malware scanning, safe storage and retention/deletion policy.
- PII redaction and explicit consent for third-party LLM/OCR services.
- Audit log integrity and access controls.
- Idempotency and reconciliation for external writes.
- Never auto-pay; keep approval and sync permissions separate.
