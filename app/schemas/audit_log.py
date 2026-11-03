from datetime import datetime
from typing import Optional, Any, List
from pydantic import BaseModel


class AuditLogRead(BaseModel):
    id: int
    table_name: str
    record_id: int
    record_name: Optional[str] = None
    action: str
    changes: Optional[Any] = None
    actor_id: Optional[int] = None
    actor_email: Optional[str] = None
    actor_role: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogPaginationData(BaseModel):
    items: List[AuditLogRead]
    total: int
    page: int
    limit: int
    total_pages: int


class AuditLogListResponse(BaseModel):
    status: str = "success"
    data: AuditLogPaginationData

