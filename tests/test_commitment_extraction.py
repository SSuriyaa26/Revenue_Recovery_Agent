"""Unit and integration tests for Commitment Extraction — EDD Step 9.

Tests LLM intent extraction against structured contracts, dual-script handling
(Devanagari vs Roman Hinglish), defensive date parsing, and dev-set samples.
"""

from datetime import date
from unittest.mock import MagicMock, patch
import pytest

from contracts.perception_output import CommitmentExtraction, DetectedLanguage
from commitment_extractor import CommitmentExtractor


def test_commitment_extractor_initialization():
    """Verify CommitmentExtractor initializes with configured models and parameters."""
    extractor = CommitmentExtractor(api_key="fake_key", model_name="gemini-3.7-flash")
    assert extractor.model_name == "gemini-3.7-flash"
    assert extractor.temperature == 0.0


def test_devanagari_and_roman_script_extraction():
    """Verify extractor accurately maps structured outputs for both scripts."""
    extractor = CommitmentExtractor(api_key="fake_key")
    
    # Mock LLM client response for Devanagari mixed
    mock_devanagari_output = {
        "committed_amount": 20000.0,
        "split_pct": None,
        "committed_date": "2026-08-24",
        "confidence": 0.95,
        "language_detected": "hinglish",
        "extraction_notes": "Extracted Monday commitment from Devanagari text"
    }
    
    with patch.object(extractor, "_call_llm", return_value=mock_devanagari_output):
        res1 = extractor.extract(
            "सर मैंने सोचा था कि इस week दे दूंगा but कुछ delay हो गया Monday तक 20000 भेज दूंगा बाकी next month",
            reference_date=date(2026, 8, 20)
        )
        assert isinstance(res1, CommitmentExtraction)
        assert res1.committed_amount == 20000.0
        assert res1.committed_date == date(2026, 8, 24)
        assert res1.confidence >= 0.90

    # Mock LLM client response for Roman script Hinglish
    mock_roman_output = {
        "committed_amount": 50000.0,
        "split_pct": None,
        "committed_date": "2026-08-25",
        "confidence": 0.92,
        "language_detected": "hinglish",
        "extraction_notes": "Extracted 25th commitment from Roman text"
    }
    
    with patch.object(extractor, "_call_llm", return_value=mock_roman_output):
        res2 = extractor.extract(
            "I'll clear the full invoice by 25th no issues, bas ek do din ka time chahiye.",
            reference_date=date(2026, 8, 20),
            original_amount=50000.0
        )
        assert isinstance(res2, CommitmentExtraction)
        assert res2.committed_amount == 50000.0
        assert res2.committed_date == date(2026, 8, 25)


def test_defensive_date_parsing_vague_input():
    """Verify vague date expressions result in null committed_date and low confidence."""
    extractor = CommitmentExtractor(api_key="fake_key")
    
    mock_vague_output = {
        "committed_amount": None,
        "split_pct": None,
        "committed_date": None,
        "confidence": 0.40,
        "language_detected": "hinglish",
        "extraction_notes": "Vague intent: customer said 'agle hafte kisi din' with no specific date"
    }
    
    with patch.object(extractor, "_call_llm", return_value=mock_vague_output):
        res = extractor.extract(
            "Monday tak... ya phir... haan Monday, no wait Tuesday. Actually agle hafte kisi din de dunga.",
            reference_date=date(2026, 8, 22)
        )
        assert res.committed_date is None
        assert res.confidence < 0.70  # Below extraction_confidence_threshold
