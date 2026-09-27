import pytest
from app.db.models.employee import Employee
from app.db.models.listing import Listing


def test_employees_crud_and_lookup(client, admin_user, test_user, db_session):
    # 1. Non-admin blocked
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    res_unauth = client.get("/api/v1/employees")
    assert res_unauth.status_code == 403

    # 2. Admin login
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})

    # 3. Create employee
    res_create = client.post("/api/v1/employees", json={
        "name": "Rajesh Kumar",
        "reference_code": "TCPL01",
        "status": "active",
        "phone": "9998887771",
        "email": "rajesh@tradecall.in"
    })
    assert res_create.status_code == 200
    emp1 = res_create.json()["data"]
    assert emp1["name"] == "Rajesh Kumar"
    assert emp1["reference_code"] == "TCPL01"
    emp1_id = emp1["id"]

    # 4. Duplicate reference code rejected
    res_dup = client.post("/api/v1/employees", json={
        "name": "Another Agent",
        "reference_code": "TCPL01",
        "status": "active"
    })
    assert res_dup.status_code == 400
    assert "already in use" in res_dup.json()["detail"]

    # 5. Create second employee (inactive)
    res_emp2 = client.post("/api/v1/employees", json={
        "name": "Inactive Worker",
        "reference_code": "TCPL02",
        "status": "inactive"
    })
    assert res_emp2.status_code == 200

    # 6. Public ref-codes lookup (returns only active)
    res_ref = client.get("/api/v1/employees/ref-codes")
    assert res_ref.status_code == 200
    codes = [item["reference_code"] for item in res_ref.json()["data"]]
    assert "TCPL01" in codes
    assert "TCPL02" not in codes  # Inactive must not appear in public picker

    # Search filter
    res_search = client.get("/api/v1/employees/ref-codes?q=rajesh")
    assert res_search.status_code == 200
    assert len(res_search.json()["data"]) == 1
    assert res_search.json()["data"][0]["reference_code"] == "TCPL01"

    # 7. Update employee
    res_up = client.post(f"/api/v1/employees?employee_id={emp1_id}", json={
        "name": "Rajesh Sharma",
        "reference_code": "TCPL01",
        "status": "active"
    })
    assert res_up.status_code == 200
    assert res_up.json()["data"]["name"] == "Rajesh Sharma"

    # 8. Listing linkage and tracker listing counts
    listing = Listing(
        user_id=test_user.id,
        title="Listing with ref code",
        location="Palwal",
        price=3000000.0,
        owner_name="Test Owner",
        owner_role="Owner",
        reference_code="TCPL01",
        status="approved"
    )
    db_session.add(listing)
    db_session.commit()

    res_list = client.get("/api/v1/employees")
    assert res_list.status_code == 200
    emp_tracker = next(e for e in res_list.json()["data"] if e["id"] == emp1_id)
    assert emp_tracker["listings_created"] >= 1

    # 9. Delete employee
    res_del = client.delete(f"/api/v1/employees/{emp1_id}")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "success"
