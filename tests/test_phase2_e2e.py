from app.services.auth_service import auth_service
import hmac
import hashlib
import pytest
from app.db.models.plan import Plan
from app.db.models.listing import Listing
from app.core.config import settings


def test_complete_phase2_flow(client, test_user, admin_user, db_session):
    """
    Complete Phase 2 Buyer Engagement & Monetization Flow:
    1. Seller posts listing
    2. Buyer logs in (initial 0 leads)
    3. Buyer toggles listing to Wishlist & verifies listing is in wishlist
    4. Buyer attempts contact reveal -> blocked with 402 (0 leads)
    5. Buyer purchases Silver plan -> Razorpay order created & HMAC verified
    6. Leads and limits credited atomically
    7. Buyer reveals owner contact -> 1 lead deducted, owner phone/email unlocked
    8. Buyer views same listing contact again -> idempotent, no additional lead deducted
    9. Admin logs in -> updates Razorpay settings & creates a custom VIP plan
    """
    # 1. Setup seller and listing
    seller_res = client.post("/api/v1/auth/register", json={
        "name": "Seller Suresh",
        "email": "seller.suresh@tradecall.in",
        "phone": "9876543210",
        "password": "Password@123",
        "role": "Owner",
        "otp": auth_service.generate_and_store_otp("seller.suresh@tradecall.in", "register")
    })
    assert seller_res.status_code == 200

    listing = Listing(
        user_id=seller_res.json()["user"]["id"],
        title="Luxury 3BHK Apartment Sector 14",
        price=7500000.0,
        location="Sector 14, Gurugram, Haryana",
        owner_name="Seller Suresh",
        owner_role="Owner",
        status="approved",
        verified=1,
        form_data={"propType": "flat", "bhk": "3"}
    )
    db_session.add(listing)

    # Setup Plan
    plan = Plan(
        name="Silver Buyer Package",
        description="5 Owner Contacts and 5 Posts",
        price=999.0,
        listing_limit=5,
        leads_count=5,
        duration_days=60,
        status="active"
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(listing)
    db_session.refresh(plan)

    # 2. Buyer logs in (test_user has 0 leads initially)
    buyer_login = client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "password123"
    })
    assert buyer_login.status_code == 200
    assert test_user.leads_balance == 0

    # 3. Wishlist flow
    # Toggle wishlist -> added
    wl_add = client.post("/api/v1/wishlist/toggle", json={"listing_id": listing.id})
    assert wl_add.status_code == 200
    assert wl_add.json()["action"] == "added"
    assert wl_add.json()["wishlisted"] is True

    # Get wishlist ids
    wl_ids = client.get("/api/v1/wishlist?ids_only=true")
    assert wl_ids.status_code == 200
    assert listing.id in wl_ids.json()["data"]

    # Get full wishlist objects
    wl_full = client.get("/api/v1/wishlist")
    assert wl_full.status_code == 200
    assert any(item["id"] == listing.id for item in wl_full.json()["data"])

    # 4. Attempt contact reveal with 0 leads -> returns status: error, code: no_leads
    reveal_blocked = client.post("/api/v1/leads/reveal", json={"listing_id": listing.id})
    assert reveal_blocked.status_code == 200
    assert reveal_blocked.json()["status"] == "error"
    assert reveal_blocked.json()["code"] == "no_leads"

    # 5. Purchase Plan via Razorpay
    order_res = client.post("/api/v1/payments/create-order", json={"plan_id": plan.id})
    assert order_res.status_code == 200
    order_data = order_res.json()
    assert order_data["amount"] == 99900
    order_id = order_data["order_id"]

    # Compute valid signature
    payment_id = "pay_phase2_e2e_9876"
    msg = f"{order_id}|{payment_id}".encode("utf-8")
    valid_sig = hmac.new(settings.RAZORPAY_KEY_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    verify_res = client.post("/api/v1/payments/verify", json={
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": valid_sig,
        "plan_id": plan.id
    })
    assert verify_res.status_code == 200
    verify_data = verify_res.json()
    assert verify_data["status"] == "success"

    # Verify leads credited via leads status
    pre_st = client.get("/api/v1/leads/status")
    assert pre_st.status_code == 200
    assert pre_st.json()["leads_balance"] == 5
    assert pre_st.json()["plan_id"] == plan.id

    # 6. Unlocking Owner Contact (Lead Deduction)
    reveal_success = client.post("/api/v1/leads/reveal", json={"listing_id": listing.id})
    assert reveal_success.status_code == 200
    rev_data = reveal_success.json()
    assert rev_data["contact"]["mobile"] == "9876543210"
    assert rev_data["plan"]["leads_remaining"] == 4
    assert rev_data["already_revealed"] is False

    # 7. Duplicate reveal on same listing -> idempotent, no additional lead deduction
    reveal_again = client.post("/api/v1/leads/reveal", json={"listing_id": listing.id})
    assert reveal_again.status_code == 200
    rev_again_data = reveal_again.json()
    assert rev_again_data["contact"]["mobile"] == "9876543210"
    assert rev_again_data["plan"]["leads_remaining"] == 4  # Unchanged!
    assert rev_again_data["already_revealed"] is True

    # 8. Check Lead status endpoint
    lead_status = client.get("/api/v1/leads/status")
    assert lead_status.status_code == 200
    st_data = lead_status.json()
    assert st_data["leads_balance"] == 4
    assert st_data["leads_used"] == 1

    # 9. Admin operations
    # Login as admin
    admin_login = client.post("/api/v1/auth/login", json={
        "email": admin_user.email,
        "password": "adminpass123"
    })
    assert admin_login.status_code == 200

    # Save Razorpay settings dynamically
    save_rzp = client.post("/api/v1/payments/admin/settings", json={
        "key_id": "rzp_live_new_updated_key",
        "key_secret": "rzp_live_new_updated_secret",
        "test_mode": False
    })
    assert save_rzp.status_code == 200
    assert save_rzp.json()["data"]["key_id"] == "rzp_live_new_updated_key"
    assert save_rzp.json()["data"]["has_secret"] is True
    assert save_rzp.json()["data"]["test_mode"] is False

    # Create new VIP plan
    create_vip = client.post("/api/v1/plans", json={
        "name": "VIP Platinum Developer",
        "price": 9999.0,
        "listing_limit": 50,
        "leads_count": 100,
        "duration_days": 365,
        "description": "Enterprise package for big builders",
        "status": "active"
    })
    assert create_vip.status_code == 200
    assert create_vip.json()["data"]["name"] == "VIP Platinum Developer"
