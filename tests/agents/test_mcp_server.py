import json

from tests.agents.conftest import open_stack, seed_claims


async def call(mcp, tool, args, agent):
    return await mcp.call_tool(tool, args, meta={"aip/agent": agent})


async def test_triage_agent_can_read_claim_policy_and_documents(tmp_path):
    async with open_stack(tmp_path) as (http, _, mcp):
        seeded = (await seed_claims(http, 2))[0]
        claim_id, policy_id = seeded["claim"]["id"], seeded["policy"]["id"]

        r = await call(mcp, "get_claim", {"claim_id": claim_id}, "triage-agent@1.0")
        assert not r.is_error
        assert json.loads(r.content[0].text)["number"] == seeded["claim"]["number"]

        r = await call(mcp, "get_policy", {"policy_id": policy_id}, "triage-agent@1.0")
        assert json.loads(r.content[0].text)["product_code"] in ("MOTOR_TPL", "HOUSEHOLD")

        r = await call(mcp, "list_claim_documents", {"claim_id": claim_id}, "triage-agent@1.0")
        doc_id = json.loads(r.content[0].text)[0]["id"]
        r = await call(mcp, "get_document_text", {"document_id": doc_id}, "triage-agent@1.0")
        assert seeded["policy"]["number"] in r.content[0].text


async def test_allow_list_is_enforced_server_side(tmp_path):
    async with open_stack(tmp_path) as (http, _, mcp):
        claim_id = (await seed_claims(http, 2))[0]["claim"]["id"]
        for agent in ("summary-agent@1.0", "unknown-agent", ""):
            r = await call(mcp, "get_claim", {"claim_id": claim_id}, agent)
            assert r.is_error and "forbidden" in r.content[0].text


async def test_tool_results_do_not_expose_holder_pii(tmp_path):
    async with open_stack(tmp_path) as (http, _, mcp):
        seeded = (await seed_claims(http, 2))[0]
        r = await call(mcp, "get_claim", {"claim_id": seeded["claim"]["id"]}, "handler-assistant")
        text = r.content[0].text
        assert seeded["party"]["last_name"] not in text
        assert "national_id" not in text


async def test_no_tool_can_decide_or_pay(tmp_path):
    async with open_stack(tmp_path) as (_, _, mcp):
        names = {t.name for t in (await mcp.list_tools()).tools}
        assert not any(w in n for n in names for w in ("approve", "reject", "pay", "transition"))


async def test_core_errors_become_tool_errors(tmp_path):
    async with open_stack(tmp_path) as (_, _, mcp):
        r = await call(
            mcp,
            "get_claim",
            {"claim_id": "00000000-0000-0000-0000-000000000000"},
            "handler-assistant",
        )
        assert r.is_error and "404" in r.content[0].text
