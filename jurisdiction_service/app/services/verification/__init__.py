"""
Система верификации границ судебных участков.
docs/jurisdiction_verification_sources.md
"""
from app.services.verification.boundary_checker import BoundaryChecker
from app.services.verification.data_source_manager import DataSourceManager
from app.services.verification.validator_service import ValidatorService

__all__ = ["ValidatorService", "DataSourceManager", "BoundaryChecker"]
