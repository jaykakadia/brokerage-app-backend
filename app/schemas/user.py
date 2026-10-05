from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, EmailStr, Field

CanonicalRole = Literal["Owner", "Agent", "Builder", "Admin"]


class UserBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    phone: str = Field(..., min_length=5, max_length=30)
    email: EmailStr
    role: CanonicalRole = "Owner"
    status: str = "active"


class UserRead(UserBase):
    id: int
    plan_id: Optional[int] = None
    listing_limit: int = 1
    leads_balance: int = 0
    leads_used: int = 0
    plan_expires_at: Optional[datetime] = None
    business_name: Optional[str] = None
    whatsapp: Optional[str] = None
    facebook_url: Optional[str] = None
    website_url: Optional[str] = None
    x_url: Optional[str] = None
    youtube_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    otp: Optional[str] = None
    business_name: Optional[str] = Field(None, max_length=150)
    whatsapp: Optional[str] = Field(None, max_length=30)
    facebook_url: Optional[str] = Field(None, max_length=500)
    website_url: Optional[str] = Field(None, max_length=500)
    x_url: Optional[str] = Field(None, max_length=500)
    youtube_url: Optional[str] = Field(None, max_length=500)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)
    confirm_password: str


class AdminUserCreate(BaseModel):
    name: str
    phone: str
    email: EmailStr
    password: str = Field(..., min_length=6)
    role: CanonicalRole = "Owner"
    status: str = "active"
    plan_id: Optional[int] = None
    leads_balance: Optional[int] = 0
    plan_expires_at: Optional[datetime] = None


class AdminUserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[CanonicalRole] = None
    status: Optional[str] = None
    plan_id: Optional[int] = None
    leads_balance: Optional[int] = None
    plan_expires_at: Optional[datetime] = None


class RoleUpdateRequest(BaseModel):
    role: CanonicalRole
