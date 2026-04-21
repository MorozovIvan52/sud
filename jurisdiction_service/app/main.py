"""
FastAPI-приложение Jurisdiction Service.
Определение подсудности по адресу и координатам.
OpenAPI: /docs, ReDoc: /redoc
"""
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.database import close_db, get_redis
from app.core.exceptions import JurisdictionError

# Структурированное логирование (JSON)
logger = logging.getLogger("jurisdiction_service")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '{"time":"%(asctime)s","level":"%(levelname)s","message":"%(message)s"}'
    ))
    logger.addHandler(handler)
logger.setLevel(get_settings().log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown: подключения к БД и Redis."""
    logger.info("Starting Jurisdiction Service")
    yield
    await close_db()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Jurisdiction Service",
    description="Определение территориальной подсудности судов РФ по адресу и координатам (ГПК РФ ст. 28-30)",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Логирование входящих запросов и ответов."""
    start = time.time()
    body = await request.body()
    try:
        response = await call_next(request)
        duration = time.time() - start
        logger.info(
            json.dumps({
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration * 1000, 2),
            }, ensure_ascii=False)
        )
        return response
    except Exception as e:
        logger.error(json.dumps({"error": str(e), "path": request.url.path}, ensure_ascii=False))
        raise


@app.exception_handler(JurisdictionError)
async def jurisdiction_error_handler(request: Request, exc: JurisdictionError):
    """Обработка кастомных исключений."""
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=400,
        content={"success": False, "error": exc.message, "code": exc.code, "details": exc.details},
    )


app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """
    Проверка доступности PostGIS и Redis.
    dev.to/lisan_al_gaib/health-check-fastapi
    """
    status = {"status": "ok", "postgis": "unknown", "redis": "unknown"}

    try:
        from app.core.database import get_engine
        from sqlalchemy import text
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.execute(text("SELECT PostGIS_Version()"))
        status["postgis"] = "ok"
    except Exception as e:
        status["postgis"] = f"error: {str(e)}"
        status["status"] = "degraded"

    try:
        redis = await get_redis()
        await redis.ping()
        status["redis"] = "ok"
    except Exception as e:
        status["redis"] = f"error: {str(e)}"
        status["status"] = "degraded"

    return status


@app.get("/")
async def root():
    return {"service": "Jurisdiction Service", "docs": "/docs"}
