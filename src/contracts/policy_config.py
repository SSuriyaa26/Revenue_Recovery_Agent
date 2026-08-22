"""PolicyConfig data model — EDD Step 1, SPEC §6.4 + EDD §5.1 additions.

Central configuration for all deterministic guardrails. Every policy
decision is a pure function of (request, current_state, PolicyConfig).
No LLM call is permitted anywhere in the policy evaluation path.

Per decision A4: discount caps are per-flow, not a single global value.
Per decision B4: extraction_confidence_threshold added from EDD §5.1.
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional

from pydantic import BaseModel, Field


class PolicyConfig(BaseModel):
    """Validated PolicyConfig data model.

    All guardrail thresholds live here. This object is frozen and
    hashed before evaluation — the hash is included in every
    EvaluationResult for reproducibility (EDD §5.6).
    """
    # Per-flow discount caps (decision A4)
    max_discount_pct_p2p: float = Field(
        default=30.0, ge=0, le=100,
        description="Max discount % for B2B Promise-to-Pay flow"
    )
    max_discount_pct_payment_failure: float = Field(
        default=20.0, ge=0, le=100,
        description="Max discount % for Payment Failure flow"
    )

    # Retry caps
    max_retry_count: int = Field(
        default=3, ge=0,
        description="Max retry attempts for any single failed payment/mandate"
    )
    min_retry_spacing_hours: float = Field(
        default=4.0, gt=0,
        description="Minimum hours between retry attempts"
    )

    # Escalation
    max_broken_promises_before_escalation: int = Field(
        default=2, ge=1,
        description="Broken promise count that triggers human handoff"
    )

    # Timing
    salary_cycle_dates: list[int] = Field(
        default=[1, 15],
        description="Day-of-month dates considered salary cycle days"
    )
    bank_peak_hour_windows: list[dict] = Field(
        default=[
            {"start_hour": 20, "end_hour": 23, "banks": ["SBI", "HDFC", "ICICI"]},
            {"start_hour": 0, "end_hour": 2, "banks": ["SBI", "HDFC", "ICICI"]},
        ],
        description="Time windows (24h IST) considered bank peak hours"
    )

    # Extraction confidence (EDD §5.1, decision B4)
    extraction_confidence_threshold: float = Field(
        default=0.6, ge=0.0, le=1.0,
        description="Minimum confidence for accepting an extraction result"
    )

    # Cost weights for evaluation (EDD §2, frozen)
    cost_fp: float = Field(default=1.0, ge=0, description="Cost weight for false positives (false escalations)")
    cost_fn: float = Field(default=4.0, ge=0, description="Cost weight for false negatives (missed recoveries)")

    def config_hash(self) -> str:
        """Deterministic SHA-256 hash of this config for reproducibility.

        Included in every EvaluationResult per EDD §5.6 / P0 gate 7.
        """
        serialized = json.dumps(
            self.model_dump(),
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
