"""
Многоисточниковая верификация геокодирования.
Перекрёстная проверка Yandex и DaData, консенсус при расхождении < 100 м.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from court_locator.utils import haversine_km

# Максимальное расхождение для консенсуса (м)
MAX_CONSENSUS_DISTANCE_M = 100.0  # 100 метров

# Уровни достоверности
CONFIDENCE_EXACT = "exact"    # до дома
CONFIDENCE_STREET = "street"  # до улицы
CONFIDENCE_CITY = "city"      # до города
CONFIDENCE_LOW = "low"        # приблизительно

# Уровни обработки (4-уровневая система)
LEVEL_AUTO = "auto"       # автоматическая (высокая достоверность)
LEVEL_SEMI = "semi"       # полуавтоматическая (нужно подтверждение)
LEVEL_MANUAL = "manual"   # ручная проверка
LEVEL_EXTERNAL = "external"  # внешний запрос (не найден)


@dataclass
class GeocodeResult:
    lat: float
    lon: float
    confidence: str  # exact, street, city, low
    source: str
    normalized_address: str
    needs_manual_review: bool = False
    processing_level: str = LEVEL_AUTO


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние в метрах."""
    return haversine_km(lat1, lon1, lat2, lon2) * 1000


def check_coordinate_consistency(
    results: List[Tuple[str, Tuple[float, float]]],
    max_distance_m: float = 100,
) -> bool:
    """Проверка согласованности координат из нескольких источников."""
    if len(results) < 2:
        return True
    coords = [r[1] for r in results]
    for i in range(len(coords)):
        for j in range(i + 1, len(coords)):
            d = _haversine_m(coords[i][0], coords[i][1], coords[j][0], coords[j][1])
            if d > max_distance_m:
                return False
    return True


def weighted_average_coordinates(
    results: List[Tuple[str, Tuple[float, float]]],
    weights: Optional[Dict[str, float]] = None,
) -> Tuple[float, float]:
    """Взвешенное среднее координат. Yandex=1.0, DaData=0.9, Nominatim=0.7."""
    w = weights or {"yandex": 1.0, "dadata": 0.9, "nominatim": 0.7}
    total_w = 0
    lat_sum, lon_sum = 0.0, 0.0
    for source, (lat, lon) in results:
        k = w.get(source.lower(), 0.8)
        total_w += k
        lat_sum += lat * k
        lon_sum += lon * k
    if total_w <= 0:
        return results[0][1]
    return (lat_sum / total_w, lon_sum / total_w)


def best_available_result(
    results: List[Tuple[str, Dict[str, Any]]],
) -> Optional[GeocodeResult]:
    """Выбор лучшего результата по приоритету источника и точности."""
    if not results:
        return None
    # Приоритет: yandex > dadata > nominatim; внутри — по confidence
    conf_order = {CONFIDENCE_EXACT: 4, CONFIDENCE_STREET: 3, CONFIDENCE_CITY: 2, CONFIDENCE_LOW: 1}
    source_order = {"yandex": 3, "dadata": 2, "nominatim": 1}
    best = None
    best_score = 0
    for source, data in results:
        if not data or data.get("lat") is None or data.get("lon") is None:
            continue
        conf = (data.get("confidence") or CONFIDENCE_LOW).lower()
        score = conf_order.get(conf, 0) * 10 + source_order.get(source.lower(), 0)
        if score > best_score:
            best_score = score
            best = (source, data)
    if not best:
        return None
    src, d = best
    return GeocodeResult(
        lat=float(d["lat"]),
        lon=float(d["lon"]),
        confidence=d.get("confidence", CONFIDENCE_LOW),
        source=src,
        normalized_address=d.get("normalized_address", ""),
        needs_manual_review=conf_order.get(d.get("confidence", ""), 0) <= 2,
    )
