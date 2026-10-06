# Architecture — Agentic Insurance Platform

A scaled-down insurance core (clients, products, policies, claims, payments)
with an agentic layer on top that automates claims intake, document extraction, triage,
coverage checks and correspondence.

## Guiding principle

**Agents propose, deterministic code decides.**
Premiums, coverage limits, payouts and policy issuance are computed by tested, rule-based
code in the core. LLM agents read documents, collect data, fill forms, explain and suggest.
Every agent output that changes state goes through either a validation rule or a human.

## System overview

```
            ┌──────────────────────── Web ────────────────────────┐
            │  Customer portal (Next.js)      Handler CRM (Next.js)│
            │  quote · buy · report claim     queue · case · agent │
            └──────────────┬──────────────────────────┬───────────┘
                           │ REST (Entra ID / OIDC)   │
                           │  via ACA ingress         │
              ┌────────────▼─────────┐                │
              │  Core service        │  state change + job
              │  (modular monolith)  │  in ONE transaction
              │  policy · claims ·   ├───────────┐
              │  billing · tariff    │           │
              └──▲──────┬────────────┘           │
                 │ REST │                        │
       ┌─────────┴────┐ │             ┌──────────▼──────────────┐
       │  MCP server  │◄┼─────────────┤  Agent workers           │
       │ policy·claims│ │    MCP      │  Intake · Extraction ·   │
       │ docs·knowledge │             │  Triage · Coverage(A2A) ·│
       └──────────────┘ │             │  Fraud · Letters         │
                        │             └───┬──────────┬──────────┘
                  ┌─────▼───────────┐ ┌───▼────┐ ┌───▼──────────┐ ┌──────────┐
                  │ Postgres        │ │  LLM   │ │ Blob storage │ │  Redis   │
                  │ data · pgvector │ │gateway │ │ (documents)  │ │ cache    │
                  │ · job queue     │ └────────┘ └──────────────┘ │ only     │
                  └─────────────────┘                             └──────────┘
      Cross-cutting: OpenTelemetry → Langfuse + App Insights · PII masking · audit log · evals in CI
```

## Decision log

| # | Decision | Status |
|---|---|---|
| [0001](adr/0001-service-architecture.md) | Service architecture: modular monolith core + separate agent service | Accepted |
| [0002](adr/0002-llm-provider-and-gateway.md) | LLM provider: Claude via Anthropic API (dev) and Microsoft Foundry (prod); own SDK gateway | Accepted (revised 2) |
| [0003](adr/0003-agent-orchestration.md) | Agent orchestration: explicit workflow + thin tool-use loop; A2A only across team boundaries | Accepted (revised) |
| [0004](adr/0004-async-processing.md) | Async processing: Postgres-backed queue | Accepted (revised) |
| [0005](adr/0005-caching-strategy.md) | Caching strategy (5 layers), Redis as cache only | Accepted (revised) |
| [0006](adr/0006-retrieval-rag.md) | Retrieval / RAG store, chunking, Slovak full-text search | Accepted (revised) |
| [0007](adr/0007-document-processing.md) | Document parsing and OCR | Accepted |
| [0008](adr/0008-integration-mcp.md) | Integration of agents with core: one MCP server, server-side allow-lists | Accepted (revised) |
| [0009](adr/0009-deployment.md) | Deployment platform, IaC and CI/CD | Accepted (revised) |
| [0010](adr/0010-observability.md) | Observability: traces, cost, latency, quality | Accepted (revised) |
| [0011](adr/0011-evaluation.md) | Evaluation of non-deterministic components | Accepted (revised) |
| [0012](adr/0012-pii-and-governance.md) | PII handling and model governance | Accepted (revised) |
| [0013](adr/0013-frontend-and-auth.md) | Frontend stack and authentication | Accepted |

Each ADR follows the same template: context → options considered → decision → why →
consequences → when to revisit. "When to revisit" is deliberate: every choice here is
sized for the current scale and names the signal that would change it.

## Review log

### Review 1 — 2026-10-06

| Finding | Severity | Change |
|---|---|---|
| Redis used as both job broker and LRU cache: the eviction policies conflict, and a broker without persistence loses jobs | High | Queue moved to Postgres (Procrastinate); Redis is cache-only (0004, 0005) |
| Outbox relay plus a separate broker meant two moving parts to guarantee one thing | Medium | Job is inserted in the same transaction as the state change; reconciliation sweeper added (0004) |
| Azure Cache for Redis is being retired (new instances blocked from Oct 2026) | High | Switched to Azure Managed Redis (0005, 0009) |
| Postgres has no Slovak full-text configuration, and managed Postgres blocks custom dictionaries | High | App-side lemmatisation + `simple`/`unaccent` + `pg_trgm` (0006) |
| spaCy has no official Slovak NER pipeline, so PII masking recall for Slovak names was unaddressed | High | Multilingual transformer NER in Presidio, recall measured (0012) |
| "Pseudonymised = low risk" was legally inaccurate | Medium | Clarified: still personal data under GDPR (0012) |
| Internal hand-over was labelled "A2A" | Medium | Clarified the difference; Coverage agent exposed via A2A for cross-team use (0003) |
| Four MCP deployables with no scaling or ownership difference | Low | One server, four toolsets (0008) |
| Tool allow-lists only enforced client-side | Medium | Enforced server-side by agent identity (0008) |
| Self-hosted Langfuse needs ClickHouse, which was not accounted for | Medium | Cloud EU for demo; managed ClickHouse for prod; fallback path documented (0010) |
| Eval gates on 15–60 cases would react to noise | Medium | Pooled metrics, bootstrap CIs, hard asserts for critical cases, variance runs (0011) |
| Considered: Elasticsearch instead of Redis for the response cache | — | Rejected: a search engine, not a TTL cache. Kept as an option for RAG if already operated (0005, 0006) |

### Review 2 — 2026-10-06 (after implementing phase 2)

| Finding | Severity | Change |
|---|---|---|
| ADRs claimed "temperature 0" for deterministic extraction; current Claude models reject `temperature` and forced `tool_choice` | High | Reproducibility now comes from versioned prompts, the L2 cache and evals (0002, 0005) |
| LiteLLM proxy hid the provider-specific features the agents rely on (structured output + tools, effort, refusal fallbacks) | Medium | Own thin gateway on the Anthropic SDK; Foundry and the Anthropic API share its surface (0002) |
| A refused or truncated model call lost its usage and cost | Medium | `LLMError` carries the call; cost is recorded on failed runs (test added) |
| MCP agent identity is client-asserted (`_meta`), not authenticated | Medium | Documented as a phase-2 limitation; OAuth principal in phase 3 (0008) |
| Synthetic golden set was too easy: the regex baseline scored 100% | High | Added free-text customer e-mails; baseline drops to 25% on that slice, which makes the LLM comparison meaningful (0011) |
| German claim forms said "Rechnungsdatum" (invoice date), which mislabelled them as invoices | Low | Generator fixed; found by the eval's per-type slice |
| Fonts lived outside the Python package, which would break PDF generation in the Docker image | Medium | Moved into `aip/seed/fonts` and verified in the built wheel |
| A rejected claim could be routed to `fast_track` | Low | Routing rule: `NOT_COVERED` → at least `standard` |

### Review 3 — 2026-10-07 (after phase 3: job queue, migrations, customer portal)

Found by running the full Docker Compose stack on Postgres, not just the SQLite test suite.

| Finding | Severity | Change |
|---|---|---|
| Timestamps were `timestamp without time zone` while the code writes aware UTC datetimes; asyncpg rejects that combination | High | All `datetime` columns are `timestamptz` (SQLite keeps UTC without an offset) |
| `httpx` was only a dev dependency, but the MCP server and the worker import it at runtime; the worker container crashed on start | High | Runtime dependency; compose smoke test added to the checklist |
| Compose enabled the Redis cache, but the image was built without the optional `redis` extra | Medium | Image installs `.[redis]` |
| The unprivileged container user could not write to a fresh documents volume | Medium | `/data/documents` created and owned by the app user in the image |
| Several uploads in a row would start several pipeline runs for one claim | Low | One queued job per claim; new uploads only push its start back (debounce) |
| A customer could open any claim by id in the portal | Medium | Portal pages are scoped to the policies of the current customer (cookie stand-in for Entra External ID); E2E test asserts 404 |
