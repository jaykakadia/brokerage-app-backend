from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_current_admin, get_db
from app.core.security import hash_password, verify_password
from app.db.models.user import User
from app.schemas.common import APIResponse, MessageResponse
from app.schemas.user import (
    UserRead, UserProfileUpdate, ChangePasswordRequest,
    AdminUserCreate, AdminUserUpdate, RoleUpdateRequest
)
from app.services.auth_service import auth_service

router = APIRouter(prefix="/api/v1", tags=["Users"])


# --- USER PROFILE ENDPOINTS ---

@router.get("/users/profile", response_model=APIResponse[UserRead])
def get_profile(current_user: User = Depends(get_current_user)):
    return APIResponse(status="success", data=UserRead.model_validate(current_user))


@router.put("/users/profile", response_model=MessageResponse)
def update_profile(
    req: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    name_clean = req.name.strip() if req.name else current_user.name
    phone_clean = req.phone.strip() if req.phone else current_user.phone
    email_clean = req.email.lower().strip() if req.email else current_user.email

    # Name, phone and email identify the account, so changing them needs an OTP.
    # Business/social details can be saved without one.
    identity_changed = (
        name_clean != current_user.name
        or phone_clean != current_user.phone
        or email_clean != current_user.email
    )
    if identity_changed:
        otp = (req.otp or "").strip()
        if not otp:
            raise HTTPException(status_code=400, detail="OTP is required to change name, mobile or email.")
        if not auth_service.verify_otp(email_clean, "profile_update", otp, consume=True):
            raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

        if email_clean != current_user.email:
            exists = db.query(User).filter(User.email == email_clean, User.id != current_user.id).first()
            if exists:
                raise HTTPException(status_code=400, detail="Email is already in use by another account.")
            current_user.email = email_clean
        current_user.name = name_clean
        current_user.phone = phone_clean

    for field in ("business_name", "whatsapp", "facebook_url", "website_url", "x_url"):
        if field in req.model_fields_set:
            value = (getattr(req, field) or "").strip()
            setattr(current_user, field, value or None)

    db.commit()
    db.refresh(current_user)
    return MessageResponse(status="success", message="Profile updated successfully.")


@router.post("/users/change-password", response_model=MessageResponse)
def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not verify_password(req.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=400, detail="New password and confirm password do not match.")

    current_user.password_hash = hash_password(req.new_password)
    db.commit()
    return MessageResponse(status="success", message="Password changed successfully.")


# --- ADMIN USER MANAGEMENT ENDPOINTS ---

@router.get("/admin/users", response_model=APIResponse[List[UserRead]])
def list_admin_users(
    search: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    query = db.query(User).filter(User.status != "deleted")
    if role and role.lower() != "all":
        query = query.filter(User.role == role)
    if search:
        search_filter = f"%{search.strip()}%"
        query = query.filter(
            (User.name.ilike(search_filter)) |
            (User.email.ilike(search_filter)) |
            (User.phone.ilike(search_filter))
        )
    users = query.order_by(User.id.desc()).all()
    return APIResponse(status="success", data=[UserRead.model_validate(u) for u in users])


@router.get("/admin/users/{user_id}", response_model=APIResponse[UserRead])
def get_admin_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return APIResponse(status="success", data=UserRead.model_validate(user))


@router.post("/admin/users", response_model=APIResponse[UserRead])
def create_admin_user(
    req: AdminUserCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    # Create-only: never overwrite an existing account (and its password) from this form.
    email_clean = req.email.lower().strip()
    phone_clean = req.phone.strip()
    if db.query(User).filter(User.email == email_clean).first():
        raise HTTPException(status_code=409, detail="A user with this email already exists.")
    if db.query(User).filter(User.phone == phone_clean).first():
        raise HTTPException(status_code=409, detail="A user with this mobile number already exists.")

    new_user = User(
        name=req.name.strip(),
        phone=phone_clean,
        email=email_clean,
        password_hash=hash_password(req.password),
        role=req.role,
        status=req.status,
        plan_id=req.plan_id,
        leads_balance=req.leads_balance or 0,
        plan_expires_at=req.plan_expires_at
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return APIResponse(status="success", data=UserRead.model_validate(new_user))


@router.post("/admin/users/{user_id}/role", response_model=MessageResponse)
def update_user_role(
    user_id: int,
    req: RoleUpdateRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if req.role != "Admin" and user.role.lower() == "admin":
        _guard_admin_removal(db, admin, user)
    user.role = req.role
    db.commit()
    return MessageResponse(status="success", message=f"User role updated to {req.role}.")


@router.post("/admin/users/{user_id}/delete", response_model=MessageResponse)
def soft_delete_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.role.lower() == "admin":
        _guard_admin_removal(db, admin, user)
    user.status = "deleted"
    db.commit()
    return MessageResponse(status="success", message="User deactivated successfully.")


def _guard_admin_removal(db: Session, admin: User, user: User) -> None:
    """Called before an account loses admin access: admins can't lock themselves out, and at least one active admin must remain."""
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot remove, deactivate or demote your own admin account.")
    if user.role.lower() == "admin":
        active_admins = db.query(User).filter(User.role == "Admin", User.status == "active").count()
        if user.status == "active" and active_admins <= 1:
            raise HTTPException(status_code=400, detail="At least one active admin account is required.")


@router.put("/admin/users/{user_id}", response_model=APIResponse[UserRead])
def update_admin_user(
    user_id: int,
    req: AdminUserUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if req.status is not None and req.status not in ("active", "deleted"):
        raise HTTPException(status_code=400, detail="Status must be 'active' or 'deleted'.")
    losing_admin = (
        (req.role is not None and req.role != "Admin")
        or (req.status is not None and req.status != "active")
    )
    if losing_admin and user.role.lower() == "admin":
        _guard_admin_removal(db, admin, user)

    if req.email is not None:
        email_clean = req.email.lower().strip()
        if email_clean != user.email and db.query(User).filter(User.email == email_clean, User.id != user.id).first():
            raise HTTPException(status_code=409, detail="A user with this email already exists.")
        user.email = email_clean
    if req.phone is not None:
        phone_clean = req.phone.strip()
        if len(phone_clean) < 5:
            raise HTTPException(status_code=400, detail="Enter a valid mobile number.")
        if phone_clean != user.phone and db.query(User).filter(User.phone == phone_clean, User.id != user.id).first():
            raise HTTPException(status_code=409, detail="A user with this mobile number already exists.")
        user.phone = phone_clean
    if req.name is not None:
        if not req.name.strip():
            raise HTTPException(status_code=400, detail="Name cannot be empty.")
        user.name = req.name.strip()
    if req.password:
        if len(req.password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
        user.password_hash = hash_password(req.password)
    if req.role is not None:
        user.role = req.role
    if req.status is not None:
        user.status = req.status

    db.commit()
    db.refresh(user)
    return APIResponse(status="success", data=UserRead.model_validate(user))


@router.delete("/admin/users/{user_id}", response_model=MessageResponse)
def delete_admin_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Permanently deletes the account and its listings/wishlist; orders and lead reveals are kept with the user cleared."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.role.lower() == "admin":
        _guard_admin_removal(db, admin, user)
    db.delete(user)
    db.commit()
    return MessageResponse(status="success", message="User deleted permanently.")
