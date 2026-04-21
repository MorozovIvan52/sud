"""
Модели судебных участков и границ.
PostGIS geometry: gist.github.com/Miron-Anosov, pgdocs.ru/postgis
"""
from datetime import date, datetime
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import Date, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at, updated_at, uuid_pk


class CourtDistrict(Base):
    """
    Судебный участок с границами (полигон).
    court_type: 'районный' | 'мировой'
    geometry: POLYGON в SRID 4326 (WGS84)
    """

    __tablename__ = "court_districts"

    id: Mapped[str] = uuid_pk
    court_code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    court_name: Mapped[str] = mapped_column(String(500))
    court_type: Mapped[str] = mapped_column(String(50), default="мировой")  # районный, мировой
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    geometry: Mapped[Optional[str]] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326),
        nullable=True,
    )
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = created_at
    updated_at: Mapped[datetime] = updated_at

    __table_args__ = (
        Index("idx_court_districts_geometry", "geometry", postgresql_using="gist"),
    )


class GeocodingCache(Base):
    """Кэш результатов геокодирования (адрес → координаты)."""

    __tablename__ = "geocoding_cache"

    id: Mapped[str] = uuid_pk
    address_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    address: Mapped[str] = mapped_column(Text)
    latitude: Mapped[float] = mapped_column()
    longitude: Mapped[float] = mapped_column()
    provider: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = created_at
