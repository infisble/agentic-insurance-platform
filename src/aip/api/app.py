import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from aip.api.schemas import (
    AgentRunOut,
    AllowedTransitionsOut,
    CancelRequest,
    ClaimContextOut,
    ClaimEventOut,
    ClaimOut,
    CoverageOut,
    DocumentOut,
    DocumentTextOut,
    HolderPII,
    JobOut,
    PartyOut,
    PolicyCreate,
    PolicyIssued,
    PolicyOut,
    PremiumOut,
    QuoteRequest,
    ReviewOut,
    TransitionRequest,
)
from aip.core import errors, jobs
from aip.core.claims import agent_runs, reviews
from aip.core.claims import service as claims
from aip.core.claims.state_machine import ActorType, ClaimStatus, allowed_targets
from aip.core.config import Settings
from aip.core.db import create_schema, make_engine, make_sessionmaker
from aip.core.documents import service as documents
from aip.core.party import service as parties
from aip.core.policy import service as policies
from aip.core.tariff import PremiumBreakdown

_STATUS = {
    errors.NotFound: 404,
    errors.ValidationFailed: 422,
    errors.UnderwritingReferral: 409,
    errors.InvalidTransition: 409,
    errors.ForbiddenTransition: 403,
}


def _premium(b: PremiumBreakdown) -> PremiumOut:
    return PremiumOut.model_validate({**asdict(b), "factors": [asdict(f) for f in b.factors]})


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_url, settings.sql_echo)
    maker: async_sessionmaker[AsyncSession] = make_sessionmaker(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if settings.auto_create_schema:
            await create_schema(engine)
        yield
        await engine.dispose()

    app = FastAPI(
        title="Agentic Insurance Platform — Core API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.sessionmaker = maker

    async def session() -> AsyncIterator[AsyncSession]:
        # One transaction per request: commit on success, roll back on any error.
        async with maker() as s, s.begin():
            yield s

    Session = Annotated[AsyncSession, Depends(session)]

    @app.exception_handler(errors.DomainError)
    async def domain_error(_: Request, exc: errors.DomainError) -> JSONResponse:
        status = next((code for cls, code in _STATUS.items() if isinstance(exc, cls)), 400)
        return JSONResponse(status_code=status, content={"error": exc.code, "detail": str(exc)})

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # Parties
    @app.post("/parties", response_model=PartyOut, status_code=201, tags=["parties"])
    async def create_party(data: parties.PartyCreate, s: Session):
        return await parties.create_party(s, data)

    @app.get("/parties/{party_id}", response_model=PartyOut, tags=["parties"])
    async def get_party(party_id: uuid.UUID, s: Session):
        return await parties.get_party(s, party_id)

    @app.get("/parties/{party_id}/policies", response_model=list[PolicyOut], tags=["parties"])
    async def party_policies(party_id: uuid.UUID, s: Session):
        await parties.get_party(s, party_id)
        return await policies.list_policies_for_party(s, party_id)

    # Quotes and policies
    @app.post("/quotes", response_model=PremiumOut, tags=["policies"])
    async def quote(req: QuoteRequest):
        return _premium(policies.quote(req.risk, req.start_date))

    @app.post("/policies", response_model=PolicyIssued, status_code=201, tags=["policies"])
    async def issue_policy(req: PolicyCreate, s: Session):
        policy, breakdown = await policies.issue_policy(s, req.holder_id, req.risk, req.start_date)
        return PolicyIssued(policy=PolicyOut.model_validate(policy), premium=_premium(breakdown))

    @app.get("/policies/{policy_id}", response_model=PolicyOut, tags=["policies"])
    async def get_policy(policy_id: uuid.UUID, s: Session):
        return await policies.get_policy(s, policy_id)

    @app.post("/policies/{policy_id}/cancel", response_model=PolicyOut, tags=["policies"])
    async def cancel_policy(policy_id: uuid.UUID, req: CancelRequest, s: Session):
        return await policies.cancel_policy(s, policy_id, req.on)

    # Claims
    @app.post("/claims", response_model=ClaimOut, status_code=201, tags=["claims"])
    async def report_claim(data: claims.ClaimCreate, actor: claims.Actor, s: Session):
        return await claims.report_claim(s, data, actor)

    @app.get("/claims", response_model=list[ClaimOut], tags=["claims"])
    async def list_claims(
        s: Session,
        status: ClaimStatus | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ):
        return await claims.list_claims(s, status, limit)

    @app.get("/claims/{claim_id}", response_model=ClaimOut, tags=["claims"])
    async def get_claim(claim_id: uuid.UUID, s: Session):
        return await claims.get_claim(s, claim_id)

    @app.post("/claims/{claim_id}/coverage", response_model=CoverageOut, tags=["claims"])
    async def coverage(claim_id: uuid.UUID, s: Session):
        result = await claims.evaluate_coverage(s, claim_id)
        return CoverageOut.model_validate(
            {**asdict(result), "reasons": [asdict(r) for r in result.reasons]}
        )

    @app.get(
        "/claims/{claim_id}/transitions", response_model=AllowedTransitionsOut, tags=["claims"]
    )
    async def transitions(claim_id: uuid.UUID, actor_type: ActorType, s: Session):
        claim = await claims.get_claim(s, claim_id)
        current = ClaimStatus(claim.status)
        return AllowedTransitionsOut(
            current=current, actor_type=actor_type, targets=allowed_targets(current, actor_type)
        )

    @app.post("/claims/{claim_id}/transitions", response_model=ClaimOut, tags=["claims"])
    async def transition(claim_id: uuid.UUID, req: TransitionRequest, s: Session):
        claim = await claims.transition_claim(
            s, claim_id, req.target, req.actor, req.reason, req.approved_amount, req.queue
        )
        if claim.status == ClaimStatus.RECEIVED:  # back from NEEDS_INFO: run the agents again
            await jobs.enqueue_claim(s, claim.id, debounce)
        return claim

    @app.get("/claims/{claim_id}/events", response_model=list[ClaimEventOut], tags=["claims"])
    async def events(claim_id: uuid.UUID, s: Session):
        return await claims.claim_events(s, claim_id)

    @app.get("/policies/{policy_id}/claims", response_model=list[ClaimOut], tags=["policies"])
    async def policy_claims(policy_id: uuid.UUID, s: Session):
        return await claims.list_claims_for_policy(s, policy_id)

    # Documents
    document_dir = Path(settings.document_dir)
    debounce = timedelta(seconds=settings.job_debounce_seconds)

    @app.post(
        "/claims/{claim_id}/documents",
        response_model=DocumentOut,
        status_code=201,
        tags=["documents"],
    )
    async def upload_document(claim_id: uuid.UUID, file: UploadFile, s: Session):
        data = await file.read()
        doc = await documents.add_document(
            s,
            claim_id,
            file.filename or "upload",
            file.content_type or "application/octet-stream",
            data,
            document_dir,
        )
        # Same transaction as the upload: the job exists if and only if the document does.
        claim = await claims.get_claim(s, claim_id)
        if claim.status == ClaimStatus.RECEIVED:
            await jobs.enqueue_claim(s, claim_id, debounce)
        return doc

    @app.get("/claims/{claim_id}/documents", response_model=list[DocumentOut], tags=["documents"])
    async def claim_documents(claim_id: uuid.UUID, s: Session):
        return await documents.list_documents(s, claim_id)

    @app.get("/documents/{document_id}", response_model=DocumentTextOut, tags=["documents"])
    async def get_document(document_id: uuid.UUID, s: Session):
        return await documents.get_document(s, document_id)

    @app.get("/documents/{document_id}/file", tags=["documents"])
    async def document_file(document_id: uuid.UUID, s: Session):
        doc = await documents.get_document(s, document_id)
        path = Path(doc.storage_path).resolve()
        if not path.is_relative_to(document_dir.resolve()) or not path.exists():
            raise errors.NotFound("Stored file not available")
        return FileResponse(
            path,
            media_type=doc.content_type,
            headers={"Content-Disposition": f'inline; filename="{doc.filename}"'},
        )

    # Handler feedback on agent drafts, and quality metrics
    @app.post(
        "/claims/{claim_id}/reviews", response_model=ReviewOut, status_code=201, tags=["agents"]
    )
    async def add_review(claim_id: uuid.UUID, data: reviews.ReviewCreate, s: Session):
        return await reviews.add_review(s, claim_id, data)

    @app.get("/claims/{claim_id}/reviews", response_model=list[ReviewOut], tags=["agents"])
    async def list_reviews(claim_id: uuid.UUID, s: Session):
        return await reviews.list_reviews(s, claim_id)

    @app.get("/metrics/overview", tags=["metrics"])
    async def metrics_overview(s: Session):
        return await reviews.overview(s)

    # Agent drafts and run log
    for kind in ("extraction", "triage", "summary"):

        def _make(kind: agent_runs.DraftKind):
            async def put_draft(claim_id: uuid.UUID, update: agent_runs.DraftUpdate, s: Session):
                await agent_runs.save_draft(s, claim_id, kind, update)
                return await claims.get_claim(s, claim_id)

            return put_draft

        app.put(
            f"/claims/{{claim_id}}/{kind}",
            response_model=ClaimOut,
            tags=["agents"],
            name=f"put_{kind}",
        )(_make(kind))

    @app.post(
        "/claims/{claim_id}/agent-runs",
        response_model=AgentRunOut,
        status_code=201,
        tags=["agents"],
    )
    async def record_agent_run(claim_id: uuid.UUID, data: agent_runs.AgentRunCreate, s: Session):
        return await agent_runs.record_run(s, claim_id, data)

    @app.get("/claims/{claim_id}/agent-runs", response_model=list[AgentRunOut], tags=["agents"])
    async def list_agent_runs(claim_id: uuid.UUID, s: Session):
        return await agent_runs.list_runs(s, claim_id)

    # Job queue (ADR 0004). Workers lease jobs over HTTP, like every other caller of the core.
    @app.post("/claims/{claim_id}/process", response_model=JobOut, status_code=202, tags=["jobs"])
    async def process_claim(claim_id: uuid.UUID, s: Session):
        claim = await claims.get_claim(s, claim_id)
        if claim.status != ClaimStatus.RECEIVED:
            raise errors.ValidationFailed(f"Only RECEIVED claims are processed, not {claim.status}")
        return await jobs.enqueue_claim(s, claim_id)

    @app.get("/jobs", response_model=list[JobOut], tags=["jobs"])
    async def list_jobs(
        s: Session,
        status: jobs.JobStatus | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ):
        return await jobs.list_jobs(s, status, limit)

    @app.get("/jobs/stats", tags=["jobs"])
    async def job_stats(s: Session) -> dict[str, int]:
        return await jobs.stats(s)

    @app.post("/internal/jobs/lease", response_model=JobOut | None, tags=["internal"])
    async def lease_job(req: jobs.LeaseRequest, s: Session):
        return await jobs.lease_next(s, req)

    @app.post("/internal/jobs/{job_id}/complete", response_model=JobOut, tags=["internal"])
    async def complete_job(job_id: uuid.UUID, res: jobs.JobResult, s: Session):
        return await jobs.complete(s, job_id, res)

    @app.post("/internal/jobs/{job_id}/fail", response_model=JobOut, tags=["internal"])
    async def fail_job(job_id: uuid.UUID, res: jobs.JobResult, s: Session):
        return await jobs.fail(s, job_id, res)

    @app.post("/internal/jobs/sweep", tags=["internal"])
    async def sweep_jobs(s: Session) -> dict[str, int]:
        return await jobs.sweep(s)

    @app.get(
        "/internal/claims/{claim_id}/context", response_model=ClaimContextOut, tags=["internal"]
    )
    async def claim_context(claim_id: uuid.UUID, s: Session):
        claim = await claims.get_claim(s, claim_id)
        policy = await policies.get_policy(s, claim.policy_id)
        holder = await parties.get_party(s, policy.holder_id)
        return ClaimContextOut(
            claim=ClaimOut.model_validate(claim),
            policy=PolicyOut.model_validate(policy),
            holder=HolderPII.model_validate(holder),
            documents=[
                DocumentOut.model_validate(d) for d in await documents.list_documents(s, claim_id)
            ],
        )

    return app


app = create_app()
