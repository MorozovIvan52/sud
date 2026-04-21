"""
Административные эндпоинты: создание пользователя, загрузка тестовых данных.
Опционально для dev/setup.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.schemas.user import UserCreate, TokenResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/users", response_model=TokenResponse)
async def create_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Создание пользователя и получение JWT.
    Для первоначальной настройки. В prod — отключить или защитить.
    """
    existing = await db.execute(select(User).where(User.username == user_in.username))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Пользователь уже существует")
    user = User(
        username=user_in.username,
        hashed_password=get_password_hash(user_in.password),
        api_key=None,
        daily_limit=1000,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_access_token(subject=str(user.id))
    return TokenResponse(access_token=token)


@router.post("/auth/token", response_model=TokenResponse)
async def login(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """Получение JWT по username и password."""
    from app.core.security import verify_password
    result = await db.execute(select(User).where(User.username == user_in.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(401, "Неверный логин или пароль")
    token = create_access_token(subject=str(user.id))
    return TokenResponse(access_token=token)
