from app.services.auth_service import auth_service
import pytest
from app.core.security import create_access_token
from datetime import timedelta


def test_register_and_login_flow(client):
    # 1. Register new user
    reg_payload = {
        "name": "Jane Doe",
        "phone": "9998887776",
        "email": "jane@example.com",
        "password": "securepassword123",
        "business_name": "Doe Estates"
    }
    reg_payload["otp"] = auth_service.generate_and_store_otp(reg_payload["email"], "register")
    res = client.post("/api/v1/auth/register", json=reg_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "access_token" in client.cookies

    # 2. Access /me with cookie
    me_res = client.get("/api/v1/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["data"]["email"] == "jane@example.com"
    assert me_res.json()["data"]["business_name"] == "Doe Estates"

    # 3. Logout
    logout_res = client.post("/api/v1/auth/logout")
    assert logout_res.status_code == 200

    # 4. Verify unauthenticated after logout
    after_logout = client.get("/api/v1/auth/me")
    assert after_logout.status_code == 401


def test_login_invalid_credentials(client, test_user):
    res = client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "wrongpassword"
    })
    assert res.status_code == 401
    assert "Invalid email or password" in res.json()["detail"]


def test_login_inactive_user(client, inactive_user):
    res = client.post("/api/v1/auth/login", json={
        "email": inactive_user.email,
        "password": "password123"
    })
    assert res.status_code == 403
    assert "inactive" in res.json()["detail"].lower()


def test_expired_jwt(client, test_user):
    expired_token = create_access_token(
        subject=test_user.id,
        role=test_user.role,
        expires_delta=timedelta(seconds=-10)
    )
    client.cookies.set("access_token", expired_token)
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401


def test_otp_flow(client):
    from app.services.mail_service import mail_service
    send_res = client.post("/api/v1/auth/send-otp", json={
        "email": "otpuser@example.com",
        "action": "register"
    })
    assert send_res.status_code == 200
    assert "OTP sent to your email" in send_res.json()["message"]

    # Retrieve sent OTP from mail service
    assert len(mail_service.sent_emails) > 0
    last_mail = mail_service.sent_emails[-1]
    # Subject: "Your TradeCall Verification Code: 123456"
    otp_code = last_mail["subject"].split(":")[-1].strip()

    # Verify OTP
    verify_res = client.post("/api/v1/auth/verify-otp", json={
        "email": "otpuser@example.com",
        "otp": otp_code
    })
    assert verify_res.status_code == 200
    assert verify_res.json()["status"] == "success"


def test_register_requires_otp(client):
    payload = {
        "name": "No Otp",
        "phone": "9000000001",
        "email": "nootp@example.com",
        "password": "securepassword123"
    }
    res = client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 400

    res = client.post("/api/v1/auth/register", json={**payload, "otp": "000000"})
    assert res.status_code == 400


def test_reset_password_requires_otp(client, test_user):
    # Without an OTP nobody can take over an account by email alone
    res = client.post("/api/v1/auth/reset-password", json={"email": test_user.email, "new_password": "Hijacked123!"})
    assert res.status_code == 400
    assert "OTP is required" in res.json()["detail"]

    res = client.post("/api/v1/auth/reset-password", json={"email": test_user.email, "new_password": "Hijacked123!", "otp": "000000"})
    assert res.status_code == 400
