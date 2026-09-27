from datetime import datetime
from pydantic import BaseModel


class SystemSettingRead(BaseModel):
    id: int
    key: str
    value: str
    updated_at: datetime

    model_config = {"from_attributes": True}
