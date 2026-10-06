"""Test double for the Anthropic async client: same `beta.messages.create` surface, scripted
responses, and a log of every request so tests can assert what was (not) sent."""

import copy
import json
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any


def text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def tool_use(name: str, args: dict, id_: str = "tu_1") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=args)


def response(
    *blocks: SimpleNamespace,
    stop_reason: str = "end_turn",
    model: str = "claude-opus-5-5",
    input_tokens: int = 1000,
    output_tokens: int = 200,
) -> SimpleNamespace:
    return SimpleNamespace(
        content=list(blocks),
        stop_reason=stop_reason,
        stop_details=None,
        model=model,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
    )


def final_json(data: dict) -> SimpleNamespace:
    return response(text_block(json.dumps(data, ensure_ascii=False, default=str)))


class FakeAnthropic:
    def __init__(self, script: list[SimpleNamespace] | Callable[[dict], SimpleNamespace]):
        self.requests: list[dict[str, Any]] = []
        self._script = script
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    async def _create(self, **params: Any) -> SimpleNamespace:
        self.requests.append(copy.deepcopy(params))  # history is mutated by the caller later
        if callable(self._script):
            return self._script(params)
        return self._script.pop(0)

    def sent_text(self) -> str:
        """Everything that left the process, as text (for PII leak assertions)."""

        def flatten(obj: Any) -> str:
            if isinstance(obj, str):
                return obj
            if isinstance(obj, SimpleNamespace):
                return flatten(vars(obj))
            if isinstance(obj, dict):
                return " ".join(flatten(v) for v in obj.values())
            if isinstance(obj, list):
                return " ".join(flatten(v) for v in obj)
            return str(obj)

        return "\n".join(flatten(r["messages"]) + flatten(r["system"]) for r in self.requests)
