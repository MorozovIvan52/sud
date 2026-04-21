"""
Модели результатов верификации и истории изменений.
"""
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at, uuid_pk


class VerificationResult(Base):
    """
    Результат верификации судебного участка.
    """

    __tablename__ = "verification_results"

    id: Mapped[str] = uuid_pk
    court_id: Mapped[str] = mapped_column(String(36), index=True)  # court_districts.id (UUID)
    source_type: Mapped[str] = mapped_column(String(50))  # topology, official, commercial, manual
    verification_date: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())
    result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed")  # completed, failed, partial
    duration_ms: Mapped[Optional[float]] = mapped_column(nullable=True)
    created_at: Mapped = created_at


class VerificationHistory(Base):
    """
    История изменений результатов верификации (аудит).
    """

    __tablename__ = "verification_history"

    id: Mapped[str] = uuid_pk
    result_id: Mapped[str] = mapped_column(String(36), index=True)  # verification_results.id
    change_type: Mapped[str] = mapped_column(String(50))  # created, updated, manual_check, rejected
    change_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    change_date: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped = created_at
