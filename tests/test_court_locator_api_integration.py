"""
Интеграционные тесты: court_locator использует API и возвращает результат.
Проверяет, что при наличии ключей DaData/Yandex определение подсудности даёт ответ (успех или ошибка от API).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "parser"))

_env = ROOT / ".env"
if _env.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env)
    except ImportError:
        pass


def _has_any_geocode_key() -> bool:
    return bool(
        (os.getenv("DADATA_TOKEN") or os.getenv("DADATA_API_KEY") or
         os.getenv("YANDEX_GEO_KEY") or os.getenv("YANDEX_GEOCODER_API_KEY") or os.getenv("YANDEX_API_KEY") or "").strip()
    )


@pytest.mark.skipif(not _has_any_geocode_key(), reason="Нет DADATA_TOKEN или YANDEX_GEO_KEY")
def test_process_debtor_returns_result_for_moscow_address():
    """Пайплайн по адресу в Москве возвращает словарь с полями (суд или ошибка)."""
    from batch_processing.services.pipeline import process_debtor

    result = process_debtor(
        fio="Тест",
        address="г. Москва, ул. Тверская, 15",
        debt_amount=10000,
    )
    assert isinstance(result, dict)
    assert "Тип производства" in result
    assert "Нормализованный адрес" in result
    # Либо найден суд, либо ошибка
    if result.get("Наименование суда"):
        assert "ERROR" not in str(result.get("Тип производства", ""))
    else:
        assert result.get("_error_code") or "ERROR" in str(result.get("Тип производства", ""))


@pytest.mark.skipif(not _has_any_geocode_key(), reason="Нет DADATA_TOKEN или YANDEX_GEO_KEY")
def test_process_debtor_returns_result_for_spb_address():
    """Пайплайн по адресу в СПб возвращает словарь с полями."""
    from batch_processing.services.pipeline import process_debtor

    result = process_debtor(
        fio="Тест",
        address="Санкт-Петербург, Невский проспект, 28",
        debt_amount=5000,
    )
    assert isinstance(result, dict)
    assert "Тип производства" in result
    assert "Нормализованный адрес" in result
