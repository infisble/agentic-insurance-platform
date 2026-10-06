# ADR 0005 — Caching strategy

## Context
Two kinds of cost dominate:
1. **LLM tokens:** long, static system prompts and policy-condition context repeated on every call.
2. **Repeated reads** from the core: policy lookups by agents, tariff tables, product catalogue.

Caching in an insurance context has a specific risk. **A cached answer for a *similar* claim is not a correct answer for *this* claim**, and a cache is a store of personal data that GDPR deletion requests must reach.

## Options considered per layer

| Layer | Options | Decision |
|---|---|---|
| L1 Provider prompt caching | on / off | **On.** Static prefix (system prompt, tool schemas, product conditions) placed first; variable claim data last |
| L2 Exact-match LLM response cache | none / Redis / Postgres table / Elasticsearch | **Redis**, only for agents without tools (extraction, summary): their answer depends on the input alone |
| L3 Semantic cache (embedding similarity) | none / Redis vector / pgvector / Elasticsearch kNN | **Rejected for decisions.** Allowed only for the public FAQ bot, on pgvector |
| L4 Derived-artifact cache (OCR text, embeddings) | recompute / cache by content hash | **On**, in Blob Storage plus Postgres, keyed by SHA-256 of the file |
| L5 Application data cache | none / Redis read-through / HTTP caching | **Redis read-through** for tariffs, products and policy snapshots, with event-based invalidation |

## Which store for the response cache

| Store | Fit for an exact-match cache with TTL |
|---|---|
| **Redis-compatible (Azure Managed Redis / Valkey / Redis 8)** | Purpose-built key-value store: sub-millisecond `GET`/`SET`, native per-key TTL, LRU eviction, atomic operations. **Chosen** |
| Postgres table | Works and is simple, but no native TTL (needs a cleanup job) and puts cache churn on the transactional DB |
| Elasticsearch / OpenSearch | A search engine, not a cache: writes become visible only after refresh (~1 s), there is no per-document TTL (only index lifecycle policies), and it is a heavy JVM cluster to run. It only makes sense for L3-style similarity lookups or if the organisation already operates it. We rejected L3 for decisions, so it brings no benefit here |

**Licensing note.**
- Redis moved to RSAL/SSPL in 2024. Redis 8 (2025) added AGPLv3, and the Linux-Foundation fork Valkey stays BSD.
- We only depend on the Redis **protocol**, so any of these, or the managed Azure service, is interchangeable.
- In the cloud we use **Azure Managed Redis**. Azure Cache for Redis is being retired, and new instances are blocked from October 2026.

## Details

**L1 — Provider prompt caching**
- Prompts are assembled in a fixed order: `[system][tool schemas][product conditions][few-shot] | [claim-specific data]`.
- Azure OpenAI caches long prefixes automatically. Anthropic-style providers need explicit cache markers, which the gateway adds (ADR 0002).
- The hit rate is measured in Langfuse (ADR 0010), not assumed.

**L2 — Exact-match response cache**
- Key: `sha256(task, prompt_version, model, model_params, masked_input)`. A prompt or model change invalidates automatically because it is part of the key.
- Value stores only the **masked** model output (ADR 0012), with a TTL of 7 days.
- Because outputs contain pseudonym tokens, a hit is re-identified with the *current* claim's mapping, so the cached value never carries another person's data.
- Main payoffs: re-running the eval suite and re-processing the same document after a crash.
- **Implemented** in `src/aip/llm/cache.py` and `src/aip/agents/runtime.py` (in-memory by default, Redis when `AIP_REDIS_URL` is set). A test proves that a hit for a different person returns that person's own data (`test_cache_hit_skips_model_and_reidentifies_with_current_case`).
- **Eval caveat:** the eval suite can bypass L2 (`--no-cache`). Scheduled variance runs (n = 3) must bypass it, otherwise run-to-run nondeterminism is hidden.

**L3 — Why semantic caching is rejected for decisions**
- Two claims that differ only in policy number or event date embed almost identically but must produce different coverage answers.
- A false cache hit here is a wrong decision, not just a stale one.

**L4 — Derived artifacts**
- OCR and embeddings are keyed by the content hash of the file. Re-uploading the same invoice costs nothing.

**L5 — Application cache**
- **Tariff tables and product catalogue:** cached, invalidated on publish.
- **Policy snapshot reads from MCP tools:** TTL of 60 s and invalidated by the `policy.changed` domain event.
- **Never cached:** payment and payout state.

**Redis is a disposable cache only**
- It is configured with `allkeys-lru` and no persistence requirement. Losing it costs money and latency, never correctness.
- The job queue lives in Postgres (ADR 0004), so the eviction policy cannot drop jobs.

## Why
- Each layer targets a measured cost driver.
- Every cache key includes everything that could change the answer.
- The one layer that could silently produce wrong answers (L3) is explicitly excluded where it matters.

## Consequences
- **GDPR erasure:** pseudonymised data is still personal data (GDPR Recital 26). Cache entries are tagged with `party_id` at write time, and the erasure job purges L2 and L4 by tag.
- **Monitoring:** hit rate, size and evictions per layer are exported as metrics. Caching is part of observability, not a hidden optimisation.

## Revisit when
The L2 hit rate in production stays below ~5% (remove it), or the FAQ bot's semantic-cache false-hit rate on its eval set rises above an agreed threshold.
