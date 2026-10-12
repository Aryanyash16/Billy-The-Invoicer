#!/usr/bin/env python3
'''Export review correction pairs from the app DB for offline error analysis / prompt iteration.

This does not silently train the model. Reviewers' corrected values should be checked and
used as labelled examples only after a data-quality and privacy review.
'''
import json
from app.db import SessionLocal
from app.models import ReviewRecord


def main():
    with SessionLocal() as db:
        rows = db.query(ReviewRecord).filter(ReviewRecord.action == "corrected").all()
        for row in rows:
            print(json.dumps({
                "invoice_id": row.invoice_id,
                "reviewer": row.reviewer,
                "before": row.before,
                "corrected": row.after,
                "notes": row.notes,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }, default=str))


if __name__ == "__main__":
    main()
