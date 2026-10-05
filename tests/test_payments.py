import base64
import hmac
import hashlib
import json
import pytest
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


def _webhook_headers(body: bytes, timestamp: str = "1700000000") -> dict:
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
