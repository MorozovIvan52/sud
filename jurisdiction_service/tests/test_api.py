"""
Интеграционные тесты API.
Требуют запущенного PostGIS и Redis (docker-compose up).
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_health():
    """Эндпоинт /health возвращает статус."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r = await client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "postgis" in data
        assert "redis" in data


@pytest.mark.asyncio
async def test_root():
    """Корневой эндпоинт."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r = await client.get("/")
        assert r.status_code == 200
        assert "Jurisdiction Service" in r.json().get("service", "")


@pytest.mark.asyncio
async def test_jurisdiction_address_unauthorized():
    """Запрос без JWT возвращает 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r = await client.get("/api/v1/jurisdiction/address?address=Москва, Тверская 7")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_jurisdiction_coordinates_unauthorized():
    """Запрос по координатам без JWT возвращает 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r = await client.get("/api/v1/jurisdiction/coordinates?latitude=55.7558&longitude=37.6173")
        assert r.status_code == 401
