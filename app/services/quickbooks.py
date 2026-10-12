from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    retry_if_exception,
)
from sqlalchemy.orm import Session
from app.config import settings
from app.models import QuickBooksCredential


class QuickBooksNotConfigured(RuntimeError):
    pass


def refresh_access_token(db: Session) -> QuickBooksCredential:
    """Refresh OAuth credentials and persist rotated tokens for subsequent requests."""
    credentials = db.get(QuickBooksCredential, 1)
    refresh_token = credentials.refresh_token if credentials else settings.quickbooks_refresh_token
    realm_id = credentials.realm_id if credentials else settings.quickbooks_realm_id
    if not all([settings.quickbooks_client_id, settings.quickbooks_client_secret, refresh_token, realm_id]):
        raise QuickBooksNotConfigured("Configure QuickBooks OAuth client credentials and connect the sandbox company.")
    with httpx.Client(timeout=20) as client:
        response = client.post(
            "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            auth=(settings.quickbooks_client_id, settings.quickbooks_client_secret),
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        body = response.json()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(body.get("expires_in", 3600)))
    if credentials is None:
        credentials = QuickBooksCredential(id=1, realm_id=realm_id, access_token=body["access_token"],
                                           refresh_token=body.get("refresh_token", refresh_token), expires_at=expires_at)
        db.add(credentials)
    else:
        credentials.access_token = body["access_token"]
        credentials.refresh_token = body.get("refresh_token", refresh_token)
        credentials.expires_at = expires_at
    db.commit()
    db.refresh(credentials)
    return credentials


class QuickBooksClient:
    """Minimal QuickBooks Online sandbox client. Never initiates payment."""
    def __init__(self, db: Session):
        self.db = db
        credentials = db.get(QuickBooksCredential, 1)
        self.realm_id = credentials.realm_id if credentials else settings.quickbooks_realm_id
        self.access_token = credentials.access_token if credentials else settings.quickbooks_access_token
        required = [settings.quickbooks_client_id, settings.quickbooks_client_secret, self.realm_id, self.access_token]
        if not all(required):
            raise QuickBooksNotConfigured("Connect a QuickBooks sandbox company and configure OAuth client credentials.")
        if settings.quickbooks_env != "sandbox":
            raise QuickBooksNotConfigured("This starter intentionally permits sandbox mode only.")
        self.base_url = "https://sandbox-quickbooks.api.intuit.com"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
           retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)), reraise=True)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        retry=(
            retry_if_exception_type(
                (httpx.TimeoutException, httpx.TransportError)
            )
            | retry_if_exception(
                lambda exc: (
                    isinstance(exc, httpx.HTTPStatusError)
                    and exc.response.status_code
                    in {429, 500, 502, 503, 504}
                )
            )
        ),
        reraise=True,
    )
    def _post_bill(self, url, headers, payload, request_id):
        response = httpx.post(
            url,
            params={"requestid": request_id[:50]},
            headers=headers,
            json=payload,
            timeout=20,
        )

        # Retry only transient server/rate-limit responses.
        # A 401 must return to create_bill() for token refresh.
        if response.status_code in {429, 500, 502, 503, 504}:
            response.raise_for_status()

        return response


    def create_bill(self, invoice: dict, idempotency_key: str) -> dict:
        vendor_ref = invoice.get("quickbooks_vendor_id")
        account_ref = invoice.get("quickbooks_expense_account_id")
        if not vendor_ref:
            raise ValueError("Map vendor_name to a real QuickBooks sandbox Vendor ID before sync.")
        if not account_ref:
            raise ValueError("Set a QuickBooks sandbox expense account ID before sync.")
        total = invoice.get("total")
        if total is None:
            raise ValueError("Invoice total is required before QuickBooks sync.")
        payload = {
            "VendorRef": {"value": str(vendor_ref)},
            "DocNumber": str(invoice.get("invoice_number") or "")[:21],
            "TxnDate": str(invoice.get("invoice_date")),
            "PrivateNote": "Created by InvoiceAI; reviewed and approved.",
            "Line": [{"Amount": float(total), "DetailType": "AccountBasedExpenseLineDetail",
                      "AccountBasedExpenseLineDetail": {"AccountRef": {"value": str(account_ref)}}}],
        }
        url = f"{self.base_url}/v3/company/{self.realm_id}/bill"
        headers = {"Authorization": f"Bearer {self.access_token}", "Accept": "application/json",
                   "Content-Type": "application/json"}
        response = self._post_bill(url, headers, payload, idempotency_key)
        if response.status_code == 401:
            credentials = refresh_access_token(self.db)
            self.access_token = credentials.access_token
            headers["Authorization"] = f"Bearer {self.access_token}"
            response = self._post_bill(url, headers, payload, idempotency_key)
        if response.status_code in (401, 403):
            raise RuntimeError("QuickBooks authorization failed after token refresh; reconnect the sandbox company.")
        response.raise_for_status()
        body = response.json()
        bill = body.get("Bill", {})
        if not bill.get("Id"):
            raise RuntimeError(f"QuickBooks response did not contain Bill.Id: {body}")
        return {"external_id": str(bill["Id"]), "response": body}
