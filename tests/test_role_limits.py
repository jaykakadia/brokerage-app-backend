import pytest
from app.db.models.role_limit import RoleLimit
from app.db.models.listing import Listing


def test_role_limits_flow_and_enforcement(client, admin_user, test_user, db_session):
    # 1. Non-admin blocked from admin role-limits endpoint
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    res_unauth = client.get("/api/v1/admin/role-limits")
    assert res_unauth.status_code == 403

    # 2. Admin login & get role limits
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    res_get = client.get("/api/v1/admin/role-limits")
    assert res_get.status_code == 200
    roles = [item["role"] for item in res_get.json()["data"]]
    assert "Owner" in roles
    assert "Agent" in roles
    assert "Builder" in roles

    # 3. Admin configures Owner limit to exactly 2
    res_save = client.post("/api/v1/admin/role-limits", json={
        "limits": {
            "Owner": 2,
            "Agent": 10,
            "Builder": 50
        }
    })
    assert res_save.status_code == 200

    # Verify updated
    res_get2 = client.get("/api/v1/admin/role-limits")
    owner_limit = next(item["max_listings"] for item in res_get2.json()["data"] if item["role"] == "Owner")
    assert owner_limit == 2

    # 4. User with role Owner logs in
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})

    # Post Listing 1 (Allowed)
    res_l1 = client.post("/api/v1/listings", data={
        "title": "First Property Owner Listing",
        "location": "Palwal",
        "price": 2500000,
        "owner_name": "Test Owner",
        "owner_role": "Owner"
    })
    assert res_l1.status_code == 200

    # Post Listing 2 (Allowed)
    res_l2 = client.post("/api/v1/listings", data={
        "title": "Second Property Owner Listing",
        "location": "Palwal",
        "price": 3500000,
        "owner_name": "Test Owner",
        "owner_role": "Owner"
    })
    assert res_l2.status_code == 200

    # Post Listing 3 (Exceeds limit of 2 -> MUST BE REJECTED)
    res_l3 = client.post("/api/v1/listings", data={
        "title": "Third Property Owner Listing",
        "location": "Palwal",
        "price": 4500000,
        "owner_name": "Test Owner",
        "owner_role": "Owner"
    })
    assert res_l3.status_code == 400
    assert "maximum listing limit (2)" in res_l3.json()["detail"]

    # 5. Admin user posting listings is exempt from role limits
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    res_admin_l = client.post("/api/v1/listings", data={
        "title": "Admin Created Listing Unlimited",
        "location": "Gurugram",
        "price": 9900000,
        "owner_name": "Admin",
        "owner_role": "Admin"
    })
    assert res_admin_l.status_code == 200
