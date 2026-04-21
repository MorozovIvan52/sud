"""
Базовая модель SQLAlchemy 2.0 с DeclarativeBase и Mapped.
См. habr.com/ru/companies/amvera/articles/849836/, www.pvsm.ru
"""
from datetime import datetime
from typing import Annotated
from uuid import uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""

    pass


# Типы для переиспользования
uuid_pk = Annotated[str, mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))]
created_at = Annotated[datetime, mapped_column(DateTime(timezone=True), server_default=func.now())]
updated_at = Annotated[datetime, mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())]
