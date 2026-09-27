from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class BlogBase(BaseModel):
    title: str
    category: str = "market"
    content: str
    permalink: Optional[str] = None
    tags: Optional[str] = None
    status: str = "published"  # published, draft
    author: str = "TradeCall Team"
    image_url: Optional[str] = None


class BlogCreate(BlogBase):
    pass


class BlogUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    content: Optional[str] = None
    permalink: Optional[str] = None
    tags: Optional[str] = None
    status: Optional[str] = None
    author: Optional[str] = None
    image_url: Optional[str] = None


class BlogRead(BlogBase):
    id: int
    permalink: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
