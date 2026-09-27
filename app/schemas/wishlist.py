from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
from app.schemas.listing import ListingRead


class ToggleWishlistRequest(BaseModel):
    listing_id: int


class ToggleWishlistResponse(BaseModel):
    status: str = "success"
    wishlisted: bool
    listing_id: int
    action: Optional[str] = None


class WishlistRead(BaseModel):
    id: int
    user_id: int
    listing_id: int
    created_at: datetime
    listing: Optional[ListingRead] = None

    model_config = {"from_attributes": True}
