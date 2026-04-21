"""Интеграция UnifiedJurisdictionCore и взвешенного голосования."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from unified_jurisdiction.core import UnifiedJurisdictionCore
from unified_jurisdiction.models import FindCourtRequest, UnifiedAddress


def _u(raw: str, **kwargs) -> UnifiedAddress:
    return UnifiedAddress(
        raw=raw,
        normalized=(kwargs.get("normalized") or raw.lower()),
        region=kwargs.get("region", "Регион"),
        district=kwargs.get("district", "Район"),
        street=kwargs.get("street"),
        house=kwargs.get("house"),
    )


@pytest.fixture
def core_no_cache():
    return UnifiedJurisdictionCore(use_cache=False)


@patch("unified_jurisdiction.core.enrich_court_with_dagalin")
def test_find_court_inner_address_voting_same_section(mock_enrich, core_no_cache):
    """Полигон + DaData + Dagalin согласованы по номеру участка — итог и метаданные голосования."""
    court_c = {
        "court_name": "Судебный участок № 5",
        "section_num": 5,
        "source": "court_districts",
    }
    court_b = {
        "court_name": "Судебный участок №5",
        "section_num": 5,
        "source": "unified_B_dadata",
    }
    court_d = {
        "court_name": "Судебный участок №5",
        "section_num": 5,
        "source": "dagalin_address_match",
    }
    unified = UnifiedAddress(
        raw="ул. Ленина, 15",
        normalized="ул ленина 15",
        region="Регион",
        district="Район",
        street="Ленина",
        house="15",
    )

    core_no_cache._matcher._dadata_available = True  # noqa: SLF001 — для ветки B:dadata в тесте

    with patch("unified_jurisdiction.core.normalize_to_unified", return_value=unified):
        with patch(
            "court_locator.dagalin_address_search.find_court_by_dagalin_address_index",
            return_value=court_d,
        ):
            with patch.object(core_no_cache, "_step_a", return_value=None):
                with patch.object(core_no_cache, "_step_b", return_value=court_b):
                    with patch.object(
                        core_no_cache,
                        "_step_c_spatial",
                        return_value=(court_c, ["C:sqlite_districts"]),
                    ):
                        res = core_no_cache._find_court_inner(
                            FindCourtRequest(
                                address="ул. Ленина, 15",
                                strict_verify=True,
                            )
                        )

    assert res.success
    assert res.court is not None
    assert res.court.get("section_num") == 5
    assert res.resolution_reason
    assert "полигон" in res.resolution_reason.lower() or "улиц" in res.resolution_reason.lower()
    assert len(res.source_votes) == 3
    assert res.confidence_score is not None
    assert res.confidence_score == pytest.approx(2.0, abs=0.05)
    assert res.selected_court_id == "5"


@patch("unified_jurisdiction.core.enrich_court_with_dagalin")
def test_find_court_skips_legacy_confidence_when_votes_present(mock_enrich, core_no_cache):
    """При наличии source_votes find_court не перезаписывает confidence_score эвристикой _confidence_score."""
    court_c = {
        "court_name": "Судебный участок № 1",
        "section_num": 1,
        "source": "court_districts",
    }
    unified = UnifiedAddress(
        raw="тест",
        normalized="тест",
        region="Р",
        district="Р",
    )
    with patch("unified_jurisdiction.core.normalize_to_unified", return_value=unified):
        with patch(
            "court_locator.dagalin_address_search.find_court_by_dagalin_address_index",
            return_value=None,
        ):
            with patch.object(core_no_cache, "_step_a", return_value=None):
                with patch.object(core_no_cache, "_step_b", return_value=None):
                    with patch.object(
                        core_no_cache,
                        "_step_c_spatial",
                        return_value=(court_c, ["C:sqlite_districts"]),
                    ):
                        res = core_no_cache.find_court(
                            FindCourtRequest(address="тестовый адрес")
                        )
    assert res.source_votes
    assert res.confidence_score == pytest.approx(1.0, abs=0.01)


@patch("unified_jurisdiction.core.enrich_court_with_dagalin")
def test_missing_spatial_source_dadata_plus_dagalin(mock_enrich, core_no_cache, monkeypatch):
    """Нет шага C: только DaData + Dagalin; при пороге 1.2 сумма 0.8+0.5=1.3 без ручной проверки."""
    monkeypatch.setenv("JURISDICTION_MIN_CONFIDENCE_SUM", "1.2")
    court_b = {
        "court_name": "Судебный участок №5",
        "section_num": 5,
        "source": "unified_B_dadata",
    }
    court_d = {
        "court_name": "Судебный участок №5",
        "section_num": 5,
        "source": "dagalin_address_match",
    }
    unified = _u("ул. Ленина, 15")
    core_no_cache._matcher._dadata_available = True  # noqa: SLF001

    with patch("unified_jurisdiction.core.normalize_to_unified", return_value=unified):
        with patch(
            "court_locator.dagalin_address_search.find_court_by_dagalin_address_index",
            return_value=court_d,
        ):
            with patch.object(core_no_cache, "_step_a", return_value=None):
                with patch.object(core_no_cache, "_step_b", return_value=court_b):
                    with patch.object(
                        core_no_cache,
                        "_step_c_spatial",
                        return_value=(None, ["C:skipped"]),
                    ):
                        res = core_no_cache._find_court_inner(
                            FindCourtRequest(address="ул. Ленина, 15")
                        )

    assert res.success
    assert len(res.source_votes) == 2
    assert res.confidence_score == pytest.approx(1.3, abs=0.05)
    assert not res.needs_manual_review


@patch("unified_jurisdiction.core.enrich_court_with_dagalin")
def test_all_sources_none(mock_enrich, core_no_cache):
    """Все источники пусты — нет суда, нулевая уверенность, нужна ручная проверка / уточнение адреса."""
    unified = _u("неизвестный адрес", region=None, district=None)
    with patch("unified_jurisdiction.core.normalize_to_unified", return_value=unified):
        with patch(
            "court_locator.dagalin_address_search.find_court_by_dagalin_address_index",
            return_value=None,
        ):
            with patch.object(core_no_cache, "_step_a", return_value=None):
                with patch.object(core_no_cache, "_step_b", return_value=None):
                    with patch.object(
                        core_no_cache,
                        "_step_c_spatial",
                        return_value=(None, ["C:geocode_failed"]),
                    ):
                        res = core_no_cache._find_court_inner(
                            FindCourtRequest(address="неизвестный адрес")
                        )

    assert not res.success
    assert res.court is None
    assert res.confidence_score == pytest.approx(0.0, abs=0.01)
    assert res.needs_manual_review
    assert "нет данных" in (res.resolution_reason or "").lower()
    assert res.selected_court_id is None


@patch("unified_jurisdiction.core.enrich_court_with_dagalin")
def test_polygon_vs_dadata_conflict_manual_review(mock_enrich, core_no_cache):
    """Полигон (участок A) против DaData (участок B): при strict_verify ответ с полигона, конфликт → manual."""
    court_c = {
        "court_name": "Судебный участок №10",
        "section_num": 111,
        "source": "court_districts",
    }
    court_b = {
        "court_name": "Судебный участок №20",
        "section_num": 222,
        "source": "unified_B_dadata",
    }
    unified = _u("граница участков")
    core_no_cache._matcher._dadata_available = True  # noqa: SLF001

    with patch("unified_jurisdiction.core.normalize_to_unified", return_value=unified):
        with patch(
            "court_locator.dagalin_address_search.find_court_by_dagalin_address_index",
            return_value=None,
        ):
            with patch.object(core_no_cache, "_step_a", return_value=None):
                with patch.object(core_no_cache, "_step_b", return_value=court_b):
                    with patch.object(
                        core_no_cache,
                        "_step_c_spatial",
                        return_value=(court_c, ["C:sqlite_districts"]),
                    ):
                        res = core_no_cache._find_court_inner(
                            FindCourtRequest(
                                address="граница участков",
                                strict_verify=True,
                            )
                        )

    assert res.success
    assert res.court is court_c
    assert res.selected_court_id == "111"
    assert res.needs_manual_review
    assert "полигон" in res.resolution_reason.lower()
    assert "расхожден" in res.resolution_reason.lower()


@patch("unified_jurisdiction.core.enrich_court_with_dagalin")
def test_dadata_vs_dagalin_different_courts_manual(mock_enrich, core_no_cache):
    """Разные суды у DaData и Dagalin без полигона — узкая гонка / конфликт → needs_manual_review."""
    court_b = {
        "court_name": "Судебный участок №1",
        "section_num": 1,
        "source": "unified_B_dadata",
    }
    court_d = {
        "court_name": "Судебный участок №2",
        "section_num": 2,
        "source": "dagalin_address_match",
    }
    unified = _u("ул. Садовая, 10")
    core_no_cache._matcher._dadata_available = True  # noqa: SLF001

    with patch("unified_jurisdiction.core.normalize_to_unified", return_value=unified):
        with patch(
            "court_locator.dagalin_address_search.find_court_by_dagalin_address_index",
            return_value=court_d,
        ):
            with patch.object(core_no_cache, "_step_a", return_value=None):
                with patch.object(core_no_cache, "_step_b", return_value=court_b):
                    with patch.object(
                        core_no_cache,
                        "_step_c_spatial",
                        return_value=(None, ["C:skipped"]),
                    ):
                        res = core_no_cache._find_court_inner(
                            FindCourtRequest(address="ул. Садовая, 10")
                        )

    assert res.success
    assert res.needs_manual_review
    assert len(res.source_votes) == 2


@patch("unified_jurisdiction.core.enrich_court_with_dagalin")
def test_even_odd_ilyicha_spatial_branch(mock_enrich, core_no_cache):
    """Имитация разных полигонов для чётного и нечётного дома (разный ответ _step_c_spatial)."""
    court_even = {
        "court_name": "Судебный участок №100",
        "section_num": 100,
        "source": "court_districts",
    }
    court_odd = {
        "court_name": "Судебный участок №101",
        "section_num": 101,
        "source": "court_districts",
    }

    def spatial_side_effect(normalized: str):
        n = (normalized or "").lower()
        if "ильича" in n and ", 2" in n:
            return court_even, ["C:sqlite_districts"]
        if "ильича" in n and ", 3" in n:
            return court_odd, ["C:sqlite_districts"]
        return None, ["C:geocode_failed"]

    with patch("unified_jurisdiction.core.normalize_to_unified", side_effect=lambda a: _u(a)):
        with patch(
            "court_locator.dagalin_address_search.find_court_by_dagalin_address_index",
            return_value=None,
        ):
            with patch.object(core_no_cache, "_step_a", return_value=None):
                with patch.object(core_no_cache, "_step_b", return_value=None):
                    with patch.object(
                        core_no_cache,
                        "_step_c_spatial",
                        side_effect=spatial_side_effect,
                    ):
                        even = core_no_cache._find_court_inner(
                            FindCourtRequest(address="пр. Ильича, 2")
                        )
                        odd = core_no_cache._find_court_inner(
                            FindCourtRequest(address="пр. Ильича, 3")
                        )

    assert even.success and even.selected_court_id == "100"
    assert odd.success and odd.selected_court_id == "101"
