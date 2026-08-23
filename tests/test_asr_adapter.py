"""Unit tests for ASR Adapter Abstraction — EDD Step 9.

Tests the vendor-agnostic ASR interface, typed contract (TranscriptionResult),
Sarvam adapter, mock adapter, and provider swapping mechanism.
"""

import io
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from asr_adapter import (
    ASRAdapter,
    SarvamASRAdapter,
    MockASRAdapter,
    WhisperASRAdapter,
    TranscriptionResult,
    get_asr_adapter,
    ASRError,
)


def test_transcription_result_contract():
    """Verify TranscriptionResult typed contract fields."""
    res = TranscriptionResult(
        transcript="भैया payment Friday tak",
        language_detected="hi-IN",
        confidence=0.92,
        raw_provider_response={"status": "ok"}
    )
    assert res.transcript == "भैया payment Friday tak"
    assert res.language_detected == "hi-IN"
    assert res.confidence == 0.92
    assert res.raw_provider_response == {"status": "ok"}


def test_mock_asr_adapter():
    """Verify MockASRAdapter allows deterministic testing without network."""
    adapter = MockASRAdapter(default_transcript="Kal tak 50000 de dunga")
    result = adapter.transcribe("dummy_audio.m4a")
    
    assert isinstance(result, TranscriptionResult)
    assert result.transcript == "Kal tak 50000 de dunga"
    assert result.language_detected == "hinglish"
    assert result.raw_provider_response.get("provider") == "mock"


def test_sarvam_adapter_request_structure():
    """Verify SarvamASRAdapter formats requests with required headers and parameters."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "transcript": "भैया Monday tak 20000 de dunga",
        "language_code": "hi-IN",
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        adapter = SarvamASRAdapter(api_key="dummy_sarvam_key")
        
        # Test with bytes/io
        dummy_audio = io.BytesIO(b"fake_audio_bytes")
        result = adapter.transcribe(dummy_audio, filename="test.m4a", mode="codemix")
        
        assert mock_post.called
        call_args = mock_post.call_args
        
        # Check endpoint
        assert call_args[0][0] == "https://api.sarvam.ai/speech-to-text"
        
        # Check headers (auth subscription key)
        headers = call_args[1]["headers"]
        assert headers["api-subscription-key"] == "dummy_sarvam_key"
        
        # Check data payload
        data = call_args[1]["data"]
        assert data["model"] == "saaras:v3"
        assert data["mode"] == "codemix"
        
        # Check output transcription result
        assert result.transcript == "भैया Monday tak 20000 de dunga"
        assert result.language_detected == "hi-IN"
        assert result.raw_provider_response == mock_resp.json.return_value


def test_sarvam_adapter_error_handling():
    """Verify SarvamASRAdapter raises ASRError on API failure."""
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "Bad Request: Invalid audio format"

    with patch("requests.post", return_value=mock_resp):
        adapter = SarvamASRAdapter(api_key="dummy_sarvam_key")
        with pytest.raises(ASRError) as exc_info:
            adapter.transcribe(io.BytesIO(b"bad_audio"), filename="test.m4a")
        assert "400" in str(exc_info.value)


def test_asr_provider_factory_and_switching(monkeypatch):
    """Verify get_asr_adapter switches implementations cleanly via config."""
    monkeypatch.setenv("ASR_PROVIDER", "mock")
    adapter = get_asr_adapter()
    assert isinstance(adapter, MockASRAdapter)
    
    monkeypatch.setenv("ASR_PROVIDER", "sarvam")
    monkeypatch.setenv("SARVAM_API_KEY", "test_key")
    adapter = get_asr_adapter()
    assert isinstance(adapter, SarvamASRAdapter)
    
    monkeypatch.setenv("ASR_PROVIDER", "whisper")
    adapter = get_asr_adapter()
    assert isinstance(adapter, WhisperASRAdapter)
