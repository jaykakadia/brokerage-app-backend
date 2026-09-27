import pytest


def test_smtp_admin_settings_and_test_email(client, admin_user, test_user):
    # 1. Non-admin blocked from mail settings
    client.post("/api/v1/auth/login", json={"email": test_user.email, "password": "password123"})
    res_unauth = client.get("/api/v1/admin/settings/mail")
    assert res_unauth.status_code == 403

    # 2. Admin login & get mail settings
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    res_get = client.get("/api/v1/admin/settings/mail")
    assert res_get.status_code == 200
    cfg = res_get.json()["data"]
    assert "smtp_host" in cfg
    assert "smtp_email" in cfg
    assert "has_password" in cfg
    # Security requirement: Plaintext password is NEVER returned in response
    assert "password" not in cfg
    assert "smtp_password" not in cfg

    # 3. Admin saves new mail settings
    res_save = client.post("/api/v1/admin/settings/mail", json={
        "smtp_host": "smtp.gmail.com",
        "smtp_email": "admin.tradecall@gmail.com",
        "smtp_password": "supersecretpassword",
        "smtp_port": 587,
        "smtp_encryption": "tls",
        "from_name": "TradeCall Admin Team"
    })
    assert res_save.status_code == 200
    assert res_save.json()["status"] == "success"

    # Re-fetch: has_password must now be True, but password itself still NOT exposed
    res_get2 = client.get("/api/v1/admin/settings/mail")
    assert res_get2.status_code == 200
    cfg2 = res_get2.json()["data"]
    assert cfg2["smtp_email"] == "admin.tradecall@gmail.com"
    assert cfg2["from_name"] == "TradeCall Admin Team"
    assert cfg2["has_password"] is True
    assert "password" not in cfg2
    assert "smtp_password" not in cfg2

    # 4. Dispatch test email via admin endpoint
    res_test = client.post("/api/v1/admin/settings/mail/test", json={
        "test_email": "destination@example.com"
    })
    assert res_test.status_code == 200
    assert "Test email successfully sent" in res_test.json()["message"]


def test_smtp_secret_encrypted_at_rest_in_db(client, admin_user, db_session):
    from app.db.models.setting import SystemSetting
    from app.core.security import decrypt_secret
    from app.services.mail_service import mail_service

    # Admin login & save password
    client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "adminpass123"})
    client.post("/api/v1/admin/settings/mail", json={
        "smtp_host": "smtp.gmail.com",
        "smtp_email": "secure.admin@gmail.com",
        "smtp_password": "RealSmtpPassword123!",
        "smtp_port": 465,
        "smtp_encryption": "ssl"
    })

    # Query DB directly to verify encryption at rest
    row = db_session.query(SystemSetting).filter(SystemSetting.key == "smtp_password").first()
    assert row is not None
    assert row.is_encrypted is True
    # Crucial security guarantee: Plaintext password is NEVER stored in database
    assert row.value != "RealSmtpPassword123!"
    assert "RealSmtpPassword123!" not in row.value

    # Decryption works with derived environmental key
    decrypted = decrypt_secret(row.value)
    assert decrypted == "RealSmtpPassword123!"

    # mail_service resolves decrypted password seamlessly
    active_cfg = mail_service.get_active_config(db_session)
    assert active_cfg["password"] == "RealSmtpPassword123!"

