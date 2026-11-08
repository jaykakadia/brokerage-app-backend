from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SupportConversationInit(BaseModel):
    name: Optional[str] = Field(None, max_length=150)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=30)
    session_id: Optional[str] = Field(None, max_length=64)


class SupportMessageCreate(BaseModel):
    message: Optional[str] = Field(None, max_length=5000)
    attachment_url: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def validate_content(self):
        msg = (self.message or "").strip()
        att = (self.attachment_url or "").strip()
        if not msg and not att:
            raise ValueError("Either message text or attachment_url must be provided.")
        return self


class SupportMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    sender_type: str
    sender_id: Optional[int] = None
    sender_name: str
    message: str
    attachment_url: Optional[str] = None
    is_read: bool
    created_at: datetime


class SupportConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    user_id: Optional[int] = None
    display_name: str
    display_email: Optional[str] = None
    display_phone: Optional[str] = None
    is_registered_user: bool = False
    status: str
    unread_admin_count: int = 0
    unread_user_count: int = 0
    last_message_at: datetime
    created_at: datetime
    messages: List[SupportMessageResponse] = []


class SupportConversationListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    user_id: Optional[int] = None
    display_name: str
    display_email: Optional[str] = None
    display_phone: Optional[str] = None
    is_registered_user: bool = False
    status: str
    unread_admin_count: int = 0
    unread_user_count: int = 0
    last_message_text: Optional[str] = None
    last_message_at: datetime
    created_at: datetime


class SupportStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(open|in_progress|resolved|closed)$")
