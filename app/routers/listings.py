import os
import json
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.dependencies import get_current_user, get_current_admin, get_optional_user, get_db
from app.db.models.listing import Listing, ListingImage
from app.db.models.lead import LeadReveal
from app.db.models.user import User
from app.schemas.common import APIResponse, MessageResponse
from app.schemas.listing import (
    ListingRead, ListingCreate, ListingUpdate, ListingStatusUpdate, ListingCountsResponse
)
from app.services.storage_service import storage_service

router = APIRouter(prefix="/api/v1/listings", tags=["Listings"])


# Listing links a viewer only gets by unlocking the contact (POST /api/v1/leads/reveal)
LOCKED_FORM_FIELDS = ("websiteUrl", "facebookUrl", "xUrl", "youtubeUrl")


def _listing_for_viewer(listing: Listing, user: Optional[User], unlocked: bool = False) -> dict:
    """Serializes a listing, leaving out the locked links unless the viewer owns it, is an admin or unlocked it."""
    data = ListingRead.model_validate(listing).model_dump()
    can_see = unlocked or (user is not None and (user.role.lower() == "admin" or user.id == listing.user_id))
    if not can_see and isinstance(data.get("form_data"), dict):
        data["form_data"] = {k: v for k, v in data["form_data"].items() if k not in LOCKED_FORM_FIELDS}
    return data


def _expire_featured(db: Session) -> None:
    """Un-features listings whose paid featured period has ended."""
    expired = db.query(Listing).filter(
        Listing.is_featured == True,
        Listing.featured_until.isnot(None),
        Listing.featured_until <= datetime.now(timezone.utc)
    ).update({Listing.is_featured: False, Listing.featured_until: None}, synchronize_session=False)
    if expired:
        db.commit()


@router.get("/counts", response_model=ListingCountsResponse)
def get_listing_counts(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    counts = db.query(Listing.status, func.count(Listing.id)).group_by(Listing.status).all()
    count_dict = {
        "pending": 0,
        "approved": 0,
        "suspended": 0,
        "sold": 0,
        "rented": 0,
        "deleted": 0
    }
    for st, count in counts:
        if st in count_dict:
            count_dict[st] = count
    return ListingCountsResponse(status="success", data=count_dict)


@router.get("/stats")
def get_public_stats(db: Session = Depends(get_db)):
    """Public endpoint — returns site-wide stats for the login page hero."""
    _expire_featured(db)
    active = db.query(func.count(Listing.id)).filter(Listing.status == "approved").scalar() or 0
    featured = db.query(func.count(Listing.id)).filter(
        Listing.status == "approved", Listing.is_featured == True
    ).scalar() or 0
    cities = db.query(func.count(func.distinct(Listing.location))).filter(
        Listing.status == "approved", Listing.location.isnot(None)
    ).scalar() or 0
    users = db.query(func.count(User.id)).scalar() or 0
    return {
        "active_listings": active,
        "featured_listings": featured,
        "cities_covered": cities,
        "registered_users": users,
    }


@router.get("", response_model=dict)
def get_listings(
    status: Optional[str] = Query("approved"),
    city: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    ref_code: Optional[str] = Query(None),
    ref_name: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    _expire_featured(db)
    query = db.query(Listing)

    # Filter by user_id if requested (e.g. My Listings in Account)
    if user_id:
        query = query.filter(Listing.user_id == user_id)

    # Status filter
    if status and status.lower() != "all":
        query = query.filter(Listing.status == status.lower())
    elif not user_id and (not user or user.role.lower() != "admin"):
        # Unauthenticated or non-admin users default to approved when not querying specific user
        query = query.filter(Listing.status == "approved")

    # City filter
    if city:
        query = query.filter(Listing.location.ilike(f"%{city.strip()}%"))

    # Search filter (title / description / location)
    if search:
        s_filter = f"%{search.strip()}%"
        query = query.filter(
            (Listing.title.ilike(s_filter)) |
            (Listing.location.ilike(s_filter)) |
            (Listing.description.ilike(s_filter))
        )

    # Reference code filter
    if ref_code:
        query = query.filter(Listing.reference_code == ref_code.strip())

    listings = query.order_by(Listing.id.desc()).all()

    # Build reference summary counts for admin
    ref_summary = []
    if user and user.role.lower() == "admin":
        summary_query = db.query(
            Listing.reference_code,
            func.count(Listing.id).label("total")
        ).filter(Listing.reference_code.isnot(None))\
         .group_by(Listing.reference_code).all()
        ref_summary = [{"reference_code": r[0], "total": r[1]} for r in summary_query if r[0]]

    return {
        "status": "success",
        "data": [_listing_for_viewer(l, user) for l in listings],
        "ref_summary": ref_summary
    }


@router.get("/{listing_id}", response_model=APIResponse[ListingRead])
def get_listing(
    listing_id: str,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    _expire_featured(db)
    clean_id = listing_id.strip()
    numeric_part = clean_id
    if clean_id.upper().startswith("TC011P-"):
        numeric_part = clean_id[7:]
    elif clean_id.upper().startswith("TC-"):
        numeric_part = clean_id[3:]

    listing = None
    if numeric_part.isdigit():
        listing = db.query(Listing).filter(Listing.id == int(numeric_part)).first()

    if not listing:
        listing = db.query(Listing).filter(
            (Listing.reference_code == clean_id) | (Listing.reference_code == clean_id.upper())
        ).first()

    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")
    unlocked = user is not None and db.query(LeadReveal).filter(
        LeadReveal.user_id == user.id, LeadReveal.listing_id == listing.id
    ).first() is not None
    return APIResponse(status="success", data=_listing_for_viewer(listing, user, unlocked))


@router.post("", response_model=APIResponse[ListingRead])
async def create_listing(
    title: str = Form(...),
    location: str = Form(...),
    price: float = Form(0.0),
    description: Optional[str] = Form(None),
    owner_name: str = Form(...),
    owner_role: str = Form("Owner"),
    reference_code: Optional[str] = Form(None),
    form_data: Optional[str] = Form(None),
    photos: List[UploadFile] = File(default=[]),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Rule 1: Validate title words length (<= 50 words)
    words = title.strip().split()
    if len(words) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Listing title cannot exceed 50 words. Current words: {len(words)}"
        )

    # Validate owner_role against canonical roles
    if owner_role not in {"Owner", "Agent", "Builder", "Admin"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid owner_role '{owner_role}'. Allowed roles: Owner, Agent, Builder, Admin"
        )

    # Parse JSON form_data if provided
    parsed_form_data = None
    if form_data:
        try:
            parsed_form_data = json.loads(form_data)
        except Exception:
            parsed_form_data = form_data

    # Validate uploaded photos upfront
    for photo in photos[:10]:
        if photo.filename:
            ext = os.path.splitext(photo.filename)[1].lower()
            if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported file extension '{ext}'. Allowed extensions: ['.jpg', '.jpeg', '.png', '.webp']"
                )

    # Enforce listing limits for non-admin users
    if current_user.role.lower() != "admin":
        user_active_listings = db.query(Listing).filter(
            Listing.user_id == current_user.id,
            Listing.status != "deleted"
        ).count()

        # Check if user has an active purchased plan
        now = datetime.now(timezone.utc)
        has_active_plan = current_user.plan_id and (
            not current_user.plan_expires_at or current_user.plan_expires_at > now
        )

        if has_active_plan and current_user.listing_limit > 0:
            allowed_limit = current_user.listing_limit
        else:
            from app.db.models.role_limit import RoleLimit
            rl = db.query(RoleLimit).filter(RoleLimit.role == current_user.role).first()
            allowed_limit = rl.max_listings if rl else 0

        # Only enforce when limit is set > 0
        if allowed_limit and allowed_limit > 0 and user_active_listings >= allowed_limit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You have reached your maximum listing limit ({allowed_limit}) for {current_user.role} accounts. Please upgrade your plan to post more listings."
            )

    # Link field associate employee if reference code provided
    ref_code_clean = reference_code.strip().upper() if reference_code else None
    employee_id = None
    if ref_code_clean:
        from app.db.models.employee import Employee
        emp = db.query(Employee).filter(
            Employee.reference_code == ref_code_clean,
            Employee.status == "active"
        ).first()
        if emp:
            employee_id = emp.id

    # Initial status: Admin gets approved by default if desired, user gets pending
    init_status = "approved" if current_user.role.lower() == "admin" else "pending"

    listing = Listing(
        user_id=current_user.id,
        title=title.strip(),
        location=location.strip(),
        price=price,
        description=description,
        owner_name=owner_name.strip(),
        owner_role=owner_role.strip(),
        reference_code=ref_code_clean,
        employee_id=employee_id,
        status=init_status,
        verified=0,
        form_data=parsed_form_data
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)

    # Save photos if any
    for idx, photo in enumerate(photos[:10]):
        if photo.filename:
            rel_path, orig_name, f_size, m_type = await storage_service.validate_and_save_listing_image(
                listing.id, photo
            )
            img = ListingImage(
                listing_id=listing.id,
                file_path=rel_path,
                original_filename=orig_name,
                mime_type=m_type,
                file_size=f_size,
                sort_order=idx
            )
            db.add(img)

    db.commit()
    db.refresh(listing)
    return APIResponse(status="success", data=ListingRead.model_validate(listing))


@router.patch("/{listing_id}", response_model=APIResponse[ListingRead])
@router.post("/{listing_id}", response_model=APIResponse[ListingRead])
async def update_listing(
    listing_id: int,
    title: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    price: Optional[float] = Form(None),
    description: Optional[str] = Form(None),
    owner_name: Optional[str] = Form(None),
    owner_role: Optional[str] = Form(None),
    reference_code: Optional[str] = Form(None),
    form_data: Optional[str] = Form(None),
    remove_image_ids: Optional[str] = Form(None),  # comma-separated ListingImage ids to delete
    photos: List[UploadFile] = File(default=[]),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")

    # Authorization: Owner or Admin
    if listing.user_id != current_user.id and current_user.role.lower() != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to edit this listing.")

    if title is not None:
        words = title.strip().split()
        if len(words) > 50:
            raise HTTPException(status_code=400, detail="Listing title cannot exceed 50 words.")
        listing.title = title.strip()
    if location is not None:
        listing.location = location.strip()
    if price is not None:
        listing.price = price
    if description is not None:
        listing.description = description
    if owner_name is not None:
        listing.owner_name = owner_name.strip()
    if owner_role is not None:
        if owner_role not in {"Owner", "Agent", "Builder", "Admin"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid owner_role '{owner_role}'. Allowed roles: Owner, Agent, Builder, Admin"
            )
        listing.owner_role = owner_role.strip()
    if reference_code is not None:
        listing.reference_code = reference_code.strip() if reference_code else None
    if form_data is not None:
        try:
            listing.form_data = json.loads(form_data)
        except ValueError:
            raise HTTPException(status_code=400, detail="form_data must be valid JSON.")

    removed_files: List[str] = []
    if remove_image_ids:
        ids = {int(part) for part in remove_image_ids.split(",") if part.strip().isdigit()}
        for img in [i for i in listing.images if i.id in ids]:
            removed_files.append(img.file_path)
            listing.images.remove(img)
        db.flush()

    # Handle additional photos
    start_order = max((img.sort_order for img in listing.images), default=-1) + 1
    for idx, photo in enumerate(photos[:10]):
        if photo.filename:
            rel_path, orig_name, f_size, m_type = await storage_service.validate_and_save_listing_image(
                listing.id, photo
            )
            img = ListingImage(
                listing_id=listing.id,
                file_path=rel_path,
                original_filename=orig_name,
                mime_type=m_type,
                file_size=f_size,
                sort_order=start_order + idx
            )
            db.add(img)

    db.commit()
    # Remove files only once the database change is saved
    for path in removed_files:
        storage_service.delete_file(path)
    db.refresh(listing)
    return APIResponse(status="success", data=ListingRead.model_validate(listing))


@router.post("/{listing_id}/status", response_model=MessageResponse)
def update_listing_status(
    listing_id: int,
    req: ListingStatusUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")

    action = req.action.lower()
    if action == "approve":
        listing.status = "approved"
    elif action == "pending":
        listing.status = "pending"
    elif action == "suspended":
        listing.status = "suspended"
    elif action == "sold":
        listing.status = "sold"
    elif action == "rented":
        listing.status = "rented"
    elif action == "delete":
        listing.status = "deleted"
    elif action == "stamp":
        listing.verified = 1
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action '{req.action}'.")

    db.commit()
    return MessageResponse(status="success", message=f"Listing status updated via action '{action}'.")


@router.delete("/{listing_id}", response_model=MessageResponse)
@router.post("/{listing_id}/delete", response_model=MessageResponse)
def delete_listing(
    listing_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")

    if listing.user_id != current_user.id and current_user.role.lower() != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to delete this listing.")

    # Physical file cleanup
    storage_service.delete_listing_folder(listing.id)

    db.delete(listing)
    db.commit()
    return MessageResponse(status="success", message="Listing deleted successfully.")
