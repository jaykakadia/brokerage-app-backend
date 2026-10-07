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


def test_plans_listed_low_to_high_price(client, admin_user):
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    for name, price, order in [("Pro", 2499.0, 0), ("Basic", 499.0, 5), ("Plus", 999.0, 1)]:
        res = client.post("/api/v1/plans", json={
            "name": name, "price": price, "listing_limit": 1, "status": "active", "sort_order": order
        })
        assert res.status_code == 200
    client.cookies.clear()
    names = [p["name"] for p in client.get("/api/v1/plans").json()["data"]]
    assert names == ["Basic", "Plus", "Pro"]
