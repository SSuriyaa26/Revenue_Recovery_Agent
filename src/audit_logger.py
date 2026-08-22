"""Audit Logger — EDD Step 7.

Structured, append-only audit log that records every money-affecting or
customer-facing action. Wired into:
- Policy Engine call paths (every check_* logs its decision)
- Event Consumer (processed events and duplicate detection)
- Scheduled Executor (follow-up execution and race-skip)
- State Machine (transitions and illegal transition rejections)

Per EDD §5.5: every state transition in §4's golden trajectories must
produce at least one Audit Log Entry. Outcome values are from a defined
set — never free-text.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional
import uuid

from store import append_audit_log


# Valid outcome values — enforced to prevent free-text outcomes
# per EDD §4's "outcome with one of the enum values" requirement
VALID_OUTCOMES = frozenset({
    "denied",
    "approved",
    "retry",
    "retry_commitment",
    "exhausted",
    "escalated",
    "state_transitioned",
    "rejected_illegal_transition",
    "duplicate_event_ignored",
    "reminder_sent",
    "payment_link_generated",
    "skipped_race_detected_already_paid",
    "recovered",
    "pending",
    "failed",
    "skipped",
    "commitment_accepted",
    "schema_validation_failed",
})


def _validate_outcome(outcome: str) -> None:
    """Raise ValueError if outcome is not in the defined set."""
    if outcome not in VALID_OUTCOMES:
        raise ValueError(
            f"Invalid outcome '{outcome}'. Must be one of: {sorted(VALID_OUTCOMES)}"
        )


class AuditLogger:
    """Structured audit logger for the revenue recovery agent.

    Each log method creates an AuditLogEntry dict matching EDD §5.5
    and appends it to the store. All methods validate the outcome
    against the defined enum set.
    """

    def log_policy_decision(
        self,
        *,
        trigger_input: Any,
        decision: Any,
        outcome: str,
        actor: str = "rule_engine",
        action_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """Log a Policy Engine decision.

        Used for discount checks, retry checks, escalation checks.
        """
        _validate_outcome(outcome)

        entry = {
            "log_id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": actor,
            "trigger_input": trigger_input,
            "decision": decision,
            "resulting_action_id": action_id,
            "outcome": outcome,
            "idempotency_key": idempotency_key,
        }
        append_audit_log(entry)
        return entry

    def log_state_transition(
        self,
        *,
        entity_id: str,
        from_state: str,
        to_state: str,
        trigger_input: Any,
        outcome: str = "state_transitioned",
        actor: str = "system",
    ) -> dict[str, Any]:
        """Log a state machine transition.

        Records both the before and after states in the decision field.
        """
        _validate_outcome(outcome)

        entry = {
            "log_id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": actor,
            "trigger_input": trigger_input,
            "decision": {
                "entity_id": entity_id,
                "from_state": from_state,
                "to_state": to_state,
            },
            "resulting_action_id": None,
            "outcome": outcome,
            "idempotency_key": None,
        }
        append_audit_log(entry)
        return entry

    def log_illegal_transition(
        self,
        *,
        entity_id: str,
        from_state: str,
        to_state: str,
        actor: str = "system",
    ) -> dict[str, Any]:
        """Log a rejected illegal state transition.

        Per EDD §4: every illegal transition must produce an audit log
        entry tagged outcome: "rejected_illegal_transition".
        """
        entry = {
            "log_id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": actor,
            "trigger_input": {
                "entity_id": entity_id,
                "attempted_from": from_state,
                "attempted_to": to_state,
            },
            "decision": {
                "entity_id": entity_id,
                "from_state": from_state,
                "to_state": to_state,
                "allowed": False,
            },
            "resulting_action_id": None,
            "outcome": "rejected_illegal_transition",
            "idempotency_key": None,
        }
        append_audit_log(entry)
        return entry

    def log_scheduled_action(
        self,
        *,
        entity_id: str,
        action_type: str,
        outcome: str,
        trigger_input: Any,
        action_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Log a scheduled action execution (or skip).

        Used for both successful follow-ups and race-detected skips.
        """
        _validate_outcome(outcome)

        entry = {
            "log_id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": "scheduler",
            "trigger_input": trigger_input,
            "decision": {"action_type": action_type},
            "resulting_action_id": action_id,
            "outcome": outcome,
            "idempotency_key": None,
        }
        append_audit_log(entry)
        return entry

    def log_duplicate_event(
        self,
        *,
        trigger_input: Any,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Log a duplicate event that was ignored.

        Per decision B2: duplicate events produce a "duplicate_event_ignored"
        audit entry for judge review.
        """
        entry = {
            "log_id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": "system",
            "trigger_input": trigger_input,
            "decision": None,
            "resulting_action_id": None,
            "outcome": "duplicate_event_ignored",
            "idempotency_key": idempotency_key,
        }
        append_audit_log(entry)
        return entry

    def log_extraction_result(
        self,
        *,
        trigger_input: Any,
        outcome: str,
        details: Optional[str] = None,
        action_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Log a perception extraction result (success or failure).

        Used when the perception gateway validates an extraction result.
        """
        _validate_outcome(outcome)

        entry = {
            "log_id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": "perception_service",
            "trigger_input": trigger_input,
            "decision": {"details": details} if details else None,
            "resulting_action_id": action_id,
            "outcome": outcome,
            "idempotency_key": None,
        }
        append_audit_log(entry)
        return entry
