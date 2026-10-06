"""The migration chain must produce exactly the schema the models describe, so deployments
(`alembic upgrade head`) and tests/demo (`create_all`) never drift apart."""

import asyncio
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from aip.core.db import Base, import_models, make_engine

ROOT = Path(__file__).resolve().parents[2]


def _config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


async def _diff(url: str) -> list:
    import_models()
    engine = make_engine(url)
    async with engine.connect() as conn:
        diff = await conn.run_sync(
            lambda c: compare_metadata(MigrationContext.configure(c), Base.metadata)
        )
    await engine.dispose()
    return diff


def test_migrations_match_models_and_downgrade_cleanly(tmp_path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'm.db').as_posix()}"
    cfg = _config(url)
    command.upgrade(cfg, "head")
    assert asyncio.run(_diff(url)) == []
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
