from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class PageMetadataBase(BaseModel):
    path: str = Field(..., description="Normalized URL path (e.g. / or /properties/palwal)")
    meta_title: str = Field(..., description="Meta Name or Meta Title for the page")
    meta_description: str = Field(..., description="Meta Description for SEO and search snippets")


class PageMetadataCreate(PageMetadataBase):
    pass


class PageMetadataUpdate(BaseModel):
    path: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None


class PageMetadataRead(PageMetadataBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
