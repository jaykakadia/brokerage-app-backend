import pytest
from app.services.mail_service import mail_service
from app.services.auth_service import auth_service
from app.db.models.user import User
from datetime import datetime, timedelta, timezone


def test_mail_dispatch_mock():
    # Clear previously recorded emails
    mail_service.sent_emails.clear()

    # 1. Dispatch registration OTP
    ok = mail_service.send_verification_otp("newuser@example.com", "654321", name="Arun")
    assert ok is True
    assert len(mail_service.sent_emails) == 1
    last_email = mail_service.sent_emails[-1]
    assert last_email["to"] == "newuser@example.com"
    assert "654321" in last_email["subject"]
    assert "Arun" in last_email["html"]

    # 2. Dispatch password reset OTP
    ok2 = mail_service.send_password_reset_otp("resetuser@example.com", "998877")
    assert ok2 is True
    assert len(mail_service.sent_emails) == 2
    last_reset = mail_service.sent_emails[-1]
    assert "998877" in last_reset["subject"]

    # 3. Transactional email
    ok3 = mail_service.send_transactional_email(
        "buyer@example.com",
        "Payment Confirmation",
        "<p>Your plan is active.</p>"
    )
    assert ok3 is True
    assert len(mail_service.sent_emails) == 3


def test_otp_security_and_limits(client, db_session):
    test_email = "security_test@example.com"

    # 1. Generate OTP
    otp_code = auth_service.generate_and_store_otp(test_email, "register", db=db_session)
    assert len(otp_code) == 6

    # 2. Rate limit cooldown: Immediate second request within 60s is blocked
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as excinfo:
        auth_service.generate_and_store_otp(test_email, "register", db=db_session)
    assert excinfo.value.status_code == 429
    assert "request a new one in" in excinfo.value.detail
    assert excinfo.value.headers["Retry-After"]

    # 3. Invalid OTP rejected
    is_valid_fake = auth_service.verify_otp(test_email, "register", "000000", consume=False)
    assert is_valid_fake is False

    # 4. Correct OTP verified and consumed (single-use)
    is_valid = auth_service.verify_otp(test_email, "register", otp_code, consume=True)
    assert is_valid is True

    # 5. Single-use enforcement: Attempting to verify the same OTP again fails
    is_valid_again = auth_service.verify_otp(test_email, "register", otp_code, consume=True)
    assert is_valid_again is False

    # 6. Expiration enforcement: Expired OTP is rejected
    expired_email = "expired@example.com"
    exp_code = "112233"
    hashed = auth_service._hash_otp(expired_email, exp_code)
    from app.services.auth_service import OTPRecord
    past_time = datetime.now(timezone.utc) - timedelta(minutes=15)
    auth_service._otp_store[(expired_email, "register")] = OTPRecord(hashed, "register", past_time)

    assert auth_service.verify_otp(expired_email, "register", exp_code) is False

    # 7. Max failed verification attempts lock out the OTP
    brute_email = "brute_force@example.com"
    real_code = auth_service.generate_and_store_otp(brute_email, "register", db=db_session)
    for _ in range(5):
        auth_service.verify_otp(brute_email, "register", "000000", consume=False)

    with pytest.raises(HTTPException) as exc_max:
        auth_service.verify_otp(brute_email, "register", "000000", consume=False)
    assert exc_max.value.status_code == 429
    assert "Maximum verification attempts exceeded" in exc_max.value.detail

    # 8. Verify OTP is securely hashed in storage
    from app.db.models.otp import OtpVerification
    db_record = db_session.query(OtpVerification).filter(OtpVerification.email == brute_email).first()
    assert db_record is not None
    assert db_record.otp_hash != real_code
    assert len(db_record.otp_hash) == 64  # SHA-256 hex string



def test_brevo_api_used_when_key_set(monkeypatch):
    from app.core.config import settings
    import app.services.mail_service as ms

    calls = []

    class FakeResp:
        status_code = 201
        text = "{}"

    def fake_post(url, json, headers, timeout):
        calls.append((url, json, headers))
        return FakeResp()

    monkeypatch.setattr(settings, "SMTP_MOCK", False)
    monkeypatch.setattr(settings, "BREVO_API_KEY", "test-key")
    monkeypatch.setattr(settings, "BREVO_SENDER_EMAIL", "sender@example.com")
    monkeypatch.setattr(ms.httpx, "post", fake_post)

    assert mail_service.send_verification_otp("brevo@example.com", "112233") is True
    url, payload, headers = calls[0]
    assert url == ms.BREVO_SEND_URL
    assert headers["api-key"] == "test-key"
    assert payload["sender"]["email"] == "sender@example.com"
    assert payload["to"] == [{"email": "brevo@example.com"}]
    assert "112233" in payload["subject"]


def test_brevo_rejection_reports_failure(monkeypatch):
    from app.core.config import settings
    import app.services.mail_service as ms

    class FakeResp:
        status_code = 401
        text = "unauthorized"

    monkeypatch.setattr(settings, "SMTP_MOCK", False)
    monkeypatch.setattr(settings, "BREVO_API_KEY", "bad-key")
    monkeypatch.setattr(ms.httpx, "post", lambda *a, **k: FakeResp())

    assert mail_service.send_verification_otp("brevo@example.com", "112233") is False


def test_failed_send_does_not_start_cooldown(monkeypatch):
    from fastapi import HTTPException
    email = "flaky@example.com"
    auth_service._otp_store.pop((email, "register"), None)

    monkeypatch.setattr(mail_service, "send_verification_otp", lambda *a, **k: False)
    with pytest.raises(HTTPException) as excinfo:
        auth_service.generate_and_store_otp(email, "register")
    assert excinfo.value.status_code == 503

    # The mail service recovers: an immediate retry must go through, not hit the 60s cooldown
    monkeypatch.setattr(mail_service, "send_verification_otp", lambda *a, **k: True)
    code = auth_service.generate_and_store_otp(email, "register")
    assert auth_service.verify_otp(email, "register", code)


def test_otp_verifies_across_worker_processes(db_session):
    # Production runs several uvicorn workers; the OTP may be sent by one and checked by another
    email = "multiworker@example.com"
    db_session.add(User(name="Multi", email=email, phone="9000000001", password_hash="x"))
    db_session.commit()
    code = auth_service.generate_and_store_otp(email, "forgot", db=db_session)

    auth_service._otp_store.pop((email, "forgot"))  # simulate the other worker's empty cache
    assert auth_service.verify_otp(email, "forgot", "000000", db=db_session) is False
    assert auth_service.verify_otp(email, "forgot", code, consume=True, db=db_session) is True
    assert auth_service.verify_otp(email, "forgot", code, consume=True, db=db_session) is False
