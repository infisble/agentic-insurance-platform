# ADR 0010 — Observability: latency, cost, quality

## Context
For non-deterministic systems, "is it up?" is not enough. We need per claim and per agent step:
- **latency:** p50 / p95;
- **cost:** tokens and EUR, including cache hits;
- **quality:** validation failures, human overrides, abstentions;
- **full trace:** prompt version → tool calls → output.

The trace must be stored **without leaking PII** into third-party tools.

## Options

| Option | Pros | Cons |
|---|---|---|
| A. Logs only | Nothing new | No traces across services; cost and quality cannot be aggregated |
| B. LangSmith (SaaS) | Rich LLM tracing | SaaS data residency; framework-oriented |
| **C. OpenTelemetry everywhere + self-hosted Langfuse for LLM traces + Azure Monitor / App Insights for infra** | Vendor-neutral instrumentation; LLM-specific views (cost, prompt versions, scores); data stays in our tenant | Two UIs; Langfuse must be operated |
| D. Arize Phoenix | Good for evals and offline analysis | Less mature for production operations dashboards |

## Decision
**Option C.**
- **One trace ID end-to-end:** `claim_id` flows from the HTTP request → outbox → queue → worker → LLM gateway → MCP → core.
- **The LLM gateway** records model, prompt version, tokens (cached vs. uncached), cost in EUR, latency and the cache layer hit, on **masked** payloads.
- **Quality signals become Langfuse scores:**
  - schema validation pass/fail,
  - validator failures (IBAN, totals),
  - human accept / edit / reject in the CRM,
  - abstentions.
- **Dashboards and alerts:**
  - cost per claim,
  - straight-through-processing rate,
  - human override rate per agent,
  - p95 latency per step,
  - queue depth,
  - provider error rate.

## Langfuse hosting: cost of self-hosting
Self-hosted Langfuse (v3+) is not a single container. It needs:
- web and worker containers,
- Postgres,
- **ClickHouse** (trace storage),
- Redis/Valkey,
- S3/Blob.

ClickHouse is a real operational burden for a small team. So:
- **Dev / demo (synthetic data only):** Langfuse Cloud, EU region. Nothing to operate.
- **Production:** self-hosted in our tenant with **managed ClickHouse** (ClickHouse Cloud on Azure, EU), so trace data stays under our DPA.
- **Fallback if self-hosting is not approved:** export OTel spans only to Azure Monitor and keep LLM-specific scoring in our own Postgres tables. This is less convenient but needs zero new components.

## Why
- Human overrides in the CRM are the most honest production quality metric. Wiring them back into traces closes the loop between users and engineering.
- OpenTelemetry keeps instrumentation portable whatever the backend.

## Consequences
- An alert fires on override-rate drift per agent, not only on errors and latency.
- The weekly review samples low-scored traces into the golden dataset (ADR 0011).

## Revisit when
The organisation has a standard LLM observability platform. We then switch the OTel exporter, not the instrumentation.
