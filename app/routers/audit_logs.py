import math
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin, get_db
from app.db.models.audit_log import AuditLog
from app.db.models.user import User
from app.schemas.audit_log import AuditLogListResponse, AuditLogPaginationData, AuditLogRead
from app.schemas.common import APIResponse

router = APIRouter(prefix="/api/v1/admin/audit-logs", tags=["Admin Audit Logs"])


@router.get("", response_model=AuditLogListResponse)
def get_audit_logs(
    table_name: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    record_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin-only: Query audit change logs with filters, search, and pagination."""
    query = db.query(AuditLog)

    if table_name and table_name.lower() != "all":
        query = query.filter(AuditLog.table_name == table_name.strip().lower())

    if action and action.upper() != "ALL":
        query = query.filter(AuditLog.action == action.strip().upper())

    if record_id is not None and record_id > 0:
        query = query.filter(AuditLog.record_id == record_id)

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                AuditLog.record_name.ilike(term),
                AuditLog.actor_email.ilike(term),
                AuditLog.table_name.ilike(term)
            )
        )

    total = query.count()
    total_pages = max(1, math.ceil(total / limit))

    logs = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    items = [AuditLogRead.model_validate(l) for l in logs]

    return AuditLogListResponse(
        status="success",
        data=AuditLogPaginationData(
            items=items,
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages
        )
    )


@router.get("/tables", response_model=APIResponse[List[str]])
def get_audit_tables(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin-only: Get distinct tables that have audit records."""
    rows = db.query(AuditLog.table_name).distinct().order_by(AuditLog.table_name.asc()).all()
    tables = [r[0] for r in rows if r[0]]
    if not tables:
        tables = [
            "listings",
            "users",
            "categories",
            "locations",
            "plans",
            "employees",
            "blogs",
            "enquiries",
            "page_metadata",
            "wishlists"
        ]
    return APIResponse(status="success", data=tables)

