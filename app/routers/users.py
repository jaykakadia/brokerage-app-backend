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
    if req.email and req.email.lower().strip() != current_user.email:
        # If email changed, check if OTP was verified
        if req.otp:
            is_valid = auth_service.verify_otp(req.email, "profile_update", req.otp, consume=True)
            if not is_valid:
                raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
        # Check uniqueness
        exists = db.query(User).filter(User.email == req.email.lower().strip(), User.id != current_user.id).first()
        if exists:
            raise HTTPException(status_code=400, detail="Email is already in use by another account.")
        current_user.email = req.email.lower().strip()

    if req.name:
        current_user.name = req.name.strip()
    if req.phone:
        current_user.phone = req.phone.strip()

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
def create_or_update_admin_user(
    req: AdminUserCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    email_clean = req.email.lower().strip()
    existing = db.query(User).filter(User.email == email_clean).first()
    if existing:
        existing.name = req.name
        existing.phone = req.phone
        existing.role = req.role
        existing.status = req.status
        if req.password:
            existing.password_hash = hash_password(req.password)
        db.commit()
        db.refresh(existing)
        return APIResponse(status="success", data=UserRead.model_validate(existing))

    new_user = User(
        name=req.name,
        phone=req.phone,
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
    user.status = "deleted"
    db.commit()
    return MessageResponse(status="success", message="User deactivated successfully.")
