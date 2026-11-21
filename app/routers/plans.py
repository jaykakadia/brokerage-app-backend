from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_current_admin, get_optional_user, get_db
from app.db.models.user import User
from app.db.models.plan import Plan
from app.db.models.trial_claim import TrialClaim
from app.schemas.common import APIResponse, MessageResponse
from app.schemas.plan import PlanRead, PlanCreate, PlanUpdate

router = APIRouter(prefix="/api/v1/plans", tags=["Plans"])


@router.get("", response_model=dict)
def get_plans(
    all: Optional[bool] = Query(False),
    type: str = Query("leads", pattern="^(leads|featured)$"),
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    Returns plans.
    Public users see only active plans ordered by sort_order and price.
    Admins can request all plans (including inactive).
    If the current authenticated user has already claimed a trial plan (by email),
    trial plans are excluded from the results.
    """
    query = db.query(Plan).filter(Plan.plan_type == type, Plan.is_deleted == False)
    is_admin = user and user.role.lower() == "admin"

    if not is_admin or not all:
        query = query.filter(Plan.status == "active")

    if user and not is_admin:
        email_clean = user.email.lower().strip()
        has_claimed = db.query(TrialClaim.id).filter(TrialClaim.email == email_clean).first() is not None
        if has_claimed:
            query = query.filter(Plan.is_trial == False)

    plans = query.order_by(Plan.sort_order.asc(), Plan.price.asc()).all()
    return {
        "status": "success",
        "data": [PlanRead.model_validate(p).model_dump() for p in plans]
    }


@router.get("/{plan_id}", response_model=APIResponse[PlanRead])
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.is_deleted == False).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")
    return APIResponse(status="success", data=PlanRead.model_validate(plan))


@router.post("/{plan_id}/claim-trial", response_model=APIResponse[dict])
def claim_trial_plan(
    plan_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Claims a free trial plan for the authenticated user.
    Each email address can only claim a trial plan once.
    """
    plan = db.query(Plan).filter(
        Plan.id == plan_id,
        Plan.is_deleted == False,
        Plan.status == "active"
    ).first()
    if not plan or not plan.is_trial:
        raise HTTPException(status_code=400, detail="Invalid trial plan.")

    if float(plan.price) > 0.0:
        raise HTTPException(
            status_code=400,
            detail="This trial plan requires payment. Please complete payment checkout."
        )

    email_clean = current_user.email.lower().strip()
    existing_claim = db.query(TrialClaim).filter(TrialClaim.email == email_clean).first()
    if existing_claim:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The trial plan has already been availed for this email address."
        )

    try:
        new_claim = TrialClaim(
            email=email_clean,
            phone=current_user.phone.strip() if current_user.phone else None,
            plan_id=plan.id,
            user_id=current_user.id
        )
        db.add(new_claim)

        from app.routers.payments import _extend_from
        current_user.plan_id = plan.id
        current_user.leads_balance += plan.leads_count
        current_user.listing_limit += plan.listing_limit
        current_user.plan_expires_at = _extend_from(current_user.plan_expires_at, plan.duration_days)

        db.commit()
        db.refresh(current_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The trial plan has already been availed for this email address."
        )

    return APIResponse(
        status="success",
        data={
            "message": "Trial plan activated successfully!",
            "plan_name": plan.name,
            "leads_balance": current_user.leads_balance,
            "listing_limit": current_user.listing_limit,
            "plan_expires_at": current_user.plan_expires_at.isoformat() if current_user.plan_expires_at else None
        }
    )


@router.post("", response_model=APIResponse[PlanRead])
def create_or_save_plan(
    plan_in: PlanCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin-only: Create a new plan."""
    plan = Plan(
        name=plan_in.name.strip(),
        plan_type=plan_in.plan_type,
        description=plan_in.description,
        price=plan_in.price,
        listing_limit=plan_in.listing_limit,
        leads_count=plan_in.leads_count or plan_in.listing_limit,
        duration_days=plan_in.duration_days,
        status=plan_in.status,
        sort_order=plan_in.sort_order,
        is_trial=plan_in.is_trial
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return APIResponse(status="success", data=PlanRead.model_validate(plan))


@router.put("/{plan_id}", response_model=APIResponse[PlanRead])
def update_plan(
    plan_id: int,
    plan_in: PlanUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin-only: Update existing plan."""
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    update_data = plan_in.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        if val is not None:
            setattr(plan, field, val)

    db.commit()
    db.refresh(plan)
    return APIResponse(status="success", data=PlanRead.model_validate(plan))


@router.delete("/{plan_id}", response_model=MessageResponse)
def delete_plan(
    plan_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin-only: Delete plan."""
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    plan.is_deleted = True
    plan.deleted_at = datetime.now(timezone.utc)
    plan.status = "inactive"
    db.commit()
    return MessageResponse(status="success", message="Plan deleted successfully.")
