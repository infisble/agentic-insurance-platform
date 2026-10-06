"""The bounded agent loop (ADR 0003, diagrams §5).

One agent = fixed system prompt + fixed tool allow-list + output schema + budgets.
The loop masks everything sent to the model, unmasks tool arguments before execution,
validates the final answer against the schema (one corrective retry), and stops with an
AgentError when a budget is exhausted. Errors are not hidden: the pipeline escalates the
claim to a human.

The message history is append-only: assistant turns (including thinking blocks) are sent
back exactly as received.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ValidationError

from aip.agents.schema import output_schema
from aip.agents.toolbox import Toolbox
from aip.llm.cache import ResponseCache, cache_key
from aip.llm.gateway import Effort, LLMError, LLMGateway
from aip.llm.masking import Masker
from aip.llm.pricing import Usage

CACHE_TTL_S = 7 * 24 * 3600


@dataclass(frozen=True)
class AgentSpec:
    name: str
    version: str
    system: str
    output: type[BaseModel]
    effort: Effort
    tools: frozenset[str] = frozenset()
    max_turns: int = 8
    max_tool_calls: int = 12
    timeout_s: float = 240
    max_tokens: int = 16000
    # Cache only agents without tools: their answer depends on the input alone.
    cacheable: bool = False

    @property
    def agent_id(self) -> str:
        return f"{self.name}@{self.version}"


@dataclass
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    is_error: bool


@dataclass
class AgentResult:
    output: BaseModel
    model: str
    usage: Usage
    cost_usd: Decimal
    latency_ms: int
    turns: int
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    cache_hit: bool = False


class AgentError(Exception):
    def __init__(self, message: str, usage: Usage | None = None, cost: Decimal | None = None):
        super().__init__(message)
        self.usage = usage or Usage()
        self.cost_usd = cost or Decimal("0")


def _text(content: list[Any]) -> str:
    return "".join(b.text for b in content if getattr(b, "type", None) == "text")


async def run_agent(
    spec: AgentSpec,
    user_content: str,
    *,
    llm: LLMGateway,
    model: str,
    masker: Masker,
    toolbox: Toolbox | None = None,
    cache: ResponseCache | None = None,
) -> AgentResult:
    started = time.perf_counter()
    masked_input = masker.mask(user_content)

    key = None
    if spec.cacheable and cache is not None and not spec.tools:
        key = cache_key(
            agent=spec.name,
            version=spec.version,
            model=model,
            effort=spec.effort,
            input=masked_input,
        )
        hit = await cache.get(key)
        if hit is not None:
            return AgentResult(
                output=spec.output.model_validate(masker.unmask(hit)),
                model=model,
                usage=Usage(),
                cost_usd=Decimal("0"),
                latency_ms=int((time.perf_counter() - started) * 1000),
                turns=0,
                cache_hit=True,
            )

    tools = await toolbox.definitions(spec.tools) if (toolbox and spec.tools) else []
    schema = output_schema(spec.output)
    usage = Usage()
    cost = Decimal("0")
    records: list[ToolCallRecord] = []
    messages: list[dict[str, Any]] = [{"role": "user", "content": masked_input}]
    corrections_left = 1

    async def loop() -> AgentResult:
        nonlocal cost, corrections_left
        for turn in range(1, spec.max_turns + 1):
            try:
                call = await llm.create(
                    model=model,
                    system=spec.system,
                    messages=messages,
                    effort=spec.effort,
                    tools=tools or None,
                    output_schema=schema,
                    max_tokens=spec.max_tokens,
                )
            except LLMError as exc:
                if exc.call is not None:
                    usage.add(exc.call.usage)
                    cost += exc.call.cost_usd
                raise AgentError(str(exc), usage, cost) from exc
            usage.add(call.usage)
            cost += call.cost_usd
            response = call.response
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "tool_use":
                results = []
                for block in response.content:
                    if getattr(block, "type", None) != "tool_use":
                        continue
                    args = masker.unmask(dict(block.input))
                    if block.name not in spec.tools:
                        text, is_error = (
                            f"Tool '{block.name}' is not available to this agent.",
                            True,
                        )
                    elif len(records) >= spec.max_tool_calls:
                        text, is_error = (
                            "Tool call budget exhausted; answer with what you have.",
                            True,
                        )
                    else:
                        text, is_error = await toolbox.call(block.name, args)  # type: ignore[union-attr]
                    records.append(ToolCallRecord(block.name, args, is_error))
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": masker.mask(text),
                            "is_error": is_error,
                        }
                    )
                messages.append({"role": "user", "content": results})
                continue

            raw = _text(response.content)
            try:
                data = json.loads(raw)
                output = spec.output.model_validate(masker.unmask(data))
            except (json.JSONDecodeError, ValidationError) as exc:
                if corrections_left == 0:
                    raise AgentError(f"Invalid output after retry: {exc}", usage, cost) from exc
                corrections_left -= 1
                messages.append(
                    {
                        "role": "user",
                        "content": "Your answer did not match the required schema: "
                        f"{str(exc)[:1500]}\nReply again with only the corrected JSON.",
                    }
                )
                continue

            if key is not None:
                await cache.set(key, data, CACHE_TTL_S)  # type: ignore[union-attr]
            return AgentResult(
                output=output,
                model=getattr(response, "model", None) or model,
                usage=usage,
                cost_usd=cost,
                latency_ms=int((time.perf_counter() - started) * 1000),
                turns=turn,
                tool_calls=records,
            )
        raise AgentError(f"Turn budget of {spec.max_turns} exhausted", usage, cost)

    try:
        return await asyncio.wait_for(loop(), timeout=spec.timeout_s)
    except TimeoutError as exc:
        raise AgentError(f"Timed out after {spec.timeout_s}s", usage, cost) from exc
