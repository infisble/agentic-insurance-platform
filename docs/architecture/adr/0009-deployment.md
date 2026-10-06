# ADR 0009 — Deployment platform, IaC and CI/CD

## Context
Deploy units:
- core API,
- agent workers,
- MCP server,
- 2 web apps.

Backing services: Postgres (data, vectors and job queue), Redis (cache only), Blob storage. Requirements:
- EU region,
- scale-to-zero for cost in a demo or pilot environment,
- autoscaling of workers by queue depth,
- reproducible environments (dev / staging / prod),
- low operations burden for a small team.

## Options

| Option | Pros | Cons |
|---|---|---|
| A. Docker Compose on a single VM | Cheapest; simplest | No autoscaling or HA; manual operations; not credible as production |
| **B. Azure Container Apps** | Managed containers; KEDA autoscaling on Redis queue length; scale-to-zero; managed identity; revisions for canary | Less control than Kubernetes; Azure-specific |
| C. AKS (Kubernetes) | Full control; portable; enterprise standard at scale | Cluster operations, upgrades, networking. Too much for this team size |
| D. AWS ECS Fargate | Comparable to B | Second cloud if the LLM and identity are on Azure |
| E. Serverless functions | Pay per call | Cold starts and execution limits clash with 60 s agent steps and stateful MCP connections |

## Decision
- **Local:** Docker Compose. One command brings up the whole stack with seeded data.
- **Cloud:** **Option B, Azure Container Apps.**
  - KEDA scales workers on queue depth with its PostgreSQL scaler: a `count(*)` of pending jobs per queue.
  - Managed backing services: Azure Database for PostgreSQL Flexible Server (with `pgvector`, `pg_trgm`, `unaccent`), **Azure Managed Redis**, Blob Storage, Key Vault.
  - We use Azure Managed Redis rather than Azure Cache for Redis because the latter is being retired: new instances are blocked from Oct 2026, with retirement in 2027–2028.
- **IaC:** Terraform, one module per environment.
- **CI/CD:** GitHub Actions.
  - **On every pull request:** lint, type-check, unit tests, contract tests, and the eval suite with quality gates (ADR 0011).
  - **On merge to main:** build images, deploy to staging, smoke tests.
  - **Production:** manual promotion using ACA revisions with a traffic split for canary.

## Why
- ACA delivers 90% of what Kubernetes offers here (autoscaling, revisions, identity) at a fraction of the operations work.
- The containers are standard OCI images, so moving to AKS later means changing the deployment target, not the application.
- Keeping LLM, identity and runtime in one cloud simplifies networking and the data-protection story (ADR 0002).

## Consequences
- **Secrets:** only in Key Vault, accessed via managed identity. No keys in env files.
- **Prompt and model releases:** go through the same pipeline as code. A prompt change is a deploy with eval gates, not a hot edit.

## Revisit when
The platform joins a shared enterprise Kubernetes platform, or needs networking features ACA does not support.
