"""
API системы верификации границ судебных участков.
POST /api/v1/verification/start
GET  /api/v1/verification/results/{court_id}
POST /api/v1/verification/manual-check
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.jurisdiction import CourtDistrict
from app.models.verification_result import VerificationResult, VerificationHistory
from app.schemas.verification_system import (
    ManualVerificationRequest,
    ManualVerificationResponse,
    VerificationResultsResponse,
    VerificationStartRequest,
    VerificationStartResponse,
)
from app.services.verification.validator_service import ValidatorService

router = APIRouter(prefix="/verification", tags=["verification_system"])


@router.post("/start", response_model=VerificationStartResponse)
async def start_verification(
    body: VerificationStartRequest,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    _user: Annotated[str, Depends(get_current_user)] = None,
):
    """
    Запуск процесса верификации для судебного участка.
    Требует аутентификации.
    """
    # Проверить существование суда
    row = await db.execute(select(CourtDistrict).where(CourtDistrict.id == body.court_id))
    if not row.scalar_one_or_none():
        raise HTTPException(404, "Суд не найден")

    validator = ValidatorService(db)
    result = await validator.verify_court(body.court_id)

    # Сохранить результат
    vr = VerificationResult(
        court_id=body.court_id,
        source_type="full",
        result=result,
        status=result.get("status", "completed"),
        duration_ms=result.get("duration_ms"),
    )
    db.add(vr)
    await db.commit()
    await db.refresh(vr)

    return VerificationStartResponse(
        court_id=body.court_id,
        verification_id=str(vr.id),
        result=result,
        message="Верификация выполнена",
    )


@router.get("/results/{court_id}", response_model=VerificationResultsResponse)
async def get_verification_results(
    court_id: str,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    _user: Annotated[str, Depends(get_current_user)] = None,
):
    """
    Получение результатов верификации по суду.
    """
    row = await db.execute(
        select(VerificationResult)
        .where(VerificationResult.court_id == court_id)
        .order_by(VerificationResult.verification_date.desc())
        .limit(50)
    )
    results = row.scalars().all()
    list_results = [
        {
            "id": str(r.id),
            "source_type": r.source_type,
            "verification_date": r.verification_date.isoformat() if r.verification_date else None,
            "status": r.status,
            "duration_ms": r.duration_ms,
            "result": r.result,
        }
        for r in results
    ]
    latest = list_results[0] if list_results else None
    return VerificationResultsResponse(
        court_id=court_id,
        results=list_results,
        latest=latest,
    )


@router.post("/manual-check", response_model=ManualVerificationResponse)
async def manual_verification(
    body: ManualVerificationRequest,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    user_id: Annotated[str, Depends(get_current_user)] = None,
):
    """
    Ручная верификация (оператор проверил данные).
    """
    row = await db.execute(select(CourtDistrict).where(CourtDistrict.id == body.court_id))
    if not row.scalar_one_or_none():
        raise HTTPException(404, "Суд не найден")

    vr = VerificationResult(
        court_id=body.court_id,
        source_type="manual",
        result={
            "verified_by": body.verified_by,
            "comment": body.comment,
            "status": body.status,
        },
        status=body.status,
    )
    db.add(vr)
    await db.commit()
    await db.refresh(vr)

    # Запись в историю
    hist = VerificationHistory(
        result_id=str(vr.id),
        change_type="manual_check",
        change_description=body.comment,
        user_id=user_id,
    )
    db.add(hist)
    await db.commit()

    return ManualVerificationResponse(result_id=str(vr.id))
