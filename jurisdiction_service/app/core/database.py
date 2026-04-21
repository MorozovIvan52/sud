"""
Асинхронное подключение к PostgreSQL (asyncpg) и Redis.
Пул соединений: ru.stackoverflow.com, www.tigerdata.com
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from redis.asyncio import Redis

from app.core.config import get_settings
from app.models.base import Base

# Engine с пулом соединений
_engine = None
_async_session_factory = None
_redis_client: Redis | None = None


def get_engine():
    """Создаёт async engine для PostgreSQL."""
    global _engine
    if _engine is None:
        settings = get_settings()
        # asyncpg требует postgresql+asyncpg://
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
    return _engine


def get_async_session_factory():
    """Фабрика асинхронных сессий SQLAlchemy."""
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_engine()
        _async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Зависимость FastAPI: сессия БД."""
    factory = get_async_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_redis() -> Redis:
    """Клиент Redis для кэширования и rate limit."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


async def init_db() -> None:
    """Инициализация БД: создание таблиц (для dev). В prod — Alembic."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Закрытие соединений при shutdown."""
    global _engine, _redis_client
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
