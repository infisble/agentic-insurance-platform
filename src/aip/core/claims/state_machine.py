"""Claim lifecycle state machine.

The transition table is the single source of truth for who may move a claim where.
Agents can move a claim forward through processing, escalate it or ask for information,
but they can never approve, reject or pay: those are human or system actions.
See docs/architecture/diagrams.md §3.
"""

from enum import StrEnum

from aip.core.errors import ForbiddenTransition, InvalidTransition


class ClaimStatus(StrEnum):
    RECEIVED = "RECEIVED"
    EXTRACTED = "EXTRACTED"
    TRIAGED = "TRIAGED"
    COVERAGE_CHECKED = "COVERAGE_CHECKED"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    NEEDS_INFO = "NEEDS_INFO"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PAID = "PAID"


class ActorType(StrEnum):
    CUSTOMER = "customer"
    HUMAN = "human"  # claims handler
    AGENT = "agent"  # LLM agent
    SYSTEM = "system"  # deterministic automation (payment confirmation, sweeper)


S = ClaimStatus
A = ActorType

_PROCESSING = frozenset({A.AGENT, A.SYSTEM})
_ESCALATE = frozenset({A.AGENT, A.SYSTEM, A.HUMAN})
_ASK = frozenset({A.AGENT, A.HUMAN})
_HUMAN = frozenset({A.HUMAN})

TRANSITIONS: dict[tuple[ClaimStatus, ClaimStatus], frozenset[ActorType]] = {
    # Forward processing
    (S.RECEIVED, S.EXTRACTED): _PROCESSING,
    (S.EXTRACTED, S.TRIAGED): _PROCESSING,
    (S.TRIAGED, S.COVERAGE_CHECKED): _PROCESSING,
    (S.COVERAGE_CHECKED, S.AWAITING_REVIEW): _PROCESSING,
    # Escalation to a human at any processing step
    (S.RECEIVED, S.AWAITING_REVIEW): _ESCALATE,
    (S.EXTRACTED, S.AWAITING_REVIEW): _ESCALATE,
    (S.TRIAGED, S.AWAITING_REVIEW): _ESCALATE,
    # Asking the customer for more information
    (S.RECEIVED, S.NEEDS_INFO): _ASK,
    (S.EXTRACTED, S.NEEDS_INFO): _ASK,
    (S.TRIAGED, S.NEEDS_INFO): _ASK,
    (S.COVERAGE_CHECKED, S.NEEDS_INFO): _ASK,
    (S.AWAITING_REVIEW, S.NEEDS_INFO): _HUMAN,
    (S.NEEDS_INFO, S.RECEIVED): frozenset({A.CUSTOMER, A.HUMAN, A.SYSTEM}),
    # Decisions
    (S.AWAITING_REVIEW, S.APPROVED): _HUMAN,
    (S.AWAITING_REVIEW, S.REJECTED): _HUMAN,
    # Payment is confirmed by the payment system, never by a person or an agent
    (S.APPROVED, S.PAID): frozenset({A.SYSTEM}),
}

TERMINAL: frozenset[ClaimStatus] = frozenset({S.PAID, S.REJECTED})
DECISIONS: frozenset[ClaimStatus] = frozenset({S.APPROVED, S.REJECTED, S.PAID})


def allowed_targets(current: ClaimStatus, actor: ActorType) -> list[ClaimStatus]:
    return [to for (frm, to), actors in TRANSITIONS.items() if frm is current and actor in actors]


def check_transition(current: ClaimStatus, target: ClaimStatus, actor: ActorType) -> None:
    actors = TRANSITIONS.get((current, target))
    if actors is None:
        raise InvalidTransition(f"No transition {current} → {target}")
    if actor not in actors:
        raise ForbiddenTransition(f"Actor '{actor}' may not perform {current} → {target}")
