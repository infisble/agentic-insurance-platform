# Testing strategy

Two different kinds of correctness live in this system, and they are tested differently.

| Kind | Where | How it is tested |
|---|---|---|
| **Deterministic** (tariffs, coverage rules, state machine, API contracts) | `src/aip/core` | Classic tests written first (TDD): exact expected values, run on every commit |
| **Non-deterministic** (extraction, triage, coverage reasoning, letters) | `src/aip/agents` (phase 2+) | Evals on a golden dataset with metrics and gates (ADR 0011). They do not replace tests; agents also get ordinary unit tests with recorded LLM responses |

## Test pyramid

```
                 ┌───────────┐
                 │  E2E (few)│  Playwright: portal → claim → CRM approve
                ┌┴───────────┴┐
                │   Evals     │  golden dataset, metrics, CI gates (ADR 0011)
               ┌┴─────────────┴┐
               │  Contract     │  MCP tools ↔ core OpenAPI schema
              ┌┴───────────────┴┐
              │  Integration     │  API + DB (SQLite in-memory; Postgres in CI)
             ┌┴─────────────────┴┐
             │  Unit (most)       │  pure domain: tariff, coverage, state machine
             └───────────────────┘
```

## Levels

| Level | Location | Scope | Speed | Runs |
|---|---|---|---|---|
| Unit | `tests/unit/` | Pure functions, no I/O | ms | every commit, pre-commit |
| Integration | `tests/integration/` | FastAPI app + real DB session via `httpx.ASGITransport` | < 1 s each | every commit |
| MCP | `tests/agents/test_mcp_server.py` | MCP server in process against the real core API: allow-lists, data minimisation, error mapping | fast | every commit |
| Agent | `tests/agents/` | Agent loop and full pipeline with a scripted model double (same SDK surface): budgets, allow-list, schema retry, refusal, cache, PII never sent | fast | every commit |
| Evals | `src/aip/evals/` | Generated golden set, metrics with CIs, gates | baseline: seconds; LLM: minutes, costs tokens | baseline every commit; LLM on PRs touching agents |
| E2E | `e2e/` (phase 3) | Browser through both web apps | slow | before release |

## What must always be tested

These are the invariants a reviewer or auditor cares about. Each has a dedicated test.

1. **Governance invariant:** no AGENT transition ever leads to `APPROVED`, `REJECTED` or `PAID`.
   - Test: `test_agents_can_never_decide_or_pay`.
2. **Premiums are server-side:** a policy's premium is always recomputed by the tariff engine. Client-supplied amounts are ignored.
   - Test: `test_issue_policy_recomputes_premium`.
3. **Tariff explainability:** every premium breakdown lists every factor applied. Multiplying base × factors reproduces the net premium exactly.
4. **Coverage determinism:** the same policy snapshot and facts always give the same result. Each rejection or referral carries a clause reference.
5. **Audit trail:** every claim status change writes exactly one `ClaimEvent` with the actor.
6. **Money:** all amounts are `Decimal`, rounded half-up to cents, never `float`.
7. **Synthetic PII validity:** generated rodné čísla pass the official mod-11 check, so masking recognisers can be tested against realistic data.

## TDD workflow used

1. Write the test from the specification. A specification comes from a discovery session or a product rule; see `docs/discovery/`.
2. Watch it fail.
3. Write the minimum code to pass.
4. Refactor with the test as a safety net.

Hand-calculated expected values are written into the test with the calculation in a comment. A reviewer can check the arithmetic without running the code.

## Test data policy

- **Synthetic only.** Never real customer data, in tests, fixtures, eval sets or screenshots.
- **Deterministic generation:** `python -m aip.seed --seed 42` always produces the same dataset, so test expectations are stable.
- **Realistic shapes:** Slovak and Austrian names and addresses (Faker `sk_SK` and `de_AT`), checksum-valid rodné čísla, plausible risk profiles. Realistic shapes are what make PII masking and extraction tests meaningful.

## CI stages

```
ruff (lint + format check) → pytest unit → pytest integration
   → [phase 2] contract → agent unit → evals (gated)
   → build image → deploy staging → smoke
```

## Commands

```bash
pytest                       # everything
pytest tests/unit            # fast loop
pytest -k state_machine      # one area
pytest --cov=aip             # with coverage
```
