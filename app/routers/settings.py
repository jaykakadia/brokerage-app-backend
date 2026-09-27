from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin, get_db
from app.db.models.user import User
from app.db.models.setting import SystemSetting
from app.schemas.common import APIResponse, MessageResponse
from app.schemas.setting import MailSettingsRead, MailSettingsUpdate, TestMailRequest
from app.services.mail_service import mail_service

router = APIRouter(prefix="/api/v1/admin/settings", tags=["Admin Settings"])


@router.get("/mail", response_model=APIResponse[MailSettingsRead])
def get_mail_settings(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin endpoint to view mail settings. Raw password is never exposed."""
    cfg = mail_service.get_active_config(db)
    has_pwd = bool(cfg.get("password"))
    enc_mode = "ssl" if cfg.get("use_ssl") else "tls"

    data = MailSettingsRead(
        smtp_host=cfg.get("host") or "smtp.gmail.com",
        smtp_email=cfg.get("username") or "",
        smtp_port=cfg.get("port") or 587,
        smtp_encryption=enc_mode,
        from_name=cfg.get("from_name") or "TradeCall India",
        has_password=has_pwd
    )
    return APIResponse(status="success", data=data)


@router.post("/mail", response_model=MessageResponse)
def save_mail_settings(
    req: MailSettingsUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin endpoint to update SMTP mail configuration in system_settings."""
    settings_map = {
        "smtp_host": req.smtp_host.strip(),
        "smtp_email": req.smtp_email.strip(),
        "smtp_port": str(req.smtp_port),
        "smtp_encryption": req.smtp_encryption.lower().strip(),
        "smtp_from_name": (req.from_name or "TradeCall India").strip(),
    }
    from app.core.security import encrypt_secret
    if req.smtp_password and req.smtp_password.strip():
        settings_map["smtp_password"] = encrypt_secret(req.smtp_password.strip())

    for key, val in settings_map.items():
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        is_enc = (key == "smtp_password")
        if row:
            row.value = val
            row.is_encrypted = is_enc
        else:
            db.add(SystemSetting(key=key, value=val, is_encrypted=is_enc))

    db.commit()
    return MessageResponse(status="success", message="Mail settings saved successfully.")


@router.post("/mail/test", response_model=MessageResponse)
def send_test_email(
    req: TestMailRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin endpoint to send a test email to verify SMTP configuration."""
    target_email = req.test_email.strip()
    if not target_email:
        raise HTTPException(status_code=400, detail="Test email address is required.")

    subject = "TradeCall India - SMTP Test Email"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #10b981; border-radius: 8px;">
        <h2 style="color: #0c6253;">SMTP Test Email Successful!</h2>
        <p>This email confirms that your TradeCall mail settings are properly configured and working.</p>
        <p style="color: #6b7280; font-size: 13px;">Dispatched by TradeCall Admin.</p>
    </div>
    """
    text = "TradeCall India - SMTP Test Email Successful! Your mail settings are properly configured."

    success = mail_service._send_smtp(
        to_email=target_email,
        subject=subject,
        html_content=html,
        text_content=text,
        db=db
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send test email. Please check your SMTP host, port, credentials, and encryption mode."
        )

    return MessageResponse(status="success", message=f"Test email successfully sent to {target_email}!")
