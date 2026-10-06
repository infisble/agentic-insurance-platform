"""Wiring: connect the pipeline to the core API and the MCP server.

In-process (default): core app via ASGI transport and MCP server in memory, one process,
same database. Remote: real URLs of a running core API and MCP server (Streamable HTTP).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from mcp import Client
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from aip.api.app import create_app
from aip.core.config import Settings
from aip.llm.cache import MemoryCache, RedisCache, ResponseCache
from aip.llm.gateway import DEFAULT_MODEL, LLMGateway, make_client
from aip.mcp.core_client import CoreClient
from aip.mcp.server import build_server


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIP_", env_file=".env", extra="ignore")

    llm_provider: str = "anthropic"  # anthropic | foundry
    llm_model: str = DEFAULT_MODEL
    # Read without the AIP_ prefix, so a plain ANTHROPIC_API_KEY in .env works too. When unset,
    # the SDK resolves credentials itself (environment, `ant auth login` profile).
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    foundry_resource: str | None = None
    foundry_api_key: str | None = None
    redis_url: str | None = None


def make_gateway(s: AgentSettings) -> LLMGateway:
    kwargs = {}
    if s.llm_provider == "anthropic" and s.anthropic_api_key:
        kwargs = {"api_key": s.anthropic_api_key}
    if s.llm_provider == "foundry":
        kwargs = {"resource": s.foundry_resource, "api_key": s.foundry_api_key}
    client, fallbacks = make_client(s.llm_provider, **kwargs)
    return LLMGateway(client, server_fallbacks=fallbacks)


def make_cache(s: AgentSettings) -> ResponseCache:
    return RedisCache(s.redis_url) if s.redis_url else MemoryCache()


@asynccontextmanager
async def local_stack(settings: Settings | None = None) -> AsyncIterator[tuple[CoreClient, Client]]:
    app = create_app(settings or Settings())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://core", timeout=60
        ) as http,
    ):
        core = CoreClient(http)
        async with Client(build_server(core)) as mcp:
            yield core, mcp


@asynccontextmanager
async def remote_stack(core_url: str, mcp_url: str) -> AsyncIterator[tuple[CoreClient, Client]]:
    async with httpx.AsyncClient(base_url=core_url, timeout=60) as http, Client(mcp_url) as mcp:
        yield CoreClient(http), mcp
