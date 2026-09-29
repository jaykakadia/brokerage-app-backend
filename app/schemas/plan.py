from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class PlanBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    price: float = Field(..., ge=0)
    listing_limit: int = Field(default=5, ge=0)
    leads_count: int = Field(default=5, ge=0)
    duration_days: int = Field(default=365, ge=1)
    status: str = Field(default="active")
    sort_order: int = Field(default=0)


class PlanCreate(PlanBase):
    pass


class PlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    listing_limit: Optional[int] = None
    leads_count: Optional[int] = None
    duration_days: Optional[int] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None


class PlanRead(PlanBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
