"""Pytest fixtures для тестов."""
from typing import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.security import create_access_token


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Тестовый HTTP-клиент."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers() -> dict:
    """Заголовки с JWT для тестов."""
    token = create_access_token(subject="test-user-id")
    return {"Authorization": f"Bearer {token}"}
