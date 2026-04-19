"""Движок верификации: координация проверок."""
from typing import Dict, Any
from ..models import Court
from .boundary_validator import BoundaryValidator


class VerificationEngine:
    @staticmethod
    def run_verification(court: Court) -> Dict[str, Any]:
        result = {
            "court_id": court.id,
            "source_type": "boundary_check",
            "status": "completed",
            "result": {},
        }
        if court.geometry:
            try:
                from geoalchemy2.shape import to_shape
                geom = to_shape(court.geometry)
                geojson = geom.__geo_interface__
                validation = BoundaryValidator.validate_geometry(geojson)
                result["result"]["geometry_valid"] = validation.get("valid", False)
                result["result"]["validation_details"] = validation
            except Exception as e:
                result["status"] = "failed"
                result["result"]["error"] = str(e)
        else:
            result["result"]["geometry_valid"] = None
            result["result"]["message"] = "No geometry"
        return result
