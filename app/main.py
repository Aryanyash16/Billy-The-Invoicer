import hashlib
import json
from datetime import datetime, timezone, timedelta
import secrets
from urllib.parse import urlencode
from decimal import Decimal
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db import Base, engine, get_db
from app.models import InvoiceRecord, ReviewRecord, SyncRecord, QuickBooksCredential
from app.schemas import InvoiceData, ReviewPatch, ReviewDecision
from app.config import settings
from app.services.parser import extract_text
from app.services.extractor import extract_invoice, heuristic_score
from app.services.validation import validate_invoice
from app.services.quickbooks import QuickBooksClient, QuickBooksNotConfigured
import httpx
from fastapi.middleware.cors import CORSMiddleware

Base.metadata.create_all(bind=engine)

app = FastAPI(title="InvoiceAI FDE Pipeline", version="0.1.0")

_quickbooks_oauth_states: dict[str, datetime] = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def json_safe(obj):
    return json.loads(json.dumps(obj, default=str))


def record_to_dict(row: InvoiceRecord):
    return {
        "id": row.id, "filename": row.filename, "status": row.status,
        "extracted": row.extracted, "validation": row.validation,
        "heuristic_score": row.heuristic_score,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


def existing_vendor_invoice_pairs(db: Session, exclude_invoice_id: int | None = None) -> set[tuple[str, str]]:
    statement = select(InvoiceRecord)
    if exclude_invoice_id is not None:
        statement = statement.where(InvoiceRecord.id != exclude_invoice_id)
    rows = db.scalars(statement).all()
    return {
        (r.extracted.get("vendor_name", "").casefold().strip(),
         r.extracted.get("invoice_number", "").casefold().strip())
        for r in rows
        if r.extracted.get("vendor_name") and r.extracted.get("invoice_number")
    }


@app.get("/integrations/quickbooks/connect")
def quickbooks_connect():
    if not settings.quickbooks_client_id or not settings.quickbooks_redirect_uri:
        raise HTTPException(503, "Configure QUICKBOOKS_CLIENT_ID and QUICKBOOKS_REDIRECT_URI first.")
    state = secrets.token_urlsafe(32)
    _quickbooks_oauth_states[state] = datetime.now(timezone.utc) + timedelta(minutes=10)
    params = {
        "client_id": settings.quickbooks_client_id,
        "response_type": "code",
        "scope": "com.intuit.quickbooks.accounting",
        "redirect_uri": settings.quickbooks_redirect_uri,
        "state": state,
    }
    return RedirectResponse("https://appcenter.intuit.com/connect/oauth2?" + urlencode(params))


@app.get("/integrations/quickbooks/callback")
def quickbooks_callback(code: str, state: str, realmId: str, db: Session = Depends(get_db)):
    expires = _quickbooks_oauth_states.pop(state, None)
    if expires is None or expires < datetime.now(timezone.utc):
        raise HTTPException(400, "Invalid or expired OAuth state. Start again from /integrations/quickbooks/connect.")
    if not all([settings.quickbooks_client_id, settings.quickbooks_client_secret]):
        raise HTTPException(503, "Configure QuickBooks OAuth client credentials.")
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(
                "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
                data={"grant_type": "authorization_code", "code": code, "redirect_uri": settings.quickbooks_redirect_uri},
                auth=(settings.quickbooks_client_id, settings.quickbooks_client_secret),
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            token_data = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(502, "QuickBooks OAuth token exchange failed.") from exc
    credential = db.get(QuickBooksCredential, 1)
    expiry = datetime.now(timezone.utc) + timedelta(seconds=int(token_data.get("expires_in", 3600)))
    if credential is None:
        credential = QuickBooksCredential(id=1, realm_id=realmId, access_token=token_data["access_token"],
                                          refresh_token=token_data["refresh_token"], expires_at=expiry)
        db.add(credential)
    else:
        credential.realm_id = realmId
        credential.access_token = token_data["access_token"]
        credential.refresh_token = token_data["refresh_token"]
        credential.expires_at = expiry
    db.commit()
    return {"status": "connected", "realm_id": realmId,
            "message": "QuickBooks sandbox connected. Tokens are stored in the local database; encrypt token storage before production use."}


@app.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(413, "File exceeds 15 MiB limit")
    sha = hashlib.sha256(content).hexdigest()
    prior = db.scalar(select(InvoiceRecord).where(InvoiceRecord.sha256 == sha))
    if prior:
        return {"duplicate_upload": True, "invoice": record_to_dict(prior)}

    try:
        text = extract_text(file.filename or "document.pdf", content)
        extracted, score = extract_invoice(text)
    except Exception as exc:
        raise HTTPException(422, f"Could not process document: {exc}") from exc

    validation = validate_invoice(extracted, existing_vendor_invoice_pairs(db))
    # Auto-approval is conservative and requires all deterministic checks to pass.
    status = (
        "auto_approved"
        if settings.auto_approval_enabled
        and validation["valid"]
        and score >= settings.auto_approve_min_score
        else "needs_review"
    )
    row = InvoiceRecord(
        filename=(file.filename or "upload")[:255], sha256=sha,
        status=status, extracted=json_safe(extracted.model_dump(mode="json")),
        validation=validation, heuristic_score=score
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"duplicate_upload": False, "invoice": record_to_dict(row), "text_chars": len(text)}


@app.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    rows = db.scalars(select(InvoiceRecord).order_by(InvoiceRecord.id.desc()).limit(200)).all()
    return [record_to_dict(r) for r in rows]


@app.get("/documents/{invoice_id}")
def get_document(invoice_id: int, db: Session = Depends(get_db)):
    row = db.get(InvoiceRecord, invoice_id)
    if not row:
        raise HTTPException(404, "Invoice not found")
    return record_to_dict(row)


@app.get("/reviews/queue")
def review_queue(db: Session = Depends(get_db)):
    rows = db.scalars(select(InvoiceRecord).where(InvoiceRecord.status == "needs_review").order_by(InvoiceRecord.id)).all()
    return [record_to_dict(r) for r in rows]


@app.patch("/reviews/{invoice_id}")
def correct_invoice(
    invoice_id: int, payload: ReviewPatch, db: Session = Depends(get_db),
    reviewer: str = Header(default="local-reviewer", alias="X-Reviewer")
):
    row = db.get(InvoiceRecord, invoice_id)

    if not row:
        raise HTTPException(404, "Invoice not found")

    if row.status in {"approved", "synced"}:
        raise HTTPException(
            409,
            "Approved or synced invoices cannot be edited through this endpoint.",
        )

    before = dict(row.extracted)

    candidate = {**row.extracted, **payload.corrected_fields}
    try:
        data = InvoiceData.model_validate(candidate)
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc
    row.extracted = json_safe(data.model_dump(mode="json"))
    row.validation = validate_invoice(data, existing_vendor_invoice_pairs(db, exclude_invoice_id=row.id))
    row.heuristic_score = heuristic_score(data)
    row.status = "needs_review"
    db.add(ReviewRecord(invoice_id=invoice_id, reviewer=reviewer, action="corrected",
                        before=before, after=row.extracted, notes=payload.notes))
    db.commit()
    db.refresh(row)
    return record_to_dict(row)


@app.post("/reviews/{invoice_id}/approve")
def approve_invoice(
    invoice_id: int, payload: ReviewDecision, db: Session = Depends(get_db),
    reviewer: str = Header(default="local-reviewer", alias="X-Reviewer")
):
    row = db.get(InvoiceRecord, invoice_id)
    if not row:
        raise HTTPException(404, "Invoice not found")
    # Revalidate immediately before approval so edits cannot bypass duplicate checks.
    current = InvoiceData.model_validate(row.extracted)
    row.validation = validate_invoice(current, existing_vendor_invoice_pairs(db, exclude_invoice_id=row.id))
    if not row.validation.get("valid", False):
        db.commit()
        raise HTTPException(409, "Cannot approve while validation errors remain; correct the fields first.")
    if row.status == "rejected":
        raise HTTPException(409, "Rejected invoice cannot be approved without an explicit reopen workflow.")
    row.status = "approved"
    db.add(ReviewRecord(invoice_id=invoice_id, reviewer=reviewer, action="approved",
                        before=row.extracted, after=row.extracted, notes=payload.notes))
    db.commit()
    return record_to_dict(row)


@app.post("/reviews/{invoice_id}/reject")
def reject_invoice(
    invoice_id: int, payload: ReviewDecision, db: Session = Depends(get_db),
    reviewer: str = Header(default="local-reviewer", alias="X-Reviewer")
):
    row = db.get(InvoiceRecord, invoice_id)
    if not row:
        raise HTTPException(404, "Invoice not found")
    row.status = "rejected"
    db.add(ReviewRecord(invoice_id=invoice_id, reviewer=reviewer, action="rejected",
                        before=row.extracted, after=row.extracted, notes=payload.notes))
    db.commit()
    return record_to_dict(row)



@app.post("/integrations/quickbooks/sync/{invoice_id}")
def sync_quickbooks(invoice_id: int, db: Session = Depends(get_db)):
    row = db.get(InvoiceRecord, invoice_id)
    if not row:
        raise HTTPException(404, "Invoice not found")

    key = f"invoiceai-invoice-{row.id}"
    prior = db.scalar(
        select(SyncRecord).where(
            SyncRecord.invoice_id == row.id,
            SyncRecord.provider == "quickbooks",
        )
    )

    # Return a successful result before checking the invoice status.
    if prior and prior.status == "succeeded":
        return {
            "status": "already_synced",
            "external_id": prior.external_id,
        }

    if row.status != "approved":
        raise HTTPException(
            409,
            "Only explicitly approved invoices can be synchronized.",
        )

    if prior and prior.status == "pending":
        raise HTTPException(
            409,
            "A QuickBooks sync is already in progress for this invoice.",
        )

    sync_record = prior or SyncRecord(
        invoice_id=row.id,
        provider="quickbooks",
        idempotency_key=key,
    )
    sync_record.status = "pending"
    sync_record.attempts = (sync_record.attempts or 0) + 1
    db.add(sync_record)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            409,
            "A QuickBooks sync was concurrently started; "
            "inspect its sync record before retrying.",
        ) from exc

    try:
        client = QuickBooksClient(db)
        result = client.create_bill(row.extracted, key)

        sync_record.status = "succeeded"
        sync_record.external_id = result["external_id"]
        sync_record.last_error = None
        row.status = "synced"
        db.commit()

        return {
            "status": "succeeded",
            "external_id": sync_record.external_id,
        }

    except QuickBooksNotConfigured as exc:
        sync_record.status = "not_configured"
        sync_record.last_error = str(exc)
        db.commit()
        raise HTTPException(503, str(exc)) from exc

    except Exception as exc:
        sync_record.status = "failed"
        sync_record.last_error = str(exc)[:2000]
        db.commit()
        raise HTTPException(
            502,
            f"QuickBooks sync failed; inspect sync record before retry: {exc}",
        ) from exc


@app.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    rows = db.scalars(select(InvoiceRecord)).all()
    total = len(rows)
    return {
        "total_documents": total,
        "status_counts": {s: sum(1 for r in rows if r.status == s)
                          for s in ["needs_review", "auto_approved", "approved", "rejected", "synced"]},
        "auto_approval_rate": round(sum(r.status in {"auto_approved", "synced"} for r in rows) / total, 4) if total else None,
        "average_heuristic_score": round(sum(r.heuristic_score for r in rows) / total, 4) if total else None,
        "note": "These are workflow metrics, not extraction accuracy. Use the labelled evaluation scripts for accuracy."
    }
