import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_user, get_current_admin, get_db
from app.core.security import encrypt_secret, decrypt_secret
from app.db.models.user import User
from app.db.models.plan import Plan
from app.db.models.order import Order
from app.db.models.listing import Listing
from app.db.models.setting import SystemSetting
from app.schemas.order import (
    CreateOrderRequest, CreateOrderResponse,
    VerifyPaymentRequest, VerifyPaymentResponse,
    CashfreeSettingsUpdate
)
from app.schemas.plan import PlanRead
from app.services.cashfree_service import cashfree_service

router = APIRouter(prefix="/api/v1/payments", tags=["Payments"])


def _get_setting(db: Session, key: str) -> Optional[str]:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return row.value if row and row.value else None


def _get_active_cashfree_credentials(db: Session) -> tuple[str, str, str]:
    """Returns (app_id, secret_key, environment) from system_settings, falling back to env."""
    app_id = _get_setting(db, "cashfree_app_id") or settings.CASHFREE_APP_ID
    stored_secret = _get_setting(db, "cashfree_secret_key")
    secret_key = decrypt_secret(stored_secret) if stored_secret else settings.CASHFREE_SECRET_KEY
    environment = _get_setting(db, "cashfree_environment") or settings.CASHFREE_ENVIRONMENT
    return app_id, secret_key, environment


def _checkout_mode(environment: str) -> str:
    return "mock" if cashfree_service.is_mock() else environment


def _require_credentials(app_id: str, secret_key: str) -> None:
    if not cashfree_service.is_mock() and not (app_id and secret_key):
        raise HTTPException(status_code=503, detail="Online payments are not configured yet. Please try again later.")


def _extend_from(current: Optional[datetime], days: int) -> datetime:
    """Adds days to an expiry that is still in the future, otherwise to now."""
    now = datetime.now(timezone.utc)
    if current is not None and current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    start_date = current if (current and current > now) else now
    return start_date + timedelta(days=days)


def _credit_user_plan_and_leads(db: Session, order: Order, payment_id: Optional[str] = None) -> User:
    """
    Atomically marks order as paid and credits user plan, leads balance, and validity.
    Idempotent: if order is already paid, simply returns the user without double-crediting.
    """
    if order.status == "paid":
        return db.query(User).filter(User.id == order.user_id).first()

    order.status = "paid"
    if payment_id:
        order.cashfree_payment_id = payment_id

    user = db.query(User).filter(User.id == order.user_id).with_for_update().first()
    if user and order.plan and order.plan.plan_type == "featured":
        listing = db.query(Listing).filter(Listing.id == order.listing_id).with_for_update().first()
        if listing:
            # Buying again while still featured extends the current period.
            listing.is_featured = True
            listing.featured_until = _extend_from(listing.featured_until, order.plan.duration_days)
    elif user and order.plan:
        plan = order.plan
        user.plan_id = plan.id
        user.leads_balance += plan.leads_count
        user.listing_limit += plan.listing_limit
        user.plan_expires_at = _extend_from(user.plan_expires_at, plan.duration_days)

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
    Creates a server-side Cashfree order for the selected plan and returns the
    payment_session_id the browser checkout opens with.
    Price is always loaded strictly from the database (never trusted from frontend).
    """
    plan = db.query(Plan).filter(Plan.id == req.plan_id, Plan.status == "active").first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found or inactive.")

    listing_id = None
    if plan.plan_type == "featured":
        listing = db.query(Listing).filter(Listing.id == req.listing_id).first() if req.listing_id else None
        if not listing or listing.user_id != current_user.id:
            raise HTTPException(status_code=400, detail="Choose one of your listings to feature.")
        if listing.status != "approved":
            raise HTTPException(status_code=400, detail="Only approved listings can be featured.")
        listing_id = listing.id

    app_id, secret_key, environment = _get_active_cashfree_credentials(db)
    _require_credentials(app_id, secret_key)
    amount = round(float(plan.price), 2)

    # Idempotency check if idempotency_key is provided
    if req.idempotency_key:
        existing_order = db.query(Order).filter(
            Order.idempotency_key == req.idempotency_key,
            Order.user_id == current_user.id
        ).first()
        if existing_order and existing_order.status == "created" and existing_order.payment_session_id:
            return CreateOrderResponse(
                order_id=existing_order.cashfree_order_id,
                payment_session_id=existing_order.payment_session_id,
                environment=_checkout_mode(environment),
                amount=float(existing_order.amount),
                currency=existing_order.currency,
                plan=PlanRead.model_validate(plan),
            )

    tags = {
        "user_id": str(current_user.id),
        "plan_id": str(plan.id),
        **({"listing_id": str(listing_id)} if listing_id else {})
    }
    try:
        cf_order = cashfree_service.create_order(
            order_id=f"tc_{current_user.id}_{uuid.uuid4().hex[:16]}",
            amount=amount,
            customer={
                "customer_id": f"user_{current_user.id}",
                "customer_name": current_user.name,
                "customer_email": current_user.email,
                "customer_phone": current_user.phone,
            },
            app_id=app_id,
            secret_key=secret_key,
            environment=environment,
            tags=tags,
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Unable to create payment order with Cashfree. Please try again.")

    new_order = Order(
        user_id=current_user.id,
        plan_id=plan.id,
        listing_id=listing_id,
        cashfree_order_id=cf_order["order_id"],
        payment_session_id=cf_order["payment_session_id"],
        amount=plan.price,
        currency="INR",
        status="created",
        idempotency_key=req.idempotency_key,
        notes=tags
    )
    db.add(new_order)
    db.commit()

    return CreateOrderResponse(
        order_id=cf_order["order_id"],
        payment_session_id=cf_order["payment_session_id"],
        environment=_checkout_mode(environment),
        amount=amount,
        currency="INR",
        plan=PlanRead.model_validate(plan),
    )


@router.post("/verify", response_model=VerifyPaymentResponse)
def verify_payment(
    req: VerifyPaymentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Confirms the order's payment with Cashfree (server-to-server) and atomically credits
    the user's plan and leads.
    Idempotent: Duplicate requests for the same order return success without double crediting.
    """
    order = (
        db.query(Order)
        .filter(Order.cashfree_order_id == req.order_id)
        .with_for_update()
        .first()
    )

    if not order:
        raise HTTPException(status_code=404, detail="Order not found for this payment.")

    if order.user_id and order.user_id != current_user.id and current_user.role.lower() != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to reconcile this order.")

    if order.status != "paid":
        app_id, secret_key, environment = _get_active_cashfree_credentials(db)
        _require_credentials(app_id, secret_key)
        try:
            payment = cashfree_service.get_successful_payment(
                order_id=order.cashfree_order_id,
                app_id=app_id,
                secret_key=secret_key,
                environment=environment
            )
        except httpx.HTTPError:
            raise HTTPException(status_code=502, detail="Unable to confirm payment with Cashfree. Please try again.")

        if not payment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment verification failed: payment not completed."
            )
        if "payment_amount" in payment and abs(float(payment["payment_amount"]) - float(order.amount)) > 0.01:
            raise HTTPException(status_code=400, detail="Payment verification failed: amount mismatch.")

        _credit_user_plan_and_leads(db, order, str(payment.get("cf_payment_id")))

    user = db.query(User).filter(User.id == order.user_id).first()
    plan_name = order.plan.name if order.plan else "Active Plan"
    if order.plan and order.plan.plan_type == "featured":
        listing = db.query(Listing).filter(Listing.id == order.listing_id).first()
        return VerifyPaymentResponse(
            status="success",
            message="Payment verified. Your listing is now featured!",
            plan={
                "plan_name": plan_name,
                "listing_id": order.listing_id,
                "featured_until": listing.featured_until.isoformat() if (listing and listing.featured_until) else None
            }
        )
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
async def cashfree_webhook(
    request: Request,
    x_webhook_signature: Optional[str] = Header(None),
    x_webhook_timestamp: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Cashfree Webhook endpoint. Verifies x-webhook-signature against timestamp + raw body,
    reconciles order state, and credits user plan/leads idempotently.
    """
    raw_body = await request.body()
    if not x_webhook_signature or not x_webhook_timestamp:
        raise HTTPException(status_code=400, detail="Missing x-webhook-signature or x-webhook-timestamp header.")

    _, secret_key, _ = _get_active_cashfree_credentials(db)
    is_valid = cashfree_service.verify_webhook_signature(
        raw_body=raw_body,
        timestamp=x_webhook_timestamp,
        received_signature=x_webhook_signature,
        secret_key=secret_key
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    try:
        data = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    payload = data.get("data", {})
    order_id = payload.get("order", {}).get("order_id")
    payment = payload.get("payment", {})

    if data.get("type") == "PAYMENT_SUCCESS_WEBHOOK" and payment.get("payment_status") == "SUCCESS" and order_id:
        order = db.query(Order).filter(Order.cashfree_order_id == order_id).with_for_update().first()
        if order and order.status != "paid":
            _credit_user_plan_and_leads(db, order, payment_id=str(payment.get("cf_payment_id")))

    return {"status": "ok"}


@router.get("/admin/settings", response_model=dict)
def get_cashfree_settings(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin-only: Retrieve Cashfree configuration (secret is never exposed)."""
    app_id, secret_key, environment = _get_active_cashfree_credentials(db)
    return {
        "status": "success",
        "data": {
            "app_id": app_id,
            "has_secret": bool(secret_key),
            "environment": environment
        }
    }


@router.post("/admin/settings", response_model=dict)
def save_cashfree_settings(
    req: CashfreeSettingsUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin-only: Update Cashfree App ID, Secret Key, and environment."""
    if req.environment is not None and req.environment not in ("sandbox", "production"):
        raise HTTPException(status_code=400, detail="Environment must be 'sandbox' or 'production'.")

    updates = {}
    if req.app_id and req.app_id.strip():
        updates["cashfree_app_id"] = (req.app_id.strip(), False)
    if req.secret_key and req.secret_key.strip():
        updates["cashfree_secret_key"] = (encrypt_secret(req.secret_key.strip()), True)
    if req.environment:
        updates["cashfree_environment"] = (req.environment, False)

    for key, (value, is_encrypted) in updates.items():
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if row:
            row.value = value
            row.is_encrypted = is_encrypted
        else:
            db.add(SystemSetting(key=key, value=value, is_encrypted=is_encrypted))

    db.commit()
    app_id, secret_key, environment = _get_active_cashfree_credentials(db)
    return {
        "status": "success",
        "message": "Cashfree settings updated successfully.",
        "data": {
            "app_id": app_id,
            "has_secret": bool(secret_key),
            "environment": environment
        }
    }
