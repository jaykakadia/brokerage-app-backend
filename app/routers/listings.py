import os
import json
import math
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func, or_, cast, String

from app.core.dependencies import get_current_user, get_current_admin, get_optional_user, get_db
from app.db.models.listing import Listing, ListingImage
from app.db.models.lead import LeadReveal
from app.db.models.user import User
from app.schemas.common import APIResponse, MessageResponse
from app.schemas.listing import (
    ListingRead, ListingCreate, ListingUpdate, ListingStatusUpdate, ListingCountsResponse,
    ListingFeatureUpdate
)
from app.services.storage_service import storage_service
from app.services.listing_assignment import assign_listing_to_email
from app.services.mail_service import mail_service
from app.core.validation_rules import validate_locality, validate_price, clean_and_normalize_locality

router = APIRouter(prefix="/api/v1/listings", tags=["Listings"])


# Contact details and links a viewer only gets by unlocking the contact (POST /api/v1/leads/reveal)
LOCKED_FORM_FIELDS = ("mobile", "whatsapp", "email", "websiteUrl", "facebookUrl", "xUrl", "youtubeUrl")


class ListingCache:
    """Thread-safe in-memory cache with TTL for public approved listings."""
    def __init__(self, ttl: float = 60.0):
        self._cache: dict = {}
        self._lock = threading.Lock()
        self.ttl = ttl

    def get(self, key: str) -> Optional[dict]:
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            val, expires_at = entry
            if time.time() > expires_at:
                del self._cache[key]
                return None
            return val

    def set(self, key: str, val: dict) -> None:
        with self._lock:
            now = time.time()
            if len(self._cache) > 500:
                self._cache = {k: v for k, v in self._cache.items() if v[1] > now}
            self._cache[key] = (val, now + self.ttl)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


public_listings_cache = ListingCache(ttl=60.0)


def _listing_for_card(listing: Listing, is_admin: bool = False) -> dict:
    """Lightweight listing representation containing only the fields a card displays."""
    from app.routers.listing_pages import compute_listing_seo_title
    first_image = listing.images[0].file_path if listing.images else None
    prop_type = None
    kind = "property"
    category_name = None
    deal = None
    if isinstance(listing.form_data, dict):
        prop_type = listing.form_data.get("propType")
        kind = listing.form_data.get("kind", "property")
        category_name = listing.form_data.get("categoryName")
        deal = listing.form_data.get("deal") or listing.form_data.get("purpose") or listing.form_data.get("for_what")

    city = _listing_city(listing.location, listing.form_data)

    card = {
        "id": listing.id,
        "user_id": listing.user_id,
        "title": listing.title,
        "location": listing.location,
        "city": city,
        "price": float(listing.price) if listing.price is not None else 0.0,
        "owner_name": listing.owner_name,
        "owner_role": listing.owner_role,
        "status": listing.status,
        "verified": listing.verified,
        "is_featured": listing.is_featured,
        "featured_until": listing.featured_until.isoformat() if listing.featured_until else None,
        "first_image_url": first_image,
        "image_url": first_image,
        "images": [{"file_path": first_image}] if first_image else [],
        "prop_type": prop_type,
        "kind": kind,
        "deal": deal,
        "category_name": category_name,
        "reference_code": listing.reference_code,
        "created_at": listing.created_at.isoformat() if listing.created_at else None,
        "seo_title": compute_listing_seo_title(listing)
    }
    if is_admin:
        card["assigned_email"] = listing.assigned_email
    return card


def _listing_for_viewer(listing: Listing, user: Optional[User], unlocked: bool = False, db: Optional[Session] = None) -> dict:
    """Serializes a listing, leaving out locked contact fields unless the viewer owns it, is an admin or unlocked it."""
    from app.routers.listing_pages import compute_listing_seo_title
    data = ListingRead.model_validate(listing).model_dump()
    data["seo_title"] = compute_listing_seo_title(listing, db)
    can_see = unlocked or (user is not None and (user.role.lower() == "admin" or user.id == listing.user_id))
    if not can_see and isinstance(data.get("form_data"), dict):
        data["form_data"] = {k: v for k, v in data["form_data"].items() if k not in LOCKED_FORM_FIELDS}
    if not (user is not None and user.role.lower() == "admin"):
        data["assigned_email"] = None
    return data


def _listing_city(location: Optional[str], form_data) -> Optional[str]:
    """City of a listing: the wizard's city field, else the city part of "Locality, City, State"."""
    if isinstance(form_data, dict) and str(form_data.get("city") or "").strip():
        return str(form_data["city"]).strip()
    parts = [p.strip() for p in (location or "").split(",") if p.strip()]
    if not parts:
        return None
    return parts[-2] if len(parts) >= 3 else parts[0]


def _expire_featured(db: Session) -> None:
    """Un-features listings whose paid featured period has ended."""
    expired = db.query(Listing).filter(
        Listing.is_featured == True,
        Listing.featured_until.isnot(None),
        Listing.featured_until <= datetime.now(timezone.utc)
    ).update({Listing.is_featured: False, Listing.featured_until: None}, synchronize_session=False)
    if expired:
        db.commit()
        public_listings_cache.clear()


@router.get("/counts", response_model=ListingCountsResponse)
def get_listing_counts(
    kind: Optional[str] = Query(None),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    query = db.query(Listing.status, func.count(Listing.id))
    if kind == "business":
        query = query.filter(func.json_extract_path_text(Listing.form_data, "kind") == "business")
    elif kind == "property":
        query = query.filter(
            or_(
                func.json_extract_path_text(Listing.form_data, "kind") != "business",
                func.json_extract_path_text(Listing.form_data, "kind").is_(None)
            )
        )
    counts = query.group_by(Listing.status).all()
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
    """Public endpoint — returns site-wide stats for the login page hero and browse sections."""
    _expire_featured(db)
    active = db.query(func.count(Listing.id)).filter(Listing.status == "approved").scalar() or 0
    featured = db.query(func.count(Listing.id)).filter(
        Listing.status == "approved", Listing.is_featured == True
    ).scalar() or 0
    # One listing's location reads "Palwal", "Palwal, Haryana" or "Omaxe City, Palwal, Haryana",
    # so cities are counted by the city name, not the distinct location text
    approved = db.query(Listing.location, Listing.form_data).filter(Listing.status == "approved").all()
    city_counter: dict[str, int] = {}
    for loc, fd in approved:
        c = _listing_city(loc, fd)
        if c:
            c_name = c.title().strip()
            city_counter[c_name] = city_counter.get(c_name, 0) + 1
    city_counts = [{"name": name, "count": count} for name, count in sorted(city_counter.items(), key=lambda x: -x[1])]
    users = db.query(func.count(User.id)).scalar() or 0
    return {
        "active_listings": active,
        "featured_listings": featured,
        "cities_covered": len(city_counts),
        "city_counts": city_counts,
        "registered_users": users,
    }


@router.api_route("", methods=["GET", "HEAD"], response_model=dict)
def get_listings(
    status: Optional[str] = Query("approved"),
    city: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
    ref_code: Optional[str] = Query(None),
    ref_name: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=1000),
    prop_type: Optional[str] = Query(None),
    deal: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    verified_only: Optional[bool] = Query(None),
    new_only: Optional[bool] = Query(None),
    is_featured: Optional[bool] = Query(None),
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    _expire_featured(db)

    is_admin = bool(user and user.role.lower() == "admin")

    # In-memory caching for public approved listing requests
    is_cacheable = (
        user is None
        and user_id is None
        and (status is None or status.lower() == "approved")
    )
    cache_key = (
        f"st={status}&p={page}&l={limit}&c={city}&s={search}&k={kind}&rc={ref_code}&rn={ref_name}&"
        f"pt={prop_type}&d={deal}&min={min_price}&max={max_price}&vo={verified_only}&no={new_only}&f={is_featured}"
    )

    if is_cacheable:
        cached = public_listings_cache.get(cache_key)
        if cached is not None:
            return cached

    # Query with selectinload to resolve N+1 image query bottleneck in a single query
    query = db.query(Listing).options(selectinload(Listing.images)).outerjoin(User, Listing.user_id == User.id)

    # Filter by user_id if requested (e.g. My Listings in Account)
    if user_id:
        query = query.filter(Listing.user_id == user_id)

    # Kind filter: 'business' vs 'property'
    if kind == "business":
        query = query.filter(func.json_extract_path_text(Listing.form_data, "kind") == "business")
    elif kind == "property":
        query = query.filter(
            or_(
                func.json_extract_path_text(Listing.form_data, "kind") != "business",
                func.json_extract_path_text(Listing.form_data, "kind").is_(None)
            )
        )

    # Status filter
    if status and status.lower() != "all":
        query = query.filter(Listing.status == status.lower())
    elif not user_id and not is_admin:
        # Unauthenticated or non-admin users default to approved when not querying specific user
        query = query.filter(Listing.status == "approved")

    # City filter (supports single or comma-separated multiple cities)
    if city:
        city_parts = [c.strip() for c in city.split(",") if c.strip()]
        if len(city_parts) == 1:
            query = query.filter(Listing.location.ilike(f"%{city_parts[0]}%"))
        elif len(city_parts) > 1:
            query = query.filter(or_(*[Listing.location.ilike(f"%{c}%") for c in city_parts]))

    # Search filter (title / description / location / user name, email, phone / owner / ID)
    if search:
        term = search.strip()
        s_filter = f"%{term}%"

        clean_id = term.lstrip("#").strip()
        if clean_id.upper().startswith("TC011P-"):
            clean_id = clean_id[7:]
        elif clean_id.upper().startswith("TC-"):
            clean_id = clean_id[3:]

        conds = [
            Listing.title.ilike(s_filter),
            Listing.location.ilike(s_filter),
            Listing.description.ilike(s_filter),
            Listing.owner_name.ilike(s_filter),
            Listing.assigned_email.ilike(s_filter),
            User.name.ilike(s_filter),
            User.email.ilike(s_filter),
            User.phone.ilike(s_filter),
            cast(Listing.form_data, String).ilike(s_filter)
        ]
        if clean_id.isdigit() and int(clean_id) <= 2147483647:
            conds.append(Listing.id == int(clean_id))

        query = query.filter(or_(*conds))

    # Reference code filter
    if ref_code:
        query = query.filter(Listing.reference_code == ref_code.strip())

    # Property type filter
    if prop_type:
        pt = prop_type.strip().lower()
        conds = [
            func.json_extract_path_text(Listing.form_data, "propType").ilike(f"%{pt}%"),
            Listing.title.ilike(f"%{pt}%")
        ]
        if pt == "flat":
            conds.extend([
                func.json_extract_path_text(Listing.form_data, "propType").in_(["apartment", "builder_floor"]),
                Listing.title.ilike("%apartment%"),
                Listing.title.ilike("%builder floor%")
            ])
        elif pt == "house":
            conds.extend([
                func.json_extract_path_text(Listing.form_data, "propType").in_(["villa", "kothi"]),
                Listing.title.ilike("%villa%"),
                Listing.title.ilike("%kothi%"),
                Listing.title.ilike("%bungalow%")
            ])
        elif pt == "plot":
            conds.extend([
                func.json_extract_path_text(Listing.form_data, "propType") == "plots",
                Listing.title.ilike("%plots%")
            ])
        elif pt == "agriculture":
            conds.extend([
                func.json_extract_path_text(Listing.form_data, "propType").in_(["agricultural", "farm_land"]),
                Listing.title.ilike("%agricultural%"),
                Listing.title.ilike("%farm land%")
            ])
        elif pt == "commercial":
            conds.extend([
                func.json_extract_path_text(Listing.form_data, "propType").in_(["shop", "office", "showroom", "warehouse"]),
                Listing.title.ilike("%shop%"),
                Listing.title.ilike("%office%"),
                Listing.title.ilike("%showroom%"),
                Listing.title.ilike("%warehouse%")
            ])
        query = query.filter(or_(*conds))

    # Deal filter (sale, rent, buy)
    if deal:
        d = deal.strip().lower()
        query = query.filter(
            or_(
                func.json_extract_path_text(Listing.form_data, "deal").ilike(f"%{d}%"),
                func.json_extract_path_text(Listing.form_data, "purpose").ilike(f"%{d}%"),
                func.json_extract_path_text(Listing.form_data, "for_what").ilike(f"%{d}%"),
                Listing.title.ilike(f"%{d}%")
            )
        )

    # Price range
    if min_price is not None:
        query = query.filter(Listing.price >= min_price)
    if max_price is not None:
        query = query.filter(Listing.price <= max_price)

    # Verified filter
    if verified_only:
        query = query.filter(Listing.verified == 1)

    # New only (posted today UTC)
    if new_only:
        cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        query = query.filter(Listing.created_at >= cutoff)

    # Featured filter
    if is_featured is not None:
        query = query.filter(Listing.is_featured == is_featured)

    # Total count before pagination
    total = query.count()

    # Server-side pagination
    paginated_query = query.order_by(Listing.id.desc())
    if limit > 0:
        paginated_query = paginated_query.offset((page - 1) * limit).limit(limit)
    listings = paginated_query.all()

    # Build reference summary counts for admin
    ref_summary = []
    if is_admin:
        summary_query = db.query(
            Listing.reference_code,
            func.count(Listing.id).label("total")
        ).filter(Listing.reference_code.isnot(None))\
         .group_by(Listing.reference_code).all()
        ref_summary = [{"reference_code": r[0], "total": r[1]} for r in summary_query if r[0]]

    # Card fields only for list response: excludes heavy form_data, locked contacts, full image list
    data = [_listing_for_card(l, is_admin=is_admin) for l in listings]

    total_pages = max(1, math.ceil(total / limit)) if limit > 0 else 1
    response_payload = {
        "status": "success",
        "data": data,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "ref_summary": ref_summary
    }

    if is_cacheable:
        public_listings_cache.set(cache_key, response_payload)

    return response_payload


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
    return APIResponse(status="success", data=_listing_for_viewer(listing, user, unlocked, db=db))


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
    assign_to_email: Optional[str] = Form(None),  # admin only: the user this listing belongs to
    photos: List[UploadFile] = File(default=[]),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if assign_to_email and current_user.role.lower() != "admin":
        raise HTTPException(status_code=403, detail="Only admins can assign a listing to another user.")

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

    # Form validation for property listings (locality and price cannot be bypassed via API)
    is_biz = False
    if isinstance(parsed_form_data, dict):
        is_biz = parsed_form_data.get("kind") == "business" or bool(
            parsed_form_data.get("businessName") and not parsed_form_data.get("propType")
        )

    if not is_biz:
        # Locality validation
        loc_to_check = None
        if isinstance(parsed_form_data, dict) and parsed_form_data.get("locality"):
            loc_to_check = str(parsed_form_data["locality"]).strip()
        elif location:
            loc_to_check = location.split(",")[0].strip()

        if loc_to_check:
            is_valid_loc, loc_err = validate_locality(loc_to_check)
            if not is_valid_loc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=loc_err)
            norm_loc = clean_and_normalize_locality(loc_to_check)
            if isinstance(parsed_form_data, dict) and "locality" in parsed_form_data:
                parsed_form_data["locality"] = norm_loc

        # Price validation
        for_what = "sale"
        prop_type = ""
        if isinstance(parsed_form_data, dict):
            for_what = parsed_form_data.get("forWhat", "sale")
            prop_type = parsed_form_data.get("propType", "")

        is_valid_p, p_err, is_suspicious, p_warn = validate_price(price, for_what=for_what, prop_type=prop_type)
        if not is_valid_p:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=p_err)

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
    if assign_to_email:
        assign_listing_to_email(db, listing, assign_to_email, current_user)
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
    public_listings_cache.clear()

    # Dispatch listing confirmation email to the user
    target_email = assign_to_email.strip().lower() if assign_to_email else (current_user.email.strip().lower() if current_user.email else None)
    target_name = owner_name.strip() if owner_name else current_user.name
    if target_email:
        if background_tasks:
            background_tasks.add_task(
                mail_service.send_listing_confirmation,
                to_email=target_email,
                name=target_name,
                listing_title=listing.title,
                listing_id=listing.id,
                location=listing.location,
                price=listing.price,
                status=listing.status
            )
        else:
            mail_service.send_listing_confirmation(
                to_email=target_email,
                name=target_name,
                listing_title=listing.title,
                listing_id=listing.id,
                location=listing.location,
                price=listing.price,
                status=listing.status
            )

    return APIResponse(status="success", data=_listing_for_viewer(listing, current_user, db=db))


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
    assign_to_email: Optional[str] = Form(None),  # admin only: move the listing to this user
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
    if assign_to_email and current_user.role.lower() != "admin":
        raise HTTPException(status_code=403, detail="Only admins can assign a listing to another user.")

    if assign_to_email:
        assign_listing_to_email(db, listing, assign_to_email, current_user)
    if title is not None:
        words = title.strip().split()
        if len(words) > 50:
            raise HTTPException(status_code=400, detail="Listing title cannot exceed 50 words.")
        listing.title = title.strip()
    old_price = float(listing.price) if listing.price is not None else None
    old_fd = listing.form_data if isinstance(listing.form_data, dict) else {}
    old_locality = old_fd.get("locality") or (listing.location.split(",")[0].strip() if listing.location else "")
    price_changed = price is not None and (old_price is None or float(price) != old_price)

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

    # Property listings validation on update
    fd_check = listing.form_data if isinstance(listing.form_data, dict) else {}
    is_biz = fd_check.get("kind") == "business" or bool(fd_check.get("businessName") and not fd_check.get("propType"))

    if not is_biz:
        if location is not None or form_data is not None:
            loc_check = fd_check.get("locality") or (listing.location.split(",")[0].strip() if listing.location else "")
            locality_changed = bool(loc_check and loc_check.strip().lower() != (old_locality or "").strip().lower())
            if locality_changed:
                is_valid_loc, loc_err = validate_locality(loc_check)
                if not is_valid_loc:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=loc_err)
                norm_loc = clean_and_normalize_locality(loc_check)
                if isinstance(listing.form_data, dict) and "locality" in listing.form_data:
                    listing.form_data["locality"] = norm_loc

        if price_changed and price is not None:
            for_what = fd_check.get("forWhat", "sale")
            prop_type = fd_check.get("propType", "")
            is_valid_p, p_err, is_suspicious, p_warn = validate_price(listing.price, for_what=for_what, prop_type=prop_type)
            if not is_valid_p:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=p_err)

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
    public_listings_cache.clear()
    return APIResponse(status="success", data=_listing_for_viewer(listing, current_user, db=db))


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
    public_listings_cache.clear()
    return MessageResponse(status="success", message=f"Listing status updated via action '{action}'.")


@router.post("/{listing_id}/feature", response_model=APIResponse[ListingRead])
def set_listing_featured(
    listing_id: int,
    req: ListingFeatureUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin features a listing for a number of days (or with no expiry), or removes featuring."""
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")

    if req.featured:
        if listing.status != "approved":
            raise HTTPException(status_code=400, detail="Only approved listings can be featured.")
        listing.is_featured = True
        listing.featured_until = (
            datetime.now(timezone.utc) + timedelta(days=req.days) if req.days else None
        )
    else:
        listing.is_featured = False
        listing.featured_until = None

    db.commit()
    db.refresh(listing)
    public_listings_cache.clear()
    return APIResponse(status="success", data=ListingRead.model_validate(listing))


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
    public_listings_cache.clear()
    return MessageResponse(status="success", message="Listing deleted successfully.")
