"""
Модель пользователя API для JWT и лимитов.
"""
from datetime import datetime

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at, uuid_pk


class User(Base):
    """Пользователь API с токенами и лимитами запросов."""

    __tablename__ = "users"

    id: Mapped[str] = uuid_pk
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    api_key: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=True)
    daily_limit: Mapped[int] = mapped_column(Integer, default=1000)
    created_at: Mapped[datetime] = created_at
