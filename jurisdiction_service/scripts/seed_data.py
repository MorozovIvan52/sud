"""
Скрипт загрузки тестовых данных: пользователь, полигоны судебных участков.
Запуск: python -m scripts.seed_data
"""
import asyncio
import sys
from pathlib import Path

# Добавить корень проекта в path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from geoalchemy2 import WKTElement

from app.core.database import get_engine, get_async_session_factory
from app.core.security import get_password_hash
from app.models.base import Base
from app.models.jurisdiction import CourtDistrict
from app.models.user import User


async def seed():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))

    factory = get_async_session_factory()
    async with factory() as session:
        # Тестовый пользователь
        from sqlalchemy import select
        r = await session.execute(select(User).where(User.username == "test"))
        if r.scalar_one_or_none() is None:
            user = User(
                username="test",
                hashed_password=get_password_hash("test123"),
                daily_limit=1000,
            )
            session.add(user)
            await session.commit()
            print("User test/test123 created")

        # Тестовый полигон: Москва, Тверская (lon, lat) — точка 37.6173, 55.7558 внутри
        r = await session.execute(select(CourtDistrict).where(CourtDistrict.court_code == "TEST_VNKOD"))
        if r.scalar_one_or_none() is None:
            wkt = "POLYGON((37.6 55.75, 37.65 55.75, 37.65 55.76, 37.6 55.76, 37.6 55.75))"
            district = CourtDistrict(
                court_code="TEST_VNKOD",
                court_name="Мировой судья судебного участка № 1 (тестовый)",
                court_type="мировой",
                address="г. Москва, ул. Тверская, д. 7",
                geometry=WKTElement(wkt, srid=4326),
            )
            session.add(district)
            await session.commit()
            print("Test court district created (Тверская область)")

        # Полигон для Хабаровского края, Комсомольск-на-Амуре
        r = await session.execute(select(CourtDistrict).where(CourtDistrict.court_code == "KOMS_VNKOD"))
        if r.scalar_one_or_none() is None:
            wkt = "POLYGON((136.4 50.5, 136.6 50.5, 136.6 50.6, 136.4 50.6, 136.4 50.5))"
            district = CourtDistrict(
                court_code="KOMS_VNKOD",
                court_name="Мировой судья судебного участка г. Комсомольск-на-Амуре (тестовый)",
                court_type="мировой",
                address="Хабаровский край, г. Комсомольск-на-Амуре, ул. Юбилейная, 14",
                geometry=WKTElement(wkt, srid=4326),
            )
            session.add(district)
            await session.commit()
            print("Test court district created (Комсомольск-на-Амуре)")


if __name__ == "__main__":
    asyncio.run(seed())
