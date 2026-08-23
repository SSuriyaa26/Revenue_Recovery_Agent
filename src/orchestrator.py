"""Revenue Recovery Full Orchestrator — EDD Step 10.

Unites:
Perception Service -> Policy Engine -> Action Selector -> Payment Gateway Adapter -> State Machine -> Audit Logger.
Executes complete end-to-end golden path and exception recovery trajectories.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import logging
import os
from typing import Any, Optional, Union
import uuid

from pydantic import BaseModel, Field

from contracts.audit_log_entry import AuditActor, AuditLogEntry
from contracts.invoice import InvoiceStatus
from contracts.perception_output import CommitmentExtraction, FailureClassification
from contracts.policy_config import PolicyConfig
from contracts.recovery_action import ActionOutcome, ActionType, RecoveryAction
from audit_logger import AuditLogger
from payment_adapter import PaymentGatewayAdapter, PaymentLinkResult, get_payment_adapter
from perception_service import PerceptionService, get_perception_service
import policy_engine
import state_machine

logger = logging.getLogger(__name__)


class OrchestrationResult(BaseModel):
    """End-to-end result of processing a customer recovery interaction."""
    success: bool = Field(..., description="True if payment link or next valid action was produced")
    invoice_id: str
    routed_to: str = Field(default="core_services", description="'core_services' or 'exception_list'")
    extraction: Optional[CommitmentExtraction] = None
    exception_details: Optional[dict[str, Any]] = None
    policy_decision: Optional[dict[str, Any]] = None
    payment_link: Optional[PaymentLinkResult] = None
    previous_state: str
    new_state: str
    audit_entries: list[dict[str, Any]] = Field(default_factory=list)


class RevenueRecoveryOrchestrator:
    """End-to-end orchestrator for AI revenue recovery flows."""

    def __init__(
        self,
        perception_service: Optional[PerceptionService] = None,
        payment_adapter: Optional[PaymentGatewayAdapter] = None,
        policy_config: Optional[PolicyConfig] = None,
        audit_logger: Optional[AuditLogger] = None,
    ):
        self.perception_service = perception_service or get_perception_service()
        self.payment_adapter = payment_adapter or get_payment_adapter()
        self.policy_config = policy_config or PolicyConfig()
        self.audit_logger = audit_logger or AuditLogger()

    def process_utterance(
        self,
        utterance_text: str,
        invoice_id: str,
        original_amount: float,
        current_state: Union[InvoiceStatus, str] = InvoiceStatus.OPEN,
        customer_phone: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_risk_tier: str = "LOW",
        flow: str = "p2p",
        reference_date: Optional[date] = None,
        requested_discount_pct: Optional[float] = None,
    ) -> OrchestrationResult:
        """Processes a text utterance from customer through the full recovery pipeline."""
        ref_date = reference_date or date.today()
        curr_status = current_state if isinstance(current_state, str) else current_state.value
        audit_records: list[dict[str, Any]] = []

        # 1. Perception Layer (Extraction + Sanitization Gateway)
        perception_res = self.perception_service.process_text(
            raw_text=utterance_text,
            reference_date=ref_date,
            original_amount=original_amount,
        )

        # Handle exception list routing
        if perception_res.get("routed_to") == "exception_list":
            # Audit log exception routing
            entry = self.audit_logger.log_policy_decision(
                trigger_input={"invoice_id": invoice_id, "transcript": utterance_text, "details": perception_res},
                decision="ROUTED_TO_EXCEPTION_LIST",
                outcome="schema_validation_failed",
                actor="perception_service",
            )
            audit_records.append(entry)

            return OrchestrationResult(
                success=False,
                invoice_id=invoice_id,
                routed_to="exception_list",
                exception_details=perception_res,
                previous_state=curr_status,
                new_state=curr_status,
                audit_entries=audit_records,
            )

        extraction_dict = perception_res.get("validated_output", {})
        extraction = CommitmentExtraction(**extraction_dict)

        # 2. Policy Engine Guardrails
        # Check discount if requested
        if requested_discount_pct is not None and requested_discount_pct > 0:
            max_disc = (
                self.policy_config.max_discount_pct_p2p
                if flow.lower() == "p2p"
                else self.policy_config.max_discount_pct_payment_failure
            )
            discount_decision = policy_engine.check_discount(
                requested_pct=requested_discount_pct,
                max_discount_pct=max_disc,
            )
            if discount_decision.get("decision") == "DENIED":
                # Option 2: State remains unchanged; denial is audit-logged and escalated to human operator
                entry = self.audit_logger.log_policy_decision(
                    trigger_input={"invoice_id": invoice_id, "requested_pct": requested_discount_pct, "max_pct": max_disc},
                    decision=discount_decision,
                    outcome="denied",
                    actor="rule_engine",
                )
                audit_records.append(entry)

                return OrchestrationResult(
                    success=False,
                    invoice_id=invoice_id,
                    routed_to="core_services",
                    extraction=extraction,
                    policy_decision=discount_decision,
                    previous_state=curr_status,
                    new_state=curr_status,
                    audit_entries=audit_records,
                )

        # 3. Action Selector: Determine effective payment amount
        # Rule A3: null committed_amount means full invoice balance
        if extraction.committed_amount is not None and extraction.committed_amount > 0:
            effective_amount = extraction.committed_amount
        elif extraction.split_pct is not None and extraction.split_pct > 0:
            effective_amount = round((extraction.split_pct / 100.0) * original_amount, 2)
        else:
            effective_amount = original_amount

        if requested_discount_pct is not None and requested_discount_pct > 0:
            effective_amount = round(effective_amount * (1.0 - requested_discount_pct / 100.0), 2)

        # 4. Payment Gateway Adapter: Create payment link
        payment_link = self.payment_adapter.create_payment_link(
            invoice_id=invoice_id,
            amount=effective_amount,
            customer_phone=customer_phone,
            customer_email=customer_email,
            customer_name=customer_name,
            description=f"Recovery link for invoice {invoice_id}",
        )

        # 5. State Machine Transition: Open -> P2P_Committed
        next_status = InvoiceStatus.P2P_COMMITTED.value
        state_machine.transition(entity_id=invoice_id, from_state=curr_status, to_state=next_status)

        # 6. Audit Logging: Record decision and link creation
        entry1 = self.audit_logger.log_policy_decision(
            trigger_input={
                "invoice_id": invoice_id,
                "effective_amount": effective_amount,
                "committed_date": str(extraction.committed_date),
                "confidence": extraction.confidence,
            },
            decision="commitment_accepted",
            outcome="commitment_accepted",
            action_id=payment_link.link_id,
            actor="rule_engine",
        )
        audit_records.append(entry1)

        entry2 = self.audit_logger.log_state_transition(
            entity_id=invoice_id,
            from_state=curr_status,
            to_state=next_status,
            trigger_input={"action": "create_payment_link", "link_id": payment_link.link_id},
            outcome="state_transitioned",
            actor="system",
        )
        audit_records.append(entry2)

        return OrchestrationResult(
            success=True,
            invoice_id=invoice_id,
            routed_to="core_services",
            extraction=extraction,
            payment_link=payment_link,
            previous_state=curr_status,
            new_state=next_status,
            audit_entries=audit_records,
        )

    def process_audio(
        self,
        audio_source: Any,
        invoice_id: str,
        original_amount: float,
        filename: Optional[str] = None,
        current_state: Union[InvoiceStatus, str] = InvoiceStatus.OPEN,
        customer_phone: Optional[str] = None,
        customer_email: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_risk_tier: str = "LOW",
        flow: str = "p2p",
        reference_date: Optional[date] = None,
    ) -> OrchestrationResult:
        """Processes speech audio directly through ASR -> Extractor -> Orchestrator."""
        transcription = self.perception_service.asr_adapter.transcribe(audio_source, filename=filename)
        return self.process_utterance(
            utterance_text=transcription.transcript,
            invoice_id=invoice_id,
            original_amount=original_amount,
            current_state=current_state,
            customer_phone=customer_phone,
            customer_email=customer_email,
            customer_name=customer_name,
            customer_risk_tier=customer_risk_tier,
            flow=flow,
            reference_date=reference_date,
        )


def get_orchestrator() -> RevenueRecoveryOrchestrator:
    """Factory to create a default RevenueRecoveryOrchestrator instance."""
    return RevenueRecoveryOrchestrator()
