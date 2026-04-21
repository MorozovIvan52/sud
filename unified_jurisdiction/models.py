"""
Схемы запроса/ответа и унифицированного адреса для единой цепи подсудности.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class UnifiedAddress:
    """Результат нормализации и обогащения адреса."""

    raw: str
    normalized: str
    region: Optional[str] = None
    district: Optional[str] = None
    settlement: Optional[str] = None
    street: Optional[str] = None
    house: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@dataclass
class FindCourtRequest:
    """Вход: текстовый адрес и/или WGS84. Достаточно одного способа."""

    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    strict_verify: bool = False
    """Если True — выполняются дополнительные шаги верификации (DaData при наличии токена, пространственный шаг при успешном геокодировании)."""
    prefer_dadata_court: bool = True
    """По текстовому адресу сначала подсказка суда DaData (надёжнее), затем БД по району, затем геокод (Яндекс и др.) + полигоны. Отключите для старого порядка A→B→C."""


@dataclass
class FindCourtResponse:
    """Структурированный ответ о суде."""

    success: bool
    court: Optional[Dict[str, Any]] = None
    unified_address: Optional[UnifiedAddress] = None
    resolution_steps: List[str] = field(default_factory=list)
    needs_manual_review: bool = False
    spatial_override: bool = False
    error: Optional[str] = None
    confidence_score: Optional[float] = None
    metrics: Optional[Dict[str, float]] = None
    resolution_reason: str = ""
    """Пояснение итога голосования источников (текстовый reason из resolve_weighted_votes)."""
    source_votes: List[Dict[str, Any]] = field(default_factory=list)
    """Сериализованные голоса источников для логов и отладки."""
    selected_court_id: Optional[str] = None
    """Идентификатор участка из meta голоса победителя, если был передан."""

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "success": self.success,
            "court": self.court,
            "unified_address": _unified_addr_to_dict(self.unified_address),
            "resolution_steps": list(self.resolution_steps),
            "needs_manual_review": self.needs_manual_review,
            "spatial_override": self.spatial_override,
            "error": self.error,
        }
        if self.confidence_score is not None:
            d["confidence_score"] = self.confidence_score
        if self.metrics:
            d["metrics"] = dict(self.metrics)
        if self.resolution_reason:
            d["resolution_reason"] = self.resolution_reason
        if self.source_votes:
            d["source_votes"] = list(self.source_votes)
        if self.selected_court_id is not None:
            d["selected_court_id"] = self.selected_court_id
        return d


def _unified_addr_to_dict(u: Optional[UnifiedAddress]) -> Optional[Dict[str, Any]]:
    if u is None:
        return None
    return {
        "raw": u.raw,
        "normalized": u.normalized,
        "region": u.region,
        "district": u.district,
        "settlement": u.settlement,
        "street": u.street,
        "house": u.house,
        "latitude": u.latitude,
        "longitude": u.longitude,
    }
