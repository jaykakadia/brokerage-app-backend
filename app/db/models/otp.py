from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class OtpVerification(Base):
    __tablename__ = "otp_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # register, forgot, profile_update
    otp_hash: Mapped[str] = mapped_column(String(255), nullable=False)  # Securely hashed OTP
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resend_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
