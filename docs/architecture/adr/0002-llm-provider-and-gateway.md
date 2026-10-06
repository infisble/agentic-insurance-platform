# ADR 0002 — LLM provider, data residency and gateway

**Status:** Accepted (revised in review 2 after implementation; see "What changed").

## Context
Claims documents contain personal and health data (GDPR Art. 9). Requirements:
- processing in an approved region under the enterprise DPA,
- contractual no-training terms,
- ability to switch models or hosting without touching agent code,
- tests and CI that never send data to a provider.

## Options

| Option | Pros | Cons |
|---|---|---|
| A. Azure OpenAI (EU Data Zone) | Azure-native; enterprise DPA; private networking | Different model family; agent code would target a second SDK |
| **B. Claude on Microsoft Foundry (Azure)** | Runs inside the Azure estate and its procurement and identity (Entra ID); same Anthropic SDK surface as the first-party API | Server-side refusal fallbacks are not available there; region availability must be confirmed for the EU deployment |
| **C. Claude via the Anthropic API** | Newest features first (server-side fallbacks, prompt caching); simplest for development | Separate DPA and procurement from the Azure estate |
| D. AWS Bedrock | Claude and others behind one API | Second cloud next to Azure |
| E. Self-hosted open model (vLLM) | Full data control | GPU operations; weaker German/Slovak extraction; heavy MLOps for a small team |
| F. Multi-provider proxy (LiteLLM) in front of A–D | One interface for every vendor | Extra dependency and abstraction; lowest-common-denominator API hides features we use (structured outputs + tools, effort, fallbacks) |

## Decision
- **Model:** Claude (`claude-opus-5-5` by default, configurable per environment with `AIP_LLM_MODEL`).
- **Development and evaluation: option C** (Anthropic API).
- **Production target: option B** (Claude on Microsoft Foundry), so the workload stays inside the Azure tenant, identity and procurement already used for the rest of the stack (ADR 0009, 0013).
- **Gateway:** our own thin module (`src/aip/llm/gateway.py`) on the official Anthropic SDK. Both providers expose the same SDK surface (`AsyncAnthropic` / `AsyncAnthropicFoundry`), so switching is configuration: `AIP_LLM_PROVIDER=anthropic|foundry`.
- **Tests and CI:** use a scripted test double with the same `beta.messages.create` surface. CI never calls a model except in the opt-in eval job.

## How the gateway calls the model
- **Structured output:** `output_config.format` with a JSON Schema generated from the Pydantic output model, combined with tools where an agent has them.
- **Effort:** `output_config.effort`, set per agent: extraction `high`, triage and summary `medium`. These are starting points to be tuned by evals.
- **No `temperature` and no forced `tool_choice`:** the current models reject both. Reproducibility therefore comes from versioned prompts, the L2 cache (ADR 0005) and evals (ADR 0011), not from sampling settings.
- **Refusals:**
  - on the Anthropic API the gateway opts into server-side fallbacks (`fallbacks: "default"`);
  - on Foundry that parameter is unavailable, so a refusal raises `RefusalError` and the claim is escalated to a human;
  - in both cases usage and cost of the refused call are still recorded.
- **Prompt caching:** the static system prompt carries `cache_control` (L1).

## Why
- In a regulated insurer, hosting, DPA and identity get a solution approved; Foundry keeps Claude inside the Azure estate.
- **Per-task model routing is not done yet, deliberately:**
  - the same model is used everywhere until the eval shows a cheaper model holds quality on a given task;
  - routing without that evidence is a guess.
- **Why not LiteLLM (option F):** it was the first draft. The implementation showed that the features we rely on (structured outputs together with tools, effort, refusal fallbacks) are provider-specific. One SDK that covers both of our hosting options is simpler than a proxy that abstracts them away.

## Consequences
- Prompts are versioned per agent (`AgentSpec.version`). Every eval report records model and version.
- Model or provider changes go through the eval gate before release.

## What changed (review 2)
- LiteLLM was replaced by a direct SDK gateway (see Why).
- Azure OpenAI was replaced as the production target by Claude on Foundry (still Azure).
- The claim of "temperature 0 for determinism" was removed: current models do not accept the parameter.

## Revisit when
- Volume makes per-token cost dominant: evaluate a smaller model per task, and self-hosting for the cheapest tasks.
- Foundry is not available in the required EU region.
