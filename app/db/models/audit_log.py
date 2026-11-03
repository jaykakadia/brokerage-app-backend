from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy import String, Integer, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    table_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    record_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # CREATE, UPDATE, SOFT_DELETE, RESTORE
    changes: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    actor_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    actor_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )

