"""
Зависимости FastAPI: JWT-аутентификация, rate limiting.
habr.com/ru/articles/829742/, dev.to/dpills/rate-limit-fastapi-redis
"""
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.database import get_db, get_redis
from app.core.security import decode_access_token
from sqlalchemy.ext.asyncio import AsyncSession

security = HTTPBearer(auto_error=False)


async def get_optional_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
) -> Optional[str]:
    """
    Опциональная аутентификация. Возвращает user_id или None.
    """
    if credentials is None:
        return None
    token = credentials.credentials
    payload = decode_access_token(token)
    return str(payload.get("sub", "")) if payload else None


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
) -> str:
    """
    Проверка JWT из заголовка Authorization: Bearer <token>.
    Возвращает subject (user_id) или 401.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется аутентификация",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный или истёкший токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return str(payload.get("sub", ""))


async def rate_limiter(
    request: Request,
    user_id: Annotated[str, Depends(get_current_user)],
) -> None:
    """
    Ограничение запросов на пользователя (Redis).
    При превышении — 429 Too Many Requests.
    """
    settings = get_settings()
    key = f"rate:{user_id}"
    try:
        redis: Redis = await get_redis()
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, settings.rate_limit_window)
        results = await pipe.execute()
        count = results[0]
        if count > settings.rate_limit_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Превышен лимит запросов ({settings.rate_limit_requests} в час)",
            )
    except HTTPException:
        raise
    except Exception:
        pass  # При ошибке Redis пропускаем лимит
