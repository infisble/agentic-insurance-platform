from datetime import date
from decimal import Decimal

from aip.agents.extraction import Confidence, Evidence, ExtractedDocument, LineItem
from aip.agents.schema import output_schema
from aip.agents.triage import TriageResult
from aip.agents.validators import ClaimFacts, validate
from aip.llm.pricing import Usage, cost_usd


def _walk(node, path="$"):
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


def test_output_schema_is_structured_output_compatible():
    for model in (ExtractedDocument, TriageResult):
        schema = output_schema(model)
        for path, node in _walk(schema):
            for banned in (
                "minimum",
                "maximum",
                "minLength",
                "maxLength",
                "pattern",
                "title",
                "default",
            ):
                assert banned not in node, f"{model.__name__} {path} has {banned}"
            if node.get("type") == "object" and "properties" in node:
                assert node["additionalProperties"] is False, path
                assert set(node["required"]) == set(node["properties"]), path


FACTS = ClaimFacts(
    policy_number="DOM-2026-1A2B3C4D",
    policy_start=date(2026, 1, 1),
    policy_end=date(2026, 12, 31),
    event_date=date(2026, 5, 10),
    claimed_amount=Decimal("300.00"),
)
TEXT = "Číslo poistnej zmluvy: DOM-2026-1A2B3C4D\nSpolu s DPH: 300,00 EUR"


def doc(**overrides) -> ExtractedDocument:
    base = dict(
        doc_type="invoice",
        language="sk",
        policy_number="DOM-2026-1A2B3C4D",
        claimant_name="X",
        event_date=date(2026, 5, 10),
        issue_date=None,
        vendor_name=None,
        document_number=None,
        currency="EUR",
        total_amount=Decimal("300.00"),
        iban="SK3112000000198742637541",
        line_items=[
            LineItem(description="a", amount=Decimal("100")),
            LineItem(description="b", amount=Decimal("200")),
        ],
        damage_description=None,
        evidence=[
            Evidence(
                field="total_amount", quote="Spolu s DPH: 300,00 EUR", confidence=Confidence.HIGH
            )
        ],
    )
    return ExtractedDocument(**{**base, **overrides})


def codes(issues):
    return {i.code for i in issues}


def test_clean_document_has_no_issues():
    assert validate(doc(), TEXT, FACTS) == []


def test_detects_number_and_date_problems():
    bad = doc(
        iban="SK0012000000198742637541",
        total_amount=Decimal("350.00"),
        policy_number="DOM-2026-1A2B3C4X",
        event_date=date(2026, 5, 2),
    )
    assert {
        "iban_checksum",
        "total_mismatch",
        "policy_number_mismatch",
        "event_date_differs",
        "amount_differs_from_claim",
    } <= codes(validate(bad, TEXT, FACTS))


def test_ungrounded_evidence_is_flagged():
    d = doc(evidence=[Evidence(field="iban", quote="IBAN: SK99 invented", confidence="high")])
    assert "evidence_not_found" in codes(validate(d, TEXT, FACTS))


def test_cost_uses_list_prices():
    # 1M input × $4 + 100k output × $20 / 1M = 4 + 2 = $6
    assert cost_usd("claude-opus-5-5", Usage(1_000_000, 100_000)) == Decimal("6.000000")
    assert cost_usd("unknown-model", Usage(1000, 1000)) == Decimal("0")
