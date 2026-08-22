"""Perception Gateway — EDD Step 3.

Schema validation gateway between the Perception Service (ASR + LLM
extraction) and Core Services. This is the first-class gate (EDD §5
preamble) that prevents malformed/adversarial outputs from reaching
the Policy Engine.

Every Perception output MUST pass strict schema validation here before
being allowed to proceed. Validation failures are routed to the
Exception List, never silently accepted.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from contracts.perception_output import CommitmentExtraction


# Fields that the CommitmentExtraction schema recognizes
_KNOWN_FIELDS = set(CommitmentExtraction.model_fields.keys())


def ingest_extraction(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a Perception Service extraction result against the schema.

    Per EDD §5 preamble: a validation failure is a defined outcome —
    route to Exception List with the specific field(s) that failed.

    Per EDD §6.1 Test 6:
    - Negative amount → rejected with reason "invalid_amount_negative"
    - split_pct outside [0,100] → rejected with reason "invalid_split_pct"
    - Unknown fields (e.g., "discount_override") → stripped silently
    - Missing required fields → rejected with reason "schema_validation_failed"

    Args:
        payload: Raw dict from the Perception Service.

    Returns:
        A dict with either:
        - {"routed_to": "core_services", "validated_output": {...}} on success
        - {"routed_to": "exception_list", "reason": "...", "details": "..."} on failure
    """
    # Step 1: Pre-validation checks for specific adversarial patterns
    # These produce specific reason codes per the EDD test expectations.

    if "committed_amount" in payload:
        amount = payload["committed_amount"]
        if amount is not None and amount < 0:
            return {
                "routed_to": "exception_list",
                "reason": "invalid_amount_negative",
                "details": f"committed_amount={amount} is negative",
            }

    if "split_pct" in payload:
        split = payload["split_pct"]
        if split is not None and (split < 0 or split > 100):
            return {
                "routed_to": "exception_list",
                "reason": "invalid_split_pct",
                "details": f"split_pct={split} outside valid [0, 100] range",
            }

    # Step 2: Strip unknown fields (e.g., "discount_override")
    # Only pass known schema fields to the validator.
    known_payload = {k: v for k, v in payload.items() if k in _KNOWN_FIELDS}

    # Step 3: Validate against the Pydantic model
    try:
        validated = CommitmentExtraction.model_validate(known_payload)
    except ValidationError as e:
        return {
            "routed_to": "exception_list",
            "reason": "schema_validation_failed",
            "details": str(e),
        }

    # Step 4: Semantic validation — a valid extraction must contain at least
    # one commitment field (amount or date). A payload with only raw_transcript
    # and confidence but no commitment data is not a valid extraction result
    # (catches prompt-injection and impersonation payloads).
    if validated.committed_amount is None and validated.committed_date is None:
        return {
            "routed_to": "exception_list",
            "reason": "schema_validation_failed",
            "details": "No commitment fields present (committed_amount and committed_date are both null)",
        }

    return {
        "routed_to": "core_services",
        "validated_output": validated.model_dump(mode="json"),
    }
