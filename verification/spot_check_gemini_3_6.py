"""Spot-check Gemini 3.6 Flash on structured JSON schema and confidence calibration.

Tests:
1. Devanagari commitment with concrete date & amount
2. Roman Hinglish full balance commitment with specific date
3. Vague / evasive non-commitment (defensive date & confidence < 0.70)
4. Split percentage promise (50% split)
5. Adversarial / unrealistic demand (80% discount)
"""

import json
import os
import sys
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

# Ensure UTF-8 console output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add src to path
sys.path.insert(0, str(Path("src").resolve()))

load_dotenv()

from commitment_extractor import CommitmentExtractor

extractor = CommitmentExtractor(model_name="gemini-3.6-flash", temperature=0.0)

test_cases = [
    {
        "name": "1. Devanagari Concrete Amount & Date",
        "input": "Sir मैंने सोचा था कि इस week दे दूंगा but कुछ delay हो गया Monday तक 20000 भेज दूंगा बाकी next month",
        "ref_date": date(2026, 8, 20),  # Thursday
        "original_amt": 50000.0,
    },
    {
        "name": "2. Roman Hinglish Full Balance Commitment",
        "input": "I'll clear the full invoice by 25th no issues, bas ek do din ka time chahiye.",
        "ref_date": date(2026, 8, 20),  # Thursday
        "original_amt": 75000.0,
    },
    {
        "name": "3. Vague Intent / Ambiguous Date (Defensive Parsing)",
        "input": "Monday tak... ya phir... haan Monday, no wait Tuesday. Actually agle hafte kisi din de dunga.",
        "ref_date": date(2026, 8, 20),
        "original_amt": 30000.0,
    },
    {
        "name": "4. Split Percentage Promise (50% Split)",
        "input": "Abhi 50% de deta hoon, baaki next month first week me. 37500 abhi bhej do link.",
        "ref_date": date(2026, 8, 20),
        "original_amt": 75000.0,
    },
    {
        "name": "5. Adversarial Discount Demand / Evasion",
        "input": "3 lakh toh bahut zyada hai bhai ek baar me. 80% discount de do toh abhi de deta hoon.",
        "ref_date": date(2026, 8, 20),
        "original_amt": 300000.0,
    },
]

print("=" * 80)
print("SPOT CHECK RESULTS: GEMINI 3.6 FLASH (model='gemini-3.6-flash', temperature=0.0)")
print("=" * 80)

for tc in test_cases:
    print(f"\n--- {tc['name']} ---")
    print(f"  Input:         \"{tc['input']}\"")
    res = extractor.extract(
        tc["input"],
        reference_date=tc["ref_date"],
        original_amount=tc["original_amt"]
    )
    print(f"  Amount:        {res.committed_amount}")
    print(f"  Split %:       {res.split_pct}")
    print(f"  Date:          {res.committed_date}")
    print(f"  Confidence:    {res.confidence:.2f}")
    print(f"  Language:      {res.language_detected.value}")
    print(f"  Notes:         {res.extraction_notes}")
    time.sleep(3)

print("\n" + "=" * 80)
print("Spot check complete.")
