from sqlalchemy.orm import Session
from geoalchemy2.functions import ST_Within, ST_GeomFromText, ST_Distance
from geoalchemy2.elements import WKTElement
from . import models, schemas


def get_court_by_location(db: Session, latitude: float, longitude: float):
    """Поиск суда по координатам (точка внутри полигона)."""
    point_wkt = f"POINT({longitude} {latitude})"
    court = (
        db.query(models.Court)
        .filter(
            models.Court.geometry.isnot(None),
            ST_Within(ST_GeomFromText(point_wkt, 4326), models.Court.geometry),
        )
        .first()
    )
    return court


def get_court_by_id(db: Session, court_id: int):
    """Получить суд по id."""
    return db.query(models.Court).filter(models.Court.id == court_id).first()


def create_court(db: Session, court: schemas.CourtCreate):
    """Создать запись суда."""
    data = court.model_dump(exclude={"geometry"})
    db_court = models.Court(**data)
    if court.geometry:
        from geoalchemy2 import WKTElement
        from shapely.geometry import shape
        geom = shape(court.geometry)
        db_court.geometry = WKTElement(geom.wkt, srid=4326)
    db.add(db_court)
    db.commit()
    db.refresh(db_court)
    return db_court


def create_verification_result(db: Session, court_id: int, source_type: str, result: dict, status: str):
    """Сохранить результат верификации."""
    vr = models.VerificationResult(
        court_id=court_id,
        source_type=source_type,
        result=result,
        status=status,
    )
    db.add(vr)
    db.commit()
    db.refresh(vr)
    return vr
