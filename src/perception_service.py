"""Perception Service Orchestrator — EDD Step 9.

Glues the vendor-agnostic ASR Adapter, CommitmentExtractor (LLM intent extraction),
and the Perception Gateway (schema & semantic validation) into an end-to-end
perception pipeline.
"""

from __future__ import annotations

from datetime import date
import io
from pathlib import Path
from typing import Any, Optional, Union

from asr_adapter import ASRAdapter, get_asr_adapter
from commitment_extractor import CommitmentExtractor
from contracts.perception_output import CommitmentExtraction
from perception_gateway import ingest_extraction


class PerceptionService:
    """End-to-end Perception pipeline for Voice and Text inputs."""

    def __init__(
        self,
        asr_adapter: Optional[ASRAdapter] = None,
        extractor: Optional[CommitmentExtractor] = None,
        confidence_threshold: float = 0.70,
    ):
        self.asr_adapter = asr_adapter or get_asr_adapter()
        self.extractor = extractor or CommitmentExtractor()
        self.confidence_threshold = confidence_threshold

    def process_audio(
        self,
        audio_source: Union[str, Path, io.BufferedIOBase, bytes],
        filename: Optional[str] = None,
        reference_date: Optional[date] = None,
        original_amount: Optional[float] = None,
        mode: str = "codemix",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Transcribe audio and extract structured payment commitment.

        Routes through the Perception Gateway for strict schema validation.
        """
        # Step 1: ASR Transcription
        try:
            transcription = self.asr_adapter.transcribe(
                audio_source, filename=filename, mode=mode, **kwargs
            )
        except Exception as e:
            return {
                "routed_to": "exception_list",
                "reason": "asr_transcription_failed",
                "details": str(e),
            }

        # Step 2: Intent & Commitment Extraction
        return self.process_text(
            transcription.transcript,
            reference_date=reference_date,
            original_amount=original_amount,
        )

    def process_text(
        self,
        raw_text: str,
        reference_date: Optional[date] = None,
        original_amount: Optional[float] = None,
    ) -> dict[str, Any]:
        """Extract structured payment commitment from raw text/transcript and validate."""
        # Step 1: LLM Extraction
        try:
            extraction: CommitmentExtraction = self.extractor.extract(
                raw_text,
                reference_date=reference_date,
                original_amount=original_amount,
            )
        except Exception as e:
            return {
                "routed_to": "exception_list",
                "reason": "extraction_failed",
                "details": str(e),
            }

        # Step 2: Confidence threshold check (EDD §6.1 / SPEC §6.4)
        if extraction.confidence < self.confidence_threshold:
            return {
                "routed_to": "exception_list",
                "reason": "low_confidence",
                "details": (
                    f"Extraction confidence {extraction.confidence:.2f} is below "
                    f"threshold {self.confidence_threshold:.2f}."
                ),
                "raw_transcript": extraction.raw_transcript,
                "notes": extraction.extraction_notes,
            }

        # Step 3: Perception Gateway Schema & Semantic Gate
        payload = extraction.model_dump(mode="json")
        return ingest_extraction(payload)


def get_perception_service() -> PerceptionService:
    """Factory to create a default PerceptionService instance."""
    return PerceptionService()
