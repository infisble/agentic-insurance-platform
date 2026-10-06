"""MCP server: read tools over the core API, with per-agent allow-lists enforced here.

The allow-list is checked on the server, from the caller's agent identity, not only by which
tools a client shows its model. A prompt-injected agent therefore still cannot reach a tool
outside its list. No tool here can approve, reject or pay; those are not agent capabilities.

Identity (phase 2): asserted by the client in the request `_meta` ("aip/agent"), or by the
AIP_MCP_AGENT environment variable for stdio clients such as Claude Desktop / Claude Code.
Phase 3 binds it to an authenticated principal (OAuth token) instead.
"""

import json
import os
from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from aip.core.products import ProductCode, get_product
from aip.mcp.core_client import CoreClient, CoreError

READ_TOOLS = frozenset(
    {
        "get_claim",
        "get_policy",
        "list_policy_claims",
        "list_claim_documents",
        "get_document_text",
        "get_product_conditions",
    }
)

ALLOWLIST: dict[str, frozenset[str]] = {
    "triage-agent": frozenset(
        {
            "get_claim",
            "get_policy",
            "list_policy_claims",
            "list_claim_documents",
            "get_document_text",
        }
    ),
    "summary-agent": frozenset(),
    "extraction-agent": frozenset(),
    # A handler's own assistant (e.g. Claude Code connected over stdio): read-only access.
    "handler-assistant": READ_TOOLS,
}

# Fields agents never need; dropped from tool results (data minimisation).
_CLAIM_FIELDS = (
    "id",
    "number",
    "policy_id",
    "status",
    "peril",
    "event_date",
    "reported_at",
    "channel",
    "description",
    "claimed_amount",
    "payable_amount",
    "coverage",
    "queue",
    "extraction",
)
_POLICY_FIELDS = (
    "id",
    "number",
    "product_code",
    "status",
    "start_date",
    "end_date",
    "conditions_version",
    "risk",
)


def _agent_name(ctx: Context) -> str:
    meta = getattr(ctx.request_context, "meta", None) or {}
    agent = meta.get("aip/agent") if isinstance(meta, dict) else None
    agent = agent or os.environ.get("AIP_MCP_AGENT", "")
    return str(agent).split("@", 1)[0]


def _authorize(ctx: Context, tool: str) -> None:
    agent = _agent_name(ctx)
    if tool not in ALLOWLIST.get(agent, frozenset()):
        raise ToolError(f"forbidden: tool '{tool}' is not allowed for agent '{agent or '?'}'")


def _pick(data: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {k: data.get(k) for k in fields if k in data}


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, default=str)


def build_server(core: CoreClient) -> MCPServer:
    server = MCPServer(
        "aip-insurance",
        instructions="Read access to claims, policies, documents and product conditions of the "
        "Agentic Insurance Platform. All data is synthetic.",
    )

    async def call(coro: Any) -> Any:
        try:
            return await coro
        except CoreError as exc:
            raise ToolError(f"core API error {exc.status}") from exc

    @server.tool()
    async def get_claim(claim_id: str, ctx: Context) -> str:
        """Get a claim: status, peril, dates, amounts, coverage result and extracted data."""
        _authorize(ctx, "get_claim")
        return _json(_pick(await call(core.get_claim(claim_id)), _CLAIM_FIELDS))

    @server.tool()
    async def get_policy(policy_id: str, ctx: Context) -> str:
        """Get a policy: product, period, status, conditions version and insured risk."""
        _authorize(ctx, "get_policy")
        return _json(_pick(await call(core.get_policy(policy_id)), _POLICY_FIELDS))

    @server.tool()
    async def list_policy_claims(policy_id: str, ctx: Context) -> str:
        """List all claims on a policy (claim history), oldest first."""
        _authorize(ctx, "list_policy_claims")
        claims = await call(core.list_policy_claims(policy_id))
        fields = ("id", "number", "status", "peril", "event_date", "claimed_amount")
        return _json([_pick(c, fields) for c in claims])

    @server.tool()
    async def list_claim_documents(claim_id: str, ctx: Context) -> str:
        """List documents attached to a claim (id, file name, pages)."""
        _authorize(ctx, "list_claim_documents")
        docs = await call(core.list_documents(claim_id))
        return _json([_pick(d, ("id", "filename", "content_type", "page_count")) for d in docs])

    @server.tool()
    async def get_document_text(document_id: str, ctx: Context) -> str:
        """Get the extracted text of one claim document."""
        _authorize(ctx, "get_document_text")
        doc = await call(core.get_document(document_id))
        return doc["text"]

    @server.tool()
    async def get_product_conditions(product_code: str, ctx: Context) -> str:
        """Get the insured perils, limits and clause references of a product (MOTOR_TPL or
        HOUSEHOLD)."""
        _authorize(ctx, "get_product_conditions")
        try:
            product = get_product(ProductCode(product_code))
        except ValueError as exc:
            raise ToolError(f"unknown product {product_code}") from exc
        return _json(
            {
                "product": product.code,
                "name_sk": product.name_sk,
                "conditions_version": product.conditions_version,
                "reporting_deadline_days": product.reporting_deadline_days,
                "senior_review_above_eur": str(product.auto_limit),
                "coverages": [
                    {
                        "peril": c.peril,
                        "clause": c.clause,
                        "limit_eur": str(c.fixed_limit) if c.fixed_limit else None,
                        "limit_share_of_sum_insured": str(c.share_of_sum_insured)
                        if c.share_of_sum_insured
                        else None,
                    }
                    for c in product.coverages.values()
                ],
            }
        )

    return server
