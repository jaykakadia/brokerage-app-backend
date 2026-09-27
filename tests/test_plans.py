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

    # 3. Public visitor views plans: only active plan returned
    client.cookies.clear()
    pub_res = client.get("/api/v1/plans")
    assert pub_res.status_code == 200
    plan_names = [p["name"] for p in pub_res.json()["data"]]
    assert "Gold Partner" in plan_names
    assert "Draft Plan" not in plan_names

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
