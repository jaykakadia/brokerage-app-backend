import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_

from app.db.session import get_db
from app.db.models.user import User
from app.db.models.listing import Listing
from app.db.models.review import Review
from app.core.dependencies import get_current_user, get_optional_user, get_current_admin
from app.schemas.common import APIResponse, MessageResponse
from app.schemas.review import (
    ReviewCreate,
    ReviewStatusUpdate,
    ReviewRead,
    ListingReviewsResponse,
    AdminReviewRead,
)
from app.services.storage_service import public_url, storage_service, to_key

MAX_REVIEW_IMAGES = 5

router = APIRouter(tags=["Reviews"])


def _public_review_images(raw: Optional[list]) -> List[str]:
    if not isinstance(raw, list):
        return []
    return [public_url(str(p)) for p in raw if p]


def _to_review_read(r: Review) -> ReviewRead:
    user_name = r.user.name if r.user else "Anonymous"
    return ReviewRead(
        id=r.id,
        listing_id=r.listing_id,
        user_id=r.user_id,
        user_name=user_name,
        rating=r.rating,
        comment=r.comment,
        images=_public_review_images(r.images),
        status=r.status,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def _to_admin_review_read(r: Review) -> AdminReviewRead:
    user_name = r.user.name if r.user else "Anonymous"
    user_email = r.user.email if r.user else None
    user_phone = r.user.phone if r.user else None
    listing_title = r.listing.title if r.listing else None
    listing_city = None
    listing_kind = None
    if r.listing and r.listing.form_data and isinstance(r.listing.form_data, dict):
        listing_city = r.listing.form_data.get("city")
        listing_kind = r.listing.form_data.get("kind")

    return AdminReviewRead(
        id=r.id,
        listing_id=r.listing_id,
        user_id=r.user_id,
        user_name=user_name,
        user_email=user_email,
        user_phone=user_phone,
        listing_title=listing_title,
        listing_city=listing_city,
        listing_kind=listing_kind,
        rating=r.rating,
        comment=r.comment,
        images=_public_review_images(r.images),
        status=r.status,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


# ---------------------------------------------------------------------------
# Public / User Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/v1/listings/{listing_id}/reviews", response_model=APIResponse[ListingReviewsResponse])
def get_listing_reviews(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
):
    listing = db.query(Listing).filter(Listing.id == listing_id, Listing.is_deleted == False).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")

    # All approved reviews
    approved_reviews = (
        db.query(Review)
        .filter(Review.listing_id == listing_id, Review.is_deleted == False, Review.status == "approved")
        .order_by(desc(Review.created_at))
        .all()
    )

    total_reviews = len(approved_reviews)
    distribution = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    total_score = 0
    for rev in approved_reviews:
        k = str(rev.rating)
        if k in distribution:
            distribution[k] += 1
        total_score += rev.rating

    avg_rating = round(total_score / total_reviews, 1) if total_reviews > 0 else 0.0

    review_reads = [_to_review_read(r) for r in approved_reviews]

    # Current user's own review (even if pending)
    user_review_read: Optional[ReviewRead] = None
    if current_user:
        my_review = (
            db.query(Review)
            .filter(Review.listing_id == listing_id, Review.user_id == current_user.id, Review.is_deleted == False)
            .first()
        )
        if my_review:
            user_review_read = _to_review_read(my_review)

    return APIResponse(
        status="success",
        data=ListingReviewsResponse(
            average_rating=avg_rating,
            total_reviews=total_reviews,
            distribution=distribution,
            reviews=review_reads,
            user_review=user_review_read,
        ),
    )


@router.post("/api/v1/listings/{listing_id}/reviews", response_model=APIResponse[ReviewRead])
async def submit_listing_review(
    listing_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    listing = db.query(Listing).filter(Listing.id == listing_id, Listing.is_deleted == False).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")

    if listing.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot review your own listing.")

    content_type = (request.headers.get("content-type") or "").lower()
    uploaded_files: List[UploadFile] = []
    keep_images_keys: Optional[List[str]] = None

    if "multipart/form-data" in content_type:
        form = await request.form()
        try:
            raw_rating = int(str(form.get("rating", "")).strip())
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Rating must be an integer between 1 and 5.")
        raw_comment = form.get("comment")
        req = ReviewCreate(rating=raw_rating, comment=str(raw_comment) if raw_comment is not None else None)
        uploaded_files = [f for f in form.getlist("files") if hasattr(f, "filename") and f.filename]
        raw_keep = form.get("keep_images")
        if raw_keep is not None:
            try:
                parsed_keep = json.loads(str(raw_keep))
                if isinstance(parsed_keep, list):
                    keep_images_keys = [to_key(str(u)) for u in parsed_keep if u]
            except (ValueError, TypeError):
                keep_images_keys = []
    else:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid JSON request body.")
        req = ReviewCreate.model_validate(body)

    existing = (
        db.query(Review)
        .filter(Review.listing_id == listing_id, Review.user_id == current_user.id)
        .first()
    )

    old_keys: List[str] = list(existing.images) if (existing and isinstance(existing.images, list)) else []
    if keep_images_keys is not None:
        kept = [k for k in old_keys if k in set(keep_images_keys)]
    elif "multipart/form-data" in content_type:
        kept = list(old_keys)
    else:
        kept = list(old_keys)

    if len(kept) + len(uploaded_files) > MAX_REVIEW_IMAGES:
        raise HTTPException(status_code=400, detail=f"You can attach up to {MAX_REVIEW_IMAGES} images per review.")

    new_keys: List[str] = []
    for f in uploaded_files:
        key, _, _, _ = await storage_service.validate_and_save_image(f"reviews/{int(listing_id)}", f)
        new_keys.append(key)

    final_keys = kept + new_keys
    removed_keys = [k for k in old_keys if k not in set(kept)]
    for k in removed_keys:
        try:
            storage_service.delete_file(k)
        except Exception:
            pass

    is_admin = current_user.role.lower() == "admin"
    initial_status = "approved" if is_admin else "pending"

    if existing:
        existing.rating = req.rating
        existing.comment = req.comment.strip() if req.comment else None
        existing.images = final_keys
        existing.status = initial_status
        existing.is_deleted = False
        db.commit()
        db.refresh(existing)
        msg = "Review updated and approved." if is_admin else "Review updated successfully! It will appear once approved by admin."
        return APIResponse(status="success", message=msg, data=_to_review_read(existing))

    new_review = Review(
        listing_id=listing_id,
        user_id=current_user.id,
        rating=req.rating,
        comment=req.comment.strip() if req.comment else None,
        images=final_keys,
        status=initial_status,
    )
    db.add(new_review)
    db.commit()
    db.refresh(new_review)

    msg = "Review posted and approved." if is_admin else "Thank you! Your review has been submitted for admin approval."
    return APIResponse(status="success", message=msg, data=_to_review_read(new_review))


@router.delete("/api/v1/listings/{listing_id}/reviews/me", response_model=MessageResponse)
def delete_my_review(
    listing_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    review = (
        db.query(Review)
        .filter(Review.listing_id == listing_id, Review.user_id == current_user.id, Review.is_deleted == False)
        .first()
    )
    if not review:
        raise HTTPException(status_code=404, detail="No review found to delete.")

    review.is_deleted = True
    db.commit()
    return MessageResponse(status="success", message="Your review has been removed.")


# ---------------------------------------------------------------------------
# Admin Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/v1/admin/reviews", response_model=APIResponse[List[AdminReviewRead]])
def admin_list_reviews(
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    query = db.query(Review).join(Review.user).join(Review.listing).filter(Review.is_deleted == False)

    if status_filter and status_filter.lower() in ("pending", "approved", "rejected"):
        query = query.filter(Review.status == status_filter.lower())

    if search:
        s = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(User.name).like(s),
                func.lower(User.email).like(s),
                func.lower(User.phone).like(s),
                func.lower(Listing.title).like(s),
                func.lower(Review.comment).like(s),
            )
        )

    offset = (page - 1) * limit
    reviews = query.order_by(desc(Review.created_at)).offset(offset).limit(limit).all()

    return APIResponse(
        status="success",
        data=[_to_admin_review_read(r) for r in reviews],
    )


@router.patch("/api/v1/admin/reviews/{review_id}/status", response_model=APIResponse[AdminReviewRead])
def admin_update_review_status(
    review_id: int,
    req: ReviewStatusUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    review = db.query(Review).filter(Review.id == review_id, Review.is_deleted == False).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found.")

    review.status = req.status
    db.commit()
    db.refresh(review)

    return APIResponse(
        status="success",
        message=f"Review #{review.id} status updated to '{req.status}'.",
        data=_to_admin_review_read(review),
    )


@router.delete("/api/v1/admin/reviews/{review_id}", response_model=MessageResponse)
def admin_delete_review(
    review_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    review = db.query(Review).filter(Review.id == review_id, Review.is_deleted == False).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found.")

    review.is_deleted = True
    db.commit()
    return MessageResponse(status="success", message=f"Review #{review_id} has been deleted.")
