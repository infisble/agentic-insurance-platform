"""Bridge from the agent loop to MCP tools."""

import json
from typing import Any, Protocol

from mcp import Client


class Toolbox(Protocol):
    async def definitions(self, allowed: frozenset[str]) -> list[dict[str, Any]]: ...
    async def call(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]: ...


class MCPToolbox:
    """Calls tools on the MCP server on behalf of one agent identity.

    The identity travels in the request `_meta` so the server can enforce its allow-list.
    Phase 3 replaces this asserted identity with an authenticated principal (OAuth token).
    """

    def __init__(self, client: Client, agent_id: str) -> None:
        self._client = client
        self._agent_id = agent_id

    async def definitions(self, allowed: frozenset[str]) -> list[dict[str, Any]]:
        listed = await self._client.list_tools()
        return [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.input_schema,
            }
            for t in listed.tools
            if t.name in allowed  # client-side filter; the server enforces it again
        ]

    async def call(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        result = await self._client.call_tool(name, arguments, meta={"aip/agent": self._agent_id})
        parts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
        if not parts and result.structured_content is not None:
            parts = [json.dumps(result.structured_content, ensure_ascii=False)]
        return "\n".join(parts), bool(result.is_error)
