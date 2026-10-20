import csv
import io
import re
from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_current_admin, get_db
from app.core.security import hash_password, verify_password
from app.db.models.user import User
from app.schemas.common import APIResponse, MessageResponse
from app.schemas.user import (
    UserRead, UserProfileUpdate, ChangePasswordRequest,
    AdminUserCreate, AdminUserUpdate, RoleUpdateRequest,
    BulkUserUploadResponse, BulkUserCreatedItem, BulkUserItemError
)
from app.services.auth_service import auth_service
from app.services.listing_assignment import claim_assigned_listings

router = APIRouter(prefix="/api/v1", tags=["Users"])


# --- USER PROFILE ENDPOINTS ---

PROFILE_FIELDS = ("business_name", "whatsapp", "facebook_url", "website_url", "x_url", "youtube_url")


def _apply_profile_fields(user: User, req) -> None:
    """Copies the optional business-profile fields that were sent; blank values clear a field."""
    for field in PROFILE_FIELDS:
        if field in req.model_fields_set:
            value = (getattr(req, field) or "").strip()
            setattr(user, field, value or None)


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
        if not auth_service.verify_otp(email_clean, "profile_update", otp, consume=True, db=db):
            raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

        if email_clean != current_user.email:
            exists = db.query(User).filter(User.email == email_clean, User.id != current_user.id).first()
            if exists:
                raise HTTPException(status_code=400, detail="Email is already in use by another account.")
            current_user.email = email_clean
        current_user.name = name_clean
        current_user.phone = phone_clean

    _apply_profile_fields(current_user, req)

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
    # Deactivated accounts (status "deleted") stay listed so admins can reactivate or permanently delete them.
    query = db.query(User)
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
    _apply_profile_fields(new_user, req)
    db.add(new_user)
    db.flush()
    claim_assigned_listings(db, new_user)
    db.commit()
    db.refresh(new_user)
    return APIResponse(status="success", data=UserRead.model_validate(new_user))


@router.post("/admin/users/bulk-upload", response_model=APIResponse[BulkUserUploadResponse])
async def bulk_upload_admin_users(
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Bulk import users from an Excel (.xlsx/.xls) or CSV (.csv) file.
    Expected columns: Email, Name (or Username), Phone.
    Optional columns: Role, Business Name, WhatsApp.
    Password is automatically set to the user's email address.
    """
    filename = (file.filename or "").lower()
    if not (filename.endswith(".csv") or filename.endswith(".xlsx") or filename.endswith(".xls")):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Please upload an Excel (.xlsx/.xls) or CSV (.csv) file."
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    rows: List[List[Any]] = []
    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
            sheet = wb.active
            rows = [list(row) for row in sheet.iter_rows(values_only=True)]
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Failed to read Excel file: {str(exc)}")
    else:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        reader = csv.reader(io.StringIO(text))
        rows = [list(row) for row in reader]

    if not rows or len(rows) < 2:
        raise HTTPException(status_code=400, detail="The file has no data rows. At least one user row is required.")

    # Parse headers
    raw_headers = [str(cell or "").strip().lower() for cell in rows[0]]
    col_email = -1
    col_name = -1
    col_phone = -1
    col_role = -1
    col_business_name = -1
    col_whatsapp = -1

    for idx, h in enumerate(raw_headers):
        clean_h = re.sub(r"[^a-z0-9]", "", h)
        if clean_h in ("email", "emailaddress", "emailid", "mail", "mailid") or "email" in clean_h:
            if col_email == -1:
                col_email = idx
        elif clean_h in ("name", "username", "fullname", "user", "customername", "ownername") or "username" in clean_h or "fullname" in clean_h:
            if col_name == -1:
                col_name = idx
        elif clean_h in ("phone", "mobile", "mobileno", "phonenumber", "mobilenumber", "contact", "contactno") or "mobile" in clean_h or "phone" in clean_h:
            if col_phone == -1:
                col_phone = idx
        elif clean_h in ("role", "userrole", "accounttype", "type"):
            if col_role == -1:
                col_role = idx
        elif clean_h in ("businessname", "company", "companyname", "agency"):
            if col_business_name == -1:
                col_business_name = idx
        elif clean_h in ("whatsapp", "whatsappnumber", "whatsappno", "wa"):
            if col_whatsapp == -1:
                col_whatsapp = idx

    missing_columns = []
    if col_email == -1:
        missing_columns.append("Email")
    if col_name == -1:
        missing_columns.append("Name (or Username)")
    if col_phone == -1:
        missing_columns.append("Phone (or Mobile)")

    if missing_columns:
        cols_str = ", ".join(missing_columns)
        raise HTTPException(
            status_code=400,
            detail=f"Required column(s) missing: {cols_str}. Please update your spreadsheet with the missing column(s), fill in the required data, and resubmit."
        )

    def _clean_phone(val: Any) -> str:
        if val is None:
            return ""
        if isinstance(val, float):
            if val.is_integer():
                val = int(val)
            else:
                val = str(val).rstrip("0").rstrip(".")
        s = str(val).strip()
        if s.endswith(".0"):
            s = s[:-2]
        return s

    def _clean_role(val: Any) -> str:
        r = str(val or "").strip().lower()
        if r in ("agent", "broker"):
            return "Agent"
        elif r in ("builder", "developer"):
            return "Builder"
        elif r == "admin":
            return "Admin"
        return "Owner"

    seen_emails: set[str] = set()
    seen_phones: set[str] = set()
    created_users: List[BulkUserCreatedItem] = []
    errors: List[BulkUserItemError] = []
    total_data_rows = 0

    for row_idx, row in enumerate(rows[1:], start=2):
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue  # ignore blank rows
        total_data_rows += 1

        email_val = row[col_email] if 0 <= col_email < len(row) else None
        name_val = row[col_name] if 0 <= col_name < len(row) else None
        phone_val = row[col_phone] if 0 <= col_phone < len(row) else None
        role_val = row[col_role] if 0 <= col_role < len(row) else None
        bname_val = row[col_business_name] if 0 <= col_business_name < len(row) else None
        wa_val = row[col_whatsapp] if 0 <= col_whatsapp < len(row) else None

        email = str(email_val or "").strip().lower()
        phone = _clean_phone(phone_val)
        name = str(name_val or "").strip()
        role = _clean_role(role_val)
        business_name = str(bname_val or "").strip() or None
        whatsapp = _clean_phone(wa_val) or phone or None

        # Check for missing required row fields
        missing_fields = []
        if not name:
            missing_fields.append("Name")
        if not email:
            missing_fields.append("Email")
        if not phone:
            missing_fields.append("Phone")

        if missing_fields:
            fields_str = ", ".join(missing_fields)
            errors.append(BulkUserItemError(
                row=row_idx,
                email=email or None,
                reason=f"Required field(s) missing: {fields_str}. Please fill in the required information and resubmit."
            ))
            continue

        if "@" not in email or "." not in email.split("@")[-1] or len(email) < 5:
            errors.append(BulkUserItemError(
                row=row_idx,
                email=email,
                reason="Invalid email format. Please provide a valid email address and resubmit."
            ))
            continue

        if len(phone) < 7:
            errors.append(BulkUserItemError(
                row=row_idx,
                email=email,
                reason="Invalid phone number (minimum 7 digits required). Please provide a valid phone number and resubmit."
            ))
            continue

        if email in seen_emails:
            errors.append(BulkUserItemError(row=row_idx, email=email, reason="Duplicate email in upload file"))
            continue

        if phone in seen_phones:
            errors.append(BulkUserItemError(row=row_idx, email=email, reason=f"Duplicate phone '{phone}' in upload file"))
            continue

        if db.query(User.id).filter(User.email == email).first():
            errors.append(BulkUserItemError(row=row_idx, email=email, reason="Email is already registered"))
            continue

        if db.query(User.id).filter(User.phone == phone).first():
            errors.append(BulkUserItemError(row=row_idx, email=email, reason=f"Phone number '{phone}' is already registered"))
            continue

        seen_emails.add(email)
        seen_phones.add(phone)

        new_user = User(
            name=name,
            phone=phone,
            email=email,
            password_hash=hash_password(email),
            role=role,
            status="active",
            business_name=business_name,
            whatsapp=whatsapp,
            leads_balance=0,
            listing_limit=1
        )
        db.add(new_user)
        db.flush()
        claim_assigned_listings(db, new_user)

        created_users.append(BulkUserCreatedItem(
            id=new_user.id,
            name=new_user.name,
            email=new_user.email,
            phone=new_user.phone,
            role=new_user.role
        ))

    db.commit()

    return APIResponse(
        status="success",
        data=BulkUserUploadResponse(
            total_rows=total_data_rows,
            created_count=len(created_users),
            skipped_count=len(errors),
            created_users=created_users,
            errors=errors
        )
    )


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
    _apply_profile_fields(user, req)

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
