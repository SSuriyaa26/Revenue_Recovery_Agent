"""RecoveryAction data model — EDD Step 1, EDD §5.4 (authoritative).

Represents an action taken (or scheduled) as part of the recovery workflow.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Types of recovery actions (EDD §5.4)."""
    RETRY = "retry"
    PAYMENT_LINK = "payment_link"
    REMINDER = "reminder"
    ESCALATION = "escalation"
    DENIAL_AND_ALTERNATIVE = "denial_and_alternative"
    NO_OP_RACE_SKIP = "no_op_race_skip"


class ActionOutcome(str, Enum):
    """Outcomes of a recovery action (EDD §5.4)."""
    RECOVERED = "recovered"
    PENDING = "pending"
    FAILED = "failed"
    ESCALATED = "escalated"
    SKIPPED = "skipped"


class RecoveryAction(BaseModel):
    """Validated RecoveryAction data model.

    Uses EDD §5.4 field names (authoritative per decision A2):
    - `related_entity_id` (not SPEC's `related_event_id`)
    - Extended action_type and outcome enums
    """
    action_id: str = Field(..., min_length=1)
    related_entity_id: str = Field(..., min_length=1)
    action_type: ActionType
    scheduled_time: Optional[datetime] = Field(default=None)
    executed_time: Optional[datetime] = Field(default=None)
    outcome: ActionOutcome = Field(default=ActionOutcome.PENDING)
    policy_rule_applied: str = Field(..., min_length=1)
