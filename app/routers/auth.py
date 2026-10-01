from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_user, get_db
from app.core.security import generate_csrf_token
from app.db.models.user import User
from app.schemas.auth import (
    LoginRequest, RegisterRequest, SendOtpRequest, VerifyOtpRequest,
    ResetPasswordRequest, AuthResponse, BootstrapAdminRequest
)
from app.schemas.common import APIResponse, MessageResponse
from app.schemas.user import UserRead
from app.services.auth_service import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


def _set_auth_cookie(response: Response, token: str, remember_me: bool = False):
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        max_age=30 * 24 * 60 * 60 if remember_me else None,  # 30 days or session cookie
        path="/"
    )


def _clear_auth_cookie(response: Response):
    response.delete_cookie(
        key=settings.COOKIE_NAME,
        domain=settings.COOKIE_DOMAIN,
        path="/"
    )


@router.get("/csrf")
def get_csrf():
    """Generates a fresh CSRF token."""
    return {"status": "success", "csrf_token": generate_csrf_token()}


@router.post("/send-otp", response_model=MessageResponse)
def send_otp(req: SendOtpRequest, db: Session = Depends(get_db)):
    auth_service.generate_and_store_otp(req.email, req.action, db=db, name=req.name, phone=req.phone)
    return MessageResponse(
        status="success",
        message="OTP sent to your email. Valid for 10 minutes."
    )


@router.post("/verify-otp", response_model=MessageResponse)
def verify_otp(req: VerifyOtpRequest):
    is_valid = auth_service.verify_otp(req.email, "register", req.otp, consume=False)
    if not is_valid:
        # Also check for forgot/profile_update
        is_valid = auth_service.verify_otp(req.email, "forgot", req.otp, consume=False)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP."
        )
    return MessageResponse(status="success", message="OTP verified successfully.")


@router.post("/register", response_model=AuthResponse)
def register(
    req: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    user, token, csrf = auth_service.register_user(db, req)
    _set_auth_cookie(response, token)
    return AuthResponse(
        status="success",
        message="Account created successfully!",
        redirect="account.php",
        csrf_token=csrf,
        user=UserRead.model_validate(user)
    )


@router.get("/admin-setup")
def admin_setup_status(db: Session = Depends(get_db)):
    return {"needs_admin": not auth_service.admin_exists(db)}


@router.post("/bootstrap-admin", response_model=AuthResponse)
def bootstrap_admin(
    req: BootstrapAdminRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    user, token, csrf = auth_service.bootstrap_admin(db, req)
    _set_auth_cookie(response, token)
    return AuthResponse(
        status="success",
        message="Admin account created.",
        redirect="admin-dashboard.php",
        csrf_token=csrf,
        user=UserRead.model_validate(user)
    )


@router.post("/login", response_model=AuthResponse)
def login(
    req: LoginRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    user, token, csrf = auth_service.login_user(db, req)
    _set_auth_cookie(response, token, remember_me=req.remember_me)
    redirect_target = "admin-dashboard.php" if user.role.lower() == "admin" else "account.php"
    return AuthResponse(
        status="success",
        message="Login successful",
        redirect=redirect_target,
        csrf_token=csrf,
        user=UserRead.model_validate(user)
    )


@router.post("/logout", response_model=MessageResponse)
def logout(response: Response):
    _clear_auth_cookie(response)
    return MessageResponse(status="success", message="Successfully logged out.")


@router.get("/me", response_model=APIResponse[UserRead])
def get_me(current_user: User = Depends(get_current_user)):
    return APIResponse(
        status="success",
        data=UserRead.model_validate(current_user)
    )


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    req: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    email_clean = req.email.lower().strip()
    otp = (req.otp or "").strip()
    if not otp:
        raise HTTPException(status_code=400, detail="OTP is required to reset your password.")
    if not auth_service.verify_otp(email_clean, "forgot", otp, consume=True):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

    user = db.query(User).filter(User.email == email_clean).first()
    if not user:
        raise HTTPException(status_code=404, detail="No account found with this email.")

    from app.core.security import hash_password
    user.password_hash = hash_password(req.new_password)
    db.commit()
    return MessageResponse(status="success", message="Password reset successfully! Please sign in.")
