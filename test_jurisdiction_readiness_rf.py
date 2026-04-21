"""
Готовность пайплайна подсудности по РФ: инварианты и «зацепки», мешающие результату.

Не требуют сети для части кейсов; при пустой БД судов часть тестов пропускается с причиной.

Быстрый прогон без шести сетевых вызовов по регионам:
  SKIP_REGIONAL_JURISDICTION_TESTS=1 pytest tests/test_jurisdiction_readiness_rf.py -q
"""
from __future__ import annotations

import os
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

from batch_processing.constants import ERROR_LABELS, RECOMMENDATIONS
from batch_processing.schemas.debtor_result import DEBTOR_RESULT_COLUMNS
from batch_processing.services.pipeline import process_batch, process_debtor
from batch_processing.utils.file_handler import read_file


def _courts_count() -> int:
    sys.path.insert(0, str(ROOT / "parser"))
    try:
        from courts_db import get_courts_count

        return int(get_courts_count())
    except Exception:
        return -1


@pytest.fixture(scope="module")
def courts_nonempty() -> bool:
    n = _courts_count()
    if n < 0:
        pytest.skip("Не удалось прочитать parser/courts.sqlite")
    if n == 0:
        pytest.skip("courts.sqlite пуст — импорт: docs/howto_fill_courts_db.md, bootstrap_local_databases.py")
    return True


def test_error_catalog_has_recommendation_for_every_code() -> None:
    """Каждый код ошибки из словаря меток имеет рекомендацию — чтобы пользователь не остался без подсказки."""
    for code in ERROR_LABELS:
        assert code in RECOMMENDATIONS, f"Нет рекомендации для {code}"


def test_process_debtor_never_raises_on_garbage_inputs() -> None:
    """Любой «мусор» не должен валить процесс — только словарь результата/ошибки."""
    cases = [
        {"fio": "", "address": ""},
        {"fio": "X", "address": ""},
        {"fio": "", "address": "   "},
        {"fio": "Тест", "address": "несуществующая_улица_zzz 000"},
        {"fio": "Тест", "address": "РФ"},
    ]
    for row in cases:
        try:
            r = process_debtor(
                fio=row.get("fio") or "",
                address=row.get("address") or "",
            )
        except Exception as e:
            pytest.fail(f"process_debtor не должен бросать исключение для {row!r}: {e}")
        assert isinstance(r, dict), type(r)
        assert "Тип производства" in r
        for col in DEBTOR_RESULT_COLUMNS:
            assert col in r, f"Нет колонки {col!r} в ответе"


def test_process_batch_row_without_address_yields_error_row() -> None:
    out = process_batch([{"fio": "Иванов", "address": ""}])
    assert len(out) == 1
    r = out[0]
    assert "ERROR" in (r.get("Тип производства") or "").upper() or not (r.get("Наименование суда") or "").strip()


def test_moscow_address_returns_structured_result(courts_nonempty: bool) -> None:
    """При непустой БД типичный адрес столицы должен дать структурированный ответ (успех или явная ошибка)."""
    r = process_debtor(fio="Проверка", address="г. Москва, ул. Тверская, д. 1")
    assert isinstance(r, dict)
    for col in DEBTOR_RESULT_COLUMNS:
        assert col in r
    # Либо суд, либо ERROR — но не пустой dict без ключей схемы
    assert (r.get("Наименование суда") or "").strip() or "ERROR" in (r.get("Тип производства") or "")


@pytest.mark.parametrize(
    "region_hint,address",
    [
        ("СЗФО", "г. Санкт-Петербург, Невский проспект, д. 28"),
        ("ЮФО", "г. Краснодар, ул. Красная, д. 1"),
        ("ПФО", "г. Казань, ул. Баумана, д. 1"),
        ("УФО", "г. Екатеринбург, ул. Ленина, д. 1"),
        ("СФО", "г. Новосибирск, ул. Ленина, д. 1"),
        ("ДФО", "г. Владивосток, ул. Светланская, д. 1"),
    ],
)
@pytest.mark.skipif(
    os.getenv("SKIP_REGIONAL_JURISDICTION_TESTS", "").strip().lower() in ("1", "true", "yes", "on"),
    reason="SKIP_REGIONAL_JURISDICTION_TESTS — ускоренный CI без 6 сетевых process_debtor",
)
def test_regional_addresses_do_not_crash_pipeline(courts_nonempty: bool, region_hint: str, address: str) -> None:
    """
    Региональные формулировки не должны ронять пайплайн.
    Успех зависит от наполнения БД и API; здесь ловим только сбои и отсутствие схемы ответа.
    """
    try:
        r = process_debtor(fio="Регион", address=address)
    except Exception as e:
        pytest.fail(f"[{region_hint}] Исключение при адресе {address!r}: {e}")
    assert isinstance(r, dict)
    missing = [c for c in DEBTOR_RESULT_COLUMNS if c not in r]
    assert not missing, f"[{region_hint}] Отсутствуют колонки: {missing[:5]}…"


def test_read_file_empty_excel_like_rows(tmp_path: Path) -> None:
    """Файл без распознанных колонок адреса — пустой список (пользователь увидит сообщение скрипта)."""
    import pandas as pd

    p = tmp_path / "bad.xlsx"
    pd.DataFrame([{"Столбец1": "a", "Столбец2": "b"}]).to_excel(p, index=False)
    rows = read_file(p)
    assert rows == []


def test_error_result_contains_error_code_key_when_failed() -> None:
    r = process_debtor(fio="X", address="")
    if "ERROR" in (r.get("Тип производства") or ""):
        assert "_error_code" in r or r.get("Наименование суда") == ""
