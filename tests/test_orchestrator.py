"""Integration tests for Full Orchestration — EDD Step 10.

Tests the full golden path:
Perception -> Policy Engine -> Action Selector -> Payment Gateway Adapter -> State Machine -> Audit Logger.
"""

from datetime import date, datetime
import os
from unittest.mock import MagicMock, patch
import pytest

from asr_adapter import MockASRAdapter
from commitment_extractor import CommitmentExtractor
from contracts.invoice import InvoiceStatus
from contracts.perception_output import CommitmentExtraction, DetectedLanguage
from orchestrator import RevenueRecoveryOrchestrator, OrchestrationResult
from payment_adapter import MockPaymentAdapter, PaymentLinkResult
from perception_service import PerceptionService


def _get_test_orchestrator() -> RevenueRecoveryOrchestrator:
    mock_perception = PerceptionService(
        asr_adapter=MockASRAdapter(),
        extractor=CommitmentExtractor(api_key="dummy_key"),
    )
    return RevenueRecoveryOrchestrator(
        perception_service=mock_perception,
        payment_adapter=MockPaymentAdapter(),
    )


def test_orchestration_golden_path_p2p_commitment():
    """Verify full end-to-end flow creates payment link, transitions state, and writes audit logs."""
    orchestrator = _get_test_orchestrator()

    # Mock perception extraction for 20k promise on 2026-08-24
    mock_extraction = CommitmentExtraction(
        committed_amount=20000.0,
        split_pct=None,
        committed_date=date(2026, 8, 24),
        confidence=0.95,
        raw_transcript="Monday tak 20000 de dunga",
        language_detected=DetectedLanguage.HINGLISH,
        extraction_notes="Clear promise on Monday"
    )

    with patch.object(orchestrator.perception_service.extractor, "extract", return_value=mock_extraction):
        result = orchestrator.process_utterance(
            utterance_text="Monday tak 20000 de dunga",
            invoice_id="INV-GOLDEN-001",
            original_amount=50000.0,
            current_state=InvoiceStatus.OPEN,
            customer_phone="+919876543210",
            customer_email="payer@example.com",
            customer_risk_tier="LOW",
            flow="p2p",
            reference_date=date(2026, 8, 20)
        )

        assert isinstance(result, OrchestrationResult)
        assert result.success is True
        assert result.new_state == InvoiceStatus.P2P_COMMITTED.value
        assert result.payment_link is not None
        assert result.payment_link.amount == 20000.0
        assert "rzp.io" in result.payment_link.short_url
        assert len(result.audit_entries) >= 2  # Policy decision + State transition


def test_orchestration_discount_exceeding_cap_escalates():
    """Verify requested discount exceeding policy cap (e.g. 50% vs 30% cap) is denied and logged."""
    orchestrator = _get_test_orchestrator()

    # Mock extraction requesting 50% discount (represented via requested amount or notes)
    mock_extraction = CommitmentExtraction(
        committed_amount=25000.0,
        split_pct=50.0,
        committed_date=date(2026, 8, 24),
        confidence=0.95,
        raw_transcript="50% discount de do toh abhi de deta hoon 25000",
        language_detected=DetectedLanguage.HINGLISH,
        extraction_notes="Customer requested 50% discount"
    )

    with patch.object(orchestrator.perception_service.extractor, "extract", return_value=mock_extraction):
        result = orchestrator.process_utterance(
            utterance_text="50% discount de do toh abhi de deta hoon 25000",
            invoice_id="INV-DISCOUNT-001",
            original_amount=50000.0,
            current_state=InvoiceStatus.OPEN,
            customer_phone="+919876543210",
            customer_email="payer@example.com",
            customer_risk_tier="HIGH",
            flow="p2p",
            reference_date=date(2026, 8, 20),
            requested_discount_pct=50.0
        )

        assert result.policy_decision is not None
        assert result.policy_decision.get("decision") == "DENIED"
        assert result.new_state == InvoiceStatus.ESCALATED_HUMAN.value


def test_orchestration_low_confidence_routes_to_exception():
    """Verify vague utterance with confidence < 0.70 routes to exception list with no payment link."""
    orchestrator = _get_test_orchestrator()

    mock_vague_extraction = CommitmentExtraction(
        committed_amount=None,
        split_pct=None,
        committed_date=None,
        confidence=0.40,
        raw_transcript="agle hafte kisi din de dunga",
        language_detected=DetectedLanguage.HINGLISH,
        extraction_notes="Vague date, non-committal"
    )

    with patch.object(orchestrator.perception_service.extractor, "extract", return_value=mock_vague_extraction):
        result = orchestrator.process_utterance(
            utterance_text="agle hafte kisi din de dunga",
            invoice_id="INV-VAGUE-001",
            original_amount=30000.0,
            current_state=InvoiceStatus.OPEN,
            customer_phone="+919876543210",
            customer_email="payer@example.com",
            customer_risk_tier="MEDIUM",
            flow="p2p",
            reference_date=date(2026, 8, 20)
        )

        assert result.success is False
        assert result.payment_link is None
        assert result.routed_to == "exception_list"
