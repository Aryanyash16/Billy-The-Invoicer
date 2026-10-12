# Public datasets and annotation format

Do not commit dataset files or private invoices to Git. Download datasets from official sources and comply with each dataset's license/terms.

## Suggested public datasets

- **SROIE**: scanned receipt images and labelled key information extraction. It is receipt-oriented, not a representative invoice benchmark. Use it to stress-test OCR/key-value extraction and report it separately.
- **CORD**: receipt understanding dataset with structured annotations. Also receipt-oriented; useful for OCR/layout challenges but not a substitute for invoice-specific validation.
- Add invoice-specific public samples where licensing permits, plus your own generated edge cases.

Find the official dataset repository/paper pages before downloading. Keep a `DATASET_CARD.md` per source documenting license, version, split, label mapping, exclusions and preprocessing.

## Canonical JSONL format

One JSON object per line, with stable `id` and fields matching the extracted invoice schema.

Ground truth:
```json
{"id":"sroie-test-0001","vendor_name":"Example Mart","vendor_tax_id":null,"invoice_number":"R-001","invoice_date":"2024-01-02","due_date":null,"currency":"MYR","subtotal":"10.00","tax":"0.60","total":"10.60"}
```

Predictions use the same shape. Missing values should be JSON `null`; do not omit documents that failed extraction. Keep public datasets and customer-pilot records in separate files/reports.

## Metrics to report

- Per-field exact-match accuracy with clearly described normalization.
- Document exact-match rate.
- Error categories: OCR failure, field not found, normalization, date ambiguity, currency/decimal parsing, layout/line-item mismatch, duplicate false positive, arithmetic mismatch.
- Threshold coverage and precision among eligible auto-approvals.
- Human review time and correction rate.
- Breakdown by source dataset and document quality.

SROIE/CORD are receipts datasets. Do not describe their scores as invoice-only accuracy. Build a separate invoice benchmark before making invoice-specific claims.
