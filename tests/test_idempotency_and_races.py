"""Idempotency and Race Condition Tests — EDD §6.1, Tests 4–5.

Written BEFORE event_consumer and scheduler exist (EDD Step 4).
Must fail red on first run (ImportError).
After Step 5, must all pass green.

Per decision B2: duplicate events produce 2 audit entries total
(1 for the processed action + 1 noting "duplicate event ignored"),
not 1 — more useful for judge review.
"""

import pytest

# These imports will fail red until Step 5 implements the modules.
from event_consumer import handle_event
from scheduler import run_scheduled_followup
from store import (
    get_audit_log_count,
    get_messages_sent,
    reset_store,
    set_invoice_status,
)


@pytest.fixture(autouse=True)
def clean_store():
    """Reset the in-memory store before each test."""
    reset_store()


def test_idempotent_event_handling():
    """Test 4 — EDD §6.1.

    Sending the same (invoice_id, event_type, razorpay_event_id) twice
    must produce exactly one action and two audit log entries total:
    1. The first entry for the processed action
    2. The second entry noting "duplicate event ignored"

    Per decision B2: the legacy case table (2 entries) is authoritative
    over the executable stub's assertion (1 entry).
    """
    event = {
        "invoice_id": "INV1",
        "event_type": "payment.captured",
        "razorpay_event_id": "evt_001",
    }

    # First delivery — should process normally
    actions_first = handle_event(event)
    assert len(actions_first) == 1

    # Second delivery — duplicate, should be a no-op
    actions_second = handle_event(event)
    assert len(actions_second) == 0  # No new action

    # Per B2: 2 audit entries total (processed + duplicate-ignored)
    assert get_audit_log_count(event["razorpay_event_id"]) == 2


def test_race_confirm_before_act():
    """Test 5 — EDD §6.1.

    A scheduled follow-up that finds the invoice already Paid at
    execution time must take no action, return a no_op_race_skip action,
    and send zero messages.
    """
    # Setup: invoice already paid (payment landed before follow-up fires)
    set_invoice_status("INV2", "Paid")

    # Run the scheduled follow-up
    action = run_scheduled_followup("INV2")
    assert action["action_type"] == "no_op_race_skip"
    assert get_messages_sent("INV2") == 0


def test_race_confirm_before_act_proceeds_if_unpaid():
    """Test 5 (extension) — EDD §6.1.

    If the invoice is still P2P_Committed and unpaid when the follow-up
    fires, the normal reminder/escalation flow should proceed.
    """
    set_invoice_status("INV3", "P2P_Committed")

    action = run_scheduled_followup("INV3")
    assert action["action_type"] != "no_op_race_skip"
    assert action["action_type"] in ("reminder", "escalation")
