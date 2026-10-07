import base64
import hmac
import hashlib
import json
import time
import httpx
import pytest
from app.db.models.order import Order
from app.services.cashfree_service import normalize_indian_phone
from app.db.models.plan import Plan
from app.core.config import settings
from app.services.cashfree_service import cashfree_service

WEBHOOK_SECRET = "cf_test_secret"


@pytest.fixture
def active_plan(db_session):
    plan = Plan(
        name="Silver Pro",
        description="10 leads and 10 listings",
        price=1499.0,
        listing_limit=10,
        leads_count=10,
        duration_days=90,
        status="active"
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    return plan


def _webhook_headers(body: bytes, timestamp: str = None) -> dict:
    timestamp = timestamp or str(int(time.time() * 1000))
    sig = base64.b64encode(
        hmac.new(WEBHOOK_SECRET.encode("utf-8"), timestamp.encode("utf-8") + body, hashlib.sha256).digest()
    ).decode("utf-8")
    return {"x-webhook-signature": sig, "x-webhook-timestamp": timestamp, "Content-Type": "application/json"}


def test_payment_and_cashfree_flow(client, test_user, active_plan, admin_user, monkeypatch):
    monkeypatch.setattr(settings, "CASHFREE_SECRET_KEY", WEBHOOK_SECRET)
    # 1. Log in as test user
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})

    # Initial user stats
    initial_leads = test_user.leads_balance
    initial_limits = test_user.listing_limit

    # 2. Create order with invalid plan -> 404
    inv_order = client.post("/api/v1/payments/create-order", json={"plan_id": 99999})
    assert inv_order.status_code == 404

    # 3. Create valid order
    order_res = client.post("/api/v1/payments/create-order", json={"plan_id": active_plan.id})
    assert order_res.status_code == 200
    order_data = order_res.json()
    assert order_data["status"] == "success"
    assert order_data["amount"] == 1499.0
    assert order_data["currency"] == "INR"
    assert order_data["environment"] == "mock"
    assert order_data["payment_session_id"]
    order_id = order_data["order_id"]
    assert order_id.startswith(f"tc_{test_user.id}_")

    # 4. Unknown order -> 404; unpaid order (Cashfree reports no successful payment) -> 400
    assert client.post("/api/v1/payments/verify", json={"order_id": "tc_missing"}).status_code == 404
    with monkeypatch.context() as m:
        m.setattr(cashfree_service, "get_successful_payment", lambda **kw: None)
        unpaid = client.post("/api/v1/payments/verify", json={"order_id": order_id})
    assert unpaid.status_code == 400
    assert "payment not completed" in unpaid.json()["detail"]

    # 5. Paid order -> 200 OK and credited
    ok_verify = client.post("/api/v1/payments/verify", json={"order_id": order_id})
    assert ok_verify.status_code == 200
    verify_data = ok_verify.json()
    assert verify_data["status"] == "success"
    assert verify_data["plan"]["leads_balance"] == initial_leads + active_plan.leads_count
    assert verify_data["plan"]["listing_limit"] == initial_limits + active_plan.listing_limit

    # 6. Idempotency test: Re-submitting the same verification MUST NOT double-credit!
    dup_verify = client.post("/api/v1/payments/verify", json={"order_id": order_id})
    assert dup_verify.status_code == 200
    assert dup_verify.json()["plan"]["leads_balance"] == initial_leads + active_plan.leads_count

    # 7. Webhook test: Create another order and confirm it via webhook
    order_id2 = client.post("/api/v1/payments/create-order", json={"plan_id": active_plan.id}).json()["order_id"]
    webhook_payload = json.dumps({
        "type": "PAYMENT_SUCCESS_WEBHOOK",
        "data": {
            "order": {"order_id": order_id2, "order_amount": 1499.0},
            "payment": {"cf_payment_id": 5114910123, "payment_status": "SUCCESS", "payment_amount": 1499.0}
        }
    }).encode("utf-8")
    wh_res = client.post("/api/v1/payments/webhook", content=webhook_payload, headers=_webhook_headers(webhook_payload))
    assert wh_res.status_code == 200
    assert wh_res.json()["status"] == "ok"
    leads = client.get("/api/v1/leads/status").json()["leads_balance"]
    assert leads == initial_leads + 2 * active_plan.leads_count

    # 8. Admin Settings: Cashfree credentials test
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    settings_res = client.get("/api/v1/payments/admin/settings")
    assert settings_res.status_code == 200
    data = settings_res.json()["data"]
    assert "app_id" in data and "has_secret" in data and "environment" in data
    # Secret must never be exposed!
    assert "secret_key" not in data

    save_res = client.post("/api/v1/payments/admin/settings", json={
        "app_id": "TEST_new_app_123",
        "secret_key": "new_secret_456",
        "environment": "production"
    })
    assert save_res.status_code == 200
    assert save_res.json()["data"] == {"app_id": "TEST_new_app_123", "has_secret": True, "environment": "production"}

    bad_env = client.post("/api/v1/payments/admin/settings", json={"environment": "live"})
    assert bad_env.status_code == 400


def test_live_mode_without_credentials_refuses_orders(client, test_user, active_plan, monkeypatch):
    monkeypatch.setattr(settings, "CASHFREE_MOCK", False)
    monkeypatch.setattr(settings, "CASHFREE_APP_ID", "")
    monkeypatch.setattr(settings, "CASHFREE_SECRET_KEY", "")
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    res = client.post("/api/v1/payments/create-order", json={"plan_id": active_plan.id})
    assert res.status_code == 503


def test_featured_plan_features_one_listing(client, db_session, test_user, admin_user):
    from datetime import datetime, timedelta, timezone
    from app.db.models.listing import Listing

    featured_plan = Plan(name="Featured 7 Days", plan_type="featured", price=299.0,
                         listing_limit=0, leads_count=0, duration_days=7, status="active")
    leads_plan = Plan(name="Leads Basic", price=499.0, listing_limit=5, leads_count=5, duration_days=30, status="active")
    mine = Listing(user_id=test_user.id, title="My Plot", location="Palwal", owner_name="John", status="approved")
    pending = Listing(user_id=test_user.id, title="Pending Plot", location="Palwal", owner_name="John", status="pending")
    others = Listing(user_id=admin_user.id, title="Admin Plot", location="Palwal", owner_name="Admin", status="approved")
    db_session.add_all([featured_plan, leads_plan, mine, pending, others])
    db_session.commit()

    # Plans are listed by type; the default stays "leads" for existing callers
    names = [p["name"] for p in client.get("/api/v1/plans").json()["data"]]
    assert names == ["Leads Basic"]
    featured_names = [p["name"] for p in client.get("/api/v1/plans", params={"type": "featured"}).json()["data"]]
    assert featured_names == ["Featured 7 Days"]

    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    initial_leads = test_user.leads_balance

    # A featured plan needs one of the user's own approved listings
    for bad in ({}, {"listing_id": others.id}, {"listing_id": pending.id}):
        res = client.post("/api/v1/payments/create-order", json={"plan_id": featured_plan.id, **bad})
        assert res.status_code == 400

    order_id = client.post("/api/v1/payments/create-order",
                           json={"plan_id": featured_plan.id, "listing_id": mine.id}).json()["order_id"]
    verify = client.post("/api/v1/payments/verify", json={"order_id": order_id})
    assert verify.status_code == 200
    assert verify.json()["plan"]["listing_id"] == mine.id

    listing = client.get(f"/api/v1/listings/{mine.id}").json()["data"]
    assert listing["is_featured"] is True
    featured_until = datetime.fromisoformat(listing["featured_until"])
    if featured_until.tzinfo is None:
        featured_until = featured_until.replace(tzinfo=timezone.utc)
    assert timedelta(days=6) < featured_until - datetime.now(timezone.utc) <= timedelta(days=7)

    # Featuring does not touch the user's leads plan
    profile = client.get("/api/v1/users/profile").json()["data"]
    assert profile["leads_balance"] == initial_leads
    assert profile["plan_id"] is None

    # Once the period ends the listing is no longer featured
    db_session.query(Listing).filter(Listing.id == mine.id).update(
        {Listing.featured_until: datetime.now(timezone.utc) - timedelta(minutes=1)})
    db_session.commit()
    expired = client.get(f"/api/v1/listings/{mine.id}").json()["data"]
    assert expired["is_featured"] is False
    assert expired["featured_until"] is None


def _login(client, user, password="password123"):
    client.post("/api/v1/auth/login", json={"email": user.email, "password": password})


def _success_webhook(order_id: str, amount: float = 1499.0, currency: str = "INR") -> bytes:
    return json.dumps({
        "type": "PAYMENT_SUCCESS_WEBHOOK",
        "data": {
            "order": {"order_id": order_id, "order_amount": amount},
            "payment": {"cf_payment_id": 777, "payment_status": "SUCCESS",
                        "payment_amount": amount, "payment_currency": currency},
        },
    }).encode("utf-8")


def _live_mode(monkeypatch, payment=None):
    monkeypatch.setattr(settings, "CASHFREE_MOCK", False)
    monkeypatch.setattr(settings, "CASHFREE_APP_ID", "app")
    monkeypatch.setattr(settings, "CASHFREE_SECRET_KEY", "secret")
    monkeypatch.setattr(cashfree_service, "create_order",
                        lambda **kw: {"order_id": kw["order_id"], "payment_session_id": "s"})
    monkeypatch.setattr(cashfree_service, "get_successful_payment", lambda **kw: dict(payment) if payment else None)


def test_idempotency_key_reuse(client, db_session, test_user, admin_user, active_plan):
    other_plan = Plan(name="Gold", price=2999.0, listing_limit=20, leads_count=20, duration_days=90, status="active")
    db_session.add(other_plan)
    db_session.commit()
    _login(client, test_user)

    first = client.post("/api/v1/payments/create-order", json={"plan_id": active_plan.id, "idempotency_key": "k1"})
    again = client.post("/api/v1/payments/create-order", json={"plan_id": active_plan.id, "idempotency_key": "k1"})
    assert first.status_code == again.status_code == 200
    assert first.json()["order_id"] == again.json()["order_id"]

    # Same key for a different plan -> conflict, not a 500
    assert client.post("/api/v1/payments/create-order",
                       json={"plan_id": other_plan.id, "idempotency_key": "k1"}).status_code == 409

    # Once paid the key cannot start another checkout
    assert client.post("/api/v1/payments/verify", json={"order_id": first.json()["order_id"]}).status_code == 200
    assert client.post("/api/v1/payments/create-order",
                       json={"plan_id": active_plan.id, "idempotency_key": "k1"}).status_code == 409

    # Another user's key -> conflict
    _login(client, admin_user, "adminpass123")
    assert client.post("/api/v1/payments/create-order",
                       json={"plan_id": active_plan.id, "idempotency_key": "k1"}).status_code == 409
    assert db_session.query(Order).filter(Order.idempotency_key == "k1").count() == 1


@pytest.mark.parametrize("raw,expected", [
    ("9876543210", "9876543210"),
    ("+91 98765-43210", "9876543210"),
    ("098765 43210", "9876543210"),
    ("919876543210", "9876543210"),
    ("12345", None),
    ("5876543210", None),
    ("", None),
    (None, None),
])
def test_normalize_indian_phone(raw, expected):
    assert normalize_indian_phone(raw) == expected


def test_order_sends_normalized_phone_and_rejects_invalid(client, db_session, test_user, active_plan, monkeypatch):
    sent = {}

    def fake_create_order(**kw):
        sent.update(kw)
        return {"order_id": kw["order_id"], "payment_session_id": "session_x"}

    monkeypatch.setattr(cashfree_service, "create_order", fake_create_order)
    _login(client, test_user)

    test_user.phone = "+91 98765-43210"
    db_session.commit()
    assert client.post("/api/v1/payments/create-order", json={"plan_id": active_plan.id}).status_code == 200
    assert sent["customer"]["customer_phone"] == "9876543210"

    test_user.phone = "12345"
    db_session.commit()
    sent.clear()
    res = client.post("/api/v1/payments/create-order", json={"plan_id": active_plan.id})
    assert res.status_code == 400
    assert "mobile number" in res.json()["detail"]
    assert not sent, "Cashfree must not be called with an invalid phone"


def test_cashfree_errors_are_logged(client, test_user, active_plan, monkeypatch, caplog):
    def failing_create_order(**kw):
        request = httpx.Request("POST", "https://sandbox.cashfree.com/pg/orders")
        response = httpx.Response(400, request=request, text='{"message":"customer_phone is invalid"}')
        raise httpx.HTTPStatusError("bad request", request=request, response=response)

    monkeypatch.setattr(cashfree_service, "create_order", failing_create_order)
    _login(client, test_user)
    res = client.post("/api/v1/payments/create-order", json={"plan_id": active_plan.id})
    assert res.status_code == 502
    assert "customer_phone is invalid" in caplog.text


@pytest.mark.parametrize("payment", [
    {"cf_payment_id": 1, "payment_status": "SUCCESS"},  # amount missing
    {"cf_payment_id": 1, "payment_status": "SUCCESS", "payment_amount": 1.0},
    {"cf_payment_id": 1, "payment_status": "SUCCESS", "payment_amount": 1499.0, "payment_currency": "USD"},
])
def test_verify_fails_closed_on_amount_or_currency(client, test_user, active_plan, monkeypatch, payment):
    _live_mode(monkeypatch, payment)
    _login(client, test_user)
    initial_leads = test_user.leads_balance

    order_id = client.post("/api/v1/payments/create-order", json={"plan_id": active_plan.id}).json()["order_id"]
    res = client.post("/api/v1/payments/verify", json={"order_id": order_id})
    assert res.status_code == 400
    assert "amount mismatch" in res.json()["detail"]
    assert client.get("/api/v1/leads/status").json()["leads_balance"] == initial_leads


def test_verify_in_live_mode_credits_matching_payment(client, test_user, active_plan, monkeypatch):
    _live_mode(monkeypatch, {"cf_payment_id": 42, "payment_status": "SUCCESS",
                             "payment_amount": 1499.0, "payment_currency": "INR"})
    _login(client, test_user)
    initial_leads = test_user.leads_balance

    order_id = client.post("/api/v1/payments/create-order", json={"plan_id": active_plan.id}).json()["order_id"]
    res = client.post("/api/v1/payments/verify", json={"order_id": order_id})
    assert res.status_code == 200
    assert res.json()["plan"]["leads_balance"] == initial_leads + active_plan.leads_count


def test_webhook_rejects_stale_timestamp_and_mismatched_amount(client, test_user, active_plan, monkeypatch):
    monkeypatch.setattr(settings, "CASHFREE_SECRET_KEY", WEBHOOK_SECRET)
    _login(client, test_user)
    initial_leads = test_user.leads_balance
    order_id = client.post("/api/v1/payments/create-order", json={"plan_id": active_plan.id}).json()["order_id"]

    # Correctly signed but 10 minutes old -> replay, rejected
    body = _success_webhook(order_id)
    stale = str(int((time.time() - 600) * 1000))
    assert client.post("/api/v1/payments/webhook", content=body,
                       headers=_webhook_headers(body, stale)).status_code == 400

    # Signed and fresh but for the wrong amount -> acknowledged, not credited
    body = _success_webhook(order_id, amount=1.0)
    assert client.post("/api/v1/payments/webhook", content=body, headers=_webhook_headers(body)).status_code == 200
    assert client.get("/api/v1/leads/status").json()["leads_balance"] == initial_leads

    # Fresh, seconds-based timestamp and correct amount -> credited
    body = _success_webhook(order_id)
    res = client.post("/api/v1/payments/webhook", content=body,
                      headers=_webhook_headers(body, str(int(time.time()))))
    assert res.status_code == 200
    assert client.get("/api/v1/leads/status").json()["leads_balance"] == initial_leads + active_plan.leads_count


def test_failed_webhook_marks_order_failed_and_retry_still_credits(client, db_session, test_user, active_plan, monkeypatch):
    monkeypatch.setattr(settings, "CASHFREE_SECRET_KEY", WEBHOOK_SECRET)
    _login(client, test_user)
    initial_leads = test_user.leads_balance
    order_id = client.post("/api/v1/payments/create-order", json={"plan_id": active_plan.id}).json()["order_id"]

    failed = json.dumps({
        "type": "PAYMENT_FAILED_WEBHOOK",
        "data": {"order": {"order_id": order_id}, "payment": {"payment_status": "FAILED"}},
    }).encode("utf-8")
    assert client.post("/api/v1/payments/webhook", content=failed, headers=_webhook_headers(failed)).status_code == 200
    order = db_session.query(Order).filter(Order.cashfree_order_id == order_id).first()
    db_session.refresh(order)
    assert order.status == "failed"

    # The customer retries on the same order and succeeds
    body = _success_webhook(order_id)
    assert client.post("/api/v1/payments/webhook", content=body, headers=_webhook_headers(body)).status_code == 200
    db_session.refresh(order)
    assert order.status == "paid"
    assert client.get("/api/v1/leads/status").json()["leads_balance"] == initial_leads + active_plan.leads_count


def test_featured_order_for_deleted_listing_is_flagged_for_refund(client, db_session, test_user, caplog):
    from app.db.models.listing import Listing

    featured_plan = Plan(name="Featured 7 Days", plan_type="featured", price=299.0,
                         listing_limit=0, leads_count=0, duration_days=7, status="active")
    mine = Listing(user_id=test_user.id, title="My Plot", location="Palwal", owner_name="John", status="approved")
    db_session.add_all([featured_plan, mine])
    db_session.commit()
    _login(client, test_user)

    order_id = client.post("/api/v1/payments/create-order",
                           json={"plan_id": featured_plan.id, "listing_id": mine.id}).json()["order_id"]
    db_session.delete(mine)
    db_session.commit()

    assert client.post("/api/v1/payments/verify", json={"order_id": order_id}).status_code == 200
    order = db_session.query(Order).filter(Order.cashfree_order_id == order_id).first()
    db_session.refresh(order)
    assert order.status == "paid"
    assert "needs_refund" in order.notes
    assert "needs refund" in caplog.text


def test_notify_url_is_sent_only_when_configured(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

        def post(self, url, json, headers):
            captured["payload"] = json
            return httpx.Response(200, json={"order_id": json["order_id"], "payment_session_id": "s"},
                                  request=httpx.Request("POST", url))

    monkeypatch.setattr(settings, "CASHFREE_MOCK", False)
    monkeypatch.setattr(httpx, "Client", FakeClient)
    args = dict(order_id="tc_1", amount=10.0, customer={}, app_id="a", secret_key="s", environment="sandbox")

    monkeypatch.setattr(settings, "CASHFREE_NOTIFY_URL", "")
    cashfree_service.create_order(**args)
    assert "order_meta" not in captured["payload"]

    monkeypatch.setattr(settings, "CASHFREE_NOTIFY_URL", "https://api.example.com/api/v1/payments/webhook")
    cashfree_service.create_order(**args)
    assert captured["payload"]["order_meta"] == {"notify_url": "https://api.example.com/api/v1/payments/webhook"}
