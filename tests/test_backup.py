import io
import json
import zipfile
import pytest

from app.db.models.category import Category
from app.db.models.audit_log import AuditLog


def test_backup_admin_protection(client, test_user, admin_user):
    # 1. Unauthenticated access is blocked (401)
    res = client.get("/api/v1/admin/backup/stats")
    assert res.status_code == 401

    res = client.get("/api/v1/admin/backup/export")
    assert res.status_code == 401

    res = client.post("/api/v1/admin/backup/restore")
    assert res.status_code == 401

    # 2. Regular non-admin user is blocked (403 Forbidden)
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})

    res = client.get("/api/v1/admin/backup/stats")
    assert res.status_code == 403

    res = client.get("/api/v1/admin/backup/export")
    assert res.status_code == 403

    res = client.post("/api/v1/admin/backup/restore")
    assert res.status_code == 403


def test_backup_export_and_restore_cycle(client, admin_user, db_session):
    # 1. Login as admin
    client.post("/api/v1/auth/logout")
    login_res = client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    assert login_res.status_code == 200

    # 2. Check stats endpoint
    stats_res = client.get("/api/v1/admin/backup/stats")
    assert stats_res.status_code == 200
    stats_data = stats_res.json()["data"]
    assert "tables" in stats_data
    assert "users" in stats_data["tables"]
    assert stats_data["total_records"] > 0

    # 3. Create a distinct category to verify export/restore
    cat = Category(name="Backup Test Category", description="Should survive round-trip")
    db_session.add(cat)
    db_session.commit()
    db_session.refresh(cat)
    cat_id = cat.id

    # 4. Export backup archive
    export_res = client.get("/api/v1/admin/backup/export")
    assert export_res.status_code == 200
    assert export_res.headers["content-type"] == "application/zip"
    zip_bytes = export_res.content

    # Inspect zip contents
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        namelist = zf.namelist()
        assert "manifest.json" in namelist
        assert "tables/users.json" in namelist
        assert "tables/categories.json" in namelist

        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest["app"] == "TradeCall API"
        assert manifest["exported_by"] == admin_user.email

        categories_data = json.loads(zf.read("tables/categories.json").decode("utf-8"))
        cat_names = [c["name"] for c in categories_data]
        assert "Backup Test Category" in cat_names

    # 5. Modify or delete category locally
    cat_to_del = db_session.query(Category).filter(Category.id == cat_id).first()
    db_session.delete(cat_to_del)
    db_session.commit()
    assert db_session.query(Category).filter(Category.id == cat_id).first() is None

    # 6. Restore the backup archive (mode=replace)
    restore_res = client.post(
        "/api/v1/admin/backup/restore?mode=replace",
        files={"file": ("backup.zip", zip_bytes, "application/zip")}
    )
    assert restore_res.status_code == 200
    restore_data = restore_res.json()
    assert restore_data["status"] == "success"
    assert restore_data["data"]["tables_restored"]["categories"] > 0

    # Verify category is restored in DB
    db_session.expire_all()
    restored_cat = db_session.query(Category).filter(Category.id == cat_id).first()
    assert restored_cat is not None
    assert restored_cat.name == "Backup Test Category"

    # 7. Verify audit log entry was created for restore
    audit = db_session.query(AuditLog).filter(AuditLog.action == "RESTORE_BACKUP").first()
    assert audit is not None
    assert audit.actor_email == admin_user.email


def test_backup_restore_rejection_security(client, admin_user):
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})

    # 1. Reject non-zip file
    res = client.post(
        "/api/v1/admin/backup/restore",
        files={"file": ("test.txt", b"plain text", "text/plain")}
    )
    assert res.status_code == 400

    # 2. Reject corrupted zip
    res = client.post(
        "/api/v1/admin/backup/restore",
        files={"file": ("corrupt.zip", b"PK\x03\x04corrupteddata", "application/zip")}
    )
    assert res.status_code == 400

    # 3. Reject zip containing path traversal (zip slip)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../etc/passwd", "malicious")
        zf.writestr("tables/categories.json", "[]")
    
    res = client.post(
        "/api/v1/admin/backup/restore",
        files={"file": ("malicious.zip", buf.getvalue(), "application/zip")}
    )
    assert res.status_code == 400
    assert "unsafe" in res.json()["detail"].lower()

