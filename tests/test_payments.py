import hmac
import hashlib
import json
import pytest
from app.db.models.plan import Plan
from app.core.config import settings


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


def test_payment_and_razorpay_flow(client, test_user, active_plan, admin_user):
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
    assert order_data["amount"] == 149900  # 1499 * 100 paise
    assert order_data["currency"] == "INR"
    order_id = order_data["order_id"]
    assert order_id.startswith("order_")

    # 4. Verify payment with fake/invalid signature -> 400
    fake_verify = client.post("/api/v1/payments/verify", json={
        "razorpay_order_id": order_id,
        "razorpay_payment_id": "pay_fake12345",
        "razorpay_signature": "invalidsignature123",
        "plan_id": active_plan.id
    })
    assert fake_verify.status_code == 400
    assert "Invalid Razorpay signature" in fake_verify.json()["detail"]

    # 5. Compute real valid signature using server secret
    payment_id = "pay_test98765"
    payload = f"{order_id}|{payment_id}".encode("utf-8")
    valid_signature = hmac.new(settings.RAZORPAY_KEY_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    # 6. Verify payment with valid signature -> 200 OK
    ok_verify = client.post("/api/v1/payments/verify", json={
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": valid_signature,
        "plan_id": active_plan.id
    })
    assert ok_verify.status_code == 200
    verify_data = ok_verify.json()
    assert verify_data["status"] == "success"
    assert verify_data["plan"]["leads_balance"] == initial_leads + active_plan.leads_count
    assert verify_data["plan"]["listing_limit"] == initial_limits + active_plan.listing_limit

    # 7. Idempotency test: Re-submitting the exact same payment verification MUST NOT double-credit!
    dup_verify = client.post("/api/v1/payments/verify", json={
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": valid_signature,
        "plan_id": active_plan.id
    })
    assert dup_verify.status_code == 200
    # Balance must remain unchanged!
    assert dup_verify.json()["plan"]["leads_balance"] == initial_leads + active_plan.leads_count

    # 8. Webhook test: Create another order and verify via webhook
    order_res2 = client.post("/api/v1/payments/create-order", json={"plan_id": active_plan.id})
    order_id2 = order_res2.json()["order_id"]
    webhook_payment_id = "pay_webhook_12345"

    webhook_payload = json.dumps({
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": webhook_payment_id,
                    "order_id": order_id2,
                    "amount": 149900,
                    "status": "captured"
                }
            }
        }
    }).encode("utf-8")

    # Compute valid webhook signature
    webhook_sig = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), webhook_payload, hashlib.sha256).hexdigest()

    # Post webhook
    wh_res = client.post(
        "/api/v1/payments/webhook",
        content=webhook_payload,
        headers={"X-Razorpay-Signature": webhook_sig, "Content-Type": "application/json"}
    )
    assert wh_res.status_code == 200
    assert wh_res.json()["status"] == "ok"

    # 9. Admin Settings: Razorpay credentials test
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    settings_res = client.get("/api/v1/payments/admin/settings")
    assert settings_res.status_code == 200
    assert "razorpay_key_id" in settings_res.json()["data"]
    # Secret must never be exposed!
    assert "razorpay_key_secret" not in settings_res.json()["data"]
    assert "has_secret" in settings_res.json()["data"]

    # Save new settings
    save_res = client.post("/api/v1/payments/admin/settings", json={
        "razorpay_key_id": "rzp_test_new_key_123",
        "razorpay_key_secret": "new_secret_456"
    })
    assert save_res.status_code == 200
    assert save_res.json()["status"] == "success"
