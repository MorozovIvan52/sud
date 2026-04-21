"""
FastAPI: POST /api/v1/find-court — единый эндпоинт подсудности.
Запуск: uvicorn unified_jurisdiction.api_app:app --host 0.0.0.0 --port 8010
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
except ImportError as e:
    raise ImportError("Установите fastapi и pydantic для unified_jurisdiction.api_app") from e

from unified_jurisdiction.core import UnifiedJurisdictionCore
from unified_jurisdiction.models import FindCourtRequest, FindCourtResponse

app = FastAPI(
    title="Unified jurisdiction",
    version="0.1.0",
    description="Единая точка определения подсудности по адресу или координатам",
)

_core: UnifiedJurisdictionCore | None = None


def get_core() -> UnifiedJurisdictionCore:
    global _core
    if _core is None:
        _core = UnifiedJurisdictionCore(use_cache=True)
    return _core


class FindCourtBody(BaseModel):
    address: str | None = Field(None, description="Полный адрес")
    latitude: float | None = None
    longitude: float | None = None
    strict_verify: bool = False
    prefer_dadata_court: bool = Field(
        True,
        description="True: порядок B (DaData) → A (район в БД) → C (геокод). False: A → B → C",
    )


@app.post("/api/v1/find-court")
async def find_court(body: FindCourtBody):
    if not body.address and (body.latitude is None or body.longitude is None):
        raise HTTPException(status_code=400, detail="Укажите address или latitude и longitude")
    req = FindCourtRequest(
        address=body.address,
        latitude=body.latitude,
        longitude=body.longitude,
        strict_verify=body.strict_verify,
        prefer_dadata_court=body.prefer_dadata_court,
    )
    res: FindCourtResponse = get_core().find_court(req)
    return res.to_dict()


@app.on_event("shutdown")
async def shutdown_event():
    global _core
    if _core:
        _core.close()
        _core = None
