from typing import Optional
from sqlalchemy import Integer, Text, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin, SoftDeleteMixin


class Review(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "listing_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    listing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 to 5
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )  # pending, approved, rejected

    __table_args__ = (
        UniqueConstraint("user_id", "listing_id", name="uq_user_listing_review"),
    )

    user = relationship("User", backref="reviews")
    listing = relationship("Listing", backref="reviews")
