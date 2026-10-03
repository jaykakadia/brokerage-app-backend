import hashlib
import random
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password, create_access_token, generate_csrf_token
from app.db.models.user import User
from app.db.models.otp import OtpVerification
from app.schemas.auth import RegisterRequest, LoginRequest
from app.services.mail_service import mail_service


class OTPRecord:
    def __init__(self, hashed_code: str, action: str, expires_at: datetime):
        self.hashed_code = hashed_code
        self.action = action
        self.expires_at = expires_at
        self.attempts = 0
        self.max_attempts = 5
        self.resend_count = 0
        self.is_used = False
        self.created_at = datetime.now(timezone.utc)


class AuthService:
    def __init__(self):
        # Fast memory cache for OTP validation
        self._otp_store: Dict[Tuple[str, str], OTPRecord] = {}

    def _hash_otp(self, email: str, code: str) -> str:
        """Securely hash OTP with email salt."""
        return hashlib.sha256(f"{email.lower().strip()}:{code}".encode()).hexdigest()

    def generate_and_store_otp(
        self,
        email: str,
        action: str,
        db: Optional[Session] = None,
        name: Optional[str] = None,
        phone: Optional[str] = None
    ) -> str:
        """Generates random 6-digit OTP, hashes it, stores with expiry/rate-limit, and dispatches via MailService."""
        email_clean = email.lower().strip()
        key = (email_clean, action)

        now = datetime.now(timezone.utc)

        # Database checks before sending OTP
        if db:
            if action == "register":
                existing_email = db.query(User).filter(User.email == email_clean).first()
                if existing_email:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="This email is already registered. Please sign in."
                    )
                if phone and phone.strip():
                    phone_clean = phone.strip()
                    existing_phone = db.query(User).filter(User.phone == phone_clean).first()
                    if existing_phone:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="This mobile number is already registered. Please sign in."
                        )
            elif action == "forgot":
                existing_user = db.query(User).filter(User.email == email_clean).first()
                if not existing_user:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="No account found with this email address."
                    )

        existing = self._otp_store.get(key)

        # Rate limit: 60 seconds cooldown between resends
        if existing and not existing.is_used and (now - existing.created_at).total_seconds() < 60:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Please wait at least 60 seconds before requesting a new OTP."
            )

        # Rate limit: max 5 resends per session
        resends = existing.resend_count + 1 if existing else 0
        if resends > 5:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many OTP requests for this email. Please try again later."
            )

        # Generate 6-digit OTP
        code = str(random.randint(100000, 999999))
        hashed = self._hash_otp(email_clean, code)
        expires_at = now + timedelta(minutes=10)

        record = OTPRecord(hashed, action, expires_at)
        record.resend_count = resends
        self._otp_store[key] = record

        # Persist to database if db session provided
        if db:
            try:
                db_record = OtpVerification(
                    email=email_clean,
                    action=action,
                    otp_hash=hashed,
                    attempts=0,
                    resend_count=resends,
                    last_sent_at=now,
                    expires_at=expires_at,
                    is_used=False
                )
                db.add(db_record)
                db.commit()
            except Exception:
                db.rollback()

        # Dispatch via MailService
        sent_ok = True
        if action == "register":
            sent_ok = mail_service.send_verification_otp(email_clean, code, name=name)
        elif action == "forgot":
            sent_ok = mail_service.send_password_reset_otp(email_clean, code)
        elif action == "profile_update":
            sent_ok = mail_service.send_profile_verification_otp(email_clean, code)

        if not sent_ok:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to send verification email. Please try again later."
            )

        return code

    def verify_otp(self, email: str, action: str, code: str, consume: bool = True) -> bool:
        """Validates OTP hash, single-use, and attempt limit."""
        email_clean = email.lower().strip()
        key = (email_clean, action)
        record = self._otp_store.get(key)
        if not record:
            return False

        now = datetime.now(timezone.utc)
        if record.is_used or now > record.expires_at:
            return False

        if record.attempts >= record.max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Maximum verification attempts exceeded. Please request a new OTP."
            )

        record.attempts += 1
        expected_hash = self._hash_otp(email_clean, code)
        if secrets.compare_digest(record.hashed_code, expected_hash):
            if consume:
                record.is_used = True
            return True
        return False

    def register_user(self, db: Session, req: RegisterRequest) -> Tuple[User, str, str]:
        """Registers a new user and returns (user, token, csrf_token)."""
        email_clean = req.email.lower().strip()
        
        # Check if user already exists
        existing_email = db.query(User).filter(User.email == email_clean).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This email is already registered. Please sign in."
            )

        phone_clean = req.phone.strip()
        existing_phone = db.query(User).filter(User.phone == phone_clean).first()
        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This mobile number is already registered. Please sign in."
            )

        # Validate OTP if provided
        if req.otp:
            is_valid = self.verify_otp(email_clean, "register", req.otp, consume=True)
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired OTP."
                )

        new_user = User(
            name=req.name.strip(),
            phone=req.phone.strip(),
            email=email_clean,
            password_hash=hash_password(req.password),
            role=req.role if req.role in {"Owner", "Agent", "Builder"} else "Owner",
            status="active",
            listing_limit=1,
            leads_balance=0,
            leads_used=0
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        token = create_access_token(subject=new_user.id, role=new_user.role)
        csrf = generate_csrf_token()
        return new_user, token, csrf

    def login_user(self, db: Session, req: LoginRequest) -> Tuple[User, str, str]:
        """Authenticates user and returns (user, token, csrf_token)."""
        email_clean = req.email.lower().strip()
        user = db.query(User).filter(User.email == email_clean).first()
        if not user or not verify_password(req.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password."
            )

        if user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive or suspended. Please contact support."
            )

        token = create_access_token(subject=user.id, role=user.role)
        csrf = generate_csrf_token()
        return user, token, csrf


auth_service = AuthService()
