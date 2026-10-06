"""Thin gateway over the Anthropic SDK.

Agents never construct API requests themselves; they call `LLMGateway.create`, which:
- sends the request with effort, optional structured-output schema and tools,
- opts into server-side refusal fallbacks where the platform supports them,
- turns refusals and truncation into typed errors,
- returns usage and cost for observability (ADR 0010).
"""

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from aip.llm.pricing import Usage, cost_usd

Effort = Literal["low", "medium", "high", "xhigh", "max"]

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(Exception):
    def __init__(self, message: str, call: "LLMCall | None" = None) -> None:
        super().__init__(message)
        self.call = call  # a refused or truncated request can still be billed


class RefusalError(LLMError):
    pass


class TruncatedError(LLMError):
    pass


@dataclass
class LLMCall:
    response: Any
    usage: Usage
    cost_usd: Decimal
    latency_ms: int


def _usage(response: Any) -> Usage:
    u = response.usage
    return Usage(
        input_tokens=getattr(u, "input_tokens", 0) or 0,
        output_tokens=getattr(u, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
    )


class LLMGateway:
    def __init__(self, client: Any, *, server_fallbacks: bool = True) -> None:
        # `client` is an anthropic.AsyncAnthropic (or AsyncAnthropicFoundry, or a test double
        # with the same `beta.messages.create` surface).
        self._client = client
        self._server_fallbacks = server_fallbacks

    async def create(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        effort: Effort,
        tools: list[dict[str, Any]] | None = None,
        output_schema: dict[str, Any] | None = None,
        max_tokens: int = 16000,
    ) -> LLMCall:
        output_config: dict[str, Any] = {"effort": effort}
        if output_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": output_schema}
        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            # Stable system prompt first, so provider prompt caching can reuse it (L1).
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "output_config": output_config,
        }
        if tools:
            params["tools"] = tools
        if self._server_fallbacks:
            params["betas"] = [FALLBACK_BETA]
            params["fallbacks"] = "default"

        started = time.perf_counter()
        response = await self._client.beta.messages.create(**params)
        latency_ms = int((time.perf_counter() - started) * 1000)

        usage = _usage(response)
        served_by = getattr(response, "model", None) or model
        call = LLMCall(response, usage, cost_usd(served_by, usage), latency_ms)
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise RefusalError(f"Model declined the request (category: {category})", call)
        if response.stop_reason == "max_tokens":
            raise TruncatedError("Output hit max_tokens; result would be incomplete", call)
        return call


def make_client(provider: str, **kwargs: Any) -> tuple[Any, bool]:
    """Returns (client, server_fallbacks_supported)."""
    if provider == "anthropic":
        from anthropic import AsyncAnthropic

        return AsyncAnthropic(**kwargs), True
    if provider == "foundry":
        # Claude on Microsoft Foundry (Azure). Server-side fallbacks are not available there;
        # a refusal surfaces as RefusalError and the claim is escalated to a human.
        from anthropic import AsyncAnthropicFoundry

        return AsyncAnthropicFoundry(**kwargs), False
    raise ValueError(f"Unknown LLM provider: {provider}")
