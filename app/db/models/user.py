from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="Owner", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    
    # Phase 2 forward compatibility fields
    plan_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    listing_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    leads_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    leads_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    plan_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Public business profile (optional, editable without OTP)
    business_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    whatsapp: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    facebook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    website_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    x_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    youtube_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Relationships
    listings: Mapped[List["Listing"]] = relationship("Listing", back_populates="user", cascade="all, delete-orphan")
