# ADR 0008 — Integration of agents with the core: MCP

## Context
Agents need to read policies, check coverage limits, create and update claims, and attach documents. The core already exposes a REST API for the portal and the CRM. The question is how agents call it, and how the set of operations an agent may perform is controlled.

## Options

| Option | Pros | Cons |
|---|---|---|
| A. Agents call the core REST API via hand-written function-calling wrappers | Simple | Tool definitions are duplicated per agent; no standard discovery; harder to reuse from other clients (Copilot, IDE, other teams' agents) |
| B. Agents access the database directly | Fast to build | Bypasses domain rules and the audit trail; unacceptable |
| **C. MCP servers in front of the core API, one per domain** | Standard protocol; tools, schemas and descriptions defined once; reusable by any MCP client; natural place for auth and allow-lists | Extra hop; MCP auth and versioning still maturing |

## Decision
**Option C.** One MCP server **deployable** with four domain toolsets.
- **Not four separate services:** four MCP services would add three deploy units with no difference in scaling or ownership.
- **Domains stay separate in code** (one module each), so any toolset can be split into its own server later.

The toolsets:
- `policy-mcp`: `get_policy`, `get_policy_snapshot_at(date)`, `list_coverages`
- `claims-mcp`: `create_claim_draft`, `update_claim_fields`, `attach_document`, `request_human_review`
- `docs-mcp`: `get_document_text`, `get_document_page_image`
- `knowledge-mcp`: `search_conditions(product, version, query)`

**Rules**
- **Transport:** Streamable HTTP. Each MCP server calls the core **REST API** with a service identity. It never touches the DB, so domain rules and the audit trail always apply.
- **Per-agent allow-lists:** the Triage agent cannot call `update_claim_fields`, and no agent has a tool to settle or pay. Settlement is a human or rule action.
  - Allow-lists are enforced **server-side** from the caller's agent identity, not only by which tools the client chooses to show the model.
  - A prompt-injected agent therefore still cannot reach a tool outside its list.
- **Draft mode for writes:** writes create *drafts* or *proposals* that a human or a validation rule confirms.

## Implementation status (phase 2)
- **Server:** `src/aip/mcp/server.py`, built on the official MCP Python SDK 2.x (`MCPServer`).
- **Transports:** stdio (Claude Code / Claude Desktop, see `.mcp.json`) or Streamable HTTP. The tools call the core REST API.
- **Tools:** read-only only — `get_claim`, `get_policy`, `list_policy_claims`, `list_claim_documents`, `get_document_text`, `get_product_conditions`. Drafts and transitions are written by the deterministic pipeline, not by tools the model can call.
- **Identity:** asserted by the client in the request `_meta` (`aip/agent`), or by `AIP_MCP_AGENT` for stdio. This is a client-supplied claim, not authentication.
- **Phase 3:** bind identity to an OAuth-authenticated principal; the SDK supports token verification.
- **Allow-lists:** enforced on the server from that identity. Tests cover denial for unknown and empty identities and confirm that no tool can decide or pay.

## Why
- This is the realistic integration pattern for an enterprise core: wrap existing APIs, do not rewrite them.
- MCP makes the same tools usable from the handler's Copilot-style assistant and from batch agents without duplication.
- The tool surface is the security boundary. Keeping it small and explicit is the main safety control.

## Consequences
- Tool descriptions are prompts too: they are versioned and covered by evals.
- Contract tests run between the MCP servers and the core OpenAPI schema in CI.

## Revisit when
The organisation standardises on a gateway product for agent tool access, or the MCP authorization spec requires changes to the service-identity model.
