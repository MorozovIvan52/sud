"""
Доступ к модулям в каталоге parser/ без `import parser` (конфликт со stdlib).
"""
from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parent.parent


def _load_module(module_qualname: str, relative_path: str):
    path = _ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_qualname, path)
    if not spec or not spec.loader:
        raise ImportError(f"parser_bridge: cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@lru_cache(maxsize=1)
def _dadata_module():
    return _load_module("_parser_dadata_bridge", "parser/dadata_api.py")


def dadata_geocode_address(address: str, *, token: str) -> Optional[Dict[str, Any]]:
    return _dadata_module().geocode_address(address, token=token)


def dadata_geolocate_address(lat: float, lon: float, *, token: str) -> Optional[Dict[str, Any]]:
    """Обратное геокодирование DaData (fallback при сбое Yandex)."""
    return _dadata_module().geolocate_address(lat, lon, token=token)


def dadata_find_court_by_address(
    address: str, *, region: Optional[str], token: str
) -> Optional[Dict[str, Any]]:
    return _dadata_module().find_court_by_address(address, region=region, token=token)


def dadata_standardize_address(address: str, *, token: str) -> Optional[str]:
    return _dadata_module().standardize_address(address, token=token)
