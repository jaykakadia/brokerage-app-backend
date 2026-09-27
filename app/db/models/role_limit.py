from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin


class RoleLimit(Base, TimestampMixin):
    """Configurable max listings limit per user role."""
    __tablename__ = "role_limits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)  # Owner, Agent, Builder
    max_listings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

