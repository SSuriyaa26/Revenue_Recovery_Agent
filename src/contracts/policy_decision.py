"""PolicyDecision data model — EDD Step 1, EDD §5.3 (authoritative).

Output of every Policy Engine function. Produced by a pure function of
(request, current_state, PolicyConfig) — no LLM call permitted.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class PolicyDecisionType(str, Enum):
    """Decision outcomes from the Policy Engine (EDD §5.3)."""
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    RETRY = "RETRY"
    RETRY_COMMITMENT = "RETRY_COMMITMENT"
    ESCALATE = "ESCALATE"
    EXHAUSTED = "EXHAUSTED"


class PolicyDecision(BaseModel):
    """Validated PolicyDecision data model.

    This is the contract between the Policy Engine and the Action
    Selector. Every field is deterministically produced — no
    randomness, no LLM involvement.
    """
    decision: PolicyDecisionType
    reason_code: str = Field(..., min_length=1)
    alternative_offer: Optional[dict[str, Any]] = Field(default=None)
    policy_version: str = Field(default="1.0")
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)
