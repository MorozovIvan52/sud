"""
Мониторинг качества геокодирования.
Логирование: адрес, регион, источник, confidence, результат.
Метод generate_report() для простого отчёта по метрикам.
"""
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class GeocodeLogEntry:
    address: str
    region: Optional[str]
    source: str
    confidence: str
    lat: float
    lon: float
    court_found: bool
    needs_manual_review: bool
    processing_level: str


class GeocodeQualityMonitor:
    """Сбор метрик геокодирования для отчёта."""

    def __init__(self):
        self._entries: List[GeocodeLogEntry] = []
        self._max_entries = 10000

    def log(
        self,
        address: str,
        region: Optional[str],
        source: str,
        confidence: str,
        lat: float,
        lon: float,
        court_found: bool,
        needs_manual_review: bool = False,
        processing_level: str = "auto",
    ) -> None:
        """Логирует один результат геокодирования."""
        entry = GeocodeLogEntry(
            address=address,
            region=region,
            source=source,
            confidence=confidence,
            lat=lat,
            lon=lon,
            court_found=court_found,
            needs_manual_review=needs_manual_review,
            processing_level=processing_level,
        )
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]
        logger.debug(
            "geocode: address=%s region=%s source=%s confidence=%s court=%s review=%s",
            address[:50], region, source, confidence, court_found, needs_manual_review,
        )

    def generate_report(self) -> Dict[str, Any]:
        """
        Простой отчёт по метрикам: по регионам, источникам, точности.
        """
        if not self._entries:
            return {"total": 0, "by_region": {}, "by_source": {}, "by_confidence": {}}

        by_region: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "ok": 0, "review": 0})
        by_source: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "ok": 0, "review": 0})
        by_confidence: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "ok": 0, "review": 0})

        for e in self._entries:
            reg = e.region or "_unknown"
            by_region[reg]["total"] += 1
            if e.court_found:
                by_region[reg]["ok"] += 1
            if e.needs_manual_review:
                by_region[reg]["review"] += 1

            by_source[e.source]["total"] += 1
            if e.court_found:
                by_source[e.source]["ok"] += 1
            if e.needs_manual_review:
                by_source[e.source]["review"] += 1

            by_confidence[e.confidence]["total"] += 1
            if e.court_found:
                by_confidence[e.confidence]["ok"] += 1
            if e.needs_manual_review:
                by_confidence[e.confidence]["review"] += 1

        total = len(self._entries)
        ok_count = sum(1 for e in self._entries if e.court_found)
        review_count = sum(1 for e in self._entries if e.needs_manual_review)

        return {
            "total": total,
            "court_found": ok_count,
            "needs_manual_review": review_count,
            "by_region": dict(by_region),
            "by_source": dict(by_source),
            "by_confidence": dict(by_confidence),
        }

    def clear(self) -> None:
        """Очищает накопленные записи."""
        self._entries.clear()


_default_monitor: Optional[GeocodeQualityMonitor] = None


def get_monitor() -> GeocodeQualityMonitor:
    global _default_monitor
    if _default_monitor is None:
        _default_monitor = GeocodeQualityMonitor()
    return _default_monitor
