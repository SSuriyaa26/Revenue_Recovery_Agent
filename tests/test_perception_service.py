"""Unit tests for PerceptionService orchestrator — EDD Step 9.

Tests end-to-end integration across ASR Adapter, CommitmentExtractor,
and Perception Gateway sanitization.
"""

from datetime import date
from unittest.mock import MagicMock, patch
import pytest

from asr_adapter import MockASRAdapter, TranscriptionResult
from contracts.perception_output import CommitmentExtraction
from perception_service import PerceptionService


def test_perception_service_with_mock_asr_routes_to_core():
    """Verify PerceptionService transcribes audio via adapter and routes valid output to core_services."""
    mock_asr = MockASRAdapter(default_transcript="Bhaiya kal tak 50000 de dunga pakka")
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = CommitmentExtraction(
        committed_amount=50000.0,
        split_pct=None,
        committed_date=date(2026, 8, 21),
        confidence=0.95,
        raw_transcript="Bhaiya kal tak 50000 de dunga pakka",
    )

    service = PerceptionService(asr_adapter=mock_asr, extractor=mock_extractor)
    
    result = service.process_audio(
        "sample_audio.m4a",
        reference_date=date(2026, 8, 20),
        original_amount=50000.0
    )
    
    assert result["routed_to"] == "core_services"
    assert result["validated_output"]["committed_amount"] == 50000.0
    assert result["validated_output"]["committed_date"] == "2026-08-21"


def test_perception_service_low_confidence_routes_to_exception_list():
    """Verify vague/adversarial/low-confidence output routes to exception_list."""
    mock_asr = MockASRAdapter(default_transcript="Abhi kuch nahi bol sakta")
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = CommitmentExtraction(
        committed_amount=None,
        split_pct=None,
        committed_date=None,
        confidence=0.35,
        raw_transcript="Abhi kuch nahi bol sakta",
    )

    service = PerceptionService(
        asr_adapter=mock_asr,
        extractor=mock_extractor,
        confidence_threshold=0.70
    )
    
    result = service.process_audio("vague_audio.m4a")
    
    assert result["routed_to"] == "exception_list"
    assert result["reason"] in ["low_confidence", "schema_validation_failed"]
