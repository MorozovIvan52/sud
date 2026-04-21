"""
Единая точка входа для определения подсудности (адрес и/или координаты).
"""
from unified_jurisdiction.client import UnifiedJurisdictionClient
from unified_jurisdiction.models import (
    FindCourtRequest,
    FindCourtResponse,
    UnifiedAddress,
)

__all__ = [
    "UnifiedJurisdictionClient",
    "FindCourtRequest",
    "FindCourtResponse",
    "UnifiedAddress",
]
