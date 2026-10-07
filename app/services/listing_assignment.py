from typing import Optional
from fastapi import HTTPException
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.db.models.listing import Listing
from app.db.models.user import User


_email = TypeAdapter(EmailStr)


def assign_listing_to_email(db: Session, listing: Listing, email: str, admin: User) -> None:
    """Gives the listing to the user with this email, or holds it under the admin until they sign up."""
    email_clean = email.lower().strip()
    try:
        _email.validate_python(email_clean)
    except ValidationError:
        raise HTTPException(status_code=400, detail="Enter a valid email to assign this listing to.")
    owner: Optional[User] = db.query(User).filter(User.email == email_clean).first()
    if owner:
        listing.user_id = owner.id
        listing.assigned_email = None
    else:
        # Held by the admin so the previous owner can no longer edit or delete it
        listing.user_id = admin.id
        listing.assigned_email = email_clean


def claim_assigned_listings(db: Session, user: User) -> int:
    """Moves listings held for this user's email onto their account. Caller commits."""
    listings = db.query(Listing).filter(Listing.assigned_email == user.email.lower().strip()).all()
    for listing in listings:
        listing.user_id = user.id
        listing.assigned_email = None
    return len(listings)
