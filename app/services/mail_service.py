import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict, Any, Optional
from app.core.config import settings


class MailService:
    def __init__(self):
        self.sent_emails: List[Dict[str, Any]] = []

    def _send_smtp(self, to_email: str, subject: str, html_content: str, text_content: Optional[str] = None) -> bool:
        """
        Internal dispatcher. If SMTP_MOCK is True or credentials not provided,
        records the email in memory for test assertions and safe dev runs.
        Otherwise connects via real SMTP with TLS/SSL.
        """
        email_record = {
            "to": to_email,
            "subject": subject,
            "html": html_content,
            "text": text_content or html_content,
        }

        # Safe Mock Mode (for tests and local dev without live SMTP credentials)
        if settings.SMTP_MOCK or not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
            self.sent_emails.append(email_record)
            return True

        # Real SMTP Delivery
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
            msg["To"] = to_email

            if text_content:
                msg.attach(MIMEText(text_content, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            if settings.SMTP_USE_SSL:
                server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
            else:
                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
                if settings.SMTP_USE_TLS:
                    server.starttls()

            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
            server.quit()

            self.sent_emails.append(email_record)
            return True
        except Exception:
            # Safe failure: never leak credentials or internal traceback to client
            return False

    def send_verification_otp(self, to_email: str, otp: str, name: Optional[str] = None) -> bool:
        """Sends registration OTP verification email."""
        display_name = name or "Customer"
        subject = f"Your TradeCall Verification Code: {otp}"
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 8px;">
            <h2 style="color: #0c6253;">Welcome to TradeCall India</h2>
            <p>Hello {display_name},</p>
            <p>Thank you for creating an account with TradeCall. Use the following One-Time Password (OTP) to verify your email address:</p>
            <div style="margin: 20px 0; text-align: center;">
                <span style="display: inline-block; font-size: 26px; font-weight: bold; letter-spacing: 6px; padding: 12px 24px; background: #f0faf7; color: #0c6253; border: 1px dashed #0c6253; border-radius: 6px;">
                    {otp}
                </span>
            </div>
            <p style="color: #6b7280; font-size: 13px;">This code is valid for 10 minutes and can only be used once. If you did not request this verification, please ignore this email.</p>
            <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
            <p style="color: #9ca3af; font-size: 12px; text-align: center;">&copy; TradeCall India &middot; Direct Property & Business Portal</p>
        </div>
        """
        text = f"Hello {display_name},\nYour TradeCall verification code is: {otp}\nValid for 10 minutes."
        return self._send_smtp(to_email, subject, html, text)

    def send_password_reset_otp(self, to_email: str, otp: str) -> bool:
        """Sends password reset OTP email."""
        subject = f"TradeCall Password Reset Code: {otp}"
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 8px;">
            <h2 style="color: #b91c1c;">Reset Your Password</h2>
            <p>We received a request to reset your TradeCall password.</p>
            <div style="margin: 20px 0; text-align: center;">
                <span style="display: inline-block; font-size: 26px; font-weight: bold; letter-spacing: 6px; padding: 12px 24px; background: #fef2f2; color: #b91c1c; border: 1px dashed #b91c1c; border-radius: 6px;">
                    {otp}
                </span>
            </div>
            <p style="color: #6b7280; font-size: 13px;">Valid for 10 minutes. If you did not request a password reset, your account is safe and you can ignore this email.</p>
        </div>
        """
        text = f"Your TradeCall password reset code is: {otp}\nValid for 10 minutes."
        return self._send_smtp(to_email, subject, html, text)

    def send_profile_verification_otp(self, to_email: str, otp: str) -> bool:
        """Sends email verification OTP when updating profile contact details."""
        subject = f"TradeCall Profile Update Verification: {otp}"
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #e5e7eb; border-radius: 8px;">
            <h2 style="color: #0c6253;">Verify Email Change</h2>
            <p>Please confirm your new email address by entering this verification code:</p>
            <div style="margin: 20px 0; text-align: center;">
                <span style="display: inline-block; font-size: 26px; font-weight: bold; letter-spacing: 6px; padding: 12px 24px; background: #f0faf7; color: #0c6253; border: 1px dashed #0c6253; border-radius: 6px;">
                    {otp}
                </span>
            </div>
            <p style="color: #6b7280; font-size: 13px;">Valid for 10 minutes.</p>
        </div>
        """
        text = f"Your TradeCall email change code is: {otp}"
        return self._send_smtp(to_email, subject, html, text)

    def send_transactional_email(self, to_email: str, subject: str, body_html: str, body_text: Optional[str] = None) -> bool:
        """Sends arbitrary transactional email (e.g. payment receipt or plan activation)."""
        return self._send_smtp(to_email, subject, body_html, body_text)


mail_service = MailService()
