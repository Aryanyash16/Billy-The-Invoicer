# 3–4 minute demo recording script

Record only after the flow works on your machine. Use public or synthetic documents unless you have explicit consent for customer material.

## 0:00–0:20 — The problem
"Invoice formats vary. The goal is not just extraction; it is to validate results, send uncertain cases to a person, and sync only approved records."

## 0:20–1:00 — Upload and extraction
- Upload one clean digital PDF.
- Upload one scan or low-quality sample.
- Show extracted fields and validation findings.
- Show what happens when the model is not configured or a field is missing.

## 1:00–1:45 — Human review
- Open review queue.
- Correct a wrong field.
- Show correction audit history.
- Try to approve an invoice with a validation error and show that the API blocks it.

## 1:45–2:30 — Metrics and evaluation
- Show the field-level evaluation JSON.
- Show threshold coverage vs. precision.
- Explain the dataset size and its limits; distinguish receipt datasets from invoice-specific samples.

## 2:30–3:15 — Accounting integration
- In your own sandbox, sync an approved invoice.
- Show the returned QuickBooks Bill ID.
- Retry the same request and demonstrate the local sync ledger prevents a second create.
- If sandbox setup is incomplete, show the explicit not-configured response; do not fake a successful sync.

## 3:15–3:45 — Engineering lessons
Discuss one failure, its root cause, the fix, and the regression test. Finish with measured results only.
