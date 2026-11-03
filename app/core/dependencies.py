from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.db.models.user import User
from app.core.audit import set_audit_actor


def get_token_from_request(request: Request) -> Optional[str]:
    # 1. First check HTTP-only cookie
    token = request.cookies.get(settings.COOKIE_NAME)
    if token:
        return token
    # 2. Check Authorization Bearer header as fallback for tests/API clients
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    return None


def get_optional_user(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None)
    token = get_token_from_request(request)
    if not token:
        set_audit_actor(user_id=None, email="anonymous", role="anonymous", ip_address=client_ip)
        return None
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        set_audit_actor(user_id=None, email="anonymous", role="anonymous", ip_address=client_ip)
        return None
    try:
        user_id = int(payload["sub"])
    except (ValueError, TypeError):
        set_audit_actor(user_id=None, email="anonymous", role="anonymous", ip_address=client_ip)
        return None
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.status != "active" or getattr(user, "is_deleted", False):
        set_audit_actor(user_id=None, email="anonymous", role="anonymous", ip_address=client_ip)
        return None
    set_audit_actor(user_id=user.id, email=user.email, role=user.role, ip_address=client_ip)
    return user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    user = get_optional_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return user


def get_current_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.role.lower() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required."
        )
    return current_user
