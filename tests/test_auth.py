import pytest
from app.core.security import create_access_token
from datetime import timedelta


def test_register_and_login_flow(client):
    # 1. Register new user
    reg_payload = {
        "name": "Jane Doe",
        "phone": "9998887776",
        "email": "jane@example.com",
        "password": "securepassword123"
    }
    res = client.post("/api/v1/auth/register", json=reg_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "access_token" in client.cookies

    # 2. Access /me with cookie
    me_res = client.get("/api/v1/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["data"]["email"] == "jane@example.com"

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
    send_res = client.post("/api/v1/auth/send-otp", json={
        "email": "otpuser@example.com",
        "action": "register"
    })
    assert send_res.status_code == 200
    msg = send_res.json()["message"]
    assert "Dev Code:" in msg
    otp_code = msg.split("Dev Code:")[1].strip(" )")

    # Verify OTP
    verify_res = client.post("/api/v1/auth/verify-otp", json={
        "email": "otpuser@example.com",
        "otp": otp_code
    })
    assert verify_res.status_code == 200
    assert verify_res.json()["status"] == "success"
