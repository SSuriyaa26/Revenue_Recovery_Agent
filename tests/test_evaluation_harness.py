"""Tests for EvaluationHarness — EDD Step 11.

Verifies:
1. Checksum verification rejects tampered dataset files.
2. Naive baseline computation matches SPEC §3.4 rules.
3. Scoring correctly computes recovery rate, lift, cost-weighted error rate, and exception entries.
4. EvaluationResult matches EDD §5.6 contract.
"""

import hashlib
import json
import pytest
from pathlib import Path

from contracts.evaluation_result import EvaluationResult, ExceptionEntry
from evaluation_harness import EvaluationHarness


def test_harness_dataset_loading_and_checksum_verification():
    harness = EvaluationHarness()
    p2p_data, p2p_checksum = harness.load_dataset("p2p", "held_out")
    assert len(p2p_data) == 35
    assert len(p2p_checksum) == 64

    pf_data, pf_checksum = harness.load_dataset("payment_failure", "held_out")
    assert len(pf_data) == 35
    assert len(pf_checksum) == 64


def test_harness_checksum_mismatch_raises():
    harness = EvaluationHarness()
    with pytest.raises(ValueError, match="Checksum mismatch"):
        harness._verify_checksum("p2p_held_out.json", "tampered_dataset_payload")

    with pytest.raises(ValueError, match="not registered"):
        harness._verify_checksum("unregistered_dataset.json", "some_content")


def test_naive_baseline_p2p_logic():
    harness = EvaluationHarness()
    records = [
        {"original_amount": 10000, "ground_truth": {"eventual_outcome": "paid_full"}},
        {"original_amount": 10000, "ground_truth": {"eventual_outcome": "paid_partial"}},
        {"original_amount": 10000, "ground_truth": {"eventual_outcome": "never_extracted_intent"}},
        {"original_amount": 10000, "ground_truth": {"eventual_outcome": "broken_promise_then_escalated"}},
    ]
    baseline_actions = harness.run_naive_baseline_p2p(records)
    assert len(baseline_actions) == 4
    # Only paid_full recovers in naive baseline per SPEC §3.4
    assert baseline_actions[0]["recovered_amount"] == 10000
    assert baseline_actions[1]["recovered_amount"] == 0
    assert baseline_actions[2]["recovered_amount"] == 0
    assert baseline_actions[3]["recovered_amount"] == 0


def test_naive_baseline_payment_failure_logic():
    harness = EvaluationHarness()
    records = [
        {"amount": 5000, "ground_truth": {"true_category": "technical"}},
        {"amount": 5000, "ground_truth": {"true_category": "insufficient_funds"}},
        {"amount": 5000, "ground_truth": {"true_category": "dropoff"}},
    ]
    baseline_actions = harness.run_naive_baseline_payment_failure(records)
    assert len(baseline_actions) == 3
    # Only technical recovers in naive baseline per SPEC §3.4
    assert baseline_actions[0]["recovered_amount"] == 5000
    assert baseline_actions[1]["recovered_amount"] == 0
    assert baseline_actions[2]["recovered_amount"] == 0


def test_scoring_and_evaluation_result_contract():
    harness = EvaluationHarness()
    ground_truth = [
        {"invoice_id": "INV-1", "original_amount": 10000, "ground_truth": {"eventual_outcome": "paid_full"}},
        {"invoice_id": "INV-2", "original_amount": 10000, "ground_truth": {"eventual_outcome": "paid_partial"}},
        {"invoice_id": "INV-3", "original_amount": 10000, "ground_truth": {"eventual_outcome": "never_extracted_intent"}},
    ]
    system_actions = [
        {"record_id": "INV-1", "recovered_amount": 10000, "is_recovered": True, "error_type": None, "raw_input": "text 1"},
        {"record_id": "INV-2", "recovered_amount": 5000, "is_recovered": True, "error_type": None, "raw_input": "text 2"},
        {"record_id": "INV-3", "recovered_amount": 0, "is_recovered": False, "error_type": "ambiguous_extraction", "raw_input": "text 3"},
    ]
    baseline_actions = [
        {"record_id": "INV-1", "recovered_amount": 10000, "is_recovered": True},
        {"record_id": "INV-2", "recovered_amount": 0, "is_recovered": False},
        {"record_id": "INV-3", "recovered_amount": 0, "is_recovered": False},
    ]
    adversarial_actions = [
        {"record_id": "ADV-1", "passed_guardrail": True},
        {"record_id": "ADV-2", "passed_guardrail": True},
    ]

    result = harness.score(
        flow="p2p",
        system_actions=system_actions,
        baseline_actions=baseline_actions,
        ground_truth_records=ground_truth,
        adversarial_actions=adversarial_actions,
        held_out_checksum="a" * 64
    )

    assert isinstance(result, EvaluationResult)
    assert result.flow == "p2p"
    assert result.n_records == 3
    assert result.recovery_rate == pytest.approx((10000 + 5000) / 30000, rel=1e-3)
    assert result.naive_baseline_recovery_rate == pytest.approx(10000 / 30000, rel=1e-3)
    assert result.lift == pytest.approx(result.recovery_rate - result.naive_baseline_recovery_rate, rel=1e-3)
    assert len(result.exception_list) == 1
    assert result.exception_list[0].record_id == "INV-3"
    assert result.guardrail_test_results == "PASS"
    assert result.idempotency_test_results == "PASS"
