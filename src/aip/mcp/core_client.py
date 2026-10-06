"""Typed HTTP client for the core REST API. Used by the MCP server and the agent pipeline;
neither of them touches the database directly, so domain rules and the audit trail apply."""

from typing import Any

import httpx


class CoreError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"core API {status}: {body[:500]}")
        self.status = status


class CoreClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def _req(self, method: str, url: str, **kw: Any) -> Any:
        r = await self._http.request(method, url, **kw)
        if r.status_code >= 400:
            raise CoreError(r.status_code, r.text)
        return r.json()

    async def get_claim(self, claim_id: str) -> dict[str, Any]:
        return await self._req("GET", f"/claims/{claim_id}")

    async def list_claims(self, status: str | None = None, limit: int = 500) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return await self._req("GET", "/claims", params=params)

    async def get_policy(self, policy_id: str) -> dict[str, Any]:
        return await self._req("GET", f"/policies/{policy_id}")

    async def list_policy_claims(self, policy_id: str) -> list[dict]:
        return await self._req("GET", f"/policies/{policy_id}/claims")

    async def list_documents(self, claim_id: str) -> list[dict]:
        return await self._req("GET", f"/claims/{claim_id}/documents")

    async def get_document(self, document_id: str) -> dict[str, Any]:
        return await self._req("GET", f"/documents/{document_id}")

    async def context(self, claim_id: str) -> dict[str, Any]:
        return await self._req("GET", f"/internal/claims/{claim_id}/context")

    async def evaluate_coverage(self, claim_id: str) -> dict[str, Any]:
        return await self._req("POST", f"/claims/{claim_id}/coverage")

    async def transition(
        self,
        claim_id: str,
        target: str,
        actor_id: str,
        reason: str | None = None,
        queue: str | None = None,
        actor_type: str = "agent",
    ) -> dict[str, Any]:
        body = {"target": target, "actor": {"type": actor_type, "id": actor_id}, "reason": reason}
        if queue:
            body["queue"] = queue
        return await self._req("POST", f"/claims/{claim_id}/transitions", json=body)

    async def save_draft(self, claim_id: str, kind: str, actor_id: str, payload: dict) -> Any:
        body = {"actor": {"type": "agent", "id": actor_id}, "payload": payload}
        return await self._req("PUT", f"/claims/{claim_id}/{kind}", json=body)

    async def record_run(self, claim_id: str, run: dict[str, Any]) -> Any:
        return await self._req("POST", f"/claims/{claim_id}/agent-runs", json=run)

    # Job queue
    async def lease_job(self, worker_id: str, lease_seconds: int = 300) -> dict[str, Any] | None:
        body = {"worker_id": worker_id, "lease_seconds": lease_seconds}
        return await self._req("POST", "/internal/jobs/lease", json=body)

    async def complete_job(self, job_id: str, worker_id: str) -> Any:
        return await self._req(
            "POST", f"/internal/jobs/{job_id}/complete", json={"worker_id": worker_id}
        )

    async def fail_job(self, job_id: str, worker_id: str, error: str) -> Any:
        body = {"worker_id": worker_id, "error": error[:4000]}
        return await self._req("POST", f"/internal/jobs/{job_id}/fail", json=body)

    async def sweep_jobs(self) -> dict[str, int]:
        return await self._req("POST", "/internal/jobs/sweep")
