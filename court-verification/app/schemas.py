from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class CourtBase(BaseModel):
    court_code: str
    court_name: str
    court_type: str
    address: Optional[str] = None
    source_accuracy: Optional[str] = None


class CourtCreate(CourtBase):
    geometry: Optional[Dict[str, Any]] = None


class CourtResponse(CourtBase):
    id: int
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None

    class Config:
        from_attributes = True


class VerificationRequest(BaseModel):
    court_id: int


class VerificationResponse(BaseModel):
    court_id: int
    source_type: str
    status: str
    result: Optional[Dict[str, Any]] = None


class LocationRequest(BaseModel):
    latitude: float
    longitude: float


class LocationResponse(BaseModel):
    court: Optional[CourtResponse] = None
    distance_km: Optional[float] = None
    found: bool = False
