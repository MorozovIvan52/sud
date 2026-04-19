"""
Сбор метрик системы определения подсудности.
Метрики: точность, время обработки, частота ошибок, распределение по районам и источникам.
"""
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class MetricsCollector:
    """
    Сбор показателей: успех/ошибки, время обработки, типы ошибок, районы, источники.
    """

    success_count: int = 0
    failure_count: int = 0
    processing_times: list = field(default_factory=list)
    errors: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    district_stats: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    source_stats: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    max_times_kept: int = 10000

    def log_request(
        self,
        success: bool,
        processing_time: float,
        error_type: Optional[str] = None,
        district: Optional[str] = None,
        source: Optional[str] = None,
    ) -> None:
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
            if error_type:
                self.errors[error_type] += 1

        self.processing_times.append(processing_time)
        if len(self.processing_times) > self.max_times_kept:
            self.processing_times = self.processing_times[-self.max_times_kept :]

        if district:
            self.district_stats[district] += 1
        if source:
            self.source_stats[source] += 1

    def get_statistics(self) -> Dict[str, Any]:
        total = self.success_count + self.failure_count
        return {
            "total_requests": total,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": self.success_count / total if total else 0.0,
            "average_time_ms": (
                sum(self.processing_times) / len(self.processing_times) * 1000
                if self.processing_times
                else 0
            ),
            "error_distribution": dict(self.errors),
            "district_performance": dict(self.district_stats),
            "source_performance": dict(self.source_stats),
        }

    def reset(self) -> None:
        self.success_count = 0
        self.failure_count = 0
        self.processing_times.clear()
        self.errors.clear()
        self.district_stats.clear()
        self.source_stats.clear()


_default_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    global _default_collector
    if _default_collector is None:
        _default_collector = MetricsCollector()
    return _default_collector
