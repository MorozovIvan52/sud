"""
Эндпоинты определения подсудности.
GET /api/v1/jurisdiction/address
GET /api/v1/jurisdiction/coordinates
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, rate_limiter
from app.core.database import get_db
from app.core.exceptions import (
    AddressNotFoundError,
    CourtNotFoundError,
    GeocodingError,
    JurisdictionError,
    ValidationError,
)
from app.schemas.jurisdiction import (
    JurisdictionErrorResponse,
    JurisdictionResponse,
)
from app.services.jurisdiction_service import JurisdictionService

router = APIRouter(prefix="/jurisdiction", tags=["jurisdiction"])


def _error_response(exc: JurisdictionError) -> JurisdictionErrorResponse:
    return JurisdictionErrorResponse(
        success=False,
        error=exc.message,
        code=exc.code,
        details=exc.details if exc.details else None,
    )


@router.get(
    "/address",
    response_model=JurisdictionResponse,
    responses={
        400: {"model": JurisdictionErrorResponse, "description": "Неверный адрес"},
        401: {"description": "Требуется аутентификация"},
        404: {"model": JurisdictionErrorResponse, "description": "Адрес или суд не найден"},
        429: {"description": "Превышен лимит запросов"},
    },
)
async def get_jurisdiction_by_address(
    address: Annotated[str, Query(..., min_length=5)],
    court_type: Annotated[str | None, Query()] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    _user: Annotated[str, Depends(get_current_user)] = None,
    _rate: Annotated[None, Depends(rate_limiter)] = None,
):
    """
    Определение подсудности по адресу.
    Пример: ?address=г. Москва, ул. Тверская, д. 7
    """
    service = JurisdictionService(db)
    try:
        result = await service.determine_by_address(address, court_type)
        return JurisdictionResponse(**result)
    except ValidationError as e:
        from fastapi import HTTPException
        raise HTTPException(400, detail=_error_response(e).model_dump())
    except AddressNotFoundError as e:
        from fastapi import HTTPException
        raise HTTPException(404, detail=_error_response(e).model_dump())
    except CourtNotFoundError as e:
        from fastapi import HTTPException
        raise HTTPException(404, detail=_error_response(e).model_dump())
    except GeocodingError as e:
        from fastapi import HTTPException
        raise HTTPException(502, detail=_error_response(e).model_dump())


@router.get(
    "/coordinates",
    response_model=JurisdictionResponse,
    responses={
        401: {"description": "Требуется аутентификация"},
        404: {"model": JurisdictionErrorResponse, "description": "Суд не найден"},
        429: {"description": "Превышен лимит запросов"},
    },
)
async def get_jurisdiction_by_coordinates(
    latitude: Annotated[float, Query(ge=-90, le=90)],
    longitude: Annotated[float, Query(ge=-180, le=180)],
    court_type: Annotated[str | None, Query()] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    _user: Annotated[str, Depends(get_current_user)] = None,
    _rate: Annotated[None, Depends(rate_limiter)] = None,
):
    """
    Определение подсудности по координатам (WGS84).
    Пример: ?latitude=55.7558&longitude=37.6173
    """
    service = JurisdictionService(db)
    try:
        result = await service.determine_by_coordinates(latitude, longitude, court_type)
        return JurisdictionResponse(**result)
    except CourtNotFoundError as e:
        from fastapi import HTTPException
        raise HTTPException(404, detail=_error_response(e).model_dump())
