"""Claim pipeline: deterministic orchestration of bounded agents (ADR 0003, diagrams §4).

RECEIVED → extraction → EXTRACTED → triage → TRIAGED → coverage engine → COVERAGE_CHECKED
→ summary → AWAITING_REVIEW. A human decides from there; nothing here can approve or pay.

Agents propose; this module applies deterministic routing rules on top of their proposals,
records every run (model, tokens, cost, latency), and escalates to a human on any failure.
"""

import json
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from mcp import Client

from aip.agents import baseline, offline
from aip.agents import extraction as extraction_agent
from aip.agents import summary as summary_agent
from aip.agents import triage as triage_agent
from aip.agents.runtime import AgentError, AgentResult, AgentSpec, run_agent
from aip.agents.toolbox import MCPToolbox
from aip.agents.triage import Queue, TriageResult
from aip.agents.validators import ClaimFacts, validate
from aip.llm.cache import ResponseCache
from aip.llm.gateway import LLMGateway
from aip.llm.masking import Masker
from aip.mcp.core_client import CoreClient

Mode = Literal["llm", "offline"]
PIPELINE_ID = "claims-pipeline@1.0"


@dataclass
class StepReport:
    step: str
    status: str
    detail: str = ""
    cost_usd: Decimal = Decimal("0")


@dataclass
class ClaimReport:
    claim_id: str
    number: str
    final_status: str
    queue: str | None = None
    recommendation: str | None = None
    steps: list[StepReport] = field(default_factory=list)

    @property
    def cost_usd(self) -> Decimal:
        return sum((s.cost_usd for s in self.steps), Decimal("0"))

    @property
    def escalated(self) -> bool:
        return any(s.status == "failed" for s in self.steps)


class Escalate(Exception):
    pass


def masker_for(holder: dict[str, Any]) -> Masker:
    full = " ".join(p for p in (holder.get("first_name"), holder.get("last_name")) if p)
    return Masker(
        {
            "PERSON": [full, holder.get("last_name")],
            "NATIONAL_ID": [holder.get("national_id")],
            "EMAIL": [holder.get("email")],
            "PHONE": [holder.get("phone")],
            "ADDRESS": [holder.get("street")],
        }
    )


def route(
    proposed: Queue, triage: TriageResult, coverage: dict, issues: list[dict]
) -> tuple[Queue, list[str]]:
    """Deterministic routing rules applied on top of the triage agent's proposal."""
    queue, why = proposed, []
    if triage.fraud_signals and queue is not Queue.FRAUD_REVIEW:
        queue, why = Queue.FRAUD_REVIEW, [*why, "fraud signals present → fraud_review"]
    if coverage["decision"] == "REFER" and queue in (Queue.FAST_TRACK, Queue.STANDARD):
        queue, why = Queue.SENIOR, [*why, "coverage REFER → senior"]
    if coverage["decision"] == "NOT_COVERED" and queue is Queue.FAST_TRACK:
        queue, why = Queue.STANDARD, [*why, "NOT_COVERED → standard (rejection letter needed)"]
    has_errors = any(i["severity"] == "error" for i in issues)
    if has_errors and queue is Queue.FAST_TRACK:
        queue, why = Queue.STANDARD, [*why, "validation errors → not fast_track"]
    return queue, why


class ClaimPipeline:
    def __init__(
        self,
        core: CoreClient,
        *,
        mode: Mode,
        llm: LLMGateway | None = None,
        mcp: Client | None = None,
        model: str = "claude-opus-5-5",
        cache: ResponseCache | None = None,
    ) -> None:
        if mode == "llm" and (llm is None or mcp is None):
            raise ValueError("llm mode needs an LLM gateway and an MCP client")
        self.core, self.mode, self.llm, self.mcp = core, mode, llm, mcp
        self.model, self.cache = model, cache

    async def _record(
        self,
        claim_id: str,
        spec: AgentSpec,
        result: AgentResult | None,
        err: Exception | None,
        started: float,
    ) -> Decimal:
        model = (result.model if result else self.model) if self.mode == "llm" else "rules"
        usage = result.usage if result else getattr(err, "usage", None)
        cost = result.cost_usd if result else getattr(err, "cost_usd", Decimal("0"))
        await self.core.record_run(
            claim_id,
            {
                "agent": spec.name,
                "agent_version": spec.version,
                "model": model,
                "status": "ok" if err is None else "failed",
                "turns": result.turns if result else 0,
                "tool_calls": len(result.tool_calls) if result else 0,
                "input_tokens": usage.input_tokens if usage else 0,
                "output_tokens": usage.output_tokens if usage else 0,
                "cache_read_tokens": usage.cache_read_tokens if usage else 0,
                "cost_usd": str(cost),
                "latency_ms": result.latency_ms
                if result
                else int((time.perf_counter() - started) * 1000),
                "cache_hit": bool(result and result.cache_hit),
                "error": str(err)[:2000] if err else None,
            },
        )
        return cost

    async def _run(
        self,
        claim_id: str,
        spec: AgentSpec,
        text: str,
        masker: Masker,
        report: ClaimReport,
        step: str,
    ) -> AgentResult:
        started = time.perf_counter()
        toolbox = MCPToolbox(self.mcp, spec.agent_id) if (spec.tools and self.mcp) else None
        try:
            result = await run_agent(
                spec,
                text,
                llm=self.llm,
                model=self.model,
                masker=masker,  # type: ignore[arg-type]
                toolbox=toolbox,
                cache=self.cache,
            )
        except AgentError as exc:
            cost = await self._record(claim_id, spec, None, exc, started)
            report.steps.append(StepReport(step, "failed", str(exc), cost))
            raise Escalate(f"{spec.name} failed: {exc}") from exc
        cost = await self._record(claim_id, spec, result, None, started)
        detail = f"{result.turns} turns, {len(result.tool_calls)} tool calls" + (
            ", cache hit" if result.cache_hit else ""
        )
        report.steps.append(StepReport(step, "ok", detail, cost))
        return result

    async def _offline_step(
        self, claim_id: str, spec: AgentSpec, report: ClaimReport, step: str, value: Any
    ) -> Any:
        await self.core.record_run(
            claim_id,
            {"agent": spec.name, "agent_version": spec.version, "model": "rules", "status": "ok"},
        )
        report.steps.append(StepReport(step, "ok", "rules"))
        return value

    async def process(self, claim_id: str) -> ClaimReport:
        ctx = await self.core.context(claim_id)
        claim, policy, holder = ctx["claim"], ctx["policy"], ctx["holder"]
        report = ClaimReport(claim_id, claim["number"], claim["status"])
        if claim["status"] != "RECEIVED":
            report.steps.append(StepReport("skip", "skipped", f"status is {claim['status']}"))
            return report
        masker = masker_for(holder)
        try:
            await self._pipeline(claim_id, claim, policy, holder, ctx["documents"], masker, report)
        except Escalate as exc:
            current = (await self.core.get_claim(claim_id))["status"]
            if current not in ("AWAITING_REVIEW", "NEEDS_INFO"):
                await self.core.transition(
                    claim_id,
                    "AWAITING_REVIEW",
                    PIPELINE_ID,
                    reason=str(exc)[:1900],
                    actor_type="system",
                )
        final = await self.core.get_claim(claim_id)
        report.final_status, report.queue = final["status"], final["queue"]
        if final.get("summary"):
            report.recommendation = final["summary"].get("recommendation")
        return report

    async def _pipeline(
        self,
        claim_id: str,
        claim: dict,
        policy: dict,
        holder: dict,
        documents: list[dict],
        masker: Masker,
        report: ClaimReport,
    ) -> None:
        # 1. Extraction, one document at a time, then deterministic validation.
        if not documents:
            await self.core.transition(
                claim_id,
                "NEEDS_INFO",
                PIPELINE_ID,
                reason="No documents attached",
                actor_type="system",
            )
            report.steps.append(StepReport("extraction", "needs_info", "no documents"))
            return
        facts = ClaimFacts(
            policy_number=policy["number"],
            policy_start=date.fromisoformat(policy["start_date"]),
            policy_end=date.fromisoformat(policy["end_date"]),
            event_date=date.fromisoformat(claim["event_date"]),
            claimed_amount=Decimal(claim["claimed_amount"]),
        )
        extracted, all_issues = [], []
        for doc_meta in documents:
            doc = await self.core.get_document(doc_meta["id"])
            if not doc["text"].strip():
                raise Escalate(f"Document {doc['filename']} has no text layer (OCR not wired)")
            if self.mode == "llm":
                result = await self._run(
                    claim_id,
                    extraction_agent.SPEC,
                    extraction_agent.build_input(doc["filename"], doc["text"]),
                    masker,
                    report,
                    "extraction",
                )
                data = result.output
            else:
                data = await self._offline_step(
                    claim_id,
                    extraction_agent.SPEC,
                    report,
                    "extraction",
                    baseline.extract(doc["text"]),
                )
            issues = [i.as_dict() for i in validate(data, doc["text"], facts)]  # type: ignore[arg-type]
            all_issues += issues
            extracted.append(
                {
                    "document_id": doc["id"],
                    "filename": doc["filename"],
                    "data": data.model_dump(mode="json"),
                    "issues": issues,
                }
            )
        await self.core.save_draft(
            claim_id, "extraction", extraction_agent.SPEC.agent_id, {"documents": extracted}
        )
        await self.core.transition(claim_id, "EXTRACTED", extraction_agent.SPEC.agent_id)

        # 2. Triage (tools via MCP in llm mode).
        claim_view = {
            k: claim[k]
            for k in (
                "number",
                "peril",
                "event_date",
                "reported_at",
                "claimed_amount",
                "description",
                "policy_id",
            )
        }
        if self.mode == "llm":
            result = await self._run(
                claim_id,
                triage_agent.SPEC,
                triage_agent.build_input(
                    claim_id,
                    json.dumps(claim_view, ensure_ascii=False, indent=1),
                    json.dumps([e["data"] for e in extracted], ensure_ascii=False, indent=1),
                    json.dumps(all_issues, ensure_ascii=False, indent=1),
                ),
                masker,
                report,
                "triage",
            )
            triage: TriageResult = result.output  # type: ignore[assignment]
        else:
            triage = await self._offline_step(
                claim_id,
                triage_agent.SPEC,
                report,
                "triage",
                offline.triage(claim, policy, all_issues),
            )
        await self.core.transition(
            claim_id, "TRIAGED", triage_agent.SPEC.agent_id, queue=triage.queue.value
        )

        # 3. Coverage: deterministic engine in the core, then routing rules.
        coverage = await self.core.evaluate_coverage(claim_id)
        queue, overrides = route(triage.queue, triage, coverage, all_issues)
        await self.core.save_draft(
            claim_id,
            "triage",
            triage_agent.SPEC.agent_id,
            {
                **triage.model_dump(mode="json"),
                "proposed_queue": triage.queue.value,
                "final_queue": queue.value,
                "routing_overrides": overrides,
            },
        )
        await self.core.transition(
            claim_id, "COVERAGE_CHECKED", PIPELINE_ID, queue=queue.value, actor_type="system"
        )
        report.steps.append(StepReport("coverage", "ok", coverage["decision"]))

        # 4. Summary for the handler.
        case = {
            "language": holder["language"],
            "claim": {**claim_view, "number": claim["number"]},
            "policy": {
                k: policy[k]
                for k in ("number", "product_code", "start_date", "end_date", "conditions_version")
            },
            "extraction": [e["data"] for e in extracted],
            "issues": all_issues,
            "triage": {**triage.model_dump(mode="json"), "queue": queue.value},
            "coverage": coverage,
        }
        if self.mode == "llm":
            result = await self._run(
                claim_id,
                summary_agent.SPEC,
                summary_agent.build_input(json.dumps(case, ensure_ascii=False, indent=1)),
                masker,
                report,
                "summary",
            )
            brief = result.output
        else:
            brief = await self._offline_step(
                claim_id, summary_agent.SPEC, report, "summary", offline.summary(case)
            )
        await self.core.save_draft(
            claim_id, "summary", summary_agent.SPEC.agent_id, brief.model_dump(mode="json")
        )
        await self.core.transition(
            claim_id,
            "AWAITING_REVIEW",
            summary_agent.SPEC.agent_id,
            reason="Ready for handler review",
        )
