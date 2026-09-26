from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class LocationBase(BaseModel):
    city_name: str = Field(..., min_length=1, max_length=100)
    state: str = Field(default="Haryana", max_length=100)
    category: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class LocationCreate(LocationBase):
    pass


class LocationUpdate(BaseModel):
    city_name: Optional[str] = None
    state: Optional[str] = None
    category: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class LocationRead(LocationBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}
