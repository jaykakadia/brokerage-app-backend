import pytest


def test_plans_flow_and_rbac(client, test_user, admin_user):
    # 1. Non-admin cannot create plans
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    forbidden_res = client.post("/api/v1/plans", json={
        "name": "Standard Plan",
        "price": 999.0,
        "listing_limit": 10,
        "leads_count": 10,
        "duration_days": 365,
        "status": "active"
    })
    assert forbidden_res.status_code == 403

    # 2. Admin creates active plan
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    create_res = client.post("/api/v1/plans", json={
        "name": "Gold Partner",
        "description": "Premium visibility with 25 leads",
        "price": 2499.0,
        "listing_limit": 15,
        "leads_count": 25,
        "duration_days": 180,
        "status": "active",
        "sort_order": 1
    })
    assert create_res.status_code == 200
    plan_id = create_res.json()["data"]["id"]
    assert create_res.json()["data"]["name"] == "Gold Partner"

    # Admin creates inactive plan
    inact_res = client.post("/api/v1/plans", json={
        "name": "Draft Plan",
        "price": 499.0,
        "listing_limit": 5,
        "status": "inactive"
    })
    assert inact_res.status_code == 200

    unlimited_res = client.post("/api/v1/plans", json={
        "name": "Unlimited Plan",
        "price": 0.0,
        "listing_limit": 0,
        "leads_count": 0,
        "duration_days": 365,
        "status": "active"
    })
    assert unlimited_res.status_code == 200
    assert unlimited_res.json()["data"]["listing_limit"] == 0

    # 3. Public visitor views plans: only active plans returned
    client.cookies.clear()
    pub_res = client.get("/api/v1/plans")
    assert pub_res.status_code == 200
    plans_by_name = {p["name"]: p for p in pub_res.json()["data"]}
    assert "Gold Partner" in plans_by_name
    assert "Draft Plan" not in plans_by_name
    assert plans_by_name["Unlimited Plan"]["listing_limit"] == 0

    # 4. Admin updates plan
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    upd_res = client.put(f"/api/v1/plans/{plan_id}", json={
        "price": 2199.0,
        "leads_count": 30
    })
    assert upd_res.status_code == 200
    assert float(upd_res.json()["data"]["price"]) == 2199.0
    assert upd_res.json()["data"]["leads_count"] == 30

    # 5. Admin deletes plan
    del_res = client.delete(f"/api/v1/plans/{plan_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    # Verify deleted
    get_res = client.get(f"/api/v1/plans/{plan_id}")
    assert get_res.status_code == 404


def test_trial_plan_lifecycle_and_re_signup(client, admin_user):
    from app.services.auth_service import auth_service

    # 1. Admin creates active trial plan
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    create_trial = client.post("/api/v1/plans", json={
        "name": "14-Day Free Starter Trial",
        "description": "3 free leads and 2 property posts",
        "price": 0.0,
        "listing_limit": 2,
        "leads_count": 3,
        "duration_days": 14,
        "status": "active",
        "is_trial": True,
        "sort_order": 0
    })
    assert create_trial.status_code == 200
    trial_plan_id = create_trial.json()["data"]["id"]
    assert create_trial.json()["data"]["is_trial"] is True
    client.cookies.clear()

    # 2. Register fresh user
    user_email = "trial.tester@example.com"
    otp = auth_service.generate_and_store_otp(user_email, "register")
    reg_res = client.post("/api/v1/auth/register", json={
        "name": "Trial Tester",
        "email": user_email,
        "phone": "9876500001",
        "password": "Password123!",
        "otp": otp
    })
    assert reg_res.status_code == 200

    # 3. User views plans: trial plan IS visible
    plans_res = client.get("/api/v1/plans")
    assert plans_res.status_code == 200
    plan_ids = [p["id"] for p in plans_res.json()["data"]]
    assert trial_plan_id in plan_ids

    # 4. Cashfree checkout blocked for trial plan
    cf_res = client.post("/api/v1/payments/create-order", json={"plan_id": trial_plan_id})
    assert cf_res.status_code == 400
    assert "claim it directly" in cf_res.json()["detail"].lower()

    # 5. Claim trial plan
    claim_res = client.post(f"/api/v1/plans/{trial_plan_id}/claim-trial")
    assert claim_res.status_code == 200
    claim_data = claim_res.json()["data"]
    assert claim_data["leads_balance"] == 3
    assert claim_data["listing_limit"] == 3  # default 1 + 2

    # 6. User views plans again: trial plan is HIDDEN
    plans_res_after = client.get("/api/v1/plans")
    assert plans_res_after.status_code == 200
    plan_ids_after = [p["id"] for p in plans_res_after.json()["data"]]
    assert trial_plan_id not in plan_ids_after

    # 7. User tries to claim again: 409 Conflict
    dup_claim = client.post(f"/api/v1/plans/{trial_plan_id}/claim-trial")
    assert dup_claim.status_code == 409

    # 8. User removes/deactivates their own account
    del_acc = client.delete("/api/v1/users/profile")
    assert del_acc.status_code == 200
    client.cookies.clear()

    # 9. Verify user cannot sign in with deactivated account
    login_fail = client.post("/api/v1/auth/login", json={"email": user_email, "password": "Password123!"})
    assert login_fail.status_code == 403

    # 10. User registers again with the same email
    re_otp = auth_service.generate_and_store_otp(user_email, "register")
    re_reg = client.post("/api/v1/auth/register", json={
        "name": "Trial Tester New",
        "email": user_email,
        "phone": "9876500001",
        "password": "NewPassword123!",
        "otp": re_otp
    })
    assert re_reg.status_code == 200

    # 11. Re-registered user views plans: trial plan is STILL NOT SHOWN
    new_plans_res = client.get("/api/v1/plans")
    assert new_plans_res.status_code == 200
    new_plan_ids = [p["id"] for p in new_plans_res.json()["data"]]
    assert trial_plan_id not in new_plan_ids

    # 12. Direct API call to claim trial plan still fails with 409 Conflict
    re_claim_blocked = client.post(f"/api/v1/plans/{trial_plan_id}/claim-trial")
    assert re_claim_blocked.status_code == 409


def test_paid_discounted_trial_plan_lifecycle(client, admin_user):
    from app.services.auth_service import auth_service

    # 1. Admin creates a paid discounted trial plan (e.g. Welcome 1 @ Rs 21)
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    create_paid_trial = client.post("/api/v1/plans", json={
        "name": "Welcome 1 Introductory",
        "description": "1 lead for Rs 21",
        "price": 21.0,
        "listing_limit": 1,
        "leads_count": 1,
        "duration_days": 30,
        "status": "active",
        "is_trial": True,
        "sort_order": 0
    })
    assert create_paid_trial.status_code == 200
    trial_id = create_paid_trial.json()["data"]["id"]
    client.cookies.clear()

    # 2. Register fresh buyer
    user_email = "paid.trial.user@example.com"
    otp = auth_service.generate_and_store_otp(user_email, "register")
    reg_res = client.post("/api/v1/auth/register", json={
        "name": "Paid Trial User",
        "email": user_email,
        "phone": "9876500099",
        "password": "Password123!",
        "otp": otp
    })
    assert reg_res.status_code == 200

    # 3. User views plans: Welcome 1 trial plan is visible
    plans_res = client.get("/api/v1/plans")
    assert plans_res.status_code == 200
    ids = [p["id"] for p in plans_res.json()["data"]]
    assert trial_id in ids

    # 4. User cannot bypass payment via /claim-trial because price > 0
    free_claim_res = client.post(f"/api/v1/plans/{trial_id}/claim-trial")
    assert free_claim_res.status_code == 400
    assert "requires payment" in free_claim_res.json()["detail"].lower()

    # 5. User pays Rs 21 through Cashfree checkout
    order_res = client.post("/api/v1/payments/create-order", json={"plan_id": trial_id})
    assert order_res.status_code == 200
    assert order_res.json()["amount"] == 21.0
    order_id = order_res.json()["order_id"]

    verify_res = client.post("/api/v1/payments/verify", json={"order_id": order_id})
    assert verify_res.status_code == 200
    assert verify_res.json()["status"] == "success"

    # 6. User views plans again: trial plan is now HIDDEN
    plans_after = client.get("/api/v1/plans")
    assert plans_after.status_code == 200
    ids_after = [p["id"] for p in plans_after.json()["data"]]
    assert trial_id not in ids_after

    # 7. User tries to create payment order for same trial plan again: 409 Conflict
    dup_order = client.post("/api/v1/payments/create-order", json={"plan_id": trial_id})
    assert dup_order.status_code == 409
    assert "once per email" in dup_order.json()["detail"].lower()

    # 8. User deactivates account and signs up again
    del_res = client.delete("/api/v1/users/profile")
    assert del_res.status_code == 200
    client.cookies.clear()

    re_otp = auth_service.generate_and_store_otp(user_email, "register")
    client.post("/api/v1/auth/register", json={
        "name": "Paid Trial User Re-registered",
        "email": user_email,
        "phone": "9876500099",
        "password": "NewPassword123!",
        "otp": re_otp
    })

    # 9. Re-registered user: trial plan is STILL hidden and cannot be ordered
    re_plans = client.get("/api/v1/plans")
    assert trial_id not in [p["id"] for p in re_plans.json()["data"]]

    re_order_blocked = client.post("/api/v1/payments/create-order", json={"plan_id": trial_id})
    assert re_order_blocked.status_code == 409


