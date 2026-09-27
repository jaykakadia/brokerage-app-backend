from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel


class LeadStatusResponse(BaseModel):
    status: str = "success"
    leads_balance: int
    leads_used: int
    plan_id: Optional[int] = None
    plan_expires_at: Optional[datetime] = None


class RevealContactRequest(BaseModel):
    listing_id: int


class RevealContactResponse(BaseModel):
    status: str = "success"
    contact: Dict[str, str]
    plan: Dict[str, int]
    already_revealed: bool = False
