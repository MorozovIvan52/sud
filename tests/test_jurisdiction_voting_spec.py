"""
Контрактные тесты по ТЗ: веса источников, порог 1.5, конфликты полигона.
Реальные полигоны и DaData здесь не вызываются — только модуль voting.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from unified_jurisdiction.court_name_normalize import courts_same_by_key, normalize_court_key
from unified_jurisdiction.voting import WeightedSourceVote, resolve_weighted_votes


def test_case1_polygon_plus_street_match():
    r = resolve_weighted_votes(
        [
            WeightedSourceVote("polygon", "Мировой судебный участок №1 г. X", 1.0),
            WeightedSourceVote("dadata", "Мировой судебный участок №1 г. X", 0.8),
        ]
    )
    assert r.confidence_score == 1.8
    assert r.needs_manual_review is False
    assert "полигон" in r.reason.lower()


def test_case2_street_and_range():
    r = resolve_weighted_votes(
        [
            WeightedSourceVote("dadata", "Мировой судебный участок №A", 0.8),
            WeightedSourceVote("dagalin", "Мировой судебный участок №A", 0.5),
        ]
    )
    assert r.confidence_score == 1.3
    assert r.needs_manual_review is True
    assert r.reason.startswith("совпадение улицы")


def test_case3_street_only_low_confidence():
    r = resolve_weighted_votes(
        [
            WeightedSourceVote("dagalin", "Мировой судебный участок №X", 0.5),
        ]
    )
    assert r.confidence_score == 0.5
    assert r.needs_manual_review is True
    assert "только улицы" in r.reason or "низкая" in r.reason


def test_case4_polygon_vs_dadata_conflict():
    r = resolve_weighted_votes(
        [
            WeightedSourceVote("polygon", "Мировой судебный участок №1", 1.0),
            WeightedSourceVote("dadata", "Мировой судебный участок №2", 0.8),
        ]
    )
    assert normalize_court_key(r.court_name or "") == normalize_court_key("Мировой судебный участок №1")
    assert r.confidence_score == 1.0
    assert r.needs_manual_review is True
    assert r.conflict is True


def test_case5_all_sources_different():
    r = resolve_weighted_votes(
        [
            WeightedSourceVote("polygon", "Мировой судебный участок №1", 1.0),
            WeightedSourceVote("dadata", "Мировой судебный участок №2", 0.8),
            WeightedSourceVote("dagalin", "Мировой судебный участок №3", 0.5),
            WeightedSourceVote("sqlite", "Мировой судебный участок №4", 0.3),
        ]
    )
    assert r.confidence_score == float(os.getenv("JURISDICTION_DISAGREEMENT_CONFIDENCE", "0.3"))
    assert r.needs_manual_review is True
    assert r.conflict is True


def test_case6_duplicate_street_different_districts():
    r = resolve_weighted_votes(
        [
            WeightedSourceVote("dadata", "МСУ №5 Советского района", 0.8),
            WeightedSourceVote("dagalin", "МСУ №5 Приокского района", 0.5),
        ]
    )
    assert r.needs_manual_review is True
    assert r.conflict is True


def test_case7_even_odd_different_units():
    r_even = resolve_weighted_votes(
        [
            WeightedSourceVote("polygon", "Мировой судебный участок №2 пр. Ильича (чёт)", 1.0),
            WeightedSourceVote("dadata", "Мировой судебный участок №2 пр. Ильича (чёт)", 0.8),
        ]
    )
    assert r_even.confidence_score >= 1.0
    r_odd = resolve_weighted_votes(
        [
            WeightedSourceVote("polygon", "Мировой судебный участок №8 пр. Ильича (нечёт)", 1.0),
            WeightedSourceVote("dadata", "Мировой судебный участок №8 пр. Ильича (нечёт)", 0.8),
        ]
    )
    assert r_odd.confidence_score >= 1.0


def test_case8_incomplete_address_street_only():
    r = resolve_weighted_votes(
        [
            WeightedSourceVote("dagalin", "Мировой судебный участок №1", 0.5),
            WeightedSourceVote("sqlite", "Мировой судебный участок №1", 0.3),
        ]
    )
    assert r.confidence_score == 0.8
    assert r.needs_manual_review is True


def test_case9_garbage_no_votes():
    r = resolve_weighted_votes([])
    assert r.court_name is None
    assert r.confidence_score == 0.0
    assert r.needs_manual_review is True


def test_case10_two_low_sources_agree_sum_below_threshold():
    r = resolve_weighted_votes(
        [
            WeightedSourceVote("dadata", "Мировой судебный участок №9", 0.8),
            WeightedSourceVote("dagalin", "Мировой судебный участок №9", 0.5),
        ]
    )
    assert r.confidence_score == 1.3
    assert r.needs_manual_review is True


def test_case11_polygon_and_dadata_agree_dagalin_differs():
    r = resolve_weighted_votes(
        [
            WeightedSourceVote("polygon", "Мировой судебный участок №A", 1.0),
            WeightedSourceVote("dadata", "Мировой судебный участок №A", 0.8),
            WeightedSourceVote("dagalin", "Мировой судебный участок №B", 0.5),
        ]
    )
    assert "A" in (r.court_name or "")
    assert r.confidence_score == 1.8
    assert r.needs_manual_review is False


def test_normalize_court_key_strips_prefixes():
    a = "Судебный участок № 5 г. Нижний Новгород"
    b = "Мировой судебный участок №5 г. Нижний Новгород"
    assert courts_same_by_key(a, b) or normalize_court_key(a) == normalize_court_key(b)


def test_threshold_env(monkeypatch):
    monkeypatch.setenv("JURISDICTION_MIN_CONFIDENCE_SUM", "2.0")
    r = resolve_weighted_votes(
        [
            WeightedSourceVote("dadata", "Мировой судебный участок №1", 0.8),
            WeightedSourceVote("dagalin", "Мировой судебный участок №1", 0.5),
        ]
    )
    assert r.confidence_score == 1.3
    assert r.needs_manual_review is True
