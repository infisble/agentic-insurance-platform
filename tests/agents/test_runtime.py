import pytest
from pydantic import BaseModel
from tests.agents.fakes import FakeAnthropic, final_json, response, text_block, tool_use

from aip.agents.runtime import AgentError, AgentSpec, run_agent
from aip.llm.cache import MemoryCache
from aip.llm.gateway import LLMGateway
from aip.llm.masking import Masker


class Answer(BaseModel):
    name: str
    amount: int


SPEC = AgentSpec(name="test-agent", version="1", system="sys", output=Answer, effort="low")
TOOL_SPEC = AgentSpec(
    name="test-agent",
    version="1",
    system="sys",
    output=Answer,
    effort="low",
    tools=frozenset({"lookup"}),
    max_tool_calls=2,
)


class FakeToolbox:
    def __init__(self):
        self.calls = []

    async def definitions(self, allowed):
        return [
            {"name": n, "description": "", "input_schema": {"type": "object"}}
            for n in sorted(allowed)
        ]

    async def call(self, name, arguments):
        self.calls.append((name, arguments))
        return f"record of {arguments.get('who')}: Ján Novák, tel. +421 905 111 222", False


def gateway(fake) -> LLMGateway:
    return LLMGateway(fake, server_fallbacks=True)


async def run(spec, fake, masker=None, toolbox=None, cache=None, text="Ján Novák, 120"):
    return await run_agent(
        spec,
        text,
        llm=gateway(fake),
        model="claude-opus-5-5",
        masker=masker or Masker({"PERSON": ["Ján Novák"]}),
        toolbox=toolbox,
        cache=cache,
    )


async def test_structured_answer_is_unmasked_and_validated():
    fake = FakeAnthropic([final_json({"name": "<PERSON_1>", "amount": 120})])
    result = await run(SPEC, fake)
    assert result.output == Answer(name="Ján Novák", amount=120)
    assert "Ján Novák" not in fake.sent_text()
    req = fake.requests[0]
    assert req["output_config"]["effort"] == "low"
    assert req["output_config"]["format"]["type"] == "json_schema"
    assert req["fallbacks"] == "default" and req["betas"] == ["server-side-fallback-2026-07-01"]
    assert "temperature" not in req and "tool_choice" not in req


async def test_tool_loop_unmasks_arguments_and_masks_results():
    fake = FakeAnthropic(
        [
            response(tool_use("lookup", {"who": "<PERSON_1>"}), stop_reason="tool_use"),
            final_json({"name": "<PERSON_1>", "amount": 1}),
        ]
    )
    tb = FakeToolbox()
    result = await run(TOOL_SPEC, fake, toolbox=tb)
    assert tb.calls == [("lookup", {"who": "Ján Novák"})]  # tool got the real value
    assert "+421 905 111 222" not in fake.sent_text()  # tool result was masked
    assert result.turns == 2 and len(result.tool_calls) == 1
    assert [t["name"] for t in fake.requests[0]["tools"]] == ["lookup"]


async def test_tool_outside_allow_list_is_refused():
    fake = FakeAnthropic(
        [
            response(tool_use("approve_claim", {}), stop_reason="tool_use"),
            final_json({"name": "x", "amount": 1}),
        ]
    )
    tb = FakeToolbox()
    result = await run(TOOL_SPEC, fake, toolbox=tb)
    assert tb.calls == []
    assert result.tool_calls[0].is_error
    tool_result = fake.requests[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] and "not available" in tool_result["content"]


async def test_tool_budget_is_enforced():
    looping = [
        response(tool_use("lookup", {"who": "a"}, f"t{i}"), stop_reason="tool_use")
        for i in range(3)
    ]
    fake = FakeAnthropic([*looping, final_json({"name": "x", "amount": 1})])
    tb = FakeToolbox()
    await run(TOOL_SPEC, fake, toolbox=tb)
    assert len(tb.calls) == 2  # third call answered with "budget exhausted"


async def test_invalid_output_gets_one_correction():
    fake = FakeAnthropic([final_json({"name": "x"}), final_json({"name": "x", "amount": 2})])
    result = await run(SPEC, fake)
    assert result.output.amount == 2
    assert "did not match" in fake.requests[1]["messages"][-1]["content"]


async def test_invalid_output_twice_fails():
    fake = FakeAnthropic([response(text_block("not json"))] * 2)
    with pytest.raises(AgentError, match="Invalid output"):
        await run(SPEC, fake)


async def test_turn_budget():
    spec = AgentSpec(
        name="t",
        version="1",
        system="s",
        output=Answer,
        effort="low",
        tools=frozenset({"lookup"}),
        max_turns=2,
        max_tool_calls=10,
    )
    fake = FakeAnthropic(lambda p: response(tool_use("lookup", {}), stop_reason="tool_use"))
    with pytest.raises(AgentError, match="Turn budget"):
        await run(spec, fake, toolbox=FakeToolbox())


async def test_refusal_becomes_agent_error_with_cost():
    fake = FakeAnthropic([response(stop_reason="refusal")])
    with pytest.raises(AgentError, match="declined") as exc:
        await run(SPEC, fake)
    assert exc.value.cost_usd > 0


async def test_cache_hit_skips_model_and_reidentifies_with_current_case():
    cache = MemoryCache()
    spec = AgentSpec(name="c", version="1", system="s", output=Answer, effort="low", cacheable=True)
    fake = FakeAnthropic([final_json({"name": "<PERSON_1>", "amount": 5})])
    first = await run(spec, fake, cache=cache)
    second = await run(spec, fake, cache=cache)
    assert len(fake.requests) == 1
    assert second.cache_hit and second.output == first.output
    # Same masked input from a different person → same cached tokens, their own name back.
    third = await run(
        spec, fake, cache=cache, masker=Masker({"PERSON": ["Eva Malá"]}), text="Eva Malá, 120"
    )
    assert third.cache_hit and third.output.name == "Eva Malá"
