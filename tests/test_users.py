def _profile_otp(client, email: str) -> str:
    from app.services.mail_service import mail_service

    send_res = client.post("/api/v1/auth/send-otp", json={
        "email": email,
        "action": "profile_update"
    })
    assert send_res.status_code == 200
    return mail_service.sent_emails[-1]["subject"].split(":")[-1].strip()


def test_user_profile_and_password(client, test_user):
    # Log in as test user
    client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "password123"
    })

    # Read profile
    res = client.get("/api/v1/users/profile")
    assert res.status_code == 200
    assert res.json()["data"]["name"] == "John Doe"

    missing_otp = client.put("/api/v1/users/profile", json={
        "name": "John Updated",
        "phone": "9998881112"
    })
    assert missing_otp.status_code == 400

    otp_code = _profile_otp(client, test_user.email)
    upd = client.put("/api/v1/users/profile", json={
        "name": "John Updated",
        "phone": "9998881112",
        "otp": otp_code
    })
    assert upd.status_code == 200
    assert "Profile updated" in upd.json()["message"]

    new_email = "john.updated@example.com"
    email_otp = _profile_otp(client, new_email)
    email_upd = client.put("/api/v1/users/profile", json={
        "email": new_email,
        "otp": email_otp
    })
    assert email_upd.status_code == 200

    # Verify updated profile
    res2 = client.get("/api/v1/users/profile")
    assert res2.json()["data"]["name"] == "John Updated"

    # Change password
    pwd_res = client.post("/api/v1/users/change-password", json={
        "current_password": "password123",
        "new_password": "newsecurepass999",
        "confirm_password": "newsecurepass999"
    })
    assert pwd_res.status_code == 200

    # Log in with new password
    login_new = client.post("/api/v1/auth/login", json={
        "email": "john.updated@example.com",
        "password": "newsecurepass999"
    })
    assert login_new.status_code == 200


def test_admin_user_management(client, admin_user, test_user):
    # Log in as admin
    client.post("/api/v1/auth/login", json={
        "email": admin_user.email,
        "password": "adminpass123"
    })

    # List all users
    list_res = client.get("/api/v1/admin/users")
    assert list_res.status_code == 200
    users = list_res.json()["data"]
    assert len(users) >= 2

    # Update test user role to Builder
    role_res = client.post(f"/api/v1/admin/users/{test_user.id}/role", json={"role": "Builder"})
    assert role_res.status_code == 200

    # Update test user role to Agent
    role_res2 = client.post(f"/api/v1/admin/users/{test_user.id}/role", json={"role": "Agent"})
    assert role_res2.status_code == 200

    # Reject invalid role (e.g. Broker or Superuser)
    invalid_role = client.post(f"/api/v1/admin/users/{test_user.id}/role", json={"role": "Broker"})
    assert invalid_role.status_code == 422  # Pydantic Literal validation

    # Non-admin access forbidden
    client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "password123"
    })
    forbidden = client.get("/api/v1/admin/users")
    assert forbidden.status_code == 403


def test_business_profile_fields_save_without_otp(client, test_user):
    client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "password123"
    })

    res = client.put("/api/v1/users/profile", json={
        "name": test_user.name,
        "phone": test_user.phone,
        "email": test_user.email,
        "business_name": "Doe Realty",
        "whatsapp": test_user.phone,
        "facebook_url": "https://facebook.com/doerealty",
        "website_url": "https://doerealty.in",
        "x_url": "https://x.com/doerealty",
        "youtube_url": "https://youtube.com/@doerealty"
    })
    assert res.status_code == 200

    data = client.get("/api/v1/users/profile").json()["data"]
    assert data["business_name"] == "Doe Realty"
    assert data["whatsapp"] == test_user.phone
    assert data["x_url"] == "https://x.com/doerealty"
    assert data["youtube_url"] == "https://youtube.com/@doerealty"

    # Blank values clear a field
    client.put("/api/v1/users/profile", json={"website_url": "  "})
    assert client.get("/api/v1/users/profile").json()["data"]["website_url"] is None

    # Changing the phone along with business details still needs an OTP
    blocked = client.put("/api/v1/users/profile", json={
        "phone": "9000000001",
        "business_name": "Other"
    })
    assert blocked.status_code == 400


def test_admin_create_user(client, admin_user, test_user):
    client.post("/api/v1/auth/login", json={
        "email": admin_user.email,
        "password": "adminpass123"
    })

    payload = {
        "name": "New Agent",
        "phone": "9000000123",
        "email": "New.Agent@Example.com",
        "password": "agentpass123",
        "role": "Agent",
        "business_name": "Agent Realty",
        "whatsapp": "9000000123",
        "youtube_url": "https://youtube.com/@agentrealty"
    }
    res = client.post("/api/v1/admin/users", json=payload)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["email"] == "new.agent@example.com"
    assert data["role"] == "Agent"
    assert data["business_name"] == "Agent Realty"
    assert data["youtube_url"] == "https://youtube.com/@agentrealty"

    # Admin edit can update and clear profile fields
    updated = client.put(f"/api/v1/admin/users/{data['id']}", json={"website_url": "https://agentrealty.in", "youtube_url": ""})
    assert updated.status_code == 200
    assert updated.json()["data"]["website_url"] == "https://agentrealty.in"
    assert updated.json()["data"]["youtube_url"] is None

    # Duplicate email must not overwrite the existing account
    dup_email = client.post("/api/v1/admin/users", json={**payload, "phone": "9000000124", "password": "overwrite999"})
    assert dup_email.status_code == 409
    dup_phone = client.post("/api/v1/admin/users", json={**payload, "email": "other@example.com", "phone": test_user.phone})
    assert dup_phone.status_code == 409

    client.post("/api/v1/auth/logout")
    login = client.post("/api/v1/auth/login", json={"email": "new.agent@example.com", "password": "agentpass123"})
    assert login.status_code == 200

    # Non-admins cannot create users
    forbidden = client.post("/api/v1/admin/users", json={**payload, "email": "x@example.com", "phone": "9000000999"})
    assert forbidden.status_code == 403


def test_admin_edit_and_delete_user(client, admin_user, test_user, db_session):
    from app.db.models.user import User
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})

    upd = client.put(f"/api/v1/admin/users/{test_user.id}", json={
        "name": "Renamed", "email": "renamed@example.com", "phone": "9111111111",
        "role": "Builder", "password": "freshpass123"
    })
    assert upd.status_code == 200
    data = upd.json()["data"]
    assert (data["name"], data["email"], data["role"]) == ("Renamed", "renamed@example.com", "Builder")

    # Email / phone already used by another account
    assert client.put(f"/api/v1/admin/users/{test_user.id}", json={"email": admin_user.email}).status_code == 409
    assert client.put(f"/api/v1/admin/users/{test_user.id}", json={"phone": admin_user.phone}).status_code == 409

    # Admin can't demote, deactivate or delete themselves (also the last admin)
    assert client.put(f"/api/v1/admin/users/{admin_user.id}", json={"role": "Owner"}).status_code == 400
    assert client.put(f"/api/v1/admin/users/{admin_user.id}", json={"status": "deleted"}).status_code == 400
    assert client.post(f"/api/v1/admin/users/{admin_user.id}/role", json={"role": "Owner"}).status_code == 400
    assert client.delete(f"/api/v1/admin/users/{admin_user.id}").status_code == 400

    # New password works for the edited user
    client.post("/api/v1/auth/logout")
    assert client.post("/api/v1/auth/login", json={"email": "renamed@example.com", "password": "freshpass123"}).status_code == 200
    # Non-admins can't delete
    assert client.delete(f"/api/v1/admin/users/{admin_user.id}").status_code == 403

    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    res = client.delete(f"/api/v1/admin/users/{test_user.id}")
    assert res.status_code == 200
    db_session.expire_all()
    assert db_session.query(User).filter(User.id == test_user.id).first() is None
    assert client.delete(f"/api/v1/admin/users/{test_user.id}").status_code == 404


def test_bulk_user_upload(client, admin_user):
    import io
    import openpyxl
    from app.core.security import verify_password

    # Log in as admin
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})

    # 1. Test CSV Bulk Upload
    csv_data = (
        "Name,Email,Phone,Role,Business Name\n"
        "Bulk User One,bulk1@example.com,9870000001,Agent,Agency 1\n"
        "Bulk User Two,bulk2@example.com,9870000002.0,Builder,\n"
        "Duplicate Email,bulk1@example.com,9870000003,Owner,\n"
    ).encode("utf-8")

    res = client.post(
        "/api/v1/admin/users/bulk-upload",
        files={"file": ("users.csv", csv_data, "text/csv")}
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["created_count"] == 2
    assert data["skipped_count"] == 1
    assert data["errors"][0]["reason"] == "Duplicate email in upload file"

    # Verify password is set to email for created user
    client.post("/api/v1/auth/logout")
    login_res = client.post("/api/v1/auth/login", json={"email": "bulk1@example.com", "password": "bulk1@example.com"})
    assert login_res.status_code == 200

    # 2. Test Excel Bulk Upload (.xlsx)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Username", "Email Address", "Mobile No", "Type"])
    ws.append(["Excel User Three", "bulk3@example.com", 9870000004, "Agent"])
    ws.append(["Existing User", "bulk1@example.com", 9870000005, "Owner"])  # Already in DB

    excel_bytes = io.BytesIO()
    wb.save(excel_bytes)
    excel_bytes.seek(0)

    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    res2 = client.post(
        "/api/v1/admin/users/bulk-upload",
        files={"file": ("users.xlsx", excel_bytes.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    assert res2.status_code == 200, res2.text
    data2 = res2.json()["data"]
    assert data2["created_count"] == 1
    assert data2["skipped_count"] == 1
    assert "already registered" in data2["errors"][0]["reason"]

    # 3. Test Missing Header Column (e.g. missing Phone)
    bad_csv = "Name,Email\nTest User,test@example.com\n".encode("utf-8")
    res_bad_headers = client.post(
        "/api/v1/admin/users/bulk-upload",
        files={"file": ("missing_col.csv", bad_csv, "text/csv")}
    )
    assert res_bad_headers.status_code == 400
    assert "Required column(s) missing: Phone" in res_bad_headers.json()["detail"]

    # 4. Test Missing Required Row Fields (e.g. blank name / phone in row)
    missing_fields_csv = (
        "Name,Email,Phone\n"
        ",missing_name@example.com,9870000010\n"
        "Missing Phone,missing_phone@example.com,\n"
    ).encode("utf-8")
    res_missing_row = client.post(
        "/api/v1/admin/users/bulk-upload",
        files={"file": ("missing_fields.csv", missing_fields_csv, "text/csv")}
    )
    assert res_missing_row.status_code == 200
    missing_data = res_missing_row.json()["data"]
    assert missing_data["created_count"] == 0
    assert missing_data["skipped_count"] == 2
    assert "Required field(s) missing: Name" in missing_data["errors"][0]["reason"]
    assert "Required field(s) missing: Phone" in missing_data["errors"][1]["reason"]
