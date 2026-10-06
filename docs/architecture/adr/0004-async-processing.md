# ADR 0004 — Async processing and job queue

## Context
Agent steps take 2–60 s and can fail transiently (rate limits, timeouts). They must not run inside HTTP requests. They need:
- retries with backoff,
- priorities (motor claim from the portal > nightly re-extraction),
- concurrency limits per provider,
- visibility into queue depth.

Expected volume is low: tens to hundreds of claims per hour, not thousands per second. The agent code is `async` (httpx, MCP client).

## Options

| Option | Pros | Cons |
|---|---|---|
| A. FastAPI BackgroundTasks | Zero infrastructure | Lost on restart; no retries or visibility; not for production |
| **B. Postgres-backed queue (Procrastinate, `SELECT … FOR UPDATE SKIP LOCKED`)** | Job is inserted **in the same transaction** as the state change, so there is no dual-write; durable by default; asyncio-native; no new infrastructure | Polling and locking load on the DB; throughput ceiling in the low thousands of jobs/s, far above our need |
| C. Redis + Celery | Mature; retries, rate limits, Flower UI | Needs an outbox relay to avoid dual-write; a Redis broker loses jobs without persistence; `visibility_timeout` redelivery pitfalls; Celery is not asyncio-native; sharing Redis with the cache conflicts on eviction policy (`noeviction` for queues vs `allkeys-lru` for caches) |
| D. Azure Service Bus | Managed; dead-letter queues; sessions | Cloud lock-in; harder local development; still needs an outbox |
| E. Kafka / Event Hubs | Event streaming, replay | Massive overkill for this volume |

## Decision
**Option B (Procrastinate on Postgres).**
- The claim state transition and the job that processes the next step are written in **one transaction**. A job exists if and only if the state change was committed, with no outbox relay to build and operate.
- Queues are split by profile: `llm-fast`, `llm-heavy`, `ocr`, `notifications`. Workers set concurrency per queue.
- **Provider rate limits** are enforced in the LLM gateway (ADR 0002) with a token bucket, not in the queue, so every caller is covered.
- **Reconciliation sweeper:** a periodic job finds claims stuck in a non-terminal state longer than the step SLA and re-enqueues them or escalates. This catches anything that slipped through (worker crash mid-step, bug).

## Implementation status (phase 3)
- **Wired, with a small in-house queue instead of Procrastinate** (`src/aip/core/jobs.py`, ~200 lines). Procrastinate is Postgres-only, and local development, tests and the demo run on SQLite. The in-house table keeps the properties this ADR chose Option B for:
  - **Transactional enqueue.** Uploading a document to a `RECEIVED` claim, or a customer answering a `NEEDS_INFO` request, inserts the job in the same request transaction.
  - **Leasing.** `SELECT … FOR UPDATE SKIP LOCKED` on Postgres plus a conditional `UPDATE … WHERE status = 'queued'`, which is also correct on SQLite with several workers.
  - **Retries** with exponential backoff (10 s, 40 s, 160 s, capped at 30 min), then `dead`. A dead job escalates its claim to a human (`AWAITING_REVIEW`, system actor, reason in the audit trail).
  - **Debounce.** One queued job per claim; more uploads only push its start back.
  - **Reconciliation sweeper.** Re-queues jobs whose lease expired (worker crash) and escalates claims stuck mid-pipeline for more than 15 minutes. Every worker runs it once a minute; it is safe to run concurrently.
- **Workers are stateless** and talk to the core over HTTP (`/internal/jobs/lease|complete|fail|sweep`), like the MCP server. Run with `python -m aip.agents worker`; `python -m aip.demo` starts one in-process.
- **Not yet:** separate queues per profile (`llm-fast`, `llm-heavy`, `ocr`) and KEDA autoscaling. The `queue` column is there; workers do not filter on it yet.
- **Swap to Procrastinate** when the deployment is Postgres-only: the enqueue call and the worker loop are the only two places that change.

## Why
- At this volume the database is not the bottleneck, and removing a component removes a whole class of failures (dual-write, broker data loss, cache/queue eviction conflict).
- Durability comes for free from Postgres backups and HA. Redis can stay a pure, disposable cache (ADR 0005).
- Asyncio-native workers run the same async agent code as the API, with no `asyncio.run` shims.

## Consequences
- Every task is idempotent (ADR 0003 keys). Retries are at-least-once.
- Failed jobs after max retries create a manual-review task in the handler CRM instead of disappearing silently.
- Workers autoscale on queue depth via the KEDA PostgreSQL scaler (ADR 0009).
- **Rejected earlier draft:** Celery + Redis with an outbox relay. Moved away from it after review because of the dual-write and eviction-policy issues above.

## Revisit when
Sustained load exceeds ~500 jobs/s, or job polling shows up in Postgres CPU profiles. Then move to Service Bus (D) with an outbox, behind the same queue interface.
