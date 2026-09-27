from typing import Optional, Literal
from pydantic import BaseModel, EmailStr, Field
from app.schemas.user import UserRead


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    phone: str = Field(..., min_length=5, max_length=30)
    email: EmailStr
    password: str = Field(..., min_length=6)
    confirm_password: Optional[str] = None
    role: Optional[Literal["Owner", "Agent", "Builder"]] = "Owner"
    otp: Optional[str] = None


class SendOtpRequest(BaseModel):
    email: EmailStr
    action: str = "register"  # "register", "forgot", "profile_update"
    name: Optional[str] = None
    phone: Optional[str] = None


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    new_password: str = Field(..., min_length=6)
    otp: Optional[str] = None


class AuthResponse(BaseModel):
    status: str = "success"
    message: str = "Success"
    redirect: Optional[str] = "account.php"
    csrf_token: Optional[str] = None
    user: Optional[UserRead] = None
