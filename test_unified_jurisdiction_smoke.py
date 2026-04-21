"""
Дымовые тесты unified_jurisdiction: структура ответа и resolution_steps.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_env = ROOT / ".env"
if _env.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(_env)
    except ImportError:
        pass


@pytest.fixture()
def uj_client():
    from unified_jurisdiction import UnifiedJurisdictionClient

    c = UnifiedJurisdictionClient(use_cache=False)
    yield c
    c.close()


def test_find_by_coords_moscow_structure(uj_client):
    """По координатам центра Москвы — успех при покрытии полигонами/геокодером; иначе skip (не красный CI)."""
    from unified_jurisdiction import FindCourtRequest

    r = uj_client.find_court(FindCourtRequest(latitude=55.7558, longitude=37.6173))
    if not r.success:
        pytest.skip(
            "Координаты без результата: нет полигона в локальной БД и/или недоступен обратный геокод "
            f"(проверьте YANDEX_GEO_KEY для geocode-maps.yandex.ru). Ответ: {r.error!r}"
        )
    assert r.court and r.court.get("court_name")
    assert "coords_only" in r.resolution_steps
    assert r.metrics and "total_ms" in r.metrics
    assert r.confidence_score is not None


def test_find_by_address_resolution_steps_shape(uj_client):
    """По адресу — список шагов без падения."""
    from unified_jurisdiction import FindCourtRequest

    r = uj_client.find_court(
        FindCourtRequest(address="г. Москва, ул. Тверская, д. 1", prefer_dadata_court=True)
    )
    assert isinstance(r.resolution_steps, list)
    assert len(r.resolution_steps) >= 1
    if r.success:
        assert r.court
        assert r.metrics and "total_ms" in r.metrics
