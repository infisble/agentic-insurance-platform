"""Extraction eval: field accuracy, anomaly detection and PII masking recall.

    python -m aip.evals extraction --extractor baseline             # free, deterministic
    python -m aip.evals extraction --extractor llm --limit 20       # Claude, costs tokens
    python -m aip.evals extraction --extractor llm --gate           # exit 1 below thresholds

The golden set is generated deterministically (seed), so the same documents are evaluated on
every run. The report is written to evals/reports/.
"""

import asyncio
import io
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from aip.agents import baseline
from aip.agents import extraction as extraction_agent
from aip.agents.extraction import ExtractedDocument
from aip.agents.pipeline import masker_for
from aip.agents.runtime import AgentError, run_agent
from aip.agents.validators import ClaimFacts, validate
from aip.evals.metrics import Rate, bootstrap_rate
from aip.llm.cache import MemoryCache
from aip.seed.__main__ import build_documents
from aip.seed.generator import generate

CRITICAL = ("policy_number", "event_date", "total_amount", "iban")
FIELDS = (
    *CRITICAL,
    "claimant_name",
    "issue_date",
    "document_number",
    "vendor_name",
    "doc_type",
    "language",
)
GATES = {"critical": 0.98, "overall": 0.92}


def _norm(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field in ("total_amount",):
        return Decimal(str(value)).quantize(Decimal("0.01"))
    if field in ("event_date", "issue_date"):
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    if field == "iban":
        return str(value).replace(" ", "").upper()
    return " ".join(str(value).split()).casefold()


@dataclass
class DocResult:
    file: str
    language: str
    doc_type: str
    layout: str = "form"
    field_hits: dict[str, bool] = field(default_factory=dict)
    items_ok: bool = False
    anomalies: list[str] = field(default_factory=list)
    detected: set[str] = field(default_factory=set)
    error: str | None = None
    cost_usd: Decimal = Decimal("0")
    latency_ms: int = 0


def score(doc: ExtractedDocument, label: dict) -> tuple[dict[str, bool], bool]:
    truth = {**label["fields"], "doc_type": label["doc_type"], "language": label["language"]}
    got = doc.model_dump()
    hits = {f: _norm(f, got.get(f)) == _norm(f, truth.get(f)) for f in FIELDS}
    items_ok = sorted(i.amount for i in doc.line_items) == sorted(
        Decimal(i["amount"]) for i in truth["line_items"]
    )
    return hits, items_ok


async def run(
    extractor: str,
    parties: int,
    seed: int,
    limit: int | None,
    concurrency: int,
    gateway: Any = None,
    model: str | None = None,
) -> dict[str, Any]:
    ds = generate(seed=seed, n_parties=parties)
    docs = build_documents(ds, seed)[:limit]
    policies = {p["key"]: p for p in ds.policies}
    parties_by_key = {p["key"]: p for p in ds.parties}
    claims = {c["key"]: c for c in ds.claims}
    cache = MemoryCache()
    sem = asyncio.Semaphore(concurrency)
    masking: list[tuple[int, int]] = []
    missed_pii: list[str] = []

    async def one(d) -> DocResult:
        text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(d.pdf)).pages)
        claim = claims[d.claim_key]
        policy = policies[claim["policy"]]
        party = parties_by_key[policy["holder"]]
        layout = "free-text e-mail" if d.label["variant"] == 2 else "form"
        res = DocResult(
            d.filename, d.label["language"], d.label["doc_type"], layout, anomalies=d.anomalies
        )

        masker = masker_for(party)
        masked = masker.mask(text)
        found = [p for p in d.label["pii"] if p in text]
        leaked = [p for p in found if p in masked]
        masking.append((len(found) - len(leaked), len(found)))
        missed_pii.extend(leaked)

        started = time.perf_counter()
        try:
            if extractor == "baseline":
                out = baseline.extract(text)
            else:
                async with sem:
                    result = await run_agent(
                        extraction_agent.SPEC,
                        extraction_agent.build_input(d.filename, text),
                        llm=gateway,
                        model=model,
                        masker=masker,
                        cache=cache,
                    )
                out, res.cost_usd = result.output, result.cost_usd
        except AgentError as exc:
            res.error = str(exc)[:300]
            res.cost_usd = exc.cost_usd
            return res
        res.latency_ms = int((time.perf_counter() - started) * 1000)
        res.field_hits, res.items_ok = score(out, d.label)
        start = date.fromisoformat(policy["start_date"])
        facts = ClaimFacts(
            policy["number"],
            start,
            start.replace(year=start.year + 1),
            date.fromisoformat(claim["event_date"]),
            Decimal(claim["claimed_amount"]),
        )
        res.detected = {i.code for i in validate(out, text, facts)}
        return res

    results = await asyncio.gather(*(one(d) for d in docs))
    return summarize(extractor, model, seed, results, masking, missed_pii)


def summarize(extractor, model, seed, results: list[DocResult], masking, missed_pii) -> dict:
    ok = [r for r in results if r.error is None]

    def rate(fields: tuple[str, ...], subset=None) -> Rate:
        rows = subset if subset is not None else ok
        return bootstrap_rate([(sum(r.field_hits[f] for f in fields), len(fields)) for r in rows])

    per_field = {f: rate((f,)) for f in FIELDS}
    by_lang = {lang: rate(FIELDS, [r for r in ok if r.language == lang]) for lang in ("sk", "de")}
    by_type = {
        t: rate(FIELDS, [r for r in ok if r.doc_type == t])
        for t in sorted({r.doc_type for r in ok})
    }
    by_layout = {
        lay: rate(CRITICAL, [r for r in ok if r.layout == lay])
        for lay in sorted({r.layout for r in ok})
    }
    anomalous = [r for r in ok if r.anomalies]
    detection = bootstrap_rate(
        [(sum(a in r.detected for a in r.anomalies), len(r.anomalies)) for r in anomalous]
    )
    clean = [r for r in ok if not r.anomalies]
    false_alarms = bootstrap_rate(
        [(int(bool(r.detected & {"policy_number_mismatch", "total_mismatch"})), 1) for r in clean]
    )
    return {
        "extractor": extractor,
        "model": model,
        "seed": seed,
        "documents": len(results),
        "errors": [{"file": r.file, "error": r.error} for r in results if r.error],
        "critical": rate(CRITICAL),
        "overall": rate(FIELDS),
        "line_items": bootstrap_rate([(int(r.items_ok), 1) for r in ok]),
        "per_field": per_field,
        "by_language": by_lang,
        "by_doc_type": by_type,
        "by_layout": by_layout,
        "anomaly_detection": detection,
        "false_alarms_on_clean_docs": false_alarms,
        "masking_recall": bootstrap_rate(masking),
        "masking_missed_examples": sorted(set(missed_pii))[:10],
        "cost_usd": sum((r.cost_usd for r in results), Decimal("0")),
        "mean_latency_ms": int(sum(r.latency_ms for r in ok) / len(ok)) if ok else 0,
    }


def render(s: dict) -> str:
    lines = [
        f"# Extraction eval — {s['extractor']}" + (f" ({s['model']})" if s["model"] else ""),
        "",
        f"- Generated: {datetime.now(UTC):%Y-%m-%d %H:%M} UTC, seed {s['seed']}, "
        f"{s['documents']} documents, {len(s['errors'])} errors",
        f"- Cost: ${s['cost_usd']:.4f}, mean latency {s['mean_latency_ms']} ms",
        "",
        "| Metric | Value | Gate |",
        "|---|---|---|",
        f"| Critical fields ({', '.join(CRITICAL)}) | {s['critical']} "
        f"| ≥ {GATES['critical']:.0%} |",
        f"| All fields | {s['overall']} | ≥ {GATES['overall']:.0%} |",
        f"| Line items exact | {s['line_items']} | |",
        f"| Anomaly detection (validators on extracted data) | {s['anomaly_detection']} | |",
        f"| False alarms on clean documents | {s['false_alarms_on_clean_docs']} | |",
        f"| PII masking recall | {s['masking_recall']} | |",
        "",
        "## Critical fields by layout",
        "",
        "| Layout | Critical-field accuracy |",
        "|---|---|",
        *[f"| {k} | {r} |" for k, r in s["by_layout"].items()],
        "",
        "## Per field",
        "",
        "| Field | Accuracy |",
        "|---|---|",
        *[f"| {f} | {r} |" for f, r in s["per_field"].items()],
        "",
        "## By language / document type",
        "",
        "| Slice | All-field accuracy |",
        "|---|---|",
        *[f"| {k} | {r} |" for k, r in {**s["by_language"], **s["by_doc_type"]}.items()],
        "",
        "## PII not masked (examples)",
        "",
        "Known gap: names of people other than the policyholder need NER (ADR 0012).",
        "",
        *[f"- `{x}`" for x in s["masking_missed_examples"]],
    ]
    if s["errors"]:
        lines += ["", "## Errors", "", *[f"- {e['file']}: {e['error']}" for e in s["errors"]]]
    return "\n".join(lines) + "\n"


def gate_failures(s: dict) -> list[str]:
    fails = []
    for name, threshold in GATES.items():
        if s[name].total and s[name].value < threshold:
            fails.append(f"{name} {s[name].value:.1%} < {threshold:.0%}")
    if s["errors"]:
        fails.append(f"{len(s['errors'])} documents failed")
    return fails


def write_report(s: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"extraction-{s['extractor']}" + (f"-{s['model']}" if s["model"] else "")
    path = out_dir / f"{name}.md"
    path.write_text(render(s), encoding="utf-8")
    summary = {
        k: (str(v) if isinstance(v, (Rate, Decimal)) else v)
        for k, v in s.items()
        if k not in ("per_field", "by_language", "by_doc_type", "by_layout")
    }
    (out_dir / f"{name}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path
