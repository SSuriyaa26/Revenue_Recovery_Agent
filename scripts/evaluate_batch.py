"""Batch Evaluation Runner — EDD Step 11.

Executes batch evaluation across:
1. P2P Held-Out (35 records) + Adversarial (12 records)
2. Payment Failure Held-Out (35 records) + Adversarial (12 records)

Using Groq (llama-3.3-70b-versatile) with SHA-256 deduplication cache.
Outputs the quantitative evaluation scorecard per SPEC §8.3.
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
load_dotenv()

from evaluation_harness import EvaluationHarness


def main():
    print("=" * 85)
    print("  AI REVENUE RECOVERY AGENT — HELD-OUT BATCH EVALUATION HARNESS")
    print("=" * 85)

    start_time = time.time()
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    print(f"LLM Provider: {provider.upper()}")
    print("Executing batch evaluation across frozen held-out and adversarial sets...\n")

    harness = EvaluationHarness(llm_provider=provider)

    # 1. Flow 1: B2B Promise-to-Pay
    print("[1/2] Evaluating Flow 1 (Promise-to-Pay Recovery)...")
    p2p_t0 = time.time()
    p2p_res = harness.evaluate_flow("p2p")
    p2p_elapsed = time.time() - p2p_t0
    print(f"      Completed {p2p_res.n_records} held-out + 12 adversarial records in {p2p_elapsed:.2f}s")

    # 2. Flow 2: Payment Failure / Checkout Recovery
    print("[2/2] Evaluating Flow 2 (Payment Failure Recovery)...")
    pf_t0 = time.time()
    pf_res = harness.evaluate_flow("payment_failure")
    pf_elapsed = time.time() - pf_t0
    print(f"      Completed {pf_res.n_records} held-out + 12 adversarial records in {pf_elapsed:.2f}s")

    total_elapsed = time.time() - start_time
    print(f"\nTotal Batch Evaluation Time: {total_elapsed:.2f}s (Budget: < 90s)\n")

    # Render scorecard
    scorecard = harness.report(p2p_res, pf_res)
    print(scorecard)

    # Print Exception List details
    print("\n" + "=" * 85)
    print("  DETAILED EXCEPTION LIST (UNRESOLVED CASES)")
    print("=" * 85)

    print(f"\n[Flow 1: P2P Exceptions ({len(p2p_res.exception_list)} records)]:")
    for idx, exc in enumerate(p2p_res.exception_list, 1):
        print(f"  {idx:02d}. [{exc.record_id}] Reason: {exc.reason}")
        print(f"      Raw Input: \"{exc.raw_input}\"")

    print(f"\n[Flow 2: Payment Failure Exceptions ({len(pf_res.exception_list)} records)]:")
    for idx, exc in enumerate(pf_res.exception_list, 1):
        print(f"  {idx:02d}. [{exc.record_id}] Reason: {exc.reason}")
        print(f"      Raw Event: \"{exc.raw_input}\"")

    print("\n" + "=" * 85)
    print("Batch evaluation artifacts saved to: data/evaluation_latest.json")
    print("=" * 85)


if __name__ == "__main__":
    main()
