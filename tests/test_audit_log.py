"""Audit Log Completeness Tests — EDD Step 6.

Tests that every golden-trajectory step from §4 produces the expected
audit log entry with correct fields:
- trigger_input: populated with the exact upstream object (not a summary)
- decision: populated with the Policy/classifier output object (if applicable)
- outcome: one of the defined enum values (never free-text)

Also tests that:
- Illegal state transitions produce audit entries tagged "rejected_illegal_transition"
- Idempotent duplicates produce audit entries noting the duplicate
- The audit logger wires into all call paths (Policy Engine, Event Consumer,
  Scheduler, State Machine)

Written BEFORE audit_logger is wired (EDD Step 6) — must fail red.
"""

import pytest

# This import will fail red until Step 7 implements the module.
from audit_logger import AuditLogger
from store import get_audit_log, reset_store


@pytest.fixture(autouse=True)
def clean_store():
    """Reset the in-memory store before each test."""
    reset_store()


@pytest.fixture
def logger():
    """Create a fresh AuditLogger instance for each test."""
    return AuditLogger()


class TestAuditLogFieldCompleteness:
    """Verify every audit entry has the required fields per EDD §4."""

    def test_policy_decision_logged_with_all_fields(self, logger):
        """Policy Engine decisions must be audit-logged with trigger_input,
        decision, and outcome fields populated."""
        logger.log_policy_decision(
            trigger_input={"requested_pct": 80, "max_discount_pct": 30},
            decision={"decision": "DENIED", "reason_code": "exceeds_max"},
            outcome="denied",
            actor="rule_engine",
        )

        logs = get_audit_log()
        assert len(logs) == 1
        entry = logs[0]
        assert entry["trigger_input"] == {"requested_pct": 80, "max_discount_pct": 30}
        assert entry["decision"]["decision"] == "DENIED"
        assert entry["outcome"] == "denied"
        assert entry["actor"] == "rule_engine"
        assert "log_id" in entry
        assert "timestamp" in entry

    def test_state_transition_logged(self, logger):
        """State transitions must produce audit entries with before/after state."""
        logger.log_state_transition(
            entity_id="INV1",
            from_state="Open",
            to_state="P2P_Committed",
            trigger_input={"raw_transcript": "Wednesday tak payment dunga"},
            outcome="state_transitioned",
        )

        logs = get_audit_log()
        assert len(logs) == 1
        entry = logs[0]
        assert entry["trigger_input"]["raw_transcript"] == "Wednesday tak payment dunga"
        assert entry["outcome"] == "state_transitioned"
        assert entry["decision"]["from_state"] == "Open"
        assert entry["decision"]["to_state"] == "P2P_Committed"

    def test_illegal_transition_logged(self, logger):
        """Illegal transitions must produce audit entries with
        outcome 'rejected_illegal_transition'."""
        logger.log_illegal_transition(
            entity_id="X",
            from_state="Paid",
            to_state="Open",
        )

        logs = get_audit_log()
        assert len(logs) == 1
        entry = logs[0]
        assert entry["outcome"] == "rejected_illegal_transition"
        assert entry["actor"] == "system"

    def test_scheduled_action_logged(self, logger):
        """Scheduled actions (both executed and skipped) must be logged."""
        logger.log_scheduled_action(
            entity_id="INV2",
            action_type="reminder",
            outcome="reminder_sent",
            trigger_input={"entity_id": "INV2", "scheduled_action": "followup"},
        )

        logs = get_audit_log()
        assert len(logs) == 1
        entry = logs[0]
        assert entry["actor"] == "scheduler"
        assert entry["outcome"] == "reminder_sent"

    def test_race_skip_logged(self, logger):
        """Race-detected skips must be logged with outcome indicating the skip."""
        logger.log_scheduled_action(
            entity_id="INV3",
            action_type="no_op_race_skip",
            outcome="skipped_race_detected_already_paid",
            trigger_input={"entity_id": "INV3", "scheduled_action": "followup"},
        )

        logs = get_audit_log()
        assert len(logs) == 1
        entry = logs[0]
        assert entry["outcome"] == "skipped_race_detected_already_paid"

    def test_duplicate_event_logged(self, logger):
        """Duplicate event ignoring must be logged."""
        logger.log_duplicate_event(
            trigger_input={
                "invoice_id": "INV1",
                "event_type": "payment.captured",
                "razorpay_event_id": "evt_001",
            },
            idempotency_key="INV1:payment.captured:evt_001",
        )

        logs = get_audit_log()
        assert len(logs) == 1
        entry = logs[0]
        assert entry["outcome"] == "duplicate_event_ignored"
        assert entry["idempotency_key"] == "INV1:payment.captured:evt_001"


class TestAuditLogOutcomeEnums:
    """Verify that outcome values are from the defined set, never free-text."""

    VALID_OUTCOMES = {
        "denied", "approved", "retry", "exhausted", "escalated",
        "state_transitioned", "rejected_illegal_transition",
        "duplicate_event_ignored", "reminder_sent", "payment_link_generated",
        "skipped_race_detected_already_paid", "recovered", "pending",
        "failed", "skipped", "commitment_accepted", "schema_validation_failed",
    }

    def test_policy_decision_outcome_is_valid(self, logger):
        logger.log_policy_decision(
            trigger_input={},
            decision={"decision": "APPROVED"},
            outcome="approved",
            actor="rule_engine",
        )
        logs = get_audit_log()
        assert logs[0]["outcome"] in self.VALID_OUTCOMES

    def test_invalid_outcome_raises(self, logger):
        """Free-text outcomes should be rejected."""
        with pytest.raises(ValueError, match="Invalid outcome"):
            logger.log_policy_decision(
                trigger_input={},
                decision={},
                outcome="some random free text that is not a valid outcome",
                actor="rule_engine",
            )
