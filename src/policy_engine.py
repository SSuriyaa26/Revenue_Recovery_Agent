"""Deterministic Policy Engine — EDD Step 3.

Pure functions that enforce guardrails: discount caps, retry caps,
escalation stopping rules. These functions:
- Take explicit parameters (no hidden state, no config singletons)
- Make no network calls (enforced by test_no_network_in_policy_engine)
- Make no LLM calls (structural guarantee per EDD §5.3)
- Are deterministic: same input always produces same output

The caller (Action Selector / orchestrator) is responsible for passing
the correct per-flow max_discount_pct from PolicyConfig (A4 decision).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional


def check_discount(
    *,
    requested_pct: float,
    max_discount_pct: float,
) -> dict[str, Any]:
    """Check whether a requested discount percentage is within policy.

    EDD §6.1 Test 1. Boundary: requested_pct == max_discount_pct is APPROVED
    (inclusive). Anything above is DENIED with a 3_month_split alternative.

    Args:
        requested_pct: The discount percentage requested (0–100).
        max_discount_pct: The maximum allowed discount for this flow.

    Returns:
        A dict with 'decision', 'reason_code', and optionally 'alternative_offer'.
    """
    if requested_pct <= max_discount_pct:
        return {
            "decision": "APPROVED",
            "reason_code": "discount_within_policy",
            "alternative_offer": None,
            "policy_version": "1.0",
            "evaluated_at": datetime.now(UTC).isoformat(),
        }
    else:
        return {
            "decision": "DENIED",
            "reason_code": f"discount_{requested_pct}pct_exceeds_max_{max_discount_pct}pct",
            "alternative_offer": {
                "type": "3_month_split",
                "description": "Split payment over 3 months at full amount",
            },
            "policy_version": "1.0",
            "evaluated_at": datetime.now(UTC).isoformat(),
        }


def check_retry(
    *,
    attempt_count: int,
    max_retry_count: int,
) -> dict[str, Any]:
    """Check whether a retry is permitted given the current attempt count.

    EDD §6.1 Test 2. attempt_count >= max_retry_count returns EXHAUSTED;
    below returns RETRY.

    Args:
        attempt_count: Number of retry attempts already made.
        max_retry_count: Maximum allowed retries from PolicyConfig.

    Returns:
        A dict with 'decision' and 'reason_code'.
    """
    if attempt_count >= max_retry_count:
        return {
            "decision": "EXHAUSTED",
            "reason_code": f"retry_count_{attempt_count}_reached_max_{max_retry_count}",
            "alternative_offer": None,
            "policy_version": "1.0",
            "evaluated_at": datetime.now(UTC).isoformat(),
        }
    else:
        return {
            "decision": "RETRY",
            "reason_code": f"retry_permitted_attempt_{attempt_count}_of_{max_retry_count}",
            "alternative_offer": None,
            "policy_version": "1.0",
            "evaluated_at": datetime.now(UTC).isoformat(),
        }


def check_escalation(
    *,
    broken_promise_count: int,
    max_broken_promises: int,
) -> dict[str, Any]:
    """Check whether to escalate to human handoff or retry commitment.

    EDD §6.1 Test 3. broken_promise_count >= max_broken_promises triggers
    ESCALATE; below triggers RETRY_COMMITMENT.

    Per decision A5: Partially_Paid → Broken_Promise increments the count
    the same as a fully unpaid promise.

    Args:
        broken_promise_count: Number of broken promises so far.
        max_broken_promises: Threshold from PolicyConfig (default 2).

    Returns:
        A dict with 'decision' and 'reason_code'.
    """
    if broken_promise_count >= max_broken_promises:
        return {
            "decision": "ESCALATE",
            "reason_code": f"broken_promises_{broken_promise_count}_reached_max_{max_broken_promises}",
            "alternative_offer": None,
            "policy_version": "1.0",
            "evaluated_at": datetime.now(UTC).isoformat(),
        }
    else:
        return {
            "decision": "RETRY_COMMITMENT",
            "reason_code": f"broken_promises_{broken_promise_count}_below_max_{max_broken_promises}",
            "alternative_offer": None,
            "policy_version": "1.0",
            "evaluated_at": datetime.now(UTC).isoformat(),
        }


def get_retry_policy(
    *,
    category: str,
    attempt_count: int,
    policy_config: Optional[dict] = None,
) -> dict[str, Any]:
    """Determine the retry policy based on failure category and attempt count.

    Combines failure classification with retry cap enforcement.
    Selects timing based on category (bank peak hour → next morning,
    insufficient funds → salary cycle, etc.).

    Args:
        category: Failure category from FailureClassification.
        attempt_count: Current attempt count.
        policy_config: Optional PolicyConfig as dict for timing lookups.

    Returns:
        A dict with 'decision', 'scheduled_time' hint, and 'reason_code'.
    """
    max_retry = 3
    if policy_config and "max_retry_count" in policy_config:
        max_retry = policy_config["max_retry_count"]

    # First check if retries are exhausted
    retry_check = check_retry(attempt_count=attempt_count, max_retry_count=max_retry)
    if retry_check["decision"] == "EXHAUSTED":
        return retry_check

    # Category-specific timing
    if category == "technical":
        return {
            "decision": "RETRY",
            "reason_code": "technical_failure_retry_next_morning",
            "scheduled_time_hint": "next_day_06:30",
            "alternative_offer": None,
            "policy_version": "1.0",
            "evaluated_at": datetime.now(UTC).isoformat(),
        }
    elif category == "insufficient_funds":
        return {
            "decision": "RETRY",
            "reason_code": "insufficient_funds_retry_salary_cycle",
            "scheduled_time_hint": "next_salary_cycle_date",
            "alternative_offer": None,
            "policy_version": "1.0",
            "evaluated_at": datetime.utcnow().isoformat(),
        }
    elif category == "dropoff":
        return {
            "decision": "RETRY",
            "reason_code": "dropoff_offer_split_payment",
            "scheduled_time_hint": "immediate",
            "alternative_offer": {
                "type": "split_payment",
                "description": "Split payment into smaller installments",
            },
            "policy_version": "1.0",
            "evaluated_at": datetime.utcnow().isoformat(),
        }
    else:
        # category == "other" — generic retry
        return {
            "decision": "RETRY",
            "reason_code": "unclassified_failure_generic_retry",
            "scheduled_time_hint": "next_day_09:00",
            "alternative_offer": None,
            "policy_version": "1.0",
            "evaluated_at": datetime.utcnow().isoformat(),
        }
