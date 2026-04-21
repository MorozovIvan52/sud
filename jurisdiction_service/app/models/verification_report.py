"""
Модель отчётов о верификации подсудности (краудсорсинг).
docs/jurisdiction_verification_sources.md
"""
from typing import Optional

from sqlalchemy import Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at, uuid_pk


class VerificationReport(Base):
    """
    Сообщение пользователя об ошибке определения подсудности.
    Используется для краудсорсинговой верификации данных.
    """

    __tablename__ = "verification_reports"

    id: Mapped[str] = uuid_pk
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reported_court: Mapped[str] = mapped_column(String(500))  # суд, который вернула система
    suggested_court: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # суд по мнению пользователя
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # опционально: id пользователя
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, reviewed, rejected
    created_at: Mapped = created_at
