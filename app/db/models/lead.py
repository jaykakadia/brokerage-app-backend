from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class LeadReveal(Base):
    __tablename__ = "lead_reveals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    listing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_name_revealed: Mapped[str | None] = mapped_column(String(150), nullable=True)
    owner_phone_revealed: Mapped[str | None] = mapped_column(String(50), nullable=True)
    owner_email_revealed: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "listing_id", name="uq_user_listing_lead_reveal"),
    )

    user = relationship("User", backref="lead_reveals")
    listing = relationship("Listing", backref="lead_reveals")
