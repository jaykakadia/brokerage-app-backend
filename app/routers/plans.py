from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin, get_optional_user, get_db
from app.db.models.user import User
from app.db.models.plan import Plan
from app.schemas.common import APIResponse, MessageResponse
from app.schemas.plan import PlanRead, PlanCreate, PlanUpdate

router = APIRouter(prefix="/api/v1/plans", tags=["Plans"])


@router.get("", response_model=dict)
def get_plans(
    all: Optional[bool] = Query(False),
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """
    Returns plans.
    Public users see only active plans ordered by sort_order and price.
    Admins can request all plans (including inactive).
    """
    query = db.query(Plan)
    is_admin = user and user.role.lower() == "admin"

    if not is_admin or not all:
        query = query.filter(Plan.status == "active")

    plans = query.order_by(Plan.sort_order.asc(), Plan.price.asc()).all()
    return {
        "status": "success",
        "data": [PlanRead.model_validate(p).model_dump() for p in plans]
    }


@router.get("/{plan_id}", response_model=APIResponse[PlanRead])
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")
    return APIResponse(status="success", data=PlanRead.model_validate(plan))


@router.post("", response_model=APIResponse[PlanRead])
def create_or_save_plan(
    plan_in: PlanCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin-only: Create a new plan."""
    plan = Plan(
        name=plan_in.name.strip(),
        description=plan_in.description,
        price=plan_in.price,
        listing_limit=plan_in.listing_limit,
        leads_count=plan_in.leads_count or plan_in.listing_limit,
        duration_days=plan_in.duration_days,
        status=plan_in.status,
        sort_order=plan_in.sort_order
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

    db.delete(plan)
    db.commit()
    return MessageResponse(status="success", message="Plan deleted successfully.")
