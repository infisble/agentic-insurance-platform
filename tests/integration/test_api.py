from datetime import date, timedelta

from httpx import AsyncClient

HUMAN = {"type": "human", "id": "handler.novak"}
AGENT = {"type": "agent", "id": "triage-agent@v1"}
CUSTOMER = {"type": "customer", "id": "portal"}

MOTOR_RISK = {
    "product": "MOTOR_TPL",
    "engine_kw": 85,
    "holder_age": 40,
    "region": "BA",
    "bonus_malus_level": 4,
}
HOUSEHOLD_RISK = {
    "product": "HOUSEHOLD",
    "sum_insured": "50000",
    "property_type": "FLAT",
    "region": "KE",
    "flood_zone": 2,
    "deductible": "100",
}


async def create_party(client: AsyncClient) -> str:
    r = await client.post(
        "/parties",
        json={
            "kind": "person",
            "first_name": "Jana",
            "last_name": "Kováčová",
            "birth_date": "1986-04-12",
            "national_id": "865412/1234",
            "email": "jana.kovacova@example.sk",
            "country": "SK",
            "language": "sk",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def issue(client: AsyncClient, risk: dict, start: date | None = None) -> dict:
    holder = await create_party(client)
    start = start or date.today() - timedelta(days=60)
    r = await client.post(
        "/policies", json={"holder_id": holder, "risk": risk, "start_date": start.isoformat()}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def report(client: AsyncClient, policy_id: str, **overrides) -> dict:
    data = {
        "policy_id": policy_id,
        "peril": "WATER_LEAK",
        "event_date": (date.today() - timedelta(days=2)).isoformat(),
        "description": "Prasknuté potrubie v kúpeľni.",
        "claimed_amount": "1200",
        **overrides,
    }
    r = await client.post("/claims", json={"data": data, "actor": CUSTOMER})
    assert r.status_code == 201, r.text
    return r.json()


async def move(client: AsyncClient, claim_id: str, target: str, actor: dict, **extra):
    return await client.post(
        f"/claims/{claim_id}/transitions", json={"target": target, "actor": actor, **extra}
    )


async def test_health(client: AsyncClient):
    assert (await client.get("/health")).json() == {"status": "ok"}


async def test_party_response_hides_national_id(client: AsyncClient):
    party_id = await create_party(client)
    body = (await client.get(f"/parties/{party_id}")).json()
    assert "national_id" not in body


async def test_quote_returns_explainable_breakdown(client: AsyncClient):
    r = await client.post("/quotes", json={"risk": MOTOR_RISK, "start_date": "2026-03-01"})
    assert r.status_code == 200
    body = r.json()
    assert body["net_premium"] == "193.44"
    assert len(body["factors"]) == 4


async def test_issue_policy_recomputes_premium(client: AsyncClient):
    """A client cannot set its own premium: extra fields are ignored, the tariff decides."""
    holder = await create_party(client)
    r = await client.post(
        "/policies",
        json={
            "holder_id": holder,
            "risk": MOTOR_RISK,
            "start_date": "2026-03-01",
            "gross_premium": "1.00",
        },
    )
    assert r.status_code == 201
    assert r.json()["policy"]["gross_premium"] == "208.92"
    assert r.json()["policy"]["end_date"] == "2027-02-28"


async def test_unknown_holder_is_404(client: AsyncClient):
    r = await client.post(
        "/policies",
        json={
            "holder_id": "00000000-0000-0000-0000-000000000000",
            "risk": MOTOR_RISK,
            "start_date": "2026-03-01",
        },
    )
    assert r.status_code == 404


async def test_underwriting_referral_is_409(client: AsyncClient):
    risk = {**HOUSEHOLD_RISK, "sum_insured": "900000"}
    r = await client.post("/quotes", json={"risk": risk, "start_date": "2026-03-01"})
    assert r.status_code == 409
    assert r.json()["error"] == "underwriting_referral"


async def test_full_claim_lifecycle_with_audit_trail(client: AsyncClient):
    policy = (await issue(client, HOUSEHOLD_RISK))["policy"]
    claim = await report(client, policy["id"])
    cid = claim["id"]
    assert claim["status"] == "RECEIVED"

    for target in ("EXTRACTED", "TRIAGED"):
        r = await move(client, cid, target, AGENT)
        assert r.status_code == 200, r.text

    cov = (await client.post(f"/claims/{cid}/coverage")).json()
    assert cov["decision"] == "COVERED"
    assert cov["payable_amount"] == "1100.00"

    for target in ("COVERAGE_CHECKED", "AWAITING_REVIEW"):
        assert (await move(client, cid, target, AGENT)).status_code == 200

    r = await move(client, cid, "APPROVED", HUMAN, approved_amount="1100")
    assert r.status_code == 200, r.text
    assert r.json()["approved_amount"] == "1100.00"

    events = (await client.get(f"/claims/{cid}/events")).json()
    assert [e["to_status"] for e in events] == [
        "RECEIVED",
        "EXTRACTED",
        "TRIAGED",
        "COVERAGE_CHECKED",
        "AWAITING_REVIEW",
        "APPROVED",
    ]
    assert events[-1]["actor_type"] == "human"
    assert [e["seq"] for e in events] == list(range(1, 7))


async def test_agent_cannot_approve(client: AsyncClient):
    policy = (await issue(client, HOUSEHOLD_RISK))["policy"]
    cid = (await report(client, policy["id"]))["id"]
    await move(client, cid, "AWAITING_REVIEW", AGENT, reason="Low extraction confidence")
    r = await move(client, cid, "APPROVED", AGENT, approved_amount="100")
    assert r.status_code == 403
    assert r.json()["error"] == "forbidden_transition"


async def test_invalid_transition_is_409(client: AsyncClient):
    policy = (await issue(client, HOUSEHOLD_RISK))["policy"]
    cid = (await report(client, policy["id"]))["id"]
    r = await move(client, cid, "PAID", HUMAN)
    assert r.status_code == 409


async def test_approval_requires_coverage_check(client: AsyncClient):
    policy = (await issue(client, HOUSEHOLD_RISK))["policy"]
    cid = (await report(client, policy["id"]))["id"]
    await move(client, cid, "AWAITING_REVIEW", HUMAN, reason="Manual handling")
    r = await move(client, cid, "APPROVED", HUMAN, approved_amount="500")
    assert r.status_code == 422


async def test_escalation_requires_reason(client: AsyncClient):
    policy = (await issue(client, HOUSEHOLD_RISK))["policy"]
    cid = (await report(client, policy["id"]))["id"]
    r = await move(client, cid, "AWAITING_REVIEW", AGENT)
    assert r.status_code == 422


async def test_failed_transition_does_not_write_audit_event(client: AsyncClient):
    policy = (await issue(client, HOUSEHOLD_RISK))["policy"]
    cid = (await report(client, policy["id"]))["id"]
    await move(client, cid, "APPROVED", AGENT)
    events = (await client.get(f"/claims/{cid}/events")).json()
    assert len(events) == 1


async def test_allowed_transitions_endpoint(client: AsyncClient):
    policy = (await issue(client, HOUSEHOLD_RISK))["policy"]
    cid = (await report(client, policy["id"]))["id"]
    r = await client.get(f"/claims/{cid}/transitions", params={"actor_type": "agent"})
    assert set(r.json()["targets"]) == {"EXTRACTED", "AWAITING_REVIEW", "NEEDS_INFO"}


async def test_event_in_future_is_rejected(client: AsyncClient):
    policy = (await issue(client, HOUSEHOLD_RISK))["policy"]
    data = {
        "policy_id": policy["id"],
        "peril": "FIRE",
        "event_date": (date.today() + timedelta(days=3)).isoformat(),
        "description": "x",
        "claimed_amount": "100",
    }
    r = await client.post("/claims", json={"data": data, "actor": CUSTOMER})
    assert r.status_code == 422


async def test_claim_after_cancellation_is_not_covered(client: AsyncClient):
    policy = (await issue(client, HOUSEHOLD_RISK, start=date.today() - timedelta(days=100)))[
        "policy"
    ]
    cancel_on = (date.today() - timedelta(days=30)).isoformat()
    r = await client.post(f"/policies/{policy['id']}/cancel", json={"on": cancel_on})
    assert r.status_code == 200
    cid = (await report(client, policy["id"]))["id"]
    cov = (await client.post(f"/claims/{cid}/coverage")).json()
    assert cov["decision"] == "NOT_COVERED"
    assert cov["reasons"][0]["code"] == "outside_policy_period"


async def test_list_claims_by_status(client: AsyncClient):
    policy = (await issue(client, HOUSEHOLD_RISK))["policy"]
    await report(client, policy["id"])
    r = await client.get("/claims", params={"status": "RECEIVED"})
    assert r.status_code == 200
    assert len(r.json()) == 1
