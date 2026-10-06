import uuid
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from mcp import Client
from sqlalchemy import update
from tests.agents.conftest import seed_claims

from aip.agents.pipeline import ClaimPipeline
from aip.agents.worker import Worker
from aip.api.app import create_app
from aip.core import jobs
from aip.core.claims.models import Claim
from aip.core.config import Settings
from aip.core.db import utcnow
from aip.mcp.core_client import CoreClient, CoreError
from aip.mcp.server import build_server

AGENT = {"type": "agent", "id": "extraction-agent@v1"}


@asynccontextmanager
async def open_queue_stack(tmp_path):
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        document_dir=str(tmp_path / "docs"),
        job_debounce_seconds=0,
    )
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://core") as http,
    ):
        core = CoreClient(http)
        async with Client(build_server(core)) as mcp:
            yield app, http, core, mcp


async def _set(app, model, row_id, **values):
    async with app.state.sessionmaker() as s, s.begin():
        await s.execute(update(model).where(model.id == uuid.UUID(row_id)).values(**values))


class ExplodesFor:
    def __init__(self, claim_id: str, fallback: ClaimPipeline) -> None:
        self.claim_id, self.fallback = claim_id, fallback

    async def process(self, claim_id: str):
        if claim_id == self.claim_id:
            raise RuntimeError("model provider down")
        return await self.fallback.process(claim_id)


async def test_document_upload_enqueues_and_worker_brings_claims_to_review(tmp_path):
    async with open_queue_stack(tmp_path) as (_, http, core, mcp):
        seeded = await seed_claims(http, 4)
        queued = (await http.get("/jobs", params={"status": "queued"})).json()
        assert len(queued) == len(seeded)  # one job per claim, in the upload transaction

        worker = Worker(core, ClaimPipeline(core, mode="offline", mcp=mcp), worker_id="w1")
        assert await worker.drain() == len(seeded)
        for s in seeded:
            assert (await core.get_claim(s["claim"]["id"]))["status"] == "AWAITING_REVIEW"
        stats = (await http.get("/jobs/stats")).json()
        assert stats["done"] == len(seeded) and stats["queued"] == 0


async def test_more_uploads_while_queued_do_not_duplicate_the_job(tmp_path):
    async with open_queue_stack(tmp_path) as (_, http, _core, _mcp):
        claim_id = (await seed_claims(http, 2))[0]["claim"]["id"]
        r = await http.post(
            f"/claims/{claim_id}/documents",
            files={"file": ("note.txt", "Doplnenie: faktúra v prílohe".encode(), "text/plain")},
        )
        assert r.status_code == 201
        jobs_for_claim = [j for j in (await http.get("/jobs")).json() if j["claim_id"] == claim_id]
        assert len(jobs_for_claim) == 1


async def test_failing_job_is_retried_then_dead_and_the_claim_goes_to_a_human(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(jobs, "backoff", lambda attempts: timedelta(0))
    async with open_queue_stack(tmp_path) as (_, http, core, mcp):
        seeded = await seed_claims(http, 2)
        claim_id = seeded[0]["claim"]["id"]
        pipeline = ExplodesFor(claim_id, ClaimPipeline(core, mode="offline", mcp=mcp))
        worker = Worker(core, pipeline, worker_id="w1")  # type: ignore[arg-type]
        assert await worker.drain() == len(seeded) - 1 + 3  # max_attempts for the broken one
        [job] = [j for j in (await http.get("/jobs")).json() if j["claim_id"] == claim_id]
        assert job["status"] == "dead" and job["attempts"] == 3
        assert "model provider down" in job["last_error"]

        claim = await core.get_claim(claim_id)
        assert claim["status"] == "AWAITING_REVIEW"
        events = (await http.get(f"/claims/{claim_id}/events")).json()
        assert events[-1]["actor_id"] == "job-sweeper"
        assert "failed 3×" in events[-1]["reason"]


async def test_only_the_leasing_worker_can_finish_a_job(tmp_path):
    async with open_queue_stack(tmp_path) as (_, http, core, _mcp):
        await seed_claims(http, 2)
        job = await core.lease_job("w1")
        assert job is not None and job["status"] == "running"
        try:
            await core.complete_job(job["id"], "w2")
            raise AssertionError("another worker completed a job it does not hold")
        except CoreError as e:
            assert e.status == 422
        await core.complete_job(job["id"], "w1")


async def test_sweep_recovers_jobs_from_dead_workers(tmp_path):
    async with open_queue_stack(tmp_path) as (app, http, core, _mcp):
        await seed_claims(http, 2)
        job = await core.lease_job("crashed-worker", lease_seconds=10)
        await _set(app, jobs.Job, job["id"], locked_until=utcnow() - timedelta(seconds=1))

        assert (await core.sweep_jobs())["requeued_or_dead"] == 1
        [after] = [j for j in (await http.get("/jobs")).json() if j["id"] == job["id"]]
        assert after["status"] == "queued" and "lease expired" in after["last_error"]


async def test_sweep_escalates_claims_abandoned_mid_pipeline(tmp_path):
    async with open_queue_stack(tmp_path) as (app, http, core, _mcp):
        claim_id = (await seed_claims(http, 2))[0]["claim"]["id"]
        job = await core.lease_job("w1")
        await core.complete_job(job["id"], "w1")
        await core.transition(claim_id, "EXTRACTED", AGENT["id"])
        await _set(app, Claim, claim_id, updated_at=utcnow() - timedelta(hours=1))

        assert (await core.sweep_jobs())["escalated"] >= 1
        assert (await core.get_claim(claim_id))["status"] == "AWAITING_REVIEW"


async def test_claim_back_from_needs_info_is_processed_again(tmp_path):
    async with open_queue_stack(tmp_path) as (_, http, core, mcp):
        claim_id = (await seed_claims(http, 2))[0]["claim"]["id"]
        worker = Worker(core, ClaimPipeline(core, mode="offline", mcp=mcp), worker_id="w1")
        await worker.drain()
        await core.transition(
            claim_id, "NEEDS_INFO", "handler.novak", reason="Send the invoice", actor_type="human"
        )
        await core.transition(claim_id, "RECEIVED", "portal", actor_type="customer")
        assert await worker.drain() == 1
        assert (await core.get_claim(claim_id))["status"] == "AWAITING_REVIEW"


async def test_manual_processing_only_for_received_claims(tmp_path):
    async with open_queue_stack(tmp_path) as (_, http, core, mcp):
        claim_id = (await seed_claims(http, 2))[0]["claim"]["id"]
        assert (await http.post(f"/claims/{claim_id}/process")).status_code == 202
        await Worker(core, ClaimPipeline(core, mode="offline", mcp=mcp)).drain()
        r = await http.post(f"/claims/{claim_id}/process")
        assert r.status_code == 422
