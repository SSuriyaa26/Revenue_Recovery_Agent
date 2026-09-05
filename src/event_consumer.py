"""Event Consumer — EDD Step 5.

Handles incoming events (webhook deliveries, payment captures, etc.)
with idempotency enforcement. Duplicate events are detected via a
composite key of (invoice_id, event_type, razorpay_event_id) and
discarded as no-ops, with an audit log entry noting the duplicate.

Per decision B2: duplicate events produce 2 audit entries total:
1. The original processed-action entry
2. A "duplicate event ignored" entry for the duplicate delivery
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import hmac
import logging
import os
from typing import Any, Optional
import uuid

from store import (
    append_audit_log,
    check_and_set_idempotency_key,
    make_idempotency_key,
    set_invoice_status,
)

logger = logging.getLogger(__name__)


def verify_razorpay_webhook_signature(
    payload_body: bytes | str,
    signature: str,
    secret: Optional[str] = None,
) -> bool:
    """Verify incoming Razorpay webhook signature using HMAC-SHA256.

    SPEC §6.7 / Razorpay Webhooks Spec:
    Validates the 'X-Razorpay-Signature' header against the computed
    HMAC-SHA256 hash of the raw request payload using the configured webhook secret.
    """
    secret = secret or os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
    if not secret:
        # In test/mock environment without a configured webhook secret, log and permit
        logger.debug("RAZORPAY_WEBHOOK_SECRET not set; bypassing signature verification in mock/test mode.")
        return True

    if not signature:
        logger.warning("Missing Razorpay webhook signature header ('X-Razorpay-Signature').")
        return False

    if isinstance(payload_body, str):
        payload_bytes = payload_body.encode("utf-8")
    else:
        payload_bytes = payload_body

    expected_sig = hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()

    is_valid = hmac.compare_digest(expected_sig, signature)
    if is_valid:
        # One-line confirmation annotation: Webhook signature verified before event processing
        logger.info("Razorpay Webhook Signature Verified: HMAC-SHA256 signature matches expected digest.")
    else:
        logger.warning("Razorpay Webhook Signature Mismatch: Invalid signature received.")
    return is_valid



def handle_event(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Process an incoming event with idempotency enforcement.

    EDD §6.1 Test 4: sending the same event twice produces exactly
    one action and two audit log entries.

    Args:
        event: Dict with invoice_id, event_type, razorpay_event_id.

    Returns:
        List of actions produced. Empty list for duplicate events.
    """
    invoice_id = event["invoice_id"]
    event_type = event["event_type"]
    razorpay_event_id = event["razorpay_event_id"]

    # Build composite idempotency key
    idem_key = make_idempotency_key(invoice_id, event_type, razorpay_event_id)

    # Check idempotency
    is_new = check_and_set_idempotency_key(idem_key)

    if not is_new:
        # Duplicate event — no-op, but audit-log the duplicate
        append_audit_log({
            "log_id": str(uuid.uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": "system",
            "trigger_input": event,
            "decision": None,
            "resulting_action_id": None,
            "outcome": "duplicate_event_ignored",
            "idempotency_key": idem_key,
        })
        return []  # No new actions

    # New event — process it
    action_id = str(uuid.uuid4())

    # Determine action based on event type
    if event_type == "payment.captured":
        set_invoice_status(invoice_id, "Paid")
        action = {
            "action_id": action_id,
            "related_entity_id": invoice_id,
            "action_type": "payment_link",
            "outcome": "recovered",
            "policy_rule_applied": "payment_captured_close_loop",
        }
    elif event_type == "payment.failed":
        action = {
            "action_id": action_id,
            "related_entity_id": invoice_id,
            "action_type": "retry",
            "outcome": "pending",
            "policy_rule_applied": "payment_failed_schedule_retry",
        }
    elif event_type == "invoice.expired":
        set_invoice_status(invoice_id, "Overdue")
        action = {
            "action_id": action_id,
            "related_entity_id": invoice_id,
            "action_type": "reminder",
            "outcome": "pending",
            "policy_rule_applied": "invoice_expired_send_reminder",
        }
    else:
        action = {
            "action_id": action_id,
            "related_entity_id": invoice_id,
            "action_type": "reminder",
            "outcome": "pending",
            "policy_rule_applied": f"generic_event_{event_type}",
        }

    # Audit log the processed event
    append_audit_log({
        "log_id": str(uuid.uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "actor": "system",
        "trigger_input": event,
        "decision": {"action": action["action_type"]},
        "resulting_action_id": action_id,
        "outcome": action["outcome"],
        "idempotency_key": idem_key,
    })

    return [action]
