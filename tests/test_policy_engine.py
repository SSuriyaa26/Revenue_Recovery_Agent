"""Guardrail Unit Tests — EDD §6.1, Tests 1–3 + Test 7 (no-network).

These tests are written BEFORE the Policy Engine exists (EDD Step 2).
They must all fail red on first run (ImportError — module doesn't exist).
After the Policy Engine is implemented (Step 3), they must all pass green.

Per decision A4: check_discount receives an explicit max_discount_pct
parameter, which will be set per-flow by the caller.
"""

import pytest

# These imports will fail red until Step 3 implements the module.
from policy_engine import check_discount, check_retry, check_escalation


class TestDiscountCapEnforced:
    """Test 1 — EDD §6.1.

    Verifies that the Policy Engine correctly enforces the discount cap.
    Boundary: requested_pct == max_pct is APPROVED (inclusive).
    Any value above max_pct is DENIED with a 3_month_split alternative.
    """

    @pytest.mark.parametrize("requested_pct,max_pct,expected_decision", [
        (15, 30, "APPROVED"),
        (30, 30, "APPROVED"),      # boundary inclusive
        (31, 30, "DENIED"),
        (100, 30, "DENIED"),
        (0, 30, "APPROVED"),
    ])
    def test_discount_cap(self, requested_pct, max_pct, expected_decision):
        result = check_discount(requested_pct=requested_pct, max_discount_pct=max_pct)
        assert result["decision"] == expected_decision
        if expected_decision == "DENIED":
            assert result["alternative_offer"]["type"] == "3_month_split"

    def test_discount_cap_p2p_default(self):
        """Per-flow test: P2P default is 30%."""
        result = check_discount(requested_pct=30, max_discount_pct=30)
        assert result["decision"] == "APPROVED"
        result = check_discount(requested_pct=31, max_discount_pct=30)
        assert result["decision"] == "DENIED"

    def test_discount_cap_payment_failure_default(self):
        """Per-flow test: Payment failure default is 20%."""
        result = check_discount(requested_pct=20, max_discount_pct=20)
        assert result["decision"] == "APPROVED"
        result = check_discount(requested_pct=21, max_discount_pct=20)
        assert result["decision"] == "DENIED"


class TestRetryCapEnforced:
    """Test 2 — EDD §6.1.

    Verifies that retry cap is enforced: attempt_count >= max_retry_count
    returns EXHAUSTED, below returns RETRY.
    """

    @pytest.mark.parametrize("attempt_count,max_retry,expected", [
        (0, 3, "RETRY"),
        (2, 3, "RETRY"),
        (3, 3, "EXHAUSTED"),
        (5, 3, "EXHAUSTED"),
    ])
    def test_retry_cap(self, attempt_count, max_retry, expected):
        result = check_retry(attempt_count=attempt_count, max_retry_count=max_retry)
        assert result["decision"] == expected


class TestEscalationStopEnforced:
    """Test 3 — EDD §6.1.

    Verifies the escalation stopping rule: broken_promise_count >=
    max_broken_promises triggers ESCALATE; below triggers RETRY_COMMITMENT.

    Per decision A5: Partially_Paid → Broken_Promise increments the
    count the same as a fully unpaid promise.
    """

    @pytest.mark.parametrize("broken_count,max_promises,expected", [
        (0, 2, "RETRY_COMMITMENT"),
        (1, 2, "RETRY_COMMITMENT"),
        (2, 2, "ESCALATE"),
        (4, 2, "ESCALATE"),
    ])
    def test_escalation_stop(self, broken_count, max_promises, expected):
        result = check_escalation(
            broken_promise_count=broken_count,
            max_broken_promises=max_promises,
        )
        assert result["decision"] == expected


def test_no_network_in_policy_engine():
    """Test 7 — EDD §6.1.

    Runs the Policy Engine inside a context that raises on any socket
    access. This structurally proves the Policy Engine is network-isolated
    — a core architectural claim (EDD §5.3, SPEC §6.7).
    """
    import socket
    original_socket = socket.socket

    def blocked_socket(*a, **kw):
        raise RuntimeError("Network access attempted inside Policy Engine")

    socket.socket = blocked_socket
    try:
        check_discount(requested_pct=50, max_discount_pct=30)
        check_retry(attempt_count=1, max_retry_count=3)
        check_escalation(broken_promise_count=1, max_broken_promises=2)
    finally:
        socket.socket = original_socket
