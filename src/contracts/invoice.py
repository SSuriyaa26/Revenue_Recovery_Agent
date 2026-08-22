"""Invoice data model — EDD Step 1, SPEC §6.4 + EDD §5 contracts.

Represents a B2B invoice in the Promise-to-Pay lifecycle.
State machine transitions are enforced separately in state_machine.py;
this model only validates field shapes and value constraints.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class InvoiceStatus(str, Enum):
    """Legal states in the Invoice / Promise-to-Pay lifecycle (SPEC §6.8)."""
    OPEN = "Open"
    P2P_COMMITTED = "P2P_Committed"
    PARTIALLY_PAID = "Partially_Paid"
    PAID = "Paid"
    OVERDUE = "Overdue"
    BROKEN_PROMISE = "Broken_Promise"
    ESCALATED_HUMAN = "Escalated_Human"


class Invoice(BaseModel):
    """Validated Invoice data model.

    Fields from SPEC §6.4, status enum from SPEC §6.8 state machine.
    """
    invoice_id: str = Field(..., min_length=1)
    merchant_id: str = Field(..., min_length=1)
    buyer_id: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0, description="Original invoice amount, must be positive")
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    due_date: date
    status: InvoiceStatus = Field(default=InvoiceStatus.OPEN)
    p2p_committed_amount: Optional[float] = Field(default=None, ge=0)
    p2p_committed_date: Optional[date] = Field(default=None)
    escalation_step: int = Field(default=0, ge=0)
    broken_promise_count: int = Field(default=0, ge=0)

    @field_validator("p2p_committed_amount")
    @classmethod
    def committed_amount_within_invoice(cls, v: Optional[float]) -> Optional[float]:
        """Committed amount, if present, must be non-negative.

        We don't validate against `amount` here because partial payments
        may reduce the effective balance — that logic belongs in the
        Action Selector, not the schema layer.
        """
        return v
