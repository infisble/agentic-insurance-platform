from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from aip.api.app import create_app
from aip.core.config import Settings


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(database_url="sqlite+aiosqlite:///:memory:"))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c,
    ):
        yield c
