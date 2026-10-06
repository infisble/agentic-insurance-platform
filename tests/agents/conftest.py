import io
import random
from contextlib import asynccontextmanager
from datetime import date

import httpx
from faker import Faker
from mcp import Client
from pypdf import PdfReader

from aip.api.app import create_app
from aip.core.config import Settings
from aip.mcp.core_client import CoreClient
from aip.mcp.server import build_server
from aip.seed.__main__ import build_documents
from aip.seed.documents import generate_document
from aip.seed.generator import generate


@asynccontextmanager
async def open_stack(tmp_path):
    """Core API + MCP server in process. A context manager rather than a fixture: the MCP
    client's task group must be entered and exited in the same task as the test."""
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:", document_dir=str(tmp_path / "docs")
    )
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://core") as http,
    ):
        core = CoreClient(http)
        async with Client(build_server(core)) as mcp:
            yield http, core, mcp


async def seed_claims(
    http: httpx.AsyncClient, n_parties: int = 6, typo_in_first: bool = False
) -> list[dict]:
    """Create claims through the API, each with its generated PDF. Returns the docs' labels
    joined with claim ids and the holder's PII."""
    ds = generate(seed=5, n_parties=n_parties)
    docs = {d.claim_key: d for d in build_documents(ds, 5)}
    parties = {p["key"]: p for p in ds.parties}
    policies = {p["key"]: p for p in ds.policies}
    out = []
    for c in ds.claims:
        pol = policies[c["policy"]]
        party = parties[pol["holder"]]
        r = await http.post(
            "/parties", json={k: v for k, v in party.items() if k not in ("key", "iban")}
        )
        holder_id = r.json()["id"]
        r = await http.post(
            "/policies",
            json={"holder_id": holder_id, "risk": pol["risk"], "start_date": pol["start_date"]},
        )
        policy = r.json()["policy"]
        r = await http.post(
            "/claims",
            json={
                "data": {
                    "policy_id": policy["id"],
                    "peril": c["peril"],
                    "event_date": c["event_date"],
                    "description": c["description"],
                    "claimed_amount": c["claimed_amount"],
                },
                "actor": {"type": "customer", "id": "portal"},
            },
        )
        claim = r.json()
        # Regenerate the document with the real (randomly assigned) policy number.
        written_number = policy["number"]
        if typo_in_first and not out:
            written_number = written_number[:-1] + ("0" if written_number[-1] != "0" else "1")
        doc = generate_document(
            c,
            party,
            written_number,
            random.Random(c["key"]),
            Faker("sk_SK" if c["language"] == "sk" else "de_AT"),
        )
        r = await http.post(
            f"/claims/{claim['id']}/documents",
            files={"file": (doc.filename, doc.pdf, "application/pdf")},
        )
        assert r.status_code == 201, r.text
        text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(doc.pdf)).pages)
        out.append(
            {"claim": claim, "policy": policy, "party": party, "label": doc.label, "text": text}
        )
    assert docs  # dataset produced documents
    return out


TODAY = date.today()
