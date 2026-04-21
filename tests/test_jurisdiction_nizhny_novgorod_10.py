"""
Десять адресов Нижегородской области: 5 — г. Нижний Новгород, 5 — другие НП области.

Проверяется, что batch-пайплайн не падает и возвращает полную схему колонок.
Успех (найден суд) зависит от courts.sqlite и ключей DaData/Yandex — тест не требует
совпадения конкретного названия суда.

Без сети / для CI:
  SKIP_REGIONAL_JURISDICTION_TESTS=1 pytest tests/test_jurisdiction_nizhny_novgorod_10.py -q
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


def _has_any_geocode_key() -> bool:
    return bool(
        (
            os.getenv("DADATA_TOKEN")
            or os.getenv("DADATA_API_KEY")
            or os.getenv("YANDEX_GEO_KEY")
            or os.getenv("YANDEX_GEOCODER_API_KEY")
            or os.getenv("YANDEX_API_KEY")
            or ""
        ).strip()
    )


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
        pytest.skip(
            "courts.sqlite пуст — для НН см. импорт: "
            "python parser/run_courts_collect_geocode_load.py --regions \"Нижегородская область\""
        )
    return True


@pytest.mark.parametrize(
    "zone,label,address",
    [
        (
            "NN",
            "центр — Большая Печерская",
            "603000, Нижегородская обл., г. Нижний Новгород, ул. Большая Печерская, д. 15",
        ),
        (
            "NN",
            "Нижегородский район — Рождественская",
            "603001, г. Нижний Новгород, ул. Рождественская, д. 1",
        ),
        (
            "NN",
            "Автозавод — ул. Ватутина",
            "603950, г. Нижний Новгород, ул. Ватутина, д. 10",
        ),
        (
            "NN",
            "Канавинский — Советская",
            "603082, г. Нижний Новгород, ул. Советская, д. 13",
        ),
        (
            "NN",
            "Ленинский — ул. Белинского",
            "603006, г. Нижний Новгород, ул. Белинского, д. 10",
        ),
        (
            "область",
            "Арзамас",
            "607225, Нижегородская обл., г. Арзамас, ул. Ленина, д. 15",
        ),
        (
            "область",
            "Балахна",
            "606434, Нижегородская обл., г. Балахна, ул. Ленина, д. 5",
        ),
        (
            "область",
            "Бор",
            "606440, Нижегородская обл., г. Бор, ул. Ленина, д. 55",
        ),
        (
            "область",
            "Дзержинск",
            "606000, Нижегородская обл., г. Дзержинск, ул. Лермонтова, д. 12",
        ),
        (
            "область",
            "Кстово",
            "607650, Нижегородская обл., г. Кстово, ул. Бакаева, д. 7",
        ),
    ],
)
@pytest.mark.skipif(
    not _has_any_geocode_key(),
    reason="Нужен DADATA_TOKEN и/или YANDEX_GEO_KEY для геокода и подсказок",
)
@pytest.mark.skipif(
    os.getenv("SKIP_REGIONAL_JURISDICTION_TESTS", "").strip().lower() in ("1", "true", "yes", "on"),
    reason="SKIP_REGIONAL_JURISDICTION_TESTS — без сетевых вызовов process_debtor",
)
def test_nizhny_novgorod_region_address_returns_schema(
    courts_nonempty: bool,
    zone: str,
    label: str,
    address: str,
) -> None:
    """Адрес по НН / области не роняет пайплайн; ответ содержит все колонки результата."""
    from batch_processing.schemas.debtor_result import DEBTOR_RESULT_COLUMNS
    from batch_processing.services.pipeline import process_debtor

    try:
        r = process_debtor(fio=f"Тест {zone}: {label}", address=address, debt_amount=10000)
    except Exception as e:
        pytest.fail(f"[{zone} {label}] Исключение для {address!r}: {e}")

    assert isinstance(r, dict)
    missing = [c for c in DEBTOR_RESULT_COLUMNS if c not in r]
    assert not missing, f"[{zone} {label}] Нет колонок: {missing[:8]}"
