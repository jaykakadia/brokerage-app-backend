from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from app.schemas.plan import PlanRead


class CreateOrderRequest(BaseModel):
    plan_id: int
    idempotency_key: Optional[str] = None


class CreateOrderResponse(BaseModel):
    status: str = "success"
    key_id: str
    amount: int  # amount in paise
    currency: str = "INR"
    order_id: str
    plan: PlanRead
    prefill: Dict[str, str] = {}


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan_id: Optional[int] = None


class VerifyPaymentResponse(BaseModel):
    status: str = "success"
    message: str
    plan: Dict[str, Any]


class OrderRead(BaseModel):
    id: int
    user_id: Optional[int] = None
    plan_id: Optional[int] = None
    razorpay_order_id: str
    razorpay_payment_id: Optional[str] = None
    amount: float
    currency: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RazorpaySettingsRead(BaseModel):
    razorpay_key_id: str
    key_id: Optional[str] = None
    has_secret: bool
    test_mode: Optional[bool] = True


class RazorpaySettingsUpdate(BaseModel):
    razorpay_key_id: Optional[str] = None
    razorpay_key_secret: Optional[str] = None
    key_id: Optional[str] = None
    key_secret: Optional[str] = None
    webhook_secret: Optional[str] = None
    test_mode: Optional[bool] = None
