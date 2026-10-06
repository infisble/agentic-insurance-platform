import json

from tests.agents.conftest import open_stack, seed_claims
from tests.agents.fakes import FakeAnthropic, final_json, response, tool_use

from aip.agents import baseline
from aip.agents.pipeline import ClaimPipeline
from aip.llm.cache import MemoryCache
from aip.llm.gateway import LLMGateway


async def test_offline_pipeline_brings_every_claim_to_human_review(tmp_path):
    async with open_stack(tmp_path) as (http, core, mcp):
        seeded = await seed_claims(http, 6)
        pipeline = ClaimPipeline(core, mode="offline", mcp=mcp)
        for s in seeded:
            report = await pipeline.process(s["claim"]["id"])
            assert report.final_status == "AWAITING_REVIEW", report
            claim = await core.get_claim(s["claim"]["id"])
            assert claim["extraction"] and claim["triage"] and claim["summary"]
            assert claim["approved_amount"] is None  # nothing was decided

        events = (await http.get(f"/claims/{seeded[0]['claim']['id']}/events")).json()
        assert [e["to_status"] for e in events] == [
            "RECEIVED",
            "EXTRACTED",
            "TRIAGED",
            "COVERAGE_CHECKED",
            "AWAITING_REVIEW",
        ]


async def test_pipeline_skips_claims_not_in_received(tmp_path):
    async with open_stack(tmp_path) as (http, core, mcp):
        claim_id = (await seed_claims(http, 2))[0]["claim"]["id"]
        pipeline = ClaimPipeline(core, mode="offline", mcp=mcp)
        await pipeline.process(claim_id)
        again = await pipeline.process(claim_id)
        assert again.steps[0].status == "skipped"


def scripted_claude(policy_id_holder: dict):
    """Behaves like the three agents: extraction answers from the (masked) document, triage
    calls an MCP tool first, summary answers directly."""

    def respond(params):
        system = params["system"][0]["text"]
        messages = params["messages"]
        if system.startswith("You extract"):
            text = messages[0]["content"]
            doc = baseline.extract(text)  # works on masked text, like a model would
            return final_json(doc.model_dump(mode="json"))
        if system.startswith("You triage"):
            if len(messages) == 1:
                return response(
                    tool_use("get_policy", {"policy_id": policy_id_holder["id"]}),
                    stop_reason="tool_use",
                )
            return final_json(
                {
                    "peril": "WATER_LEAK",
                    "peril_matches_reported": True,
                    "complexity": "simple",
                    "queue": "fast_track",
                    "fraud_signals": [],
                    "missing_information": [],
                    "rationale": "Jednoduchý prípad.",
                }
            )
        return final_json(
            {
                "summary_sk": "Zhrnutie <PERSON_1>.",
                "key_facts": ["a"],
                "open_questions": [],
                "recommendation": "approve",
                "recommendation_rationale": "Krytie potvrdené.",
                "draft_customer_message": "Dobrý deň, <PERSON_1>.",
            }
        )

    return respond


async def test_llm_pipeline_end_to_end_with_scripted_model(tmp_path):
    async with open_stack(tmp_path) as (http, core, mcp):
        s = (await seed_claims(http, 3))[0]
        holder = s["party"]
        fake = FakeAnthropic(scripted_claude({"id": s["policy"]["id"]}))
        pipeline = ClaimPipeline(
            core, mode="llm", llm=LLMGateway(fake), mcp=mcp, cache=MemoryCache()
        )

        report = await pipeline.process(s["claim"]["id"])
        assert report.final_status == "AWAITING_REVIEW", report
        assert [st.step for st in report.steps] == ["extraction", "triage", "coverage", "summary"]
        assert report.cost_usd > 0

        claim = await core.get_claim(s["claim"]["id"])
        full_name = f"{holder['first_name']} {holder['last_name']}"
        # Names were masked on the way out and restored on the way back.
        assert claim["extraction"]["documents"][0]["data"]["claimant_name"] == full_name
        assert claim["summary"]["summary_sk"] == f"Zhrnutie {full_name}."
        sent = fake.sent_text()
        assert full_name not in sent
        if holder.get("national_id"):
            assert holder["national_id"] not in sent

        # Triage used a real MCP tool; its run was logged with tokens and cost.
        runs = (await http.get(f"/claims/{s['claim']['id']}/agent-runs")).json()
        triage_run = next(r for r in runs if r["agent"] == "triage-agent")
        assert triage_run["tool_calls"] == 1 and triage_run["turns"] == 2
        assert float(triage_run["cost_usd"]) > 0
        # Deterministic routing may override the agent's proposal.
        assert claim["triage"]["proposed_queue"] == "fast_track"
        assert claim["queue"] == claim["triage"]["final_queue"]


async def test_agent_failure_escalates_to_human_with_reason(tmp_path):
    async with open_stack(tmp_path) as (http, core, mcp):
        s = (await seed_claims(http, 2))[0]
        fake = FakeAnthropic(lambda p: response(stop_reason="refusal"))
        pipeline = ClaimPipeline(core, mode="llm", llm=LLMGateway(fake), mcp=mcp)

        report = await pipeline.process(s["claim"]["id"])
        assert report.final_status == "AWAITING_REVIEW"
        assert report.escalated
        events = (await http.get(f"/claims/{s['claim']['id']}/events")).json()
        assert events[-1]["actor_type"] == "system"
        assert "extraction-agent failed" in events[-1]["reason"]
        runs = (await http.get(f"/claims/{s['claim']['id']}/agent-runs")).json()
        assert runs[0]["status"] == "failed"


async def test_extraction_flags_document_anomalies(tmp_path):
    """A policy-number typo in the document must surface as a validation issue."""
    async with open_stack(tmp_path) as (http, core, mcp):
        flagged = (await seed_claims(http, 2, typo_in_first=True))[:1]
        pipeline = ClaimPipeline(core, mode="offline", mcp=mcp)
        for s in flagged:
            await pipeline.process(s["claim"]["id"])
            claim = await core.get_claim(s["claim"]["id"])
            issues = claim["extraction"]["documents"][0]["issues"]
            assert "policy_number_mismatch" in {i["code"] for i in issues}, json.dumps(issues)
