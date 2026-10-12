#!/usr/bin/env python3
'''Compare JSONL predictions to labelled JSONL ground truth with normalized per-field exact match.'''
import argparse, json, re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

FIELDS = ["vendor_name", "vendor_tax_id", "invoice_number", "invoice_date", "due_date",
          "currency", "subtotal", "tax", "total"]


def norm(field, value):
    if value is None:
        return ""
    value = str(value).strip().casefold()
    if field in {"subtotal", "tax", "total"}:
        try:
            return str(Decimal(value.replace(",", "").replace("$", "").replace("₹", "")).quantize(Decimal("0.01")))
        except InvalidOperation:
            return value
    if field in {"invoice_number", "vendor_tax_id"}:
        return re.sub(r"[^a-z0-9]", "", value)
    if field in {"invoice_date", "due_date"}:
        return value[:10]
    if field == "vendor_name":
        return re.sub(r"\s+", " ", value)
    return value


def load(path):
    rows = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                rows[str(row["id"])] = row
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--predictions", required=True)
    p.add_argument("--ground-truth", required=True)
    p.add_argument("--output", default="evaluation_report.json")
    args = p.parse_args()
    preds, truth = load(args.predictions), load(args.ground_truth)
    ids = sorted(set(preds) & set(truth))
    if not ids:
        raise SystemExit("No matching IDs between predictions and ground truth.")
    report = {"documents_compared": len(ids), "fields": {}, "document_exact_match_rate": 0, "missing_prediction_ids": sorted(set(truth)-set(preds))}
    exact_docs = 0
    for doc_id in ids:
        all_ok = True
        for field in FIELDS:
            expected = norm(field, truth[doc_id].get(field))
            predicted = norm(field, preds[doc_id].get(field))
            stat = report["fields"].setdefault(field, {"correct": 0, "total": 0, "errors": []})
            stat["total"] += 1
            if expected == predicted:
                stat["correct"] += 1
            else:
                all_ok = False
                if len(stat["errors"]) < 25:
                    stat["errors"].append({"id": doc_id, "expected": truth[doc_id].get(field), "predicted": preds[doc_id].get(field)})
        exact_docs += int(all_ok)
    for field, stat in report["fields"].items():
        stat["accuracy"] = round(stat["correct"] / stat["total"], 4) if stat["total"] else None
    report["document_exact_match_rate"] = round(exact_docs / len(ids), 4)
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nSaved report to {args.output}")


if __name__ == "__main__":
    main()
