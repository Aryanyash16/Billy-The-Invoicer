from datetime import date
from decimal import Decimal

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.models import InvoiceRecord
from app.schemas import InvoiceData
from app.services.quickbooks import QuickBooksClient
from app.main import app, existing_vendor_invoice_pairs
from app.services.validation import validate_invoice
from app.models import InvoiceRecord, SyncRecord
from unittest.mock import patch


def make_invoice(number: str, **extra):
    data = {
        "vendor_name": "Acme Ltd", "invoice_number": number,
        "invoice_date": date(2025, 1, 1), "currency": "USD",
        "subtotal": Decimal("100"), "tax": Decimal("10"), "total": Decimal("110"),
    }
    data.update(extra)
    return InvoiceData(**data).model_dump(mode="json")


def test_invoice_schema_preserves_quickbooks_mappings():
    data = InvoiceData.model_validate({
        **make_invoice("INV-100"),
        "quickbooks_vendor_id": "vendor-42",
        "quickbooks_expense_account_id": "expense-7",
    })
    saved = data.model_dump(mode="json")
    assert saved["quickbooks_vendor_id"] == "vendor-42"
    assert saved["quickbooks_expense_account_id"] == "expense-7"


def test_quickbooks_create_uses_stable_requestid(monkeypatch):
    client = object.__new__(QuickBooksClient)
    client.db = None
    client.realm_id = "realm-1"
    client.access_token = "test-token"
    client.base_url = "https://sandbox-quickbooks.api.intuit.com"
    seen = {}

    def fake_post(url, params, headers, json, timeout):
        seen.update(url=url, params=params, headers=headers, payload=json)
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"Bill": {"Id": "bill-99"}}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    result = client.create_bill({
        "quickbooks_vendor_id": "vendor-42",
        "quickbooks_expense_account_id": "expense-7",
        "invoice_number": "INV-100", "invoice_date": "2025-01-01", "total": "110.00",
    }, "invoiceai-invoice-100")
    assert result["external_id"] == "bill-99"
    assert seen["params"]["requestid"] == "invoiceai-invoice-100"
    assert seen["payload"]["VendorRef"]["value"] == "vendor-42"


def test_quickbooks_requires_explicit_vendor_mapping():
    client = object.__new__(QuickBooksClient)
    client.db = None
    client.realm_id = "realm-1"
    client.access_token = "test-token"
    client.base_url = "https://sandbox-quickbooks.api.intuit.com"
    try:
        client.create_bill({"total": "10", "quickbooks_expense_account_id": "expense-7"}, "stable-key")
    except ValueError as exc:
        assert "Vendor ID" in str(exc)
    else:
        raise AssertionError("Expected missing vendor mapping to fail safely")


def test_correction_cannot_remove_duplicate_detection():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestingSession() as db:
            db.add_all([
                InvoiceRecord(filename="a.pdf", sha256="a" * 64, status="needs_review",
                              extracted=make_invoice("INV-1"), validation={"valid": True, "errors": [], "warnings": []}, heuristic_score=1),
                InvoiceRecord(filename="b.pdf", sha256="b" * 64, status="needs_review",
                              extracted=make_invoice("INV-2"), validation={"valid": True, "errors": [], "warnings": []}, heuristic_score=1),
            ])
            db.commit()
        with TestClient(app) as client:
            response = client.patch("/reviews/2", json={"corrected_fields": {"invoice_number": "INV-1"}})
            assert response.status_code == 200
            assert any(e["code"] == "duplicate_vendor_invoice" for e in response.json()["validation"]["errors"])
            approved = client.post("/reviews/2/approve", json={"notes": "test"})
            assert approved.status_code == 409
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_quickbooks_401_refreshes_token_and_reuses_requestid(monkeypatch):
    import app.services.quickbooks as qb

    client = object.__new__(QuickBooksClient)
    client.db = None
    client.realm_id = "realm-1"
    client.access_token = "expired-token"
    client.base_url = "https://sandbox-quickbooks.api.intuit.com"

    calls = []

    def fake_post(url, params, headers, json, timeout):
        calls.append({"requestid": params["requestid"], "authorization": headers["Authorization"]})
        request = httpx.Request("POST", url)
        if len(calls) == 1:
            return httpx.Response(401, json={"error": "expired"}, request=request)
        return httpx.Response(200, json={"Bill": {"Id": "bill-100"}}, request=request)

    class RefreshedCredentials:
        access_token = "fresh-token"

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(qb, "refresh_access_token", lambda db: RefreshedCredentials())

    result = client.create_bill({
        "quickbooks_vendor_id": "vendor-42",
        "quickbooks_expense_account_id": "expense-7",
        "invoice_number": "INV-100",
        "invoice_date": "2025-01-01",
        "total": "110.00",
    }, "invoiceai-invoice-100")

    assert result["external_id"] == "bill-100"
    assert len(calls) == 2
    assert calls[0]["authorization"] == "Bearer expired-token"
    assert calls[1]["authorization"] == "Bearer fresh-token"
    assert calls[0]["requestid"] == calls[1]["requestid"] == "invoiceai-invoice-100"


def test_quickbooks_retries_transient_503_with_same_requestid(monkeypatch):
    client = object.__new__(QuickBooksClient)
    client.db = None
    client.realm_id = "realm-1"
    client.access_token = "test-token"
    client.base_url = "https://sandbox-quickbooks.api.intuit.com"

    calls = []

    def fake_post(url, params, headers, json, timeout):
        calls.append(params["requestid"])
        request = httpx.Request("POST", url)
        if len(calls) < 3:
            return httpx.Response(503, json={"error": "temporarily unavailable"}, request=request)
        return httpx.Response(200, json={"Bill": {"Id": "bill-101"}}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)

    result = client.create_bill({
        "quickbooks_vendor_id": "vendor-42",
        "quickbooks_expense_account_id": "expense-7",
        "invoice_number": "INV-101",
        "invoice_date": "2025-01-01",
        "total": "110.00",
    }, "invoiceai-invoice-101")

    assert result["external_id"] == "bill-101"
    assert calls == ["invoiceai-invoice-101"] * 3

def test_approval_rechecks_duplicate_when_saved_validation_is_stale():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(
        bind=engine, autoflush=False, autocommit=False
    )

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestingSession() as db:
            first = InvoiceRecord(
                filename="first.pdf",
                sha256="a" * 64,
                status="needs_review",
                extracted=make_invoice("INV-1"),
                validation={"valid": True, "errors": [], "warnings": []},
                heuristic_score=1,
            )
            second = InvoiceRecord(
                filename="second.pdf",
                sha256="b" * 64,
                status="needs_review",
                extracted=make_invoice("INV-2"),
                validation={"valid": True, "errors": [], "warnings": []},
                heuristic_score=1,
            )
            db.add_all([first, second])
            db.commit()
            second_id = second.id

            # Simulate a stale validation result after invoice data changed.
            second.extracted = make_invoice("INV-1")
            db.commit()

        with TestClient(app) as client:
            response = client.post(
                f"/reviews/{second_id}/approve",
                json={"notes": "Test stale validation"},
            )
            assert response.status_code == 409

            with TestingSession() as db:
                second = db.get(InvoiceRecord, second_id)
                assert second.status == "needs_review"
                assert any(
                    error["code"] == "duplicate_vendor_invoice"
                    for error in second.validation["errors"]
                )
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_duplicate_detection_normalizes_vendor_case_and_whitespace():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(
        bind=engine, autoflush=False, autocommit=False
    )

    try:
        with TestingSession() as db:
            db.add(
                InvoiceRecord(
                    filename="first.pdf",
                    sha256="c" * 64,
                    status="needs_review",
                    extracted=make_invoice("INV-1"),
                    validation={"valid": True, "errors": [], "warnings": []},
                    heuristic_score=1,
                )
            )
            db.commit()

            pairs = existing_vendor_invoice_pairs(db)

            candidate = InvoiceData.model_validate(
                make_invoice("INV-1", vendor_name="  ACME LTD  ")
            )
            validation = validate_invoice(candidate, pairs)

            assert any(
                error["code"] == "duplicate_vendor_invoice"
                for error in validation["errors"]
            )
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()

def test_approved_invoice_cannot_be_corrected():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(
        bind=engine, autoflush=False, autocommit=False
    )

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestingSession() as db:
            invoice = InvoiceRecord(
                filename="approved.pdf",
                sha256="d" * 64,
                status="approved",
                extracted=make_invoice("INV-APPROVED"),
                validation={"valid": True, "errors": [], "warnings": []},
                heuristic_score=1,
            )
            db.add(invoice)
            db.commit()
            invoice_id = invoice.id

        with TestClient(app) as client:
            response = client.patch(
                f"/reviews/{invoice_id}",
                json={"corrected_fields": {"invoice_number": "INV-EDITED"}},
            )
            assert response.status_code == 409

        with TestingSession() as db:
            invoice = db.get(InvoiceRecord, invoice_id)
            assert invoice.status == "approved"
            assert invoice.extracted["invoice_number"] == "INV-APPROVED"
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_synced_invoice_cannot_be_corrected():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(
        bind=engine, autoflush=False, autocommit=False
    )

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestingSession() as db:
            invoice = InvoiceRecord(
                filename="synced.pdf",
                sha256="e" * 64,
                status="synced",
                extracted=make_invoice("INV-SYNCED"),
                validation={"valid": True, "errors": [], "warnings": []},
                heuristic_score=1,
            )
            db.add(invoice)
            db.commit()
            invoice_id = invoice.id

        with TestClient(app) as client:
            response = client.patch(
                f"/reviews/{invoice_id}",
                json={"corrected_fields": {"invoice_number": "INV-EDITED"}},
            )
            assert response.status_code == 409

        with TestingSession() as db:
            invoice = db.get(InvoiceRecord, invoice_id)
            assert invoice.status == "synced"
            assert invoice.extracted["invoice_number"] == "INV-SYNCED"
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()

def test_unapproved_invoice_cannot_sync():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestingSession() as db:
            invoice = InvoiceRecord(
                filename="unapproved.pdf",
                sha256="f" * 64,
                status="needs_review",
                extracted=make_invoice("INV-UNAPPROVED"),
                validation={"valid": True, "errors": [], "warnings": []},
                heuristic_score=1,
            )
            db.add(invoice)
            db.commit()
            invoice_id = invoice.id

        with TestClient(app) as client:
            response = client.post(
                f"/integrations/quickbooks/sync/{invoice_id}"
            )
            assert response.status_code == 409

        with TestingSession() as db:
            assert db.query(SyncRecord).count() == 0
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_successful_sync_is_recorded_and_repeat_does_not_call_quickbooks():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestingSession() as db:
            invoice = InvoiceRecord(
                filename="approved.pdf",
                sha256="g" * 64,
                status="approved",
                extracted=make_invoice("INV-APPROVED"),
                validation={"valid": True, "errors": [], "warnings": []},
                heuristic_score=1,
            )
            db.add(invoice)
            db.commit()
            invoice_id = invoice.id

        with patch("app.main.QuickBooksClient") as mock_client:
            mock_client.return_value.create_bill.return_value = {
                "external_id": "bill-test-123"
            }

            with TestClient(app) as client:
                first = client.post(
                    f"/integrations/quickbooks/sync/{invoice_id}"
                )
                assert first.status_code == 200
                assert first.json() == {
                    "status": "succeeded",
                    "external_id": "bill-test-123",
                }

                second = client.post(
                    f"/integrations/quickbooks/sync/{invoice_id}"
                )
                assert second.status_code == 200
                assert second.json() == {
                    "status": "already_synced",
                    "external_id": "bill-test-123",
                }

            mock_client.return_value.create_bill.assert_called_once()

        with TestingSession() as db:
            invoice = db.get(InvoiceRecord, invoice_id)
            sync = db.query(SyncRecord).filter_by(
                invoice_id=invoice_id, provider="quickbooks"
            ).one()
            assert invoice.status == "synced"
            assert sync.status == "succeeded"
            assert sync.external_id == "bill-test-123"
            assert sync.attempts == 1
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_pending_sync_is_not_started_twice():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestingSession() as db:
            invoice = InvoiceRecord(
                filename="pending.pdf",
                sha256="h" * 64,
                status="approved",
                extracted=make_invoice("INV-PENDING"),
                validation={"valid": True, "errors": [], "warnings": []},
                heuristic_score=1,
            )
            db.add(invoice)
            db.commit()
            invoice_id = invoice.id

            db.add(
                SyncRecord(
                    invoice_id=invoice_id,
                    provider="quickbooks",
                    idempotency_key=f"invoiceai-invoice-{invoice_id}",
                    status="pending",
                    attempts=1,
                )
            )
            db.commit()

        with patch("app.main.QuickBooksClient") as mock_client:
            with TestClient(app) as client:
                response = client.post(
                    f"/integrations/quickbooks/sync/{invoice_id}"
                )
                assert response.status_code == 409

            mock_client.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()
