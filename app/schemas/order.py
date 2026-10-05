from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel
from app.schemas.plan import PlanRead


class CreateOrderRequest(BaseModel):
    plan_id: int
    listing_id: Optional[int] = None  # required for "featured" plans
    idempotency_key: Optional[str] = None


class CreateOrderResponse(BaseModel):
    status: str = "success"
    order_id: str
    payment_session_id: str
    environment: str  # "sandbox" | "production" | "mock" (Cashfree JS SDK mode)
    amount: float  # in rupees
    currency: str = "INR"
    plan: PlanRead


class VerifyPaymentRequest(BaseModel):
    order_id: str


class VerifyPaymentResponse(BaseModel):
    status: str = "success"
    message: str
    plan: Dict[str, Any]


class OrderRead(BaseModel):
    id: int
    user_id: Optional[int] = None
    plan_id: Optional[int] = None
    cashfree_order_id: str
    cashfree_payment_id: Optional[str] = None
    amount: float
    currency: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CashfreeSettingsUpdate(BaseModel):
    app_id: Optional[str] = None
    secret_key: Optional[str] = None
    environment: Optional[str] = None  # sandbox | production
