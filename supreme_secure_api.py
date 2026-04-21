"""
Защищённый HTTP API парсера подсудности: rate limiting через slowapi.
Запуск: uvicorn supreme_secure_api:app --host 0.0.0.0 --port 8000
Перед ним рекомендуется: Nginx + Fail2Ban, CloudFlare.
"""
import os
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from jurisdiction import determine_jurisdiction, CourtResult

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Parser Supreme API", version="1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def court_to_dict(cr: CourtResult) -> Dict[str, Any]:
    return {
        "court_name": cr.court_name,
        "address": cr.address,
        "index": cr.index,
        "jurisdiction_type": cr.jurisdiction_type,
        "gpk_article": cr.gpk_article,
        "source": cr.source,
        "court_region": getattr(cr, "court_region", "") or "",
        "section_num": getattr(cr, "section_num", 0) or 0,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/determine_jurisdiction")
@limiter.limit("60/minute")  # 60 запросов в минуту с одного IP
async def api_determine_jurisdiction(request: Request, data: Dict[str, Any] = Body(...)):
    """
    Определение подсудности. Тело: JSON с полями fio, passport, address, debt_amount, contract_date и т.д.
    """
    required = ("fio", "address")
    for key in required:
        if not data.get(key):
            raise HTTPException(status_code=400, detail=f"Missing field: {key}")
    try:
        result = determine_jurisdiction(data)
        return court_to_dict(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "supreme_secure_api:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=os.getenv("API_RELOAD", "").lower() in ("1", "true", "yes"),
    )
