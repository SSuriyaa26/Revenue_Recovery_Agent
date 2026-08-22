"""PaymentEvent data model — EDD Step 1, SPEC §6.4.

Represents a payment failure or checkout abandonment event.
Internal storage model; the Failure Classifier output is a separate
contract (FailureClassification in perception_output.py).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PaymentStatus(str, Enum):
    SUCCESS = "Success"
    FAILED = "Failed"
    ABANDONED = "Abandoned"


class FailureCategory(str, Enum):
    """Failure classification categories (SPEC §6.4 / EDD §5.2)."""
    TECHNICAL = "technical"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    DROPOFF = "dropoff"
    OTHER = "other"


class PaymentChannel(str, Enum):
    UPI = "UPI"
    CARD = "card"
    NETBANKING = "netbanking"


class PaymentEvent(BaseModel):
    """Validated PaymentEvent data model.

    Fields from SPEC §6.4. The `failure_category` field is populated
    by the Failure Classifier (Perception Service) after ingestion,
    not at event creation time.
    """
    event_id: str = Field(..., min_length=1)
    transaction_id: str = Field(..., min_length=1)
    merchant_id: str = Field(..., min_length=1)
    customer_id: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    status: PaymentStatus
    failure_code: Optional[str] = Field(default=None)
    failure_category: Optional[FailureCategory] = Field(default=None)
    timestamp: datetime
    channel: PaymentChannel
    razorpay_event_id: Optional[str] = Field(default=None, min_length=1)
