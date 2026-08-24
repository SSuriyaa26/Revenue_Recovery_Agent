"""EvaluationResult data model — EDD Step 1, EDD §5.6.

The final output of the Evaluation Harness (§7). Every reported metric
must have a corresponding EvaluationResult JSON artifact to back it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ExceptionEntry(BaseModel):
    """A single record the system could not resolve/recover."""
    record_id: str
    reason: str
    raw_input: str


class EvaluationResult(BaseModel):
    """Validated EvaluationResult data model.

    EDD §5.6 contract. Includes policy_config_hash (P0 gate 7) and
    held_out_set_checksum for reproducibility.
    """
    flow: str = Field(..., pattern=r"^(p2p|payment_failure)$")
    held_out_set_checksum: str = Field(..., min_length=1)
    policy_config_hash: str = Field(
        ..., min_length=1,
        description="SHA-256 hash of the frozen PolicyConfig — makes every number reproducible (P0 gate 7)"
    )
    run_timestamp: datetime = Field(default_factory=datetime.utcnow)
    n_records: int = Field(..., ge=0)
    recovery_rate: float = Field(..., ge=0.0, le=1.0)
    naive_baseline_recovery_rate: float = Field(..., ge=0.0, le=1.0)
    lift: float = Field(...)
    cost_weighted_error_rate: float = Field(..., ge=0.0)
    cost_fp: float = Field(default=1.0)
    cost_fn: float = Field(default=4.0)
    lift_ci_lower: Optional[float] = Field(default=None, description="95% CI lower bound for Lift")
    lift_ci_upper: Optional[float] = Field(default=None, description="95% CI upper bound for Lift")
    recovery_rate_ci_lower: Optional[float] = Field(default=None, description="95% CI lower bound for Recovery Rate")
    recovery_rate_ci_upper: Optional[float] = Field(default=None, description="95% CI upper bound for Recovery Rate")
    ci_method: Optional[str] = Field(default="paired_bootstrap_95", description="Method used to compute 95% confidence interval")
    exception_list: list[ExceptionEntry] = Field(default_factory=list)
    guardrail_test_results: str = Field(..., pattern=r"^(PASS|FAIL)$")
    idempotency_test_results: str = Field(..., pattern=r"^(PASS|FAIL)$")
