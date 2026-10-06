"""Run the claim pipeline.

    python -m aip.agents process --all --offline        # no API key: rules + regex baseline
    python -m aip.agents process --all --limit 3        # Claude agents (needs credentials)
    python -m aip.agents process --claim SKD-2026-1A2B3C4D
    python -m aip.agents show SKD-2026-1A2B3C4D         # what the agents produced
    python -m aip.agents worker --core-url http://localhost:8000 --offline   # queue worker

Credentials: ANTHROPIC_API_KEY (or an `ant auth login` profile). For Claude on Microsoft
Foundry: AIP_LLM_PROVIDER=foundry, AIP_FOUNDRY_RESOURCE, AIP_FOUNDRY_API_KEY.
"""

import argparse
import asyncio
import json
import logging
import sys
from decimal import Decimal

from aip.agents.pipeline import ClaimPipeline, ClaimReport
from aip.agents.stack import AgentSettings, local_stack, make_cache, make_gateway, remote_stack
from aip.agents.worker import Worker


def _print_report(reports: list[ClaimReport]) -> None:
    print(f"\n{'claim':<22}{'status':<18}{'queue':<14}{'recommendation':<22}{'cost $':>9}  steps")
    for r in reports:
        steps = ", ".join(f"{s.step}:{s.status}" for s in r.steps)
        print(
            f"{r.number:<22}{r.final_status:<18}{(r.queue or '-'):<14}"
            f"{(r.recommendation or '-'):<22}{r.cost_usd:>9.4f}  {steps}"
        )
        for s in r.steps:
            if s.status == "failed":
                print(f"{'':<22}↳ {s.step} failed: {s.detail[:160]}")
    total = sum((r.cost_usd for r in reports), Decimal("0"))
    escalated = sum(1 for r in reports if r.escalated)
    print(f"\n{len(reports)} claims, {escalated} escalated on error, total cost ${total:.4f}")


async def _find(core, ref: str) -> str | None:
    if len(ref) == 36 and ref.count("-") == 4:
        return ref
    for c in await core.list_claims():
        if c["number"] == ref:
            return c["id"]
    print(f"claim {ref!r} not found")
    return None


async def main_async(args: argparse.Namespace) -> None:
    settings = AgentSettings()
    stack = remote_stack(args.core_url, args.mcp_url) if args.core_url else local_stack()
    async with stack as (core, mcp):
        if args.command == "show":
            if (claim_id := await _find(core, args.claim)) is None:
                return
            claim = await core.get_claim(claim_id)
            out = {
                k: claim[k]
                for k in (
                    "number",
                    "status",
                    "queue",
                    "coverage",
                    "extraction",
                    "triage",
                    "summary",
                )
            }
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return

        mode = "offline" if args.offline else "llm"
        pipeline = ClaimPipeline(
            core,
            mode=mode,
            mcp=mcp,
            model=args.model or settings.llm_model,
            llm=None if args.offline else make_gateway(settings),
            cache=make_cache(settings),
        )
        if args.command == "worker":
            worker = Worker(core, pipeline, poll_seconds=args.poll)
            if args.once:
                print(f"processed {await worker.drain()} job(s)")
                return
            stop = asyncio.Event()
            try:
                await worker.run(stop)
            finally:
                stop.set()
            return
        if args.claim:
            if (claim_id := await _find(core, args.claim)) is None:
                return
            ids = [claim_id]
        else:
            ids = [c["id"] for c in await core.list_claims(status="RECEIVED")][: args.limit]
        print(
            f"processing {len(ids)} claim(s) in {mode} mode"
            + ("" if args.offline else f" with {pipeline.model}")
        )
        reports = []
        for cid in ids:
            report = await pipeline.process(cid)
            print(f"  {report.number}: {report.final_status}")
            reports.append(report)
        _print_report(reports)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    logging.basicConfig(format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("aip").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("process", help="run the pipeline on RECEIVED claims")
    p.add_argument("--claim", help="claim number or id")
    p.add_argument("--all", action="store_true")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--offline", action="store_true", help="rules instead of Claude (no API key)")
    p.add_argument("--model", help="override AIP_LLM_MODEL")
    s = sub.add_parser("show", help="print agent drafts for a claim")
    s.add_argument("claim")
    w = sub.add_parser("worker", help="process jobs from the core job queue")
    w.add_argument("--offline", action="store_true", help="rules instead of Claude (no API key)")
    w.add_argument("--model", help="override AIP_LLM_MODEL")
    w.add_argument("--once", action="store_true", help="drain ready jobs, then exit")
    w.add_argument("--poll", type=float, default=1.0, help="seconds between empty polls")
    for sp in (p, s, w):
        sp.add_argument("--core-url", help="use a running core API instead of in-process")
        sp.add_argument("--mcp-url", default="http://localhost:8766/mcp")
    args = parser.parse_args()
    if args.command == "process" and not (args.all or args.claim):
        parser.error("use --all or --claim")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
