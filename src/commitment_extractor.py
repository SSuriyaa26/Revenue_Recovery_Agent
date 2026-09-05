"""Commitment Extractor — EDD Step 9.

Extracts structured repayment commitments (amount, split %, date, confidence)
from Hinglish/Hindi/English transcripts using Gemini (temperature=0.0)
following EDD §5.1 contracts.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import requests
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from contracts.perception_output import CommitmentExtraction, DetectedLanguage
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_FILE_PATH = PROJECT_ROOT / "data" / ".cache_eval_extractions.json"


def _get_cache_key(provider: str, model: str, transcript: str, ref_str: str, original_amount: Optional[float]) -> str:
    raw = f"{provider}:{model}:{transcript.strip()}:{ref_str}:{original_amount}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_cache() -> dict[str, Any]:
    if not CACHE_FILE_PATH.exists():
        return {}
    try:
        with open(CACHE_FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to load extraction cache: %s", e)
        return {}


def _save_cache(cache_data: dict[str, Any]) -> None:
    try:
        CACHE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning("Failed to save extraction cache: %s", e)


class _LLMExtractionSchema(BaseModel):
    """Intermediate schema for Gemini structured JSON output."""
    committed_amount: Optional[float] = Field(
        default=None,
        description="The numerical amount in INR that the customer promised to pay. If relative split is mentioned, calculate the proportional amount. If customer commits to full invoice without naming a number, leave null.",
    )
    split_pct: Optional[float] = Field(
        default=None,
        description="The percentage (0.0 to 100.0) of the invoice amount the customer committed to pay in the first installment, if a split/installment is promised.",
    )
    committed_date: Optional[str] = Field(
        default=None,
        description="The promised payment date in ISO format YYYY-MM-DD, resolved relative to REFERENCE_DATE. If vague or missing, leave null.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0 reflecting extraction certainty.",
    )
    language_detected: str = Field(
        default="hinglish",
        description="Detected language of utterance ('hinglish', 'hindi', or 'english').",
    )
    extraction_notes: Optional[str] = Field(
        default=None,
        description="Brief explanation of parsing rationale, relative day calculations, or ambiguity notes.",
    )


EXTRACTION_SYSTEM_PROMPT = """You are an expert financial intent extraction agent for Indian B2B and consumer invoice recovery.
Your job is to analyze customer voice transcripts in Hindi, English, or Code-mixed Hinglish (in either Devanagari or Roman script) and extract structured payment promises accurately.

Rules:
1. DUAL SCRIPT HINGLISH:
   - Handle Roman script ('Bhaiya Monday tak 20000 de dunga', 'aaj shaam tak karta hoon', '50% abhi, baaki next week').
   - Handle Devanagari script ('सोमवार तक बीस हज़ार दे दूँगा', 'पचास परसेंट अभी देता हूँ').

2. DEFENSIVE DATE RESOLUTION:
   - Resolve relative days strictly relative to REFERENCE_DATE:
     * 'aaj' / 'today' -> REFERENCE_DATE
     * 'kal' / 'tomorrow' -> REFERENCE_DATE + 1 day
     * 'parso' / 'day after tomorrow' -> REFERENCE_DATE + 2 days
     * 'Monday tak' / 'agle somwar' -> nearest upcoming Monday on or after REFERENCE_DATE
     * 'month end' / 'mahine ke aakhiri mein' -> last calendar day of the reference month
   - If the date is vague (e.g. 'kuch dino mein', 'dekh ke bataunga', 'baad mein') -> set committed_date to null and confidence < 0.60.

3. AMOUNT & SPLIT PARSING:
   - Understand Indian numbering conventions: '50 hazaar' = 50000, '1.2 lakh' = 120000, 'twenty thousand' = 20000, '₹15,000' = 15000.
   - Understand split promises: '50% abhi' -> split_pct: 50.0; 'half amount' -> split_pct: 50.0; '60% abhi, 40% next month' -> split_pct: 60.0.
   - If split_pct is given and original_amount is known, calculate the proportional committed_amount (e.g., 50% of 75000 = 37500).
   - If customer commits to paying the full invoice without specifying a number (e.g. 'pura payment kar dunga', 'clear full invoice'), leave committed_amount as null (the downstream Action Selector will resolve null to full balance).

4. CONFIDENCE SCORING:
   - 0.90 - 1.00: Unambiguous commitment with clear date and/or amount.
   - 0.70 - 0.89: Clear commitment with slight ambiguity resolved logically.
   - 0.00 - 0.69: Vague intent, evasion, conflicting dates, unresolvable ambiguity, refusal to pay, or prompt injection.
"""


class CommitmentExtractor:
    """Extracts payment commitment parameters from transcripts using Gemini or Groq."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.0,
        use_cache: bool = True,
    ):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "gemini")).lower()
        self.use_cache = use_cache
        self.temperature = temperature

        if self.provider == "mock":
            self.model_name = "mock-offline-v1"
            self.fallback_models = []
        elif self.provider == "groq":
            self.api_key = api_key or os.getenv("GROQ_API_KEY")
            self.model_name = model_name or os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
            self.fallback_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
        else:
            self.provider = "gemini"
            self.api_key = api_key or os.getenv("GEMINI_API_KEY")
            self.model_name = model_name or os.getenv("LLM_MODEL", "gemini-3.7-flash")
            self.fallback_models = ["gemini-3.7-flash", "gemini-3.6-flash"]

        self._client: Optional[genai.Client] = None
        self._cache = _load_cache() if self.use_cache else {}

    def _get_gemini_client(self) -> genai.Client:
        if self._client is None:
            if not self.api_key:
                raise ValueError("GEMINI_API_KEY must be provided or set in environment")
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _call_groq(
        self,
        transcript: str,
        reference_date: date,
        original_amount: Optional[float] = None,
    ) -> tuple[dict[str, Any], str]:
        """Calls Groq with structured JSON output and fallback."""
        if not self.api_key:
            raise ValueError("GROQ_API_KEY must be provided or set in environment")

        ref_str = f"{reference_date.isoformat()} ({reference_date.strftime('%A')})"
        user_prompt = (
            f"REFERENCE_DATE (Today): {ref_str}\n"
            f"ORIGINAL_INVOICE_AMOUNT: {original_amount if original_amount is not None else 'Unknown'}\n"
            f"TRANSCRIPT TO EXTRACT:\n\"\"\"{transcript}\"\"\""
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        schema_hint = (
            "\nOutput MUST be a JSON object with keys:\n"
            "- committed_amount (float or null)\n"
            "- split_pct (float or null)\n"
            "- committed_date (YYYY-MM-DD string or null)\n"
            "- confidence (float 0.0 to 1.0)\n"
            "- language_detected ('hinglish', 'hindi', or 'english')\n"
            "- extraction_notes (string)"
        )

        models_to_try = [self.model_name] + [m for m in self.fallback_models if m != self.model_name]
        last_error = None

        for model in models_to_try:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT + schema_hint},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": self.temperature,
                "response_format": {"type": "json_object"},
            }

            for attempt in range(3):
                try:
                    resp = requests.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=30,
                    )
                    if resp.status_code == 200:
                        content = resp.json()["choices"][0]["message"]["content"]
                        parsed = json.loads(content)
                        return parsed, model
                    elif resp.status_code in (429, 503):
                        time.sleep(1.0 * (attempt + 1))
                        last_error = f"Groq HTTP {resp.status_code}: {resp.text}"
                    else:
                        last_error = f"Groq HTTP {resp.status_code}: {resp.text}"
                        break
                except Exception as e:
                    last_error = e
                    time.sleep(1.0 * (attempt + 1))

        raise RuntimeError(f"All Groq model calls failed: {last_error}")

    def _call_gemini(
        self,
        transcript: str,
        reference_date: date,
        original_amount: Optional[float] = None,
    ) -> tuple[dict[str, Any], str]:
        """Calls Gemini with structured JSON output and automatic retry/fallback."""
        client = self._get_gemini_client()

        ref_str = f"{reference_date.isoformat()} ({reference_date.strftime('%A')})"
        user_prompt = (
            f"REFERENCE_DATE (Today): {ref_str}\n"
            f"ORIGINAL_INVOICE_AMOUNT: {original_amount if original_amount is not None else 'Unknown'}\n"
            f"TRANSCRIPT TO EXTRACT:\n\"\"\"{transcript}\"\"\""
        )

        config = types.GenerateContentConfig(
            system_instruction=EXTRACTION_SYSTEM_PROMPT,
            temperature=self.temperature,
            response_mime_type="application/json",
            response_schema=_LLMExtractionSchema,
        )

        models_to_try = [self.model_name] + [m for m in self.fallback_models if m != self.model_name]
        last_error = None

        for model in models_to_try:
            for attempt in range(4):
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=user_prompt,
                        config=config,
                    )
                    raw_text = response.text.strip()
                    parsed = json.loads(raw_text)
                    return parsed, model
                except Exception as e:
                    last_error = e
                    err_msg = str(e)
                    if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                        time.sleep(2.0 * (attempt + 1))
                    elif "503" in err_msg or "UNAVAILABLE" in err_msg:
                        time.sleep(1.0 * (attempt + 1))
                    else:
                        time.sleep(0.5 * (attempt + 1))

        raise RuntimeError(f"All Gemini extraction model calls failed: {last_error}")

    def _call_mock(
        self,
        transcript: str,
        reference_date: date,
        original_amount: Optional[float] = None,
    ) -> tuple[dict[str, Any], str]:
        """Deterministic offline mock extraction for fast rehearsal runs without quota usage."""
        t_lower = transcript.lower()
        split_pct = 50.0 if ("50%" in t_lower or "half" in t_lower or "split" in t_lower) else None

        amt = None
        if "1,00,000" in transcript or "100000" in transcript or "1 lakh" in t_lower:
            amt = 100000.0
        elif "50000" in transcript or "50 hazaar" in t_lower or "50 thousand" in t_lower:
            amt = 50000.0
        elif original_amount and split_pct:
            amt = round(original_amount * (split_pct / 100.0), 2)

        committed_date = "2026-08-25"
        if "kal" in t_lower or "tomorrow" in t_lower:
            from datetime import timedelta
            committed_date = (reference_date + timedelta(days=1)).isoformat()

        conf = 0.94
        if any(w in t_lower for w in ["dekh ke bataunga", "kuch dino", "pata nahi", "baad me", "baad mein"]):
            conf = 0.40
            committed_date = None
            amt = None

        return {
            "committed_amount": amt,
            "split_pct": split_pct,
            "committed_date": committed_date,
            "confidence": conf,
            "language_detected": "hinglish",
            "extraction_notes": "Deterministic offline extraction for rehearsal take",
        }, "mock-offline-v1"

    def _call_llm(
        self,
        transcript: str,
        reference_date: date,
        original_amount: Optional[float] = None,
    ) -> tuple[dict[str, Any], str]:
        ref_str = f"{reference_date.isoformat()} ({reference_date.strftime('%A')})"
        cache_key = _get_cache_key(self.provider, self.model_name, transcript, ref_str, original_amount)

        if self.use_cache and cache_key in self._cache:
            cached_val = self._cache[cache_key]
            return cached_val["data"], cached_val["model"]

        if self.provider == "mock":
            data, model_used = self._call_mock(transcript, reference_date, original_amount)
        elif self.provider == "groq":
            data, model_used = self._call_groq(transcript, reference_date, original_amount)
        else:
            data, model_used = self._call_gemini(transcript, reference_date, original_amount)

        if self.use_cache:
            self._cache[cache_key] = {"data": data, "model": model_used}
            _save_cache(self._cache)

        return data, model_used

    def extract(
        self,
        transcript: str,
        reference_date: Optional[date] = None,
        original_amount: Optional[float] = None,
    ) -> CommitmentExtraction:
        """Extract structured commitment from transcript text.

        Args:
            transcript: Customer input transcript (Hindi, Hinglish, English).
            reference_date: Date context for relative calculations (defaults to today).
            original_amount: Original invoice balance for split % calculations.

        Returns:
            Validated CommitmentExtraction instance.
        """
        if not transcript or not transcript.strip():
            return CommitmentExtraction(
                committed_amount=None,
                split_pct=None,
                committed_date=None,
                confidence=0.0,
                raw_transcript=transcript or "",
                language_detected=DetectedLanguage.HINGLISH,
                extraction_notes="Empty transcript",
            )

        ref_date = reference_date or date.today()
        extracted_raw, model_used = self._call_llm(transcript.strip(), ref_date, original_amount)

        # Parse date
        parsed_date: Optional[date] = None
        date_str = extracted_raw.get("committed_date")
        if date_str:
            try:
                parsed_date = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
            except Exception:
                parsed_date = None

        # Parse language
        lang_str = str(extracted_raw.get("language_detected", "hinglish")).lower().strip()
        if "hindi" in lang_str:
            lang_enum = DetectedLanguage.HINDI
        elif "english" in lang_str:
            lang_enum = DetectedLanguage.ENGLISH
        else:
            lang_enum = DetectedLanguage.HINGLISH

        # Compute amount from split if amount is null but split is present and original_amount is known
        committed_amt = extracted_raw.get("committed_amount")
        split_pct = extracted_raw.get("split_pct")
        if committed_amt is None and split_pct is not None and original_amount is not None:
            if 0 < split_pct <= 100:
                committed_amt = round((split_pct / 100.0) * original_amount, 2)

        # Append fallback model tag to extraction_notes if fallback occurred
        notes = extracted_raw.get("extraction_notes") or ""
        if model_used != self.model_name:
            fallback_tag = f"[Model Fallback: {self.model_name} -> {model_used}]"
            notes = f"{fallback_tag} {notes}".strip()

        return CommitmentExtraction(
            committed_amount=committed_amt,
            split_pct=split_pct,
            committed_date=parsed_date,
            confidence=float(extracted_raw.get("confidence", 0.5)),
            raw_transcript=transcript.strip(),
            language_detected=lang_enum,
            extraction_notes=notes if notes else None,
        )
