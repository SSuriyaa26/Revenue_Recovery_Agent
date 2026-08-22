"""State Machine Illegal Transition Tests — EDD §6.1 (negative state-machine tests).

The state machine must REJECT (not silently ignore) illegal transitions.
Each illegal transition must raise IllegalTransitionError and produce an
audit log entry tagged outcome: "rejected_illegal_transition".

Written BEFORE state_machine exists (EDD Step 2) — must fail red.
"""

import pytest

# These imports will fail red until Step 3 implements the module.
from state_machine import transition, IllegalTransitionError


@pytest.mark.parametrize("from_state,to_state", [
    # A human-escalated case cannot be re-automated
    ("Escalated_Human", "P2P_Committed"),
    # Terminal states are terminal
    ("Paid", "Open"),
    # Exhausted cannot go back to retry without explicit human override
    ("Exhausted", "Retry_Scheduled"),
])
def test_illegal_transition_rejected(from_state, to_state):
    """EDD §4 negative state-machine tests.

    Each illegal transition must:
    1. Raise IllegalTransitionError
    2. Produce an audit log entry with outcome 'rejected_illegal_transition'
    """
    with pytest.raises(IllegalTransitionError):
        transition(entity_id="X", from_state=from_state, to_state=to_state)
