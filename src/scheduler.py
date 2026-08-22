"""Scheduled Executor — EDD Step 5.

Implements the confirm-then-act pattern for scheduled follow-ups:
before acting on a scheduled job, re-read the current entity state.
If the state is already terminal (Paid, Recovered, Exhausted), the
follow-up is a no-op (action_type: "no_op_race_skip"), not a duplicate
action. This prevents the race condition described in SPEC §6.7.

The scheduler is a simple in-memory delayed-job check (a list keyed by
trigger time, polled on a loop) — deliberately not a standalone
scheduling service, per SPEC §6.3.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
import uuid

from store import (
    append_audit_log,
    get_invoice_status,
    record_message_sent,
    schedule_job,
)


# Terminal states where no further action should be taken
TERMINAL_STATES = {"Paid", "Recovered", "Exhausted", "Escalated_Human"}


def run_scheduled_followup(entity_id: str) -> dict[str, Any]:
    """Execute a scheduled follow-up with confirm-then-act check.

    EDD §6.1 Test 5: if the entity is already in a terminal state,
    return no_op_race_skip and send zero messages.

    Args:
        entity_id: The invoice or payment event ID to follow up on.

    Returns:
        A RecoveryAction dict describing what was done.
    """
    # Confirm-then-act: read current state immediately before acting
    current_status = get_invoice_status(entity_id)

    action_id = str(uuid.uuid4())

    if current_status in TERMINAL_STATES:
        # Race detected: payment/resolution arrived before follow-up fired
        action = {
            "action_id": action_id,
            "related_entity_id": entity_id,
            "action_type": "no_op_race_skip",
            "outcome": "skipped",
            "policy_rule_applied": "confirm_then_act_already_resolved",
        }

        append_audit_log({
            "log_id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": "scheduler",
            "trigger_input": {"entity_id": entity_id, "scheduled_action": "followup"},
            "decision": None,
            "resulting_action_id": action_id,
            "outcome": "skipped_race_detected_already_paid",
            "idempotency_key": None,
        })

        return action

    # Entity still pending — proceed with reminder/escalation
    action = {
        "action_id": action_id,
        "related_entity_id": entity_id,
        "action_type": "reminder",
        "outcome": "pending",
        "policy_rule_applied": "scheduled_followup_send_reminder",
    }

    # Send the reminder message
    record_message_sent(entity_id)

    append_audit_log({
        "log_id": str(uuid.uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "actor": "scheduler",
        "trigger_input": {"entity_id": entity_id, "scheduled_action": "followup"},
        "decision": {"action": "send_reminder"},
        "resulting_action_id": action_id,
        "outcome": "reminder_sent",
        "idempotency_key": None,
    })

    return action
