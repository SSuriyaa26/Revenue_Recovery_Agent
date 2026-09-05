"""In-Memory Data Store — EDD Step 5.

Simple in-memory store for invoices, payment events, idempotency keys,
audit logs, and message tracking. Sufficient for hackathon-scale batch
evaluation (40–50+ records) without DB infrastructure overhead.

In production, this would be backed by SQLite or PostgreSQL with the
idempotency key as a UNIQUE constraint on (invoice_id, event_type,
razorpay_event_id) per SPEC §6.7.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional
import uuid


# --- Internal storage ---
_invoices: dict[str, dict[str, Any]] = {}
_payment_events: dict[str, dict[str, Any]] = {}
_idempotency_keys: set[str] = set()
_audit_log: list[dict[str, Any]] = []
_messages_sent: dict[str, int] = {}  # entity_id → count
_scheduled_jobs: list[dict[str, Any]] = []


def reset_store() -> None:
    """Reset all in-memory state. Used by test fixtures."""
    global _invoices, _payment_events, _idempotency_keys, _audit_log, _messages_sent, _scheduled_jobs
    _invoices.clear()
    _payment_events.clear()
    _idempotency_keys.clear()
    _audit_log.clear()
    _messages_sent.clear()
    _scheduled_jobs.clear()


# --- Invoice operations ---

def set_invoice_status(invoice_id: str, status: str) -> None:
    """Create or update an invoice's status."""
    if invoice_id not in _invoices:
        _invoices[invoice_id] = {
            "invoice_id": invoice_id,
            "status": status,
            "broken_promise_count": 0,
            "escalation_step": 0,
        }
    else:
        _invoices[invoice_id]["status"] = status


def get_invoice_status(invoice_id: str) -> Optional[str]:
    """Get the current status of an invoice, or None if not found."""
    inv = _invoices.get(invoice_id)
    return inv["status"] if inv else None


def get_invoice(invoice_id: str) -> Optional[dict[str, Any]]:
    """Get the full invoice record."""
    return _invoices.get(invoice_id)


def update_invoice(invoice_id: str, **fields: Any) -> None:
    """Update specific fields on an invoice."""
    if invoice_id in _invoices:
        _invoices[invoice_id].update(fields)


def get_all_invoices() -> list[dict[str, Any]]:
    """Get all invoice records currently stored in memory."""
    return list(_invoices.values())


# --- Idempotency operations ---

def make_idempotency_key(invoice_id: str, event_type: str, razorpay_event_id: str) -> str:
    """Create a composite idempotency key."""
    return f"{invoice_id}:{event_type}:{razorpay_event_id}"


def check_and_set_idempotency_key(key: str) -> bool:
    """Check if a key exists; if not, set it and return True (new).

    Returns True if this is a NEW event (not seen before).
    Returns False if this is a DUPLICATE (already processed).
    """
    if key in _idempotency_keys:
        return False  # Duplicate
    _idempotency_keys.add(key)
    return True  # New


# --- Audit log operations ---

def append_audit_log(entry: dict[str, Any]) -> None:
    """Append an audit log entry."""
    if "log_id" not in entry:
        entry["log_id"] = str(uuid.uuid4())
    if "timestamp" not in entry:
        entry["timestamp"] = datetime.now(UTC).isoformat()
    _audit_log.append(entry)


def get_audit_log_count(razorpay_event_id: str) -> int:
    """Count audit log entries for a given razorpay_event_id.

    Matches on the idempotency_key field containing the event_id.
    """
    count = 0
    for entry in _audit_log:
        idem_key = entry.get("idempotency_key", "") or ""
        trigger = entry.get("trigger_input", {})
        trigger_event_id = ""
        if isinstance(trigger, dict):
            trigger_event_id = trigger.get("razorpay_event_id", "")

        if razorpay_event_id in idem_key or trigger_event_id == razorpay_event_id:
            count += 1
    return count


def get_audit_log() -> list[dict[str, Any]]:
    """Get the full audit log."""
    return list(_audit_log)


def get_last_audit_outcome(entity_id: str) -> Optional[str]:
    """Get the outcome of the last audit log entry for an entity."""
    for entry in reversed(_audit_log):
        trigger = entry.get("trigger_input", {})
        if isinstance(trigger, dict):
            if trigger.get("entity_id") == entity_id or trigger.get("invoice_id") == entity_id:
                return entry.get("outcome")
        if entry.get("resulting_action_id", "").startswith(entity_id):
            return entry.get("outcome")
    return None


# --- Message tracking ---

def record_message_sent(entity_id: str) -> None:
    """Record that a message was sent for an entity."""
    _messages_sent[entity_id] = _messages_sent.get(entity_id, 0) + 1


def get_messages_sent(entity_id: str) -> int:
    """Get the count of messages sent for an entity."""
    return _messages_sent.get(entity_id, 0)


# --- Scheduled jobs ---

def schedule_job(entity_id: str, trigger_time: str, action_type: str) -> str:
    """Schedule a follow-up job."""
    job_id = str(uuid.uuid4())
    _scheduled_jobs.append({
        "job_id": job_id,
        "entity_id": entity_id,
        "trigger_time": trigger_time,
        "action_type": action_type,
        "executed": False,
    })
    return job_id


def get_pending_jobs(entity_id: Optional[str] = None) -> list[dict[str, Any]]:
    """Get pending (unexecuted) jobs, optionally filtered by entity_id."""
    return [
        j for j in _scheduled_jobs
        if not j["executed"] and (entity_id is None or j["entity_id"] == entity_id)
    ]


def mark_job_executed(job_id: str) -> None:
    """Mark a scheduled job as executed."""
    for j in _scheduled_jobs:
        if j["job_id"] == job_id:
            j["executed"] = True
            break
