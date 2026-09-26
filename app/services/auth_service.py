import hashlib
import random
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password, create_access_token, generate_csrf_token
from app.db.models.user import User
from app.schemas.auth import RegisterRequest, LoginRequest


class OTPRecord:
    def __init__(self, hashed_code: str, action: str, expires_at: datetime):
        self.hashed_code = hashed_code
        self.action = action
        self.expires_at = expires_at
        self.attempts = 0
        self.max_attempts = 5
        self.is_used = False
        self.created_at = datetime.now(timezone.utc)


class AuthService:
    def __init__(self):
        # In-memory storage for OTPs with hashed codes
        self._otp_store: Dict[Tuple[str, str], OTPRecord] = {}

    def _hash_otp(self, email: str, code: str) -> str:
        """Securely hash OTP with email salt."""
        return hashlib.sha256(f"{email.lower().strip()}:{code}".encode()).hexdigest()

    def generate_and_store_otp(self, email: str, action: str) -> str:
        """Generates random 6-digit OTP, hashes it, and stores with expiry and rate-limit."""
        email_clean = email.lower().strip()
        key = (email_clean, action)

        # Rate limiting: 60 seconds cooldown
        existing = self._otp_store.get(key)
        now = datetime.now(timezone.utc)
        if existing and not existing.is_used and (now - existing.created_at).total_seconds() < 60:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Please wait at least 60 seconds before requesting a new OTP."
            )

        # Generate 6-digit OTP
        code = str(random.randint(100000, 999999))
        hashed = self._hash_otp(email_clean, code)
        expires_at = now + timedelta(minutes=10)

        self._otp_store[key] = OTPRecord(hashed, action, expires_at)
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
        existing = db.query(User).filter(User.email == email_clean).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email address already exists."
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
            role="Owner",
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
