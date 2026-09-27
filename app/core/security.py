import hmac
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(subject: str | int, role: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create signed JWT access token."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    payload: Dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp())
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate JWT access token."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except (jwt.PyJWTError, Exception):
        return None


def generate_csrf_token() -> str:
    """Generate a secure cryptographic CSRF token."""
    random_bytes = secrets.token_bytes(32)
    sig = hmac.new(settings.CSRF_SECRET_KEY.encode(), random_bytes, hashlib.sha256).hexdigest()
    return f"{random_bytes.hex()}.{sig}"


def verify_csrf_token(token: str) -> bool:
    """Verify CSRF token HMAC signature."""
    if not token or "." not in token:
        return False
    parts = token.split(".", 1)
    if len(parts) != 2:
        return False
    random_hex, received_sig = parts
    try:
        random_bytes = bytes.fromhex(random_hex)
        expected_sig = hmac.new(settings.CSRF_SECRET_KEY.encode(), random_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, received_sig)
    except Exception:
        return False


def _get_fernet():
    import base64
    from cryptography.fernet import Fernet
    # Derive deterministic 32-byte urlsafe base64 key from settings.SECRET_KEY
    key_bytes = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_secret(plain_text: str) -> str:
    """Encrypt sensitive string at rest using Fernet (AES-128-CBC + HMAC)."""
    if not plain_text:
        return ""
    f = _get_fernet()
    return f.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_secret(cipher_text: str) -> str:
    """Decrypt sensitive string from rest storage."""
    if not cipher_text:
        return ""
    try:
        f = _get_fernet()
        return f.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except Exception:
        # Fallback to plain text if not yet encrypted (legacy data)
        return cipher_text

