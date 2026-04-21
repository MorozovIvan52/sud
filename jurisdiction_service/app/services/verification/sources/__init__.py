"""
Источники данных для верификации границ судебных участков.
"""
from app.services.verification.sources.base import BaseVerificationSource
from app.services.verification.sources.official import OfficialDataSource
from app.services.verification.sources.regional import RegionalDataSource
from app.services.verification.sources.commercial import CommercialDataSource

__all__ = [
    "BaseVerificationSource",
    "OfficialDataSource",
    "RegionalDataSource",
    "CommercialDataSource",
]
