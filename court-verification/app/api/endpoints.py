from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import crud, schemas
from ..database import get_db
from ..services.verification_engine import VerificationEngine
from ..services.boundary_validator import BoundaryValidator
from ..services.yandex_maps import YandexMapsService
from ..services.dadata import DaDataService

router = APIRouter()
yandex_service = YandexMapsService()
dadata_service = DaDataService()


@router.post("/courts/", response_model=schemas.CourtResponse)
def create_court(court: schemas.CourtCreate, db: Session = Depends(get_db)):
    """Создать запись суда с геометрией."""
    db_court = crud.create_court(db, court)
    return db_court


@router.get("/courts/{court_id}", response_model=schemas.CourtResponse)
def get_court(court_id: int, db: Session = Depends(get_db)):
    """Получить суд по id."""
    court = crud.get_court_by_id(db, court_id)
    if not court:
        raise HTTPException(404, "Суд не найден")
    return court


@router.post("/find-court", response_model=schemas.CourtResponse)
def find_court_by_location(location: schemas.LocationRequest, db: Session = Depends(get_db)):
    """
    Поиск суда по координатам (точка внутри полигона).
    Если в БД нет подходящего участка — возвращается 404.
    """
    court = crud.get_court_by_location(db, location.latitude, location.longitude)
    if not court:
        raise HTTPException(
            404,
            detail="Суд не найден для указанных координат. Добавьте полигоны в таблицу courts.",
        )
    return court


@router.post("/location/", response_model=schemas.LocationResponse)
def get_court_by_location(body: schemas.LocationRequest, db: Session = Depends(get_db)):
    """Определить суд по координатам (точка внутри полигона)."""
    court = crud.get_court_by_location(db, body.latitude, body.longitude)
    if not court:
        return schemas.LocationResponse(court=None, distance_km=None, found=False)
    return schemas.LocationResponse(court=court, distance_km=0.0, found=True)


@router.post("/verification/start", response_model=schemas.VerificationResponse)
def start_verification(body: schemas.VerificationRequest, db: Session = Depends(get_db)):
    """Запуск верификации для суда."""
    court = crud.get_court_by_id(db, body.court_id)
    if not court:
        raise HTTPException(404, "Суд не найден")
    result = VerificationEngine.run_verification(court)
    vr = crud.create_verification_result(
        db,
        court_id=body.court_id,
        source_type=result["source_type"],
        result=result["result"],
        status=result["status"],
    )
    return schemas.VerificationResponse(
        court_id=body.court_id,
        source_type=result["source_type"],
        status=result["status"],
        result=result["result"],
    )


@router.post("/verification/validate-geometry")
def validate_geometry_standalone(geometry: dict):
    """Проверка геометрии без БД (тест BoundaryValidator)."""
    return BoundaryValidator.validate_geometry(geometry)
