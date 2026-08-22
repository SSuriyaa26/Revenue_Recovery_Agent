"""AuditLogEntry data model — EDD Step 1, EDD §5.5 (authoritative).

Every money-affecting or customer-facing action must produce at least one
AuditLogEntry. The audit log is immutable — entries are append-only.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class AuditActor(str, Enum):
    """Who/what originated the action (EDD §5.5)."""
    SYSTEM = "system"
    RULE_ENGINE = "rule_engine"
    PERCEPTION_SERVICE = "perception_service"
    SCHEDULER = "scheduler"


class AuditLogEntry(BaseModel):
    """Validated AuditLogEntry data model.

    Fields from EDD §5.5. `trigger_input` and `decision` are typed as
    dicts/Any because they carry the raw upstream objects (extraction
    results, policy decisions, etc.) — their internal structure is
    validated by the respective contract models before reaching here.
    """
    log_id: str = Field(..., min_length=1)
    timestamp: datetime
    actor: AuditActor
    trigger_input: Any = Field(..., description="Raw event or extraction result that triggered this action")
    decision: Optional[Any] = Field(default=None, description="PolicyDecision or classification, if applicable")
    resulting_action_id: Optional[str] = Field(default=None)
    outcome: str = Field(..., min_length=1, description="One of the defined outcome enum values, never free-text")
    idempotency_key: Optional[str] = Field(default=None)
