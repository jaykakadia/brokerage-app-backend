from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import get_current_user, get_db
from app.db.models.user import User
from app.db.models.listing import Listing
from app.db.models.wishlist import Wishlist
from app.schemas.wishlist import ToggleWishlistRequest, ToggleWishlistResponse, WishlistRead
from app.schemas.listing import ListingRead

router = APIRouter(prefix="/api/v1/wishlist", tags=["Wishlist"])


@router.get("", response_model=dict)
def get_wishlist(
    ids_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns user's wishlisted listings.
    If ids_only is True, returns a compact list of IDs for button state matching.
    """
    if ids_only:
        records = (
            db.query(Wishlist.listing_id)
            .join(Listing, Wishlist.listing_id == Listing.id)
            .filter(Wishlist.user_id == current_user.id, Listing.status != "deleted")
            .all()
        )
        ids = [r[0] for r in records]
        return {"status": "success", "ids": ids, "data": ids}

    records = (
        db.query(Wishlist)
        .options(joinedload(Wishlist.listing).joinedload(Listing.images))
        .filter(Wishlist.user_id == current_user.id)
        .order_by(Wishlist.id.desc())
        .all()
    )

    data = []
    for w in records:
        if w.listing and w.listing.status != "deleted":
            data.append(ListingRead.model_validate(w.listing).model_dump())

    return {"status": "success", "data": data}


@router.post("/toggle", response_model=ToggleWishlistResponse)
def toggle_wishlist(
    req: ToggleWishlistRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Toggles a listing in the user's wishlist.
    Adds if not present; removes if already present.
    """
    listing = db.query(Listing).filter(Listing.id == req.listing_id, Listing.status != "deleted").first()
    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found."
        )

    existing = db.query(Wishlist).filter(
        Wishlist.user_id == current_user.id,
        Wishlist.listing_id == req.listing_id
    ).first()

    if existing:
        db.delete(existing)
        db.commit()
        return ToggleWishlistResponse(
            status="success",
            wishlisted=False,
            listing_id=req.listing_id,
            action="removed"
        )

    new_item = Wishlist(user_id=current_user.id, listing_id=req.listing_id)
    db.add(new_item)
    db.commit()
    return ToggleWishlistResponse(
        status="success",
        wishlisted=True,
        listing_id=req.listing_id,
        action="added"
    )
