"""Queue worker: leases `process_claim` jobs from the core API and runs the claim pipeline.

The worker holds no state and never touches the database: leasing, retries, dead-lettering and
escalation live in the core (aip.core.jobs). Scale out by starting more workers; each one also
runs the reconciliation sweep now and then, which is safe to run concurrently.
"""

import asyncio
import contextlib
import logging
import os
import socket
import time

from aip.agents.pipeline import ClaimPipeline
from aip.mcp.core_client import CoreClient

log = logging.getLogger("aip.worker")


def default_worker_id() -> str:
    return f"worker@{socket.gethostname()}:{os.getpid()}"


class Worker:
    def __init__(
        self,
        core: CoreClient,
        pipeline: ClaimPipeline,
        *,
        worker_id: str | None = None,
        lease_seconds: int = 300,
        poll_seconds: float = 1.0,
        sweep_seconds: float = 60.0,
    ) -> None:
        self.core, self.pipeline = core, pipeline
        self.worker_id = worker_id or default_worker_id()
        self.lease_seconds, self.poll_seconds, self.sweep_seconds = (
            lease_seconds,
            poll_seconds,
            sweep_seconds,
        )
        self._last_sweep = 0.0

    async def run_once(self) -> bool:
        """Process at most one job. Returns False when the queue had nothing ready."""
        job = await self.core.lease_job(self.worker_id, self.lease_seconds)
        if job is None:
            return False
        try:
            report = await self.pipeline.process(job["claim_id"])
        except Exception as exc:  # anything the pipeline did not turn into an escalation
            log.exception("job %s failed", job["id"])
            await self.core.fail_job(job["id"], self.worker_id, f"{type(exc).__name__}: {exc}")
        else:
            log.info("job %s: %s → %s", job["id"], report.number, report.final_status)
            await self.core.complete_job(job["id"], self.worker_id)
        return True

    async def sweep_if_due(self) -> None:
        if time.monotonic() - self._last_sweep < self.sweep_seconds:
            return
        self._last_sweep = time.monotonic()
        result = await self.core.sweep_jobs()
        if any(result.values()):
            log.warning("sweep: %s", result)

    async def drain(self) -> int:
        """Process every job that is ready now, then return how many were processed."""
        n = 0
        while await self.run_once():
            n += 1
        return n

    async def run(self, stop: asyncio.Event) -> None:
        log.info("%s polling for jobs", self.worker_id)
        while not stop.is_set():
            try:
                await self.sweep_if_due()
                if await self.run_once():
                    continue
            except Exception:  # core API briefly unavailable: keep the worker alive
                log.exception("worker loop error")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.poll_seconds)
