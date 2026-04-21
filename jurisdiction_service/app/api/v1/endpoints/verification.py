"""
Краудсорсинговые отчёты о верификации подсудности.
POST /api/v1/jurisdiction/report-error — сообщение об ошибке (без JWT).
docs/jurisdiction_verification_sources.md
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_optional_user
from app.core.database import get_db, get_redis
from app.models.verification_report import VerificationReport
from app.schemas.verification import ReportErrorRequest, ReportErrorResponse

router = APIRouter(prefix="/jurisdiction", tags=["verification"])


async def rate_limit_report(request: Request) -> None:
    """Ограничение 10 отчётов в час с одного IP (для анонимных)."""
    try:
        redis = await get_redis()
        client_ip = request.client.host if request.client else "unknown"
        key = f"report_limit:{client_ip}"
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 3600)
        results = await pipe.execute()
        if results[0] > 10:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Превышен лимит отчётов (10 в час). Войдите для увеличения лимита.",
            )
    except HTTPException:
        raise
    except Exception:
        pass


@router.post(
    "/report-error",
    response_model=ReportErrorResponse,
    responses={
        400: {"description": "Неверные данные"},
        429: {"description": "Превышен лимит отчётов"},
    },
)
async def report_jurisdiction_error(
    body: ReportErrorRequest,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    _limit: Annotated[None, Depends(rate_limit_report)] = None,
    user_id: Annotated[str | None, Depends(get_optional_user)] = None,
):
    """
    Сообщить об ошибке определения подсудности (краудсорсинг).
    Не требует аутентификации. Лимит: 10 отчётов в час с одного IP.
    """
    if not body.address and (body.latitude is None or body.longitude is None):
        raise HTTPException(
            status_code=400,
            detail="Укажите адрес или координаты (latitude, longitude)",
        )

    report = VerificationReport(
        address=body.address,
        latitude=body.latitude,
        longitude=body.longitude,
        reported_court=body.reported_court,
        suggested_court=body.suggested_court,
        comment=body.comment,
        user_id=user_id if user_id else None,
        status="pending",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    return ReportErrorResponse(report_id=str(report.id))
