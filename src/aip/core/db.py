from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, DateTime, Numeric
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    type_annotation_map = {  # noqa: RUF012
        Decimal: Numeric(14, 2),
        # timestamptz on Postgres (asyncpg rejects aware datetimes for plain timestamp);
        # SQLite stores UTC without an offset.
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSON,
    }


def utcnow() -> datetime:
    return datetime.now(UTC)


def make_engine(url: str, echo: bool = False) -> AsyncEngine:
    if url.startswith("sqlite") and ":memory:" in url:
        # One shared in-memory DB across connections (used by tests).
        return create_async_engine(
            url, echo=echo, poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
    return create_async_engine(url, echo=echo)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def import_models() -> None:
    """Import every model module so its tables register on Base.metadata."""
    from aip.core import jobs as _jobs  # noqa: F401
    from aip.core.claims import agent_runs as _runs  # noqa: F401
    from aip.core.claims import models as _claims  # noqa: F401
    from aip.core.claims import reviews as _reviews  # noqa: F401
    from aip.core.documents import models as _documents  # noqa: F401
    from aip.core.party import models as _party  # noqa: F401
    from aip.core.policy import models as _policy  # noqa: F401


async def create_schema(engine: AsyncEngine) -> None:
    import_models()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def session_scope(
    maker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with maker() as session:
        yield session
