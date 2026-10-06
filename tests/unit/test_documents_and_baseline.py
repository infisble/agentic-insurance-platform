from datetime import date
from decimal import Decimal

from pypdf import PdfReader

from aip.agents.baseline import extract
from aip.seed.__main__ import build_documents
from aip.seed.generator import generate


def _docs(n=60):
    ds = generate(seed=11, n_parties=n)
    return build_documents(ds, 11)


def _text(pdf: bytes) -> str:
    import io

    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


def test_generated_pdfs_have_extractable_text_with_diacritics():
    docs = _docs(20)
    sk = next(d for d in docs if d.label["language"] == "sk")
    text = _text(sk.pdf)
    assert sk.label["fields"]["policy_number"] in text
    assert any(ch in text for ch in "áčďéíľňóôŕšťúýž")


def test_labels_are_internally_consistent():
    for d in _docs(40):
        f = d.label["fields"]
        items = sum(Decimal(i["amount"]) for i in f["line_items"])
        if "total_mismatch" in d.anomalies:
            assert items != Decimal(f["total_amount"])
        else:
            assert items == Decimal(f["total_amount"])


def test_baseline_extractor_reads_template_documents():
    """The regex baseline should be near-perfect on our own form templates. Free-text e-mails
    are excluded on purpose: that is where the LLM has to earn its cost (see the eval)."""
    docs = _docs(60)
    hits = total = 0
    forms = [d for d in docs if d.label["variant"] != 2]
    assert len(forms) < len(docs), "dataset should include free-text e-mails"
    for d in forms:
        out = extract(_text(d.pdf))
        f = d.label["fields"]
        checks = [
            out.policy_number == f["policy_number"],
            out.total_amount == Decimal(f["total_amount"]),
            out.event_date == date.fromisoformat(f["event_date"]),
            out.iban == f["iban"],
            out.claimant_name == f["claimant_name"],
        ]
        hits += sum(checks)
        total += len(checks)
    assert hits / total >= 0.95, f"baseline accuracy {hits / total:.2%}"
