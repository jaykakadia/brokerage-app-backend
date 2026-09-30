from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field
from app.schemas.user import CanonicalRole


class ListingImageRead(BaseModel):
    id: int
    file_path: str
    original_filename: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    sort_order: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class ListingBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    location: str = Field(..., min_length=1, max_length=150)
    price: float = Field(default=0.0, ge=0)
    description: Optional[str] = None
    owner_name: str = Field(..., min_length=1, max_length=150)
    owner_role: CanonicalRole = "Owner"
    reference_code: Optional[str] = None
    form_data: Optional[Any] = None


class ListingCreate(ListingBase):
    pass


class ListingUpdate(BaseModel):
    title: Optional[str] = None
    location: Optional[str] = None
    price: Optional[float] = None
    description: Optional[str] = None
    owner_name: Optional[str] = None
    owner_role: Optional[CanonicalRole] = None
    reference_code: Optional[str] = None
    status: Optional[str] = None
    verified: Optional[int] = None
    is_featured: Optional[bool] = None
    form_data: Optional[Any] = None


class ListingRead(ListingBase):
    id: int
    user_id: int
    status: str
    verified: int
    is_featured: bool = False
    created_at: datetime
    images: List[ListingImageRead] = []

    model_config = {"from_attributes": True}


class ListingStatusUpdate(BaseModel):
    action: str  # 'approve', 'pending', 'suspended', 'sold', 'rented', 'delete', 'stamp'


class ListingCountsResponse(BaseModel):
    status: str = "success"
    data: dict[str, int]
