from datetime import date
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from contracts.perception_output import CommitmentExtraction, DetectedLanguage
from dashboard_api import app


@pytest.fixture
def client():
    return TestClient(app)


def test_get_metrics_endpoint(client):
    response = client.get("/api/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "p2p" in data
    assert "payment_failure" in data
    
    p2p = data["p2p"]
    assert p2p["recovery_rate"] > 0
    assert p2p["lift"] > 0
    assert "lift_ci_lower" in p2p
    assert "lift_ci_upper" in p2p
    assert p2p["ci_method"] == "paired_bootstrap_95"
    assert len(p2p["held_out_set_checksum"]) == 64
    assert len(p2p["policy_config_hash"]) == 64


def test_get_invoices_endpoint(client):
    response = client.get("/api/invoices")
    assert response.status_code == 200
    data = response.json()
    assert "p2p_invoices" in data
    assert "payment_failures" in data
    assert len(data["p2p_invoices"]) > 0


def test_get_audit_trail_endpoint(client):
    response = client.get("/api/audit-trail")
    assert response.status_code == 200
    data = response.json()
    assert "total_entries" in data
    assert "entries" in data


def test_simulate_call_golden_path(client):
    mock_ext = CommitmentExtraction(
        committed_amount=50000.0,
        split_pct=None,
        committed_date=date(2026, 8, 28),
        confidence=0.95,
        raw_transcript="Friday tak 50000 de dunga pakka.",
        language_detected=DetectedLanguage.HINGLISH,
        extraction_notes="Clear promise on Friday"
    )
    with patch("commitment_extractor.CommitmentExtractor.extract", return_value=mock_ext):
        payload = {
            "utterance_text": "Friday tak 50000 de dunga pakka.",
            "invoice_id": "INV-TEST-API-01",
            "original_amount": 50000.0,
            "flow": "p2p",
            "current_state": "Open"
        }
        response = client.post("/api/simulate-call", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["invoice_id"] == "INV-TEST-API-01"
        assert data["routed_to"] == "core_services"
        assert data["new_state"] == "P2P_Committed"
        assert data["payment_link"] is not None
        assert "rzp.io" in data["payment_link"]["short_url"] or "mock" in data["payment_link"]["short_url"]


def test_simulate_call_discount_exceeding_cap_escalates(client):
    mock_ext = CommitmentExtraction(
        committed_amount=40000.0,
        split_pct=None,
        committed_date=date(2026, 8, 28),
        confidence=0.90,
        raw_transcript="60% discount de do toh abhi deta hoon.",
        language_detected=DetectedLanguage.HINGLISH,
        extraction_notes="Discount request"
    )
    with patch("commitment_extractor.CommitmentExtractor.extract", return_value=mock_ext):
        payload = {
            "utterance_text": "60% discount de do toh abhi deta hoon.",
            "invoice_id": "INV-TEST-API-02",
            "original_amount": 100000.0,
            "requested_discount_pct": 60.0,
            "flow": "p2p",
            "current_state": "Open"
        }
        response = client.post("/api/simulate-call", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["policy_decision"]["decision"] == "DENIED"
        assert data["payment_link"] is None


def test_simulate_call_vague_input_routes_to_exception(client):
    mock_ext = CommitmentExtraction(
        committed_amount=None,
        split_pct=None,
        committed_date=None,
        confidence=0.35,
        raw_transcript="Hmm dekhte hain... pata nahi kab...",
        language_detected=DetectedLanguage.HINGLISH,
        extraction_notes="Vague stall"
    )
    with patch("commitment_extractor.CommitmentExtractor.extract", return_value=mock_ext):
        payload = {
            "utterance_text": "Hmm dekhte hain... pata nahi kab...",
            "invoice_id": "INV-TEST-API-03",
            "original_amount": 40000.0,
            "flow": "p2p",
            "current_state": "Open"
        }
        response = client.post("/api/simulate-call", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["routed_to"] == "exception_list"


def test_simulate_payment_endpoint(client):
    payload = {
        "invoice_id": "INV-TEST-PAY-01",
        "amount": 75000.0,
        "payment_method": "upi",
    }
    response = client.post("/api/simulate-payment", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["invoice_id"] == "INV-TEST-PAY-01"
    assert data["amount"] == 75000.0
    assert data["new_status"] == "Paid"
    assert "pay_sim_" in data["payment_id"]

    # Verify that get_invoices reflects the paid invoice
    inv_resp = client.get("/api/invoices")
    assert inv_resp.status_code == 200
    p2p_invs = inv_resp.json()["p2p_invoices"]
    paid_inv = next((inv for inv in p2p_invs if inv["invoice_id"] == "INV-TEST-PAY-01"), None)
    assert paid_inv is not None
    assert paid_inv["status"] == "Paid"
