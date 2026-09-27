from typing import Optional
from sqlalchemy import String, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class Blog(Base, TimestampMixin):
    """Article / Blog model for market insights and guides."""
    __tablename__ = "blogs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), default="market", nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    permalink: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    tags: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="published", nullable=False, index=True)  # published, draft
    author: Mapped[str] = mapped_column(String(150), default="TradeCall Team", nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
