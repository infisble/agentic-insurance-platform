# ADR 0003 — Agent orchestration

## Context
A claim moves through a known lifecycle:
`received → documents_extracted → triaged → coverage_checked → (human review) → settled | rejected`.

Inside some steps, the model needs freedom (which tool to call, whether to ask the customer a follow-up question). The process as a whole must be auditable, resumable after crashes, and explainable to a claims handler and to an auditor.

## Options

| Option | Pros | Cons |
|---|---|---|
| A. Fully autonomous agent (one LLM loop decides the whole process) | Least code; impressive demos | Non-reproducible paths, hard to audit, hard to test, unacceptable for decisions with money and regulatory impact |
| B. Agent framework (LangGraph, CrewAI, AutoGen) | Graph primitives, checkpointing, ecosystem | Framework abstractions leak into the domain; fast-moving APIs; debugging through framework internals |
| C. Durable workflow engine (Temporal) | Very strong reliability, retries, long-running human waits | Heavy infrastructure for one engineer; learning curve |
| **D. Explicit state machine in Postgres + thin tool-use loop per step** | Lifecycle is plain domain code and fully testable; each step is a bounded agent with a fixed tool set; trivial to audit | We own retries and resumption logic; less "out of the box" |

## Decision
**Option D.**
- **Lifecycle:** the claim lifecycle is a state machine in the core. Transitions are persisted together with the outbox event in the same transaction.
- **Step execution:** each transition that needs AI enqueues a job (ADR 0004). A worker runs **one specialised agent**: a ~100-line tool-use loop with
  - a fixed tool allow-list,
  - a step budget (max tool calls, max tokens, timeout),
  - a Pydantic output schema.
- **Hand-over between agents:** Intake → Triage → Coverage pass control by emitting a typed result that drives the next transition. The hand-over is explicit and logged.
  - **This is intentionally *not* the A2A protocol.** A2A (Agent2Agent, Linux Foundation) is designed for agents owned by *different* teams or vendors that discover each other through Agent Cards and negotiate tasks over HTTP. Our agents share one codebase, one database and one release cycle, so an in-process typed hand-over is simpler and fully auditable.
  - **Where A2A fits:** the Coverage agent is additionally exposed as an **A2A server** (Agent Card + task endpoint). Another team's agent, for example an underwriting assistant, could then ask it "is X covered under policy Y?" without importing our code. Tool access stays MCP (ADR 0008); agent-to-agent delegation across team boundaries is A2A.

## Implementation status (phase 2)
- **Agent loop:** `src/aip/agents/runtime.py` (~150 lines). It provides:
  - masking of all model input, unmasking of tool arguments;
  - per-agent tool allow-lists and budgets (turns, tool calls, timeout);
  - one corrective retry on schema failure;
  - an append-only history (assistant turns, including thinking blocks, are sent back unchanged).
- **Orchestration:** `src/aip/agents/pipeline.py` is the deterministic workflow. Agents never call transitions themselves; the pipeline applies routing rules on top of the triage proposal and records both the proposed and the final queue.
- **Escalation:** any agent failure (refusal, invalid output, budget, timeout) escalates the claim to `AWAITING_REVIEW` with the reason, as a system actor.
- **Not built yet:** the A2A endpoint for the Coverage agent (phase 4).

## Why
- The process is known; only some decisions inside it are fuzzy. Putting the known part in code and the fuzzy part in bounded agents gives reproducibility where auditors need it and flexibility where it helps.
- Every agent can be unit-tested with recorded LLM responses and evaluated in isolation (ADR 0011).
- No framework lock-in. The loop is small enough to read in an interview.

## Consequences
- **Idempotency:** idempotency keys per (claim, step, attempt) prevent double side effects on retry.
- **Human-in-the-loop:** a human wait is just a state (`awaiting_review`). No long-running process holds memory.
- **Upgrade path:** if workflows become long-running across many systems, migrate the state machine to Temporal without changing the agents.

## Revisit when
There are more than about 5 distinct workflows with cross-system compensation logic, or human waits spanning weeks with timers and escalations. That is the point where Temporal (C) pays off.
