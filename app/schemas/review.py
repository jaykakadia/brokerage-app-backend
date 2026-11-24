from datetime import datetime
from typing import Literal, Optional, List, Dict
from pydantic import BaseModel, Field


ReviewStatus = Literal["pending", "approved", "rejected"]


class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Star rating from 1 to 5")
    comment: Optional[str] = Field(None, max_length=2000, description="Review feedback text")


class ReviewStatusUpdate(BaseModel):
    status: ReviewStatus


class ReviewRead(BaseModel):
    id: int
    listing_id: int
    user_id: int
    user_name: Optional[str] = None
    rating: int
    comment: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ListingReviewsResponse(BaseModel):
    average_rating: float = 0.0
    total_reviews: int = 0
    distribution: Dict[str, int] = Field(default_factory=lambda: {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0})
    reviews: List[ReviewRead] = Field(default_factory=list)
    user_review: Optional[ReviewRead] = None


class AdminReviewRead(ReviewRead):
    user_email: Optional[str] = None
    user_phone: Optional[str] = None
    listing_title: Optional[str] = None
    listing_city: Optional[str] = None
    listing_kind: Optional[str] = None
