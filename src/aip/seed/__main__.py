"""Generate the synthetic dataset and optionally load it into the database.

python -m aip.seed                      # write data/mock/*.json, PDFs, golden labels
python -m aip.seed --load               # also load into AIP_DATABASE_URL
"""

import argparse
import asyncio
import json
import random
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path

from faker import Faker

from aip.core.claims.service import Actor, ClaimCreate, evaluate_coverage, report_claim
from aip.core.claims.state_machine import ActorType
from aip.core.config import Settings
from aip.core.db import create_schema, make_engine, make_sessionmaker
from aip.core.documents.service import add_document
from aip.core.party.service import PartyCreate, create_party
from aip.core.policy.service import issue_policy, parse_risk
from aip.core.products import Peril
from aip.seed.documents import GeneratedDocument, generate_document
from aip.seed.generator import Dataset, generate

SEEDER = Actor(type=ActorType.SYSTEM, id="seed")


def build_documents(ds: Dataset, seed: int) -> list[GeneratedDocument]:
    rng = random.Random(seed + 1)
    fakers = {"sk": Faker("sk_SK"), "de": Faker("de_AT")}
    for f in fakers.values():
        f.seed_instance(seed + 1)
    parties = {p["key"]: p for p in ds.parties}
    policies = {p["key"]: p for p in ds.policies}
    docs = []
    for claim in ds.claims:
        policy = policies[claim["policy"]]
        party = parties[policy["holder"]]
        docs.append(
            generate_document(claim, party, policy["number"], rng, fakers[claim["language"]])
        )
    return docs


def write_files(ds: Dataset, docs: list[GeneratedDocument], out: Path, golden: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name in ("parties", "policies", "claims"):
        path = out / f"{name}.json"
        path.write_text(
            json.dumps(getattr(ds, name), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote {path} ({len(getattr(ds, name))} records)")
    doc_dir = out / "documents"
    doc_dir.mkdir(exist_ok=True)
    for d in docs:
        (doc_dir / d.filename).write_bytes(d.pdf)
    golden.mkdir(parents=True, exist_ok=True)
    labels = golden / "extraction.jsonl"
    labels.write_text(
        "".join(json.dumps(d.label, ensure_ascii=False) + "\n" for d in docs), encoding="utf-8"
    )
    anomalous = sum(1 for d in docs if d.anomalies)
    print(
        f"wrote {len(docs)} PDFs to {doc_dir} and labels to {labels} ({anomalous} with anomalies)"
    )


async def load(ds: Dataset, docs: list[GeneratedDocument], settings: Settings) -> None:
    engine = make_engine(settings.database_url)
    if settings.auto_create_schema:
        await create_schema(engine)
    maker = make_sessionmaker(engine)
    by_claim = {d.claim_key: d for d in docs}
    async with maker() as s, s.begin():
        party_ids = {}
        for p in ds.parties:
            fields = {k: v for k, v in p.items() if k not in ("key", "iban")}
            party = await create_party(s, PartyCreate.model_validate(fields))
            party_ids[p["key"]] = party.id
        policy_ids = {}
        for pol in ds.policies:
            policy, _ = await issue_policy(
                s,
                party_ids[pol["holder"]],
                parse_risk(pol["risk"]),
                date.fromisoformat(pol["start_date"]),
                number=pol["number"],
            )
            policy_ids[pol["key"]] = policy.id
        for c in ds.claims:
            claim = await report_claim(
                s,
                ClaimCreate(
                    policy_id=policy_ids[c["policy"]],
                    peril=Peril(c["peril"]),
                    event_date=date.fromisoformat(c["event_date"]),
                    description=c["description"],
                    claimed_amount=Decimal(c["claimed_amount"]),
                    channel=c["channel"],
                ),
                SEEDER,
                reported_at=datetime.combine(
                    date.fromisoformat(c["reported_date"]), time(9), tzinfo=UTC
                ),
            )
            await evaluate_coverage(s, claim.id)
            doc = by_claim[c["key"]]
            await add_document(
                s, claim.id, doc.filename, "application/pdf", doc.pdf, Path(settings.document_dir)
            )
    await engine.dispose()
    print(
        f"loaded {len(ds.parties)} parties, {len(ds.policies)} policies, "
        f"{len(ds.claims)} claims (+ documents) into {settings.database_url}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--parties", type=int, default=40)
    parser.add_argument("--out", type=Path, default=Path("data/mock"))
    parser.add_argument("--golden", type=Path, default=Path("data/golden"))
    parser.add_argument("--load", action="store_true", help="load into the database")
    args = parser.parse_args()

    ds = generate(seed=args.seed, n_parties=args.parties)
    docs = build_documents(ds, args.seed)
    write_files(ds, docs, args.out, args.golden)
    if args.load:
        asyncio.run(load(ds, docs, Settings()))


if __name__ == "__main__":
    main()
