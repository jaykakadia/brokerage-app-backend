from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, Field

EnquiryStatus = Literal["new", "in_progress", "resolved"]


class EnquiryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    email: EmailStr
    phone: str = Field(..., min_length=10, max_length=30)
    message: str = Field(..., min_length=1, max_length=5000)
    # Honeypot: hidden on the form, so only bots fill it in
    website: Optional[str] = Field(None, max_length=200)


class EnquiryUpdate(BaseModel):
    status: Optional[EnquiryStatus] = None
    admin_note: Optional[str] = Field(None, max_length=5000)


class EnquiryRead(BaseModel):
    id: int
    name: str
    email: str
    phone: str
    message: str
    status: str
    admin_note: Optional[str] = None
    source: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
