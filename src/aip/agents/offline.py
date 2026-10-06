"""Rule-based stand-ins for the triage and summary agents (offline mode, no API key).

They make the pipeline runnable end to end in tests and demos, and they are an honest
baseline: whatever the LLM agents add must be visible against these.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from aip.agents.summary import HandlerSummary, Recommendation
from aip.agents.triage import Complexity, Queue, TriageResult
from aip.core.products import Peril, ProductCode, get_product


def triage(claim: dict[str, Any], policy: dict[str, Any], issues: list[dict]) -> TriageResult:
    amount = Decimal(claim["claimed_amount"])
    product = get_product(ProductCode(policy["product_code"]))
    errors = [i for i in issues if i["severity"] == "error"]
    signals = []
    days_after_start = (
        date.fromisoformat(claim["event_date"]) - date.fromisoformat(policy["start_date"])
    ).days
    if 0 <= days_after_start <= 14:
        signals.append(f"Udalosť {days_after_start} dní po začiatku poistenia")
    signals += [i["message"] for i in errors if i["code"] in ("total_mismatch",)]

    if signals:
        queue, complexity = Queue.FRAUD_REVIEW, Complexity.COMPLEX
    elif amount > product.auto_limit or claim["peril"] == Peril.MOTOR_TP_INJURY:
        queue, complexity = Queue.SENIOR, Complexity.COMPLEX
    elif errors or amount > Decimal("1500"):
        queue, complexity = Queue.STANDARD, Complexity.STANDARD
    else:
        queue, complexity = Queue.FAST_TRACK, Complexity.SIMPLE
    return TriageResult(
        peril=Peril(claim["peril"]),
        peril_matches_reported=True,
        complexity=complexity,
        queue=queue,
        fraud_signals=signals,
        missing_information=[i["message"] for i in errors],
        rationale=f"Pravidlové zaradenie: suma {amount} EUR, {len(errors)} chýb vo validácii.",
    )


def summary(case: dict[str, Any]) -> HandlerSummary:
    coverage = case["coverage"]
    decision = coverage["decision"]
    claim = case["claim"]
    if decision == "NOT_COVERED":
        rec = Recommendation.REJECT
    elif decision == "REFER" or case["triage"]["queue"] in ("senior", "fraud_review"):
        rec = Recommendation.REFER_SENIOR
    elif case["issues"]:
        rec = Recommendation.REQUEST_INFORMATION
    else:
        rec = Recommendation.APPROVE
    reasons = "; ".join(f"{r['message']} ({r['clause']})" for r in coverage["reasons"])
    greeting = "Dobrý deň" if case["language"] == "sk" else "Guten Tag"
    body = (
        "ďakujeme za nahlásenie poistnej udalosti, posudzujeme ju."
        if case["language"] == "sk"
        else "vielen Dank für Ihre Schadenmeldung, wir prüfen sie."
    )
    return HandlerSummary(
        summary_sk=(
            f"Poistná udalosť {claim['number']} ({claim['peril']}) zo dňa {claim['event_date']}, "
            f"nárokovaná suma {claim['claimed_amount']} EUR. Výsledok krytia: {decision}, "
            f"navrhované plnenie {coverage['payable_amount']} EUR."
        ),
        key_facts=[f"Krytie: {decision}", f"Fronta: {case['triage']['queue']}"],
        open_questions=[i["message"] for i in case["issues"]],
        recommendation=rec,
        recommendation_rationale=reasons,
        draft_customer_message=f"{greeting}, {body}",
    )
