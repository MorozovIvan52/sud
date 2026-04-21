"""Цепочка геокодирования: при сбое Yandex — DaData (см. gps_handler)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_reverse_geocode_falls_back_to_dadata_when_yandex_returns_nothing() -> None:
    from court_locator.gps_handler import GPSHandler

    fake_dadata = {
        "region": "Москва",
        "district": "Тверской",
        "locality": "Москва",
        "address": "ул. Тверская",
    }
    with patch.object(GPSHandler, "_reverse_geocode_yandex", return_value=None):
        with patch.object(GPSHandler, "_reverse_geocode_dadata", return_value=fake_dadata):
            h = GPSHandler(api_key="any-yandex-key")
            r = h.reverse_geocode(55.7558, 37.6173)
    assert r == fake_dadata


def test_geolocate_address_parses_suggestion_structure() -> None:
    sys.path.insert(0, str(ROOT / "parser"))
    import dadata_api  # noqa: E402

    sample = {
        "suggestions": [
            {
                "value": "г Москва, ул Тверская, д 1",
                "data": {
                    "region": "Москва",
                    "region_with_type": "г Москва",
                    "city": "Москва",
                    "city_district": "Тверской",
                    "value": "г Москва, ул Тверская, д 1",
                },
            }
        ]
    }
    with patch.object(dadata_api.requests, "post") as post:
        post.return_value.json.return_value = sample
        post.return_value.raise_for_status = lambda: None
        out = dadata_api.geolocate_address(55.75, 37.61, token="tok")
    assert out is not None
    assert "Москва" in (out.get("region") or "")
    assert out.get("district") == "Тверской"
