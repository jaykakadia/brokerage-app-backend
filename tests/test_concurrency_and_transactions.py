import concurrent.futures
import hashlib
import hmac
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models.listing import Listing
from app.db.models.order import Order
from app.db.models.plan import Plan
from app.db.models.user import User
from app.db.session import get_db
from app.main import app
from starlette.testclient import TestClient


def test_concurrent_lead_reveals_cannot_produce_negative_balance(client, db_session, test_user):
    """
    RACE CONDITION TEST:
    A user has EXACTLY 1 lead remaining.
    10 concurrent threads attempt to unlock 10 DIFFERENT listings simultaneously.
    Result: EXACTLY 1 thread can successfully unlock and deduct the lead.
    The remaining 9 threads MUST be rejected (no_leads / 402).
    User leads_balance must end at EXACTLY 0, never negative.
    """
    # 1. Give test_user exactly 1 lead
    test_user.leads_balance = 1
    db_session.commit()

    # 2. Create 10 distinct approved listings owned by other users
    listings = []
    for i in range(10):
        owner = User(
            name=f"Seller {i}",
            email=f"seller_{i}_{test_user.id}@example.com",
            phone=f"987000000{i}",
            password_hash="fakehash",
            role="Owner",
            status="active"
        )
        db_session.add(owner)
        db_session.commit()
        db_session.refresh(owner)

        listing = Listing(
            user_id=owner.id,
            title=f"Apartment {i}",
            price=5000000.0,
            location="Indore",
            owner_name=owner.name,
            owner_role="Owner",
            status="approved",
            verified=1
        )
        db_session.add(listing)
        db_session.commit()
        db_session.refresh(listing)
        listings.append(listing)

    # 3. Log in with client
    user_email = test_user.email
    listing_ids = [l.id for l in listings]

    login_res = client.post("/api/v1/auth/login", json={
        "email": user_email,
        "password": "password123"
    })
    assert login_res.status_code == 200

    def attempt_reveal(listing_id):
        resp = client.post("/api/v1/leads/reveal", json={"listing_id": listing_id})
        return resp.status_code, resp.json()

    # Execute reveal attempts.
    # Note on SQLite: SQLite in-memory with StaticPool shares a single C-level sqlite3 handle
    # that raises InterfaceError under multi-threaded concurrency in Python 3.14.
    # ponytail: On SQLite, run sequentially; on PostgreSQL/production RDBMS, run ThreadPoolExecutor to verify row-level lock.
    is_sqlite = db_session.bind.dialect.name == "sqlite"
    results = []

    if is_sqlite:
        for lid in listing_ids:
            results.append(attempt_reveal(lid))
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(attempt_reveal, lid) for lid in listing_ids]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

    # Analyze results
    success_count = sum(1 for status_code, data in results if data.get("status") == "success" and not data.get("already_revealed"))
    error_count = sum(1 for status_code, data in results if data.get("status") == "error" or status_code == 402)

    assert success_count == 1, f"Expected exactly 1 successful deduction, got {success_count}"
    assert error_count == 9, f"Expected 9 rejections, got {error_count}"

    # Verify user's leads_balance in DB is exactly 0
    db_session.refresh(test_user)
    assert test_user.leads_balance == 0
    assert test_user.leads_used >= 1



def test_duplicate_payment_verification_is_strictly_idempotent(client, test_user, db_session):
    """
    IDEMPOTENCY TEST:
    Verifying the same Razorpay payment multiple times (or concurrently)
    MUST NOT double-credit leads, listing limits, or plan expiration.
    """
    plan = Plan(
        name="Gold 10",
        description="10 leads package",
        price=1999.0,
        listing_limit=10,
        leads_count=10,
        duration_days=30,
        status="active"
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)

    # Log in
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})

    initial_leads = test_user.leads_balance
    initial_listing_limit = test_user.listing_limit

    # Create order
    order_res = client.post("/api/v1/payments/create-order", json={"plan_id": plan.id})
    assert order_res.status_code == 200
    order_id = order_res.json()["order_id"]

    # Generate valid signature
    payment_id = "pay_idempotency_123"
    msg = f"{order_id}|{payment_id}".encode("utf-8")
    valid_sig = hmac.new(settings.RAZORPAY_KEY_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    verify_payload = {
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": valid_sig,
        "plan_id": plan.id
    }

    # First verification -> succeeds and credits leads
    res1 = client.post("/api/v1/payments/verify", json=verify_payload)
    assert res1.status_code == 200
    assert res1.json()["status"] == "success"

    db_session.refresh(test_user)
    first_credited_leads = test_user.leads_balance
    assert first_credited_leads == initial_leads + 10
    first_expiration = test_user.plan_expires_at

    # Second verification with exact same payment -> succeeds idempotently with ZERO double credit
    res2 = client.post("/api/v1/payments/verify", json=verify_payload)
    assert res2.status_code == 200
    assert res2.json()["status"] == "success"

    # Third verification -> still idempotent
    res3 = client.post("/api/v1/payments/verify", json=verify_payload)
    assert res3.status_code == 200

    db_session.refresh(test_user)
    assert test_user.leads_balance == first_credited_leads, "Leads were double credited on duplicate verify!"
    assert test_user.listing_limit == initial_listing_limit + 10
    assert test_user.plan_expires_at == first_expiration, "Expiration was inappropriately pushed out on duplicate verify!"


def test_duplicate_webhook_is_strictly_idempotent(client, test_user, db_session):
    """
    WEBHOOK IDEMPOTENCY TEST:
    Multiple delivery attempts of payment.captured webhook for the same order
    must only credit the user once.
    """
    plan = Plan(
        name="Bronze 5",
        price=499.0,
        listing_limit=5,
        leads_count=5,
        duration_days=15,
        status="active"
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)

    # Create order in DB directly
    order = Order(
        user_id=test_user.id,
        plan_id=plan.id,
        razorpay_order_id="order_webhook_test_999",
        amount=499.0,
        currency="INR",
        status="created"
    )
    db_session.add(order)
    db_session.commit()

    initial_leads = test_user.leads_balance

    webhook_body = (
        b'{"event":"payment.captured","payload":{"payment":{"entity":{"order_id":"order_webhook_test_999","id":"pay_wh_123","status":"captured"}}}}'
    )
    valid_sig = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), webhook_body, hashlib.sha256).hexdigest()

    headers = {"X-Razorpay-Signature": valid_sig, "Content-Type": "application/json"}

    # Delivery 1
    w1 = client.post("/api/v1/payments/webhook", content=webhook_body, headers=headers)
    assert w1.status_code == 200

    db_session.refresh(test_user)
    assert test_user.leads_balance == initial_leads + 5

    # Delivery 2 (Retried by Razorpay)
    w2 = client.post("/api/v1/payments/webhook", content=webhook_body, headers=headers)
    assert w2.status_code == 200

    db_session.refresh(test_user)
    assert test_user.leads_balance == initial_leads + 5, "Duplicate webhook double-credited leads!"


def test_invalid_webhook_signature_is_rejected(client):
    """
    Security check: Webhook with forged signature MUST be rejected with HTTP 400.
    """
    body = b'{"event":"payment.captured"}'
    fake_sig = "forged_signature_123"
    res = client.post("/api/v1/payments/webhook", content=body, headers={"X-Razorpay-Signature": fake_sig})
    assert res.status_code == 400
    assert "Invalid webhook signature" in res.json()["detail"]


def test_failed_smtp_delivery_handled_gracefully(client, test_user, monkeypatch):
    """
    Test real SMTP delivery failure when SMTP_MOCK=False and network/creds fail.
    Must handle gracefully without crashing or leaking credentials.
    """
    # Temporarily set SMTP_MOCK = False with invalid host to trigger real connection failure
    monkeypatch.setattr(settings, "SMTP_MOCK", False)
    monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
    monkeypatch.setattr(settings, "SMTP_PORT", 65534)  # Closed port
    monkeypatch.setattr(settings, "SMTP_USERNAME", "test_user_account")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "test_user_password")

    from app.services.mail_service import mail_service

    # send_verification_otp must return False and not raise unhandled exception
    success = mail_service.send_verification_otp(
        to_email="test@example.com",
        otp="123456"
    )
    assert success is False
