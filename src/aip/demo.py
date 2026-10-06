"""One command for a demo: fresh database → mock data with PDFs → agent pipeline → API
and a queue worker, so claims reported in the customer portal are processed live.

    python -m aip.demo                         # offline agents (no key), API on :8000
    python -m aip.demo --llm --limit 5         # first 5 claims through Claude, rest stay RECEIVED
    python -m aip.demo --db var/e2e.db --port 8100   # used by the Playwright tests

Then start the web app: cd web && npm run dev  →  http://localhost:3000 (CRM),
http://localhost:3000/portal (customer portal)
"""

import argparse
import asyncio
import logging
import shutil
from pathlib import Path

import uvicorn
from mcp import Client

from aip.agents.pipeline import ClaimPipeline
from aip.agents.stack import AgentSettings, local_stack, make_cache, make_gateway
from aip.agents.worker import Worker
from aip.api.app import create_app
from aip.core.config import Settings
from aip.mcp.core_client import CoreClient
from aip.seed.__main__ import build_documents, load
from aip.seed.generator import generate


def make_pipeline(core: CoreClient, mcp: Client, llm: bool) -> ClaimPipeline:
    agent_settings = AgentSettings()
    return ClaimPipeline(
        core,
        mode="llm" if llm else "offline",
        mcp=mcp,
        llm=make_gateway(agent_settings) if llm else None,
        model=agent_settings.llm_model,
        cache=make_cache(agent_settings),
    )


async def prepare(settings: Settings, llm: bool, limit: int | None) -> None:
    ds = generate(seed=42, n_parties=40)
    await load(ds, build_documents(ds, 42), settings)
    async with local_stack(settings) as (core, mcp):
        pipeline = make_pipeline(core, mcp, llm)
        claims = await core.list_claims(status="RECEIVED")
        for c in claims[:limit]:
            report = await pipeline.process(c["id"])
            print(f"  {report.number}: {report.final_status} (${report.cost_usd:.4f})")


async def serve(settings: Settings, port: int, llm: bool) -> None:
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
    )
    stop = asyncio.Event()
    async with local_stack(settings) as (core, mcp):
        worker = Worker(core, make_pipeline(core, mcp, llm), worker_id="demo-worker")
        task = asyncio.create_task(worker.run(stop))
        try:
            await server.serve()
        finally:
            stop.set()
            await task


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--db", default="var/demo.db")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--llm", action="store_true", help="use Claude instead of offline rules")
    parser.add_argument("--limit", type=int, help="process only the first N claims")
    args = parser.parse_args()
    logging.basicConfig(format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("aip").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    db = Path(args.db)
    docs = db.parent / f"{db.stem}-documents"
    db.unlink(missing_ok=True)
    shutil.rmtree(docs, ignore_errors=True)
    db.parent.mkdir(parents=True, exist_ok=True)
    settings = Settings(database_url=f"sqlite+aiosqlite:///{db.as_posix()}", document_dir=str(docs))

    print(f"preparing {db} ...")
    asyncio.run(prepare(settings, args.llm, args.limit))
    print(f"core API on http://localhost:{args.port}/docs, queue worker running")
    asyncio.run(serve(settings, args.port, args.llm))


if __name__ == "__main__":
    main()
