import hashlib
import random
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple, Optional
from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password, create_access_token, generate_csrf_token
from app.db.models.user import User
from app.db.models.otp import OtpVerification
from app.schemas.auth import BootstrapAdminRequest, RegisterRequest, LoginRequest
from app.services.mail_service import mail_service
from app.services.listing_assignment import claim_assigned_listings


OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5


def _as_utc(value: datetime) -> datetime:
    # SQLite hands back naive datetimes even for timezone-aware columns
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class OTPRecord:
    def __init__(self, hashed_code: str, action: str, expires_at: datetime):
        self.hashed_code = hashed_code
        self.action = action
        self.expires_at = expires_at
        self.attempts = 0
        self.max_attempts = OTP_MAX_ATTEMPTS
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
        # The API runs several worker processes, each with its own _otp_store, so the
        # database row is the shared view of the last OTP sent for this email.
        latest_row = self._latest_otp_row(db, email_clean, action) if db else None
        if latest_row:
            existing = OTPRecord(latest_row.otp_hash, action, _as_utc(latest_row.expires_at))
            existing.created_at = _as_utc(latest_row.last_sent_at)
            existing.resend_count = latest_row.resend_count
            existing.is_used = latest_row.is_used

        # Rate limit: 60 seconds cooldown between resends
        if existing and not existing.is_used:
            wait = OTP_RESEND_COOLDOWN_SECONDS - int((now - existing.created_at).total_seconds())
            if wait > 0:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"An OTP was just sent to this email. Check your inbox, or request a new one in {wait} seconds.",
                    headers={"Retry-After": str(wait)}
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

        # Dispatch via MailService. The OTP is stored only once the email has gone out,
        # so a failed send never starts the resend cooldown.
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

        return code

    @staticmethod
    def _latest_otp_row(db: Session, email: str, action: str) -> Optional[OtpVerification]:
        return (
            db.query(OtpVerification)
            .filter(OtpVerification.email == email, OtpVerification.action == action)
            .order_by(OtpVerification.id.desc())
            .first()
        )

    def verify_otp(
        self, email: str, action: str, code: str, consume: bool = True, db: Optional[Session] = None
    ) -> bool:
        """Validates OTP hash, single-use, and attempt limit.

        With a db session the stored OtpVerification row is authoritative, so the OTP
        verifies no matter which worker process sent it. Without one (or when no row
        exists) only this process's memory cache is checked.
        """
        email_clean = email.lower().strip()
        key = (email_clean, action)

        row = self._latest_otp_row(db, email_clean, action) if db else None
        if row:
            return self._verify_otp_row(db, row, key, email_clean, code, consume)

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

    def _verify_otp_row(
        self, db: Session, row: OtpVerification, key: Tuple[str, str], email_clean: str, code: str, consume: bool
    ) -> bool:
        now = datetime.now(timezone.utc)
        if row.is_used or now > _as_utc(row.expires_at):
            return False

        if row.attempts >= OTP_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Maximum verification attempts exceeded. Please request a new OTP."
            )

        row.attempts += 1
        matched = secrets.compare_digest(row.otp_hash, self._hash_otp(email_clean, code))
        if matched and consume:
            row.is_used = True
            cached = self._otp_store.get(key)
            if cached and cached.hashed_code == row.otp_hash:
                cached.is_used = True
        db.commit()
        return matched

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

        # Email OTP verification is mandatory for self-registration
        otp_clean = (req.otp or "").strip()
        if not otp_clean:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please verify your email with the OTP before creating an account."
            )
        if not self.verify_otp(email_clean, "register", otp_clean, consume=True, db=db):
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
            business_name=(req.business_name or "").strip() or None,
            status="active",
            listing_limit=1,
            leads_balance=0,
            leads_used=0
        )
        db.add(new_user)
        db.flush()
        claim_assigned_listings(db, new_user)
        db.commit()
        db.refresh(new_user)

        token = create_access_token(subject=new_user.id, role=new_user.role)
        csrf = generate_csrf_token()
        return new_user, token, csrf

    def admin_exists(self, db: Session) -> bool:
        count = db.query(func.count(User.id)).filter(func.lower(User.role) == "admin").scalar() or 0
        return count > 0

    def bootstrap_admin(self, db: Session, req: BootstrapAdminRequest) -> Tuple[User, str, str]:
        if self.admin_exists(db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="An admin account already exists. Sign in instead."
            )

        if req.confirm_password and req.confirm_password != req.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwords do not match."
            )

        email_clean = req.email.lower().strip()
        existing_email = db.query(User).filter(User.email == email_clean).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This email is already registered. Sign in, then an admin can change the role."
            )

        phone_clean = req.phone.strip()
        existing_phone = db.query(User).filter(User.phone == phone_clean).first()
        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This mobile number is already registered."
            )

        new_user = User(
            name=req.name.strip(),
            phone=phone_clean,
            email=email_clean,
            password_hash=hash_password(req.password),
            role="Admin",
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
