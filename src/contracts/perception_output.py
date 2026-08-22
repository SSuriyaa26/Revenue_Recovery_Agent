"""Perception output data models — EDD Step 1, EDD §5.1 and §5.2.

These are the contracts between the Perception Service (ASR + LLM
extraction, Failure Classifier) and Core Services. Schema validation
on these models is the first-class gate (EDD §5 preamble) that prevents
malformed/adversarial LLM outputs from reaching the Policy Engine.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class DetectedLanguage(str, Enum):
    HINGLISH = "hinglish"
    HINDI = "hindi"
    ENGLISH = "english"


class CommitmentExtraction(BaseModel):
    """Output of the ASR / text parsing → structured commitment pipeline.

    EDD §5.1 contract. Fields validated strictly — any validation
    failure routes to the Exception List, never silently accepted.
    """
    committed_amount: Optional[float] = Field(
        default=None,
        description="Extracted amount; null means full remaining balance (A3 rule applied in Action Selector)"
    )
    split_pct: Optional[float] = Field(default=None)
    committed_date: Optional[date] = Field(default=None)
    confidence: float = Field(..., ge=0.0, le=1.0)
    raw_transcript: str = Field(..., min_length=1)
    language_detected: DetectedLanguage = Field(default=DetectedLanguage.HINGLISH)
    extraction_notes: Optional[str] = Field(default=None)

    @field_validator("committed_amount")
    @classmethod
    def amount_must_be_positive_if_present(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError(f"committed_amount must be positive, got {v}")
        return v

    @field_validator("split_pct")
    @classmethod
    def split_pct_must_be_valid_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0 or v > 100):
            raise ValueError(f"split_pct must be in [0, 100], got {v}")
        return v


class FailureClassificationCategory(str, Enum):
    """Failure categories (EDD §5.2)."""
    TECHNICAL = "technical"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    DROPOFF = "dropoff"
    OTHER = "other"


class FailureClassification(BaseModel):
    """Output of the Failure Classifier.

    EDD §5.2 contract. `category: "other"` is a valid, expected output
    for genuinely ambiguous codes — the classifier must not force a
    specific category it isn't confident about.
    """
    category: FailureClassificationCategory
    confidence: float = Field(..., ge=0.0, le=1.0)
    matched_rule: Optional[str] = Field(default=None)
    raw_failure_code: str = Field(..., min_length=1)
