from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from geoalchemy2 import Geometry
from app.database import Base
from datetime import datetime


class Court(Base):
    __tablename__ = "courts"

    id = Column(Integer, primary_key=True, index=True)
    court_code = Column(String(20))
    court_name = Column(String(255))
    court_type = Column(String(50))
    address = Column(Text, nullable=True)
    geometry = Column(Geometry("POLYGON", srid=4326), nullable=True)
    source_accuracy = Column(String(20), nullable=True)
    valid_from = Column(DateTime, default=datetime.utcnow, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class VerificationResult(Base):
    __tablename__ = "verification_results"

    id = Column(Integer, primary_key=True, index=True)
    court_id = Column(Integer, ForeignKey("courts.id"), nullable=True)
    source_type = Column(String(50))
    verification_date = Column(DateTime, default=datetime.utcnow)
    result = Column(JSONB, nullable=True)
    status = Column(String(20))


class VerificationHistory(Base):
    __tablename__ = "verification_history"

    id = Column(Integer, primary_key=True, index=True)
    result_id = Column(Integer, ForeignKey("verification_results.id"), nullable=True)
    change_type = Column(String(50))
    change_description = Column(Text, nullable=True)
    change_date = Column(DateTime, default=datetime.utcnow)
