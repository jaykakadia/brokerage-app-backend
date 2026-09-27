from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class EmployeeBase(BaseModel):
    name: str
    reference_code: str
    status: str = "active"
    phone: Optional[str] = None
    email: Optional[str] = None


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    reference_code: Optional[str] = None
    status: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class EmployeeRead(EmployeeBase):
    id: int
    listings_created: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RefCodeItem(BaseModel):
    reference_code: str
    name: str

    model_config = ConfigDict(from_attributes=True)
