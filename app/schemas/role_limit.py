from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class RoleLimitRead(BaseModel):
    role: str
    max_listings: int

    model_config = ConfigDict(from_attributes=True)


class RoleLimitsUpdate(BaseModel):
    limits: Dict[str, int]
