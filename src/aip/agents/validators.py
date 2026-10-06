"""Deterministic checks on extracted data.

The most damaging LLM errors are wrong numbers and dates. These checks catch them for free
and give the handler a concrete reason to look (ADR 0007).
"""

import re
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from aip.agents.extraction import ExtractedDocument
from aip.core.identifiers import is_valid_iban

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Issue:
    code: str
    field: str
    severity: Severity
    message: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ClaimFacts:
    policy_number: str
    policy_start: date
    policy_end: date
    event_date: date
    claimed_amount: Decimal


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def validate(doc: ExtractedDocument, text: str, facts: ClaimFacts) -> list[Issue]:
    issues: list[Issue] = []
    today = date.today()

    if doc.iban and not is_valid_iban(doc.iban):
        issues.append(Issue("iban_checksum", "iban", "error", f"IBAN {doc.iban} fails mod-97"))

    if doc.total_amount is not None and doc.line_items:
        items_sum = sum((i.amount for i in doc.line_items), Decimal("0"))
        if abs(items_sum - doc.total_amount) > Decimal("0.01"):
            issues.append(
                Issue(
                    "total_mismatch",
                    "total_amount",
                    "error",
                    f"Line items sum to {items_sum}, total says {doc.total_amount}",
                )
            )

    if doc.event_date is not None:
        if doc.event_date > today:
            issues.append(Issue("event_in_future", "event_date", "error", "Event date in future"))
        elif not facts.policy_start <= doc.event_date <= facts.policy_end:
            issues.append(
                Issue(
                    "event_outside_policy",
                    "event_date",
                    "warning",
                    f"Document event date {doc.event_date} is outside the policy period",
                )
            )
        if doc.event_date != facts.event_date:
            issues.append(
                Issue(
                    "event_date_differs",
                    "event_date",
                    "warning",
                    f"Document says {doc.event_date}, claim says {facts.event_date}",
                )
            )

    if doc.policy_number and doc.policy_number.strip() != facts.policy_number:
        issues.append(
            Issue(
                "policy_number_mismatch",
                "policy_number",
                "error",
                f"Document policy number {doc.policy_number} ≠ {facts.policy_number}",
            )
        )

    if doc.total_amount is not None and facts.claimed_amount > 0:
        diff = abs(doc.total_amount - facts.claimed_amount) / facts.claimed_amount
        if diff > Decimal("0.01"):
            issues.append(
                Issue(
                    "amount_differs_from_claim",
                    "total_amount",
                    "warning",
                    f"Document total {doc.total_amount} vs claimed {facts.claimed_amount}",
                )
            )

    # Grounding: every evidence quote must actually appear in the document.
    haystack = _norm(text)
    for ev in doc.evidence:
        if _norm(ev.quote) not in haystack:
            issues.append(
                Issue(
                    "evidence_not_found",
                    ev.field,
                    "warning",
                    f"Quote for {ev.field} not found in document text",
                )
            )
    return issues
