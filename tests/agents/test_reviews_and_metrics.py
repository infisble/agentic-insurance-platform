from tests.agents.conftest import open_stack, seed_claims

from aip.agents.pipeline import ClaimPipeline

HANDLER = {"type": "human", "id": "handler.novak"}


async def processed_claims(http, core, mcp, n_parties=4):
    seeded = await seed_claims(http, n_parties)
    pipeline = ClaimPipeline(core, mode="offline", mcp=mcp)
    for s in seeded:
        await pipeline.process(s["claim"]["id"])
    return seeded


async def test_reviews_feed_override_rate_and_corrected_fields(tmp_path):
    async with open_stack(tmp_path) as (http, core, mcp):
        seeded = await processed_claims(http, core, mcp)
        a, b = seeded[0]["claim"]["id"], seeded[1]["claim"]["id"]

        r = await http.post(
            f"/claims/{a}/reviews",
            json={"kind": "extraction", "verdict": "accept", "actor": HANDLER},
        )
        assert r.status_code == 201, r.text
        r = await http.post(
            f"/claims/{b}/reviews",
            json={
                "kind": "extraction",
                "verdict": "edit",
                "actor": HANDLER,
                "corrections": {"total_amount": {"from": "100.00", "to": "110.00"}},
            },
        )
        assert r.status_code == 201, r.text
        await http.post(
            f"/claims/{a}/reviews",
            json={
                "kind": "summary",
                "verdict": "reject",
                "actor": HANDLER,
                "comment": "Recommendation ignores the late report",
            },
        )

        m = (await http.get("/metrics/overview")).json()
        agents = {x["agent"]: x for x in m["agents"]}
        assert agents["extraction-agent"]["override_rate"] == 0.5
        assert agents["summary-agent"]["override_rate"] == 1.0
        assert agents["triage-agent"]["override_rate"] is None  # nothing reviewed yet
        assert agents["extraction-agent"]["runs"] == len(seeded)
        assert m["most_corrected_fields"] == [["total_amount", 1]]
        assert m["claims_by_status"]["AWAITING_REVIEW"] == len(seeded)


async def test_review_rules(tmp_path):
    async with open_stack(tmp_path) as (http, core, mcp):
        seeded = await seed_claims(http, 2)
        cid = seeded[0]["claim"]["id"]
        # No draft yet (pipeline not run)
        r = await http.post(
            f"/claims/{cid}/reviews",
            json={"kind": "summary", "verdict": "accept", "actor": HANDLER},
        )
        assert r.status_code == 422
        await ClaimPipeline(core, mode="offline", mcp=mcp).process(cid)
        # Agents cannot review themselves
        r = await http.post(
            f"/claims/{cid}/reviews",
            json={"kind": "summary", "verdict": "accept", "actor": {"type": "agent", "id": "x"}},
        )
        assert r.status_code == 422
        # A rejection must say why
        r = await http.post(
            f"/claims/{cid}/reviews",
            json={"kind": "summary", "verdict": "reject", "actor": HANDLER},
        )
        assert r.status_code == 422


async def test_document_file_is_served(tmp_path):
    async with open_stack(tmp_path) as (http, _, _mcp):
        cid = (await seed_claims(http, 2))[0]["claim"]["id"]
        doc = (await http.get(f"/claims/{cid}/documents")).json()[0]
        r = await http.get(f"/documents/{doc['id']}/file")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF")
