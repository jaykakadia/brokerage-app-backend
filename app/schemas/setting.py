from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr


class MailSettingsRead(BaseModel):
    smtp_host: str = "smtp.gmail.com"
    smtp_email: str = ""
    smtp_port: int = 587
    smtp_encryption: str = "tls"  # ssl, tls
    from_name: str = "TradeCall India"
    has_password: bool = False

    model_config = ConfigDict(from_attributes=True)


class MailSettingsUpdate(BaseModel):
    smtp_host: str
    smtp_email: str
    smtp_password: Optional[str] = None
    smtp_port: int = 587
    smtp_encryption: str = "tls"
    from_name: Optional[str] = "TradeCall India"


class TestMailRequest(BaseModel):
    test_email: str
