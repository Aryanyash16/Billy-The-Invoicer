#!/usr/bin/env python3
'''Evaluate auto-approval thresholds from labelled records.

Input JSONL schema per row:
{"id":"x1","score":0.98,"valid":true,"prediction_correct":true}
prediction_correct should mean the critical fields are correct against labelled ground truth.
'''
import argparse, json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", default="threshold_report.json")
    p.add_argument("--thresholds", default="0.70,0.80,0.85,0.90,0.95,0.98,0.99")
    args = p.parse_args()
    rows = [json.loads(line) for line in open(args.input, encoding="utf-8") if line.strip()]
    thresholds = [float(x) for x in args.thresholds.split(",")]
    result = {"documents": len(rows), "thresholds": []}
    for t in thresholds:
        eligible = [r for r in rows if float(r.get("score", 0)) >= t and bool(r.get("valid", False))]
        correct = sum(bool(r.get("prediction_correct", False)) for r in eligible)
        result["thresholds"].append({
            "threshold": t,
            "auto_approval_coverage": round(len(eligible)/len(rows), 4) if rows else None,
            "eligible_count": len(eligible),
            "correct_among_eligible": correct,
            "precision_among_eligible": round(correct/len(eligible), 4) if eligible else None,
            "incorrect_auto_approvals": len(eligible)-correct,
        })
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
