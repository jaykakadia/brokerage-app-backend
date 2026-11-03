from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin, SoftDeleteMixin


class PageMetadata(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "page_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    path: Mapped[str] = mapped_column(String(500), unique=True, index=True, nullable=False)
    meta_title: Mapped[str] = mapped_column(String(500), nullable=False)
    meta_description: Mapped[str] = mapped_column(Text, nullable=False)
