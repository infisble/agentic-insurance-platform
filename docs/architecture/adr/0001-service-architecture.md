# ADR 0001 — Service architecture

## Context
The platform has two very different kinds of workload:
- **Core insurance domain** (policies, claims, billing, tariffs): transactional, consistency-critical, deterministic.
- **Agent workload** (LLM calls, document parsing): slow (seconds to minutes), bursty, expensive, failure-prone, and changed often (prompts, models).

The team is one engineer. The role description asks for "Python and microservices".

## Options

| Option | Pros | Cons |
|---|---|---|
| A. Single monolith (core + agents in one app) | Simplest to build and deploy | LLM latency and failures leak into transactional API; can't scale agents separately; a prompt change redeploys the core |
| B. Full microservices (policy, claims, billing, tariff, each agent as its own service) | Independent scaling and deploys; looks "enterprise" | Distributed transactions, many deploy units, network failure modes, overhead far beyond one person's capacity |
| **C. Modular monolith core + separate agent service + MCP servers** | Domain consistency stays in one DB transaction; agents isolated and scaled independently; clean seam for later extraction | Three backend deploy units (core, agent workers, MCP server); module boundaries must be enforced by discipline |

## Decision
**Option C.**
- **Core:** a modular monolith with strict internal modules (`policy`, `claims`, `billing`, `tariff`, `party`). Modules talk only through service interfaces, never through each other's tables.
- **Agent service:** a separate deployable.
- **Access path:** agents reach the core only through MCP tools (ADR 0008).

This is still a **microservice split along the boundary that matters**: three independently deployable services (core, agent workers, MCP server) plus two frontends. Its granularity is driven by runtime characteristics, not by drawing one service per entity.

## Why
- The boundary that actually matters is **deterministic vs. non-deterministic**, not policy vs. claims. That is where failure modes, scaling profile and release cadence differ.
- Splitting the domain into microservices would add distributed-consistency problems (e.g., issuing a policy + creating the first invoice) without any benefit at this scale.
- It mirrors a realistic enterprise setup: an existing core system (a policy administration system) that AI services integrate with via APIs, rather than being rewritten.

## Consequences
- Import-linter rules enforce module boundaries inside the core.
- The agent service can be scaled to zero or throttled without affecting the portal.
- Any module can later be extracted into its own service because it already has an interface.

## Revisit when
A core module needs a different release cadence or scaling profile from the others (for example, tariff calculation under heavy quote traffic).
