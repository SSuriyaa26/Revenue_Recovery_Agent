"""State Machine — EDD Step 3.

Enforces legal state transitions for the Invoice/P2P lifecycle and
Payment Failure recovery lifecycle (SPEC §6.8). Illegal transitions
raise IllegalTransitionError and are audit-logged.
"""

from __future__ import annotations

from typing import Any, Optional


class IllegalTransitionError(Exception):
    """Raised when an illegal state transition is attempted.

    Per EDD §4 negative state-machine tests: illegal transitions must
    be rejected, not silently ignored. Each rejection produces an
    audit log entry tagged outcome: "rejected_illegal_transition".
    """

    def __init__(self, entity_id: str, from_state: str, to_state: str):
        self.entity_id = entity_id
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Illegal transition for {entity_id}: {from_state} → {to_state}"
        )


# --- Invoice / Promise-to-Pay lifecycle (SPEC §6.8) ---

# Legal transitions: from_state → set of legal to_states
INVOICE_LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "Open": {"P2P_Committed", "Overdue"},
    "P2P_Committed": {"Partially_Paid", "Paid", "Broken_Promise"},
    "Partially_Paid": {"Paid", "Broken_Promise"},
    "Broken_Promise": {"P2P_Committed", "Escalated_Human"},
    "Escalated_Human": {"Paid"},  # Only resolved externally
    "Paid": set(),  # Terminal — no outgoing transitions
    "Overdue": {"P2P_Committed", "Escalated_Human"},
}

# --- Payment Failure recovery lifecycle (SPEC §6.8) ---

PAYMENT_LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "Failed": {"Classified"},
    "Classified": {"Retry_Scheduled", "Alt_Channel_Sent", "Split_Offered"},
    "Retry_Scheduled": {"Recovered", "Retry_Scheduled", "Exhausted"},
    "Alt_Channel_Sent": {"Recovered"},
    "Split_Offered": {"Recovered", "Exhausted"},
    "Recovered": set(),  # Terminal
    "Exhausted": set(),  # Terminal
}

# Combined for lookup
ALL_LEGAL_TRANSITIONS: dict[str, set[str]] = {
    **INVOICE_LEGAL_TRANSITIONS,
    **PAYMENT_LEGAL_TRANSITIONS,
}


def transition(
    *,
    entity_id: str,
    from_state: str,
    to_state: str,
    context: Optional[dict[str, Any]] = None,
) -> str:
    """Attempt a state transition; raise IllegalTransitionError if illegal.

    Args:
        entity_id: ID of the entity being transitioned.
        from_state: Current state.
        to_state: Desired next state.
        context: Optional context dict (e.g., broken_promise_count for
                 guard conditions on Broken_Promise → P2P_Committed).

    Returns:
        The new state if the transition is legal.

    Raises:
        IllegalTransitionError: If the transition is not in the legal
        transition map. Per EDD §4, this must be caught and audit-logged.
    """
    context = context or {}

    legal_targets = ALL_LEGAL_TRANSITIONS.get(from_state)

    if legal_targets is None:
        # Unknown state
        raise IllegalTransitionError(entity_id, from_state, to_state)

    if to_state not in legal_targets:
        raise IllegalTransitionError(entity_id, from_state, to_state)

    # Guard conditions (SPEC §6.8, EDD §4)
    if from_state == "Broken_Promise" and to_state == "P2P_Committed":
        max_broken = context.get("max_broken_promises", 2)
        broken_count = context.get("broken_promise_count", 0)
        if broken_count >= max_broken:
            raise IllegalTransitionError(entity_id, from_state, to_state)

    return to_state
