import pytest
from app.db.models.listing import Listing
from app.db.models.audit_log import AuditLog


def test_audit_logs_and_soft_delete(client, admin_user, test_user, db_session):
    # 1. Non-admin forbidden from viewing audit logs
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    forbidden_res = client.get("/api/v1/admin/audit-logs")
    assert forbidden_res.status_code == 403

    # 2. Login as admin
    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})

    # Check audit log tables endpoint
    tables_res = client.get("/api/v1/admin/audit-logs/tables")
    assert tables_res.status_code == 200
    assert "users" in tables_res.json()["data"]

    # 3. Create a test category to generate CREATE audit log
    create_cat = client.post("/api/v1/categories", json={
        "name": "Audit Verification Category",
        "description": "Original Description"
    })
    assert create_cat.status_code == 200
    cat_id = create_cat.json()["data"]["id"]

    # 4. Update the category to generate UPDATE audit log with before/after diff
    upd_cat = client.put(f"/api/v1/categories/{cat_id}", json={
        "description": "Modified Description"
    })
    assert upd_cat.status_code == 200

    # 5. Soft-delete the category to generate SOFT_DELETE audit log
    del_cat = client.delete(f"/api/v1/categories/{cat_id}")
    assert del_cat.status_code == 200

    # Verify category still physically exists in database with is_deleted=True
    db_session.expire_all()
    from app.db.models.category import Category
    cat_in_db = db_session.query(Category).filter(Category.id == cat_id).first()
    assert cat_in_db is not None
    assert cat_in_db.is_deleted is True
    assert cat_in_db.deleted_at is not None

    # 6. Verify audit logs API retrieves the logs
    logs_res = client.get("/api/v1/admin/audit-logs", params={"table_name": "categories", "record_id": cat_id})
    assert logs_res.status_code == 200
    items = logs_res.json()["data"]["items"]
    assert len(items) >= 3

    actions = [item["action"] for item in items]
    assert "CREATE" in actions
    assert "UPDATE" in actions
    assert "SOFT_DELETE" in actions

    # Verify the UPDATE log captured the before/after change
    update_item = next(item for item in items if item["action"] == "UPDATE")
    assert "description" in update_item["changes"]
    assert update_item["changes"]["description"]["old"] == "Original Description"
    assert update_item["changes"]["description"]["new"] == "Modified Description"

    # 7. Test Listing Audit Trail and Soft Delete Flow
    post_res = client.post("/api/v1/listings", data={
        "title": "Initial 3BHK Apartment",
        "location": "Palwal",
        "price": 4500000,
        "owner_name": "Admin Tester"
    })
    assert post_res.status_code == 200
    listing_id = post_res.json()["data"]["id"]

    # Update listing title and price
    upd_listing = client.patch(f"/api/v1/listings/{listing_id}", data={
        "title": "Renovated 3BHK Apartment",
        "price": 4800000
    })
    assert upd_listing.status_code == 200

    # Soft delete listing
    del_listing = client.delete(f"/api/v1/listings/{listing_id}")
    assert del_listing.status_code == 200

    # Check listing in DB
    db_session.expire_all()
    l_in_db = db_session.query(Listing).filter(Listing.id == listing_id).first()
    assert l_in_db is not None
    assert l_in_db.is_deleted is True
    assert l_in_db.status == "deleted"

    # Verify audit logs for listing
    listing_logs_res = client.get("/api/v1/admin/audit-logs", params={"table_name": "listings", "record_id": listing_id})
    assert listing_logs_res.status_code == 200
    l_items = listing_logs_res.json()["data"]["items"]
    assert len(l_items) >= 3

    l_update = next(item for item in l_items if item["action"] == "UPDATE")
    assert "title" in l_update["changes"]
    assert l_update["changes"]["title"]["old"] == "Initial 3BHK Apartment"
    assert l_update["changes"]["title"]["new"] == "Renovated 3BHK Apartment"

    l_delete = next(item for item in l_items if item["action"] == "SOFT_DELETE")
    assert l_delete["changes"]["is_deleted"]["new"] is True

    # Public search should not return soft-deleted listing
    client.post("/api/v1/auth/logout")
    pub_search = client.get("/api/v1/listings", params={"status": "approved"})
    assert pub_search.status_code == 200
    listing_ids = [l["id"] for l in pub_search.json()["data"]]
    assert listing_id not in listing_ids
