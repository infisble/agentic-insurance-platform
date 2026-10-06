import pytest

from aip.core.claims.state_machine import (
    DECISIONS,
    TERMINAL,
    TRANSITIONS,
    ActorType,
    ClaimStatus,
    allowed_targets,
    check_transition,
)
from aip.core.errors import ForbiddenTransition, InvalidTransition

S, A = ClaimStatus, ActorType


def test_agents_can_never_decide_or_pay():
    """Governance invariant (ADR 0012): no agent edge leads to a decision or a payment."""
    for (_, target), actors in TRANSITIONS.items():
        if target in DECISIONS:
            assert A.AGENT not in actors, f"agent may reach {target}"


def test_only_humans_approve_or_reject():
    for target in (S.APPROVED, S.REJECTED):
        assert TRANSITIONS[(S.AWAITING_REVIEW, target)] == {A.HUMAN}


def test_only_system_confirms_payment():
    assert TRANSITIONS[(S.APPROVED, S.PAID)] == {A.SYSTEM}


def test_happy_path_by_agents_then_human():
    path = [
        (S.RECEIVED, S.EXTRACTED, A.AGENT),
        (S.EXTRACTED, S.TRIAGED, A.AGENT),
        (S.TRIAGED, S.COVERAGE_CHECKED, A.AGENT),
        (S.COVERAGE_CHECKED, S.AWAITING_REVIEW, A.AGENT),
        (S.AWAITING_REVIEW, S.APPROVED, A.HUMAN),
        (S.APPROVED, S.PAID, A.SYSTEM),
    ]
    for current, target, actor in path:
        check_transition(current, target, actor)


def test_agent_approval_is_forbidden():
    with pytest.raises(ForbiddenTransition):
        check_transition(S.AWAITING_REVIEW, S.APPROVED, A.AGENT)


def test_skipping_steps_is_invalid():
    with pytest.raises(InvalidTransition):
        check_transition(S.RECEIVED, S.APPROVED, A.HUMAN)


@pytest.mark.parametrize("terminal", sorted(TERMINAL))
def test_terminal_states_have_no_exits(terminal):
    for actor in A:
        assert allowed_targets(terminal, actor) == []


def test_every_non_terminal_state_is_reachable_and_can_progress():
    targets = {to for (_, to) in TRANSITIONS}
    sources = {frm for (frm, _) in TRANSITIONS}
    for status in S:
        if status is not S.RECEIVED:
            assert status in targets, f"{status} is unreachable"
        if status not in TERMINAL:
            assert status in sources, f"{status} is a dead end"


def test_allowed_targets_for_agent_on_new_claim():
    assert set(allowed_targets(S.RECEIVED, A.AGENT)) == {
        S.EXTRACTED,
        S.AWAITING_REVIEW,
        S.NEEDS_INFO,
    }
