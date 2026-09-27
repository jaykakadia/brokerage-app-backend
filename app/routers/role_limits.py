from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin, get_db
from app.db.models.user import User
from app.db.models.role_limit import RoleLimit
from app.schemas.common import APIResponse, MessageResponse
from app.schemas.role_limit import RoleLimitRead, RoleLimitsUpdate

router = APIRouter(prefix="/api/v1/admin/role-limits", tags=["Role Limits"])

DEFAULT_LIMITS = {
    "Owner": 0,
    "Agent": 0,
    "Builder": 0
}


def _ensure_role_limits_exist(db: Session) -> List[RoleLimit]:
    existing = {rl.role: rl for rl in db.query(RoleLimit).all()}
    for role, default_val in DEFAULT_LIMITS.items():
        if role not in existing:
            new_rl = RoleLimit(role=role, max_listings=default_val)
            db.add(new_rl)
            db.commit()
            db.refresh(new_rl)
            existing[role] = new_rl
    return list(existing.values())


@router.get("", response_model=APIResponse[List[RoleLimitRead]])
def get_role_limits(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin endpoint to fetch listing limits per user role."""
    limits = _ensure_role_limits_exist(db)
    # Return sorted by predefined canonical roles
    sorted_limits = sorted(limits, key=lambda x: ["Owner", "Agent", "Builder"].index(x.role) if x.role in ["Owner", "Agent", "Builder"] else 99)
    data = [RoleLimitRead(role=rl.role, max_listings=rl.max_listings) for rl in sorted_limits]
    return APIResponse(status="success", data=data)


@router.post("", response_model=MessageResponse)
def save_role_limits(
    req: RoleLimitsUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin endpoint to update listing limits per user role."""
    for role, limit in req.limits.items():
        if role not in {"Owner", "Agent", "Builder"}:
            continue
        try:
            val = int(limit)
            if val < 0:
                val = 0
        except (ValueError, TypeError):
            continue

        rl = db.query(RoleLimit).filter(RoleLimit.role == role).first()
        if rl:
            rl.max_listings = val
        else:
            db.add(RoleLimit(role=role, max_listings=val))

    db.commit()
    return MessageResponse(status="success", message="Role limits saved successfully.")
