import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_user, get_current_admin, get_db
from app.db.models.user import User
from app.db.models.plan import Plan
from app.db.models.order import Order
from app.db.models.setting import SystemSetting
from app.schemas.order import (
    CreateOrderRequest, CreateOrderResponse,
    VerifyPaymentRequest, VerifyPaymentResponse,
    RazorpaySettingsRead, RazorpaySettingsUpdate
)
from app.schemas.plan import PlanRead
from app.services.razorpay_service import razorpay_service

router = APIRouter(prefix="/api/v1/payments", tags=["Payments"])


def _get_active_razorpay_credentials(db: Session) -> tuple[str, str]:
    """Retrieves active Razorpay Key ID and Key Secret from system_settings or env fallback."""
    key_id_setting = db.query(SystemSetting).filter(SystemSetting.key == "razorpay_key_id").first()
    key_secret_setting = db.query(SystemSetting).filter(SystemSetting.key == "razorpay_key_secret").first()

    key_id = key_id_setting.value if key_id_setting and key_id_setting.value else settings.RAZORPAY_KEY_ID
    key_secret = key_secret_setting.value if key_secret_setting and key_secret_setting.value else settings.RAZORPAY_KEY_SECRET
    return key_id, key_secret


def _credit_user_plan_and_leads(db: Session, order: Order, payment_id: Optional[str] = None, signature: Optional[str] = None) -> User:
    """
    Atomically marks order as paid and credits user plan, leads balance, and validity.
    Idempotent: if order is already paid, simply returns the user without double-crediting.
    """
    if order.status == "paid":
        return db.query(User).filter(User.id == order.user_id).first()

    order.status = "paid"
    if payment_id:
        order.razorpay_payment_id = payment_id
    if signature:
        order.razorpay_signature = signature

    user = db.query(User).filter(User.id == order.user_id).with_for_update().first()
    if user and order.plan:
        plan = order.plan
        user.plan_id = plan.id
        user.leads_balance += plan.leads_count
        user.listing_limit += plan.listing_limit

        now = datetime.now(timezone.utc)
        current_exp = user.plan_expires_at
        if current_exp is not None and current_exp.tzinfo is None:
            current_exp = current_exp.replace(tzinfo=timezone.utc)
        start_date = current_exp if (current_exp and current_exp > now) else now
        user.plan_expires_at = start_date + timedelta(days=plan.duration_days)

    db.commit()
    if user:
        db.refresh(user)
    return user


@router.post("/create-order", response_model=CreateOrderResponse)
def create_order(
    req: CreateOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Creates a server-side Razorpay order for the selected plan.
    Price is always loaded strictly from the database (never trusted from frontend).
    """
    plan = db.query(Plan).filter(Plan.id == req.plan_id, Plan.status == "active").first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found or inactive.")

    key_id, key_secret = _get_active_razorpay_credentials(db)
    amount_in_paise = int(round(float(plan.price) * 100))

    # Idempotency check if idempotency_key is provided
    if req.idempotency_key:
        existing_order = db.query(Order).filter(
            Order.idempotency_key == req.idempotency_key,
            Order.user_id == current_user.id
        ).first()
        if existing_order and existing_order.status == "created":
            return CreateOrderResponse(
                status="success",
                key_id=key_id,
                amount=int(round(float(existing_order.amount) * 100)),
                currency=existing_order.currency,
                order_id=existing_order.razorpay_order_id,
                plan=PlanRead.model_validate(plan),
                prefill={
                    "name": current_user.name,
                    "email": current_user.email,
                    "contact": current_user.phone
                }
            )

    rzp_order = razorpay_service.create_order(
        amount_in_paise=amount_in_paise,
        currency="INR",
        receipt=f"rcpt_u{current_user.id}_p{plan.id}",
        notes={"user_id": str(current_user.id), "plan_id": str(plan.id)},
        key_id=key_id,
        key_secret=key_secret
    )

    new_order = Order(
        user_id=current_user.id,
        plan_id=plan.id,
        razorpay_order_id=rzp_order["id"],
        amount=plan.price,
        currency="INR",
        status="created",
        idempotency_key=req.idempotency_key,
        notes=rzp_order.get("notes")
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    return CreateOrderResponse(
        status="success",
        key_id=key_id,
        amount=amount_in_paise,
        currency="INR",
        order_id=rzp_order["id"],
        plan=PlanRead.model_validate(plan),
        prefill={
            "name": current_user.name,
            "email": current_user.email,
            "contact": current_user.phone
        }
    )


@router.post("/verify", response_model=VerifyPaymentResponse)
def verify_payment(
    req: VerifyPaymentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Verifies payment signature using HMAC-SHA256 and atomically credits user plan and leads.
    Idempotent: Duplicate requests for the same order return success without double crediting.
    """
    key_id, key_secret = _get_active_razorpay_credentials(db)

    # 1. Verify cryptographic signature
    is_valid = razorpay_service.verify_payment_signature(
        razorpay_order_id=req.razorpay_order_id,
        razorpay_payment_id=req.razorpay_payment_id,
        razorpay_signature=req.razorpay_signature,
        key_secret=key_secret
    )

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment verification failed: Invalid Razorpay signature."
        )

    # 2. Lock order and execute atomic credit
    order = (
        db.query(Order)
        .filter(Order.razorpay_order_id == req.razorpay_order_id)
        .with_for_update()
        .first()
    )

    if not order:
        raise HTTPException(status_code=404, detail="Order not found for this payment.")

    if order.user_id and order.user_id != current_user.id and current_user.role.lower() != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to reconcile this order.")

    user = _credit_user_plan_and_leads(db, order, req.razorpay_payment_id, req.razorpay_signature)

    plan_name = order.plan.name if order.plan else "Active Plan"
    return VerifyPaymentResponse(
        status="success",
        message="Payment verified and plan activated successfully!",
        plan={
            "plan_name": plan_name,
            "leads_balance": user.leads_balance if user else 0,
            "listing_limit": user.listing_limit if user else 1,
            "plan_expires_at": user.plan_expires_at.isoformat() if (user and user.plan_expires_at) else None
        }
    )


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Razorpay Webhook endpoint. Verifies X-Razorpay-Signature against raw body,
    reconciles order state, and credits user plan/leads idempotently.
    """
    raw_body = await request.body()
    if not x_razorpay_signature:
        raise HTTPException(status_code=400, detail="Missing X-Razorpay-Signature header.")

    is_valid = razorpay_service.verify_webhook_signature(
        raw_body=raw_body,
        received_signature=x_razorpay_signature
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    try:
        data = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    event = data.get("event")
    payload = data.get("payload", {})
    payment_entity = payload.get("payment", {}).get("entity", {})
    order_id = payment_entity.get("order_id")
    payment_id = payment_entity.get("id")

    if event in ("payment.captured", "order.paid") and order_id:
        order = db.query(Order).filter(Order.razorpay_order_id == order_id).with_for_update().first()
        if order and order.status != "paid":
            _credit_user_plan_and_leads(db, order, payment_id=payment_id)

    return {"status": "ok"}


@router.get("/admin/settings", response_model=dict)
def get_razorpay_settings(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin-only: Retrieve Razorpay configuration (secret is never exposed)."""
    key_id_setting = db.query(SystemSetting).filter(SystemSetting.key == "razorpay_key_id").first()
    key_secret_setting = db.query(SystemSetting).filter(SystemSetting.key == "razorpay_key_secret").first()

    key_id = key_id_setting.value if key_id_setting and key_id_setting.value else settings.RAZORPAY_KEY_ID
    has_secret = bool(key_secret_setting and key_secret_setting.value) or bool(settings.RAZORPAY_KEY_SECRET and not settings.RAZORPAY_KEY_SECRET.startswith("rzp_test_secret_placeholder"))

    return {
        "status": "success",
        "data": {
            "razorpay_key_id": key_id,
            "key_id": key_id,
            "has_secret": has_secret,
            "test_mode": True
        }
    }


@router.post("/admin/settings", response_model=dict)
def save_razorpay_settings(
    req: RazorpaySettingsUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin-only: Update Razorpay Key ID and Secret securely."""
    active_key_id = req.razorpay_key_id or req.key_id
    active_key_secret = req.razorpay_key_secret or req.key_secret

    # Update Key ID if provided
    if active_key_id and active_key_id.strip():
        kid_setting = db.query(SystemSetting).filter(SystemSetting.key == "razorpay_key_id").first()
        if not kid_setting:
            kid_setting = SystemSetting(key="razorpay_key_id", value=active_key_id.strip(), is_encrypted=False)
            db.add(kid_setting)
        else:
            kid_setting.value = active_key_id.strip()

    # Update Key Secret if provided
    if active_key_secret and active_key_secret.strip():
        ksec_setting = db.query(SystemSetting).filter(SystemSetting.key == "razorpay_key_secret").first()
        if not ksec_setting:
            ksec_setting = SystemSetting(key="razorpay_key_secret", value=active_key_secret.strip(), is_encrypted=True)
            db.add(ksec_setting)
        else:
            ksec_setting.value = active_key_secret.strip()

    db.commit()
    return {
        "status": "success",
        "message": "Razorpay settings updated successfully.",
        "data": {
            "key_id": active_key_id or "",
            "razorpay_key_id": active_key_id or "",
            "has_secret": bool(active_key_secret),
            "test_mode": req.test_mode if req.test_mode is not None else True
        }
    }
