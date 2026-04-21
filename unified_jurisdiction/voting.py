"""
Взвешенное согласование источников подсудности (полигон, DaData, Dagalin, БД района).

Веса по умолчанию из ТЗ:
  полигон 1.0; улица+диапазон 0.8; только улица (Dagalin) 0.5; БД района 0.3.

Порог суммы весов: JURISDICTION_MIN_CONFIDENCE_SUM (по умолчанию 1.5).
Полный разнос источников: JURISDICTION_DISAGREEMENT_CONFIDENCE (по умолчанию 0.3).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class WeightedSourceVote:
    """Один голос источника за конкретный суд."""

    source: str
    court_name: str
    weight: float
    court_key: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.court_key and self.court_name:
            from unified_jurisdiction.court_name_normalize import normalize_court_key

            object.__setattr__(self, "court_key", normalize_court_key(self.court_name))


@dataclass
class ResolutionOutcome:
    """Итог голосования (для ответа API и логов)."""

    court_name: Optional[str]
    court_key: Optional[str]
    confidence_score: float
    reason: str
    needs_manual_review: bool
    weight_sum_by_key: Dict[str, float] = field(default_factory=dict)
    votes: List[WeightedSourceVote] = field(default_factory=list)
    conflict: bool = False


def _min_sum_threshold() -> float:
    return float(os.getenv("JURISDICTION_MIN_CONFIDENCE_SUM", "1.5"))


def jurisdiction_min_confidence_sum() -> float:
    """Порог суммы весов победителя (`JURISDICTION_MIN_CONFIDENCE_SUM`), для логов и отладки."""
    return _min_sum_threshold()


def _disagreement_floor() -> float:
    return float(os.getenv("JURISDICTION_DISAGREEMENT_CONFIDENCE", "0.3"))


def _polygon_sources() -> frozenset:
    raw = (os.getenv("JURISDICTION_POLYGON_SOURCE_NAMES") or "polygon,postgis").lower()
    return frozenset(x.strip() for x in raw.split(",") if x.strip())


def _pick_best_names(clean: List[WeightedSourceVote], by_key: Dict[str, float]) -> Dict[str, str]:
    best: Dict[str, str] = {}
    for v in clean:
        if v.court_key not in best or len(v.court_name) > len(best[v.court_key]):
            best[v.court_key] = v.court_name
    return best


def resolve_weighted_votes(votes: List[WeightedSourceVote]) -> ResolutionOutcome:
    clean = [v for v in votes if v.court_key and v.weight > 0]
    if not clean:
        return ResolutionOutcome(
            court_name=None,
            court_key=None,
            confidence_score=0.0,
            reason="нет данных от источников",
            needs_manual_review=True,
            votes=[],
        )

    by_key: Dict[str, float] = {}
    for v in clean:
        by_key[v.court_key] = by_key.get(v.court_key, 0.0) + v.weight

    sorted_keys = sorted(by_key.keys(), key=lambda k: by_key[k], reverse=True)
    winner_key = sorted_keys[0]
    winner_sum = by_key[winner_key]
    second_sum = by_key[sorted_keys[1]] if len(sorted_keys) > 1 else 0.0
    best_name = _pick_best_names(clean, by_key)

    unique_keys = len(sorted_keys)
    total_votes = len(clean)
    # Не менее трёх источников и у каждого свой уникальный суд (кейс 5 ТЗ).
    all_disagree = unique_keys == total_votes and total_votes >= 3

    if all_disagree:
        return ResolutionOutcome(
            court_name=best_name.get(winner_key),
            court_key=winner_key,
            confidence_score=_disagreement_floor(),
            reason="все источники указали разные суды",
            needs_manual_review=True,
            weight_sum_by_key=dict(by_key),
            votes=clean,
            conflict=True,
        )

    poly = _polygon_sources()
    polygon_votes = [v for v in clean if v.source.lower() in poly]
    strong_other = [
        v for v in clean if v.court_key != winner_key and v.weight >= 0.8
    ]

    close_race = len(sorted_keys) > 1 and (winner_sum - second_sum) <= 0.5
    polygon_vs_strong = bool(polygon_votes) and any(
        v.court_key != polygon_votes[0].court_key and v.weight >= 0.8 for v in clean
    )

    conflict = close_race or polygon_vs_strong or (
        len(sorted_keys) > 1 and second_sum >= 0.8 and sorted_keys[0] != sorted_keys[1]
    )

    threshold = _min_sum_threshold()
    needs_manual = winner_sum < threshold or conflict

    if polygon_vs_strong and winner_key == polygon_votes[0].court_key:
        reason = "попадание в полигон + расхождение с другими источниками"
    elif winner_sum >= 1.0 and polygon_votes and winner_key == polygon_votes[0].court_key:
        reason = "попадание в полигон + совпадение улицы"
    elif winner_sum >= 0.8:
        reason = "совпадение улицы и диапазона домов"
    elif winner_sum >= 0.5:
        reason = "совпадение только улицы"
    else:
        reason = "низкая сумма весов"

    return ResolutionOutcome(
        court_name=best_name.get(winner_key),
        court_key=winner_key,
        confidence_score=round(min(winner_sum, 2.0), 1),
        reason=reason,
        needs_manual_review=needs_manual,
        weight_sum_by_key=dict(by_key),
        votes=clean,
        conflict=conflict,
    )
