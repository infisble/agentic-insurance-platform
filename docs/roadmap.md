# Roadmap

## Phase 1 — Deterministic insurance core ✅
- [x] Architecture decision records, diagrams, testing strategy
- [x] Product catalogue: motor third-party liability (PZP), household
- [x] Tariff engine: versioned, explainable, `Decimal`
- [x] Coverage engine: deterministic, clause references, refer vs. reject
- [x] Claim state machine with actor permissions and governance invariant
- [x] Persistence and REST API; audit trail; optimistic locking
- [x] Synthetic data generator (SK/AT), checksum-valid rodné čísla and IBANs
- [x] Docker Compose, Dockerfile, CI; full stack verified on Postgres (API, MCP, worker, cache)

## Phase 2 — Agents + MCP ✅
- [x] Documents: upload, text layer (pypdf), dedupe by content hash
- [x] LLM gateway on the Anthropic SDK (Anthropic API / Microsoft Foundry), effort, structured output, refusal fallbacks, cost
- [x] PII masking: known values + checksum patterns; leak tests
- [x] L2 response cache (memory / Redis)
- [x] Agent runtime: allow-list, budgets, schema retry, append-only history
- [x] MCP server (SDK 2.x): read tools, server-side allow-lists, stdio + HTTP, `.mcp.json` for Claude Code
- [x] Extraction agent + deterministic validators (IBAN, totals, dates, policy number, grounding)
- [x] Triage agent with MCP tools + deterministic routing rules
- [x] Summary agent (Slovak brief, draft reply in customer's language)
- [x] Pipeline with escalation to a human; agent run log with tokens and cost
- [x] Offline mode (regex baseline + rules) for tests and demos without a key
- [x] Synthetic PDFs (forms + free-text e-mails, SK/DE) with labels and anomalies
- [x] Extraction eval: bootstrap CIs, slices, anomaly detection, masking recall, gates; CI job
- [ ] **Record the first LLM eval run** (needs an API key) and put the numbers in the README

## Phase 3 — Web + production plumbing ✅
- [x] Handler CRM (Next.js 16): dashboard, review queue, case view with PDF + evidence, accept/edit/reject feedback, decisions, audit trail, agent cost
- [x] Draft reviews + `/metrics/overview`: override rate per agent, most corrected fields
- [x] `python -m aip.demo`: one-command demo environment
- [x] Playwright E2E for the handler journey and the customer journey across both apps
- [x] Customer portal: quote with premium breakdown, buy, report claim with documents, claim status, answer information requests
- [x] Durable job queue: transactional enqueue, leasing, retries with backoff, dead-letter → human, reconciliation sweeper, stateless workers (ADR 0004)
- [x] Alembic migrations; a test keeps them identical to the models

## Phase 4 — Coverage reasoning, intake
- [ ] Conditions corpus (VPP) ingestion, hybrid retrieval, SK lemmatisation
- [ ] Coverage explanation agent with mandatory citations, exposed via A2A
- [ ] Intake chat agent (SK/DE)
- [ ] Presidio + multilingual NER for third-party names (close the masking gap)
- [ ] Triage and summary evals (LLM-judge calibrated on human ratings)

## Phase 5 — Production readiness
- [ ] Auth: Keycloak locally, Entra ID / Entra External ID in the cloud; actor and MCP identity from the token
- [ ] OpenTelemetry end-to-end, Langfuse, dashboards and alerts
- [ ] Terraform + Azure Container Apps deploy
- [ ] OCR for scans (Azure Document Intelligence)

## Phase 6 — Presentation
- [ ] Discovery artefacts from a real working session
- [ ] Eval results table with the real model in the README
