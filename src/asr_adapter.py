"""Vendor-Agnostic ASR Adapter Abstraction — EDD Step 9.

Provides a unified interface and normalized data contract (TranscriptionResult)
so that downstream intent extraction is 100% decoupled from specific speech-to-text
providers (Sarvam AI, Whisper, Mock, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import io
import os
from pathlib import Path
import time
from typing import Any, Optional, Union

from pydantic import BaseModel, Field
import requests


class TranscriptionResult(BaseModel):
    """Normalized output contract for any ASR provider."""
    transcript: str = Field(..., min_length=1, description="Transcribed text in Hinglish/Hindi/English")
    language_detected: str = Field(default="hinglish", description="Detected language / script code")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="ASR model confidence if provided")
    raw_provider_response: dict[str, Any] = Field(default_factory=dict, description="Raw provider metadata")


class ASRError(Exception):
    """Raised when an ASR provider request fails."""
    pass


class ASRAdapter(ABC):
    """Abstract base class for speech-to-text adapters."""

    @abstractmethod
    def transcribe(
        self,
        audio_source: Union[str, Path, io.BufferedIOBase, bytes],
        filename: Optional[str] = None,
        mode: str = "codemix",
        **kwargs: Any,
    ) -> TranscriptionResult:
        """Transcribe an audio file/stream into a normalized TranscriptionResult.

        Args:
            audio_source: File path, open file-like object, or raw bytes.
            filename: Optional filename to hint audio format (e.g. 'audio.m4a').
            mode: Transcription mode (e.g. 'codemix', 'transcribe', 'translate').
            kwargs: Provider-specific options.

        Returns:
            A normalized TranscriptionResult instance.
        """
        pass


class SarvamASRAdapter(ASRAdapter):
    """Sarvam AI Saaras v3 ASR adapter."""

    ENDPOINT = "https://api.sarvam.ai/speech-to-text"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("SARVAM_API_KEY")
        if not self.api_key:
            raise ValueError("SARVAM_API_KEY must be provided or set in environment")

    def _determine_mime_type(self, filename: str) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix in [".m4a", ".mp4", ".aac"]:
            return "audio/mp4"
        elif suffix in [".wav"]:
            return "audio/wav"
        elif suffix in [".mp3"]:
            return "audio/mpeg"
        elif suffix in [".ogg", ".opus"]:
            return "audio/ogg"
        elif suffix in [".flac"]:
            return "audio/flac"
        return "application/octet-stream"

    def transcribe(
        self,
        audio_source: Union[str, Path, io.BufferedIOBase, bytes],
        filename: Optional[str] = None,
        mode: str = "codemix",
        **kwargs: Any,
    ) -> TranscriptionResult:
        name = filename or "audio.m4a"
        if isinstance(audio_source, (str, Path)):
            p = Path(audio_source)
            if not filename:
                name = p.name
            with open(p, "rb") as f:
                audio_bytes = f.read()
        elif isinstance(audio_source, (io.BufferedIOBase, io.RawIOBase)):
            audio_bytes = audio_source.read()
        elif isinstance(audio_source, bytes):
            audio_bytes = audio_source
        else:
            raise ValueError(f"Unsupported audio_source type: {type(audio_source)}")

        mime_type = self._determine_mime_type(name)
        headers = {
            "api-subscription-key": self.api_key,
        }
        data = {
            "model": "saaras:v3",
            "mode": mode
        }

        resp = None
        last_err = None
        for attempt in range(3):
            files = {
                "file": (name, io.BytesIO(audio_bytes), mime_type)
            }
            try:
                resp = requests.post(self.ENDPOINT, headers=headers, files=files, data=data, timeout=30)
                if resp.status_code == 200:
                    break
            except Exception as e:
                last_err = e
            time.sleep(1.0 * (attempt + 1))

        if resp is None:
            raise ASRError(f"Sarvam AI network connection failed after 3 retries: {last_err}")

        if resp.status_code != 200:
            raise ASRError(f"Sarvam AI request failed [{resp.status_code}]: {resp.text}")

        try:
            resp_json = resp.json()
        except Exception as e:
            raise ASRError(f"Failed to parse Sarvam AI response as JSON: {e}") from e

        transcript = resp_json.get("transcript", "").strip()
        lang_code = resp_json.get("language_code", "hi-IN")
        confidence = resp_json.get("confidence")

        if not transcript:
            raise ASRError("Sarvam AI returned an empty transcript")

        return TranscriptionResult(
            transcript=transcript,
            language_detected=lang_code,
            confidence=confidence if isinstance(confidence, (int, float)) else None,
            raw_provider_response=resp_json,
        )


class MockASRAdapter(ASRAdapter):
    """Deterministic mock ASR adapter for testing without external networks."""

    def __init__(
        self,
        default_transcript: str = "Bhaiya, kal tak 50000 de dunga pakka.",
        default_language: str = "hinglish",
        default_confidence: float = 0.95,
    ):
        self.default_transcript = default_transcript
        self.default_language = default_language
        self.default_confidence = default_confidence

    def transcribe(
        self,
        audio_source: Union[str, Path, io.BufferedIOBase, bytes],
        filename: Optional[str] = None,
        mode: str = "codemix",
        **kwargs: Any,
    ) -> TranscriptionResult:
        transcript = kwargs.get("transcript", self.default_transcript)
        return TranscriptionResult(
            transcript=transcript,
            language_detected=self.default_language,
            confidence=self.default_confidence,
            raw_provider_response={"provider": "mock", "mode": mode},
        )


class WhisperASRAdapter(ASRAdapter):
    """Fallback Whisper ASR adapter placeholder for secondary vendor swap."""

    def __init__(self, api_key: Optional[str] = None, model_name: str = "whisper-1"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model_name

    def transcribe(
        self,
        audio_source: Union[str, Path, io.BufferedIOBase, bytes],
        filename: Optional[str] = None,
        mode: str = "codemix",
        **kwargs: Any,
    ) -> TranscriptionResult:
        # Skeleton implementation for Whisper swap
        raise NotImplementedError("Whisper fallback adapter configured but OpenAI/local whisper execution not triggered.")


def get_asr_adapter(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    **kwargs: Any,
) -> ASRAdapter:
    """Factory function returning the configured ASR adapter.

    Configured via ASR_PROVIDER environment variable ('sarvam', 'mock', 'whisper').
    """
    prov = (provider or os.getenv("ASR_PROVIDER", "sarvam")).lower().strip()

    if prov == "sarvam":
        return SarvamASRAdapter(api_key=api_key)
    elif prov == "mock":
        return MockASRAdapter(**kwargs)
    elif prov == "whisper":
        return WhisperASRAdapter(api_key=api_key)
    else:
        raise ValueError(f"Unknown ASR provider: {prov}. Choose 'sarvam', 'mock', or 'whisper'.")
