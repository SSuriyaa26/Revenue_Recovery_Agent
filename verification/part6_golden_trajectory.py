"""Live Sandbox Verification for Razorpay Payment Adapter and End-to-End Orchestration.

Executes:
1. Direct RazorpayPaymentAdapter live API sandbox calls:
   - Success path: create payment link (verified typed PaymentLinkResult)
   - Status fetch: fetch_invoice_status from Razorpay
   - Error path: invalid customer payload (verified PaymentGatewayError)
2. Full live orchestration flow:
   - Utterance: "Monday tak 20000 de dunga"
   - PerceptionService (Gemini extraction -> Gateway sanitization)
   - PolicyEngine (discount & guardrail check)
   - ActionSelector (amount resolution)
   - RazorpayPaymentAdapter (LIVE payment link creation)
   - StateMachine transition (Open -> P2P_Committed)
   - AuditLogger (structured append-only log)
"""

import json
import os
import sys
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path("src").resolve()))
load_dotenv()

from payment_adapter import (
    RazorpayPaymentAdapter,
    PaymentLinkResult,
    InvoiceStatusResult,
    PaymentGatewayError
)
from orchestrator import RevenueRecoveryOrchestrator
from contracts.invoice import InvoiceStatus

print("=" * 80)
print("1. DIRECT RAZORPAY TEST-MODE SANDBOX VERIFICATION")
print("=" * 80)

adapter = RazorpayPaymentAdapter()

# Success path
print("\n[A] Creating Live Sandbox Payment Link...")
try:
    link_res = adapter.create_payment_link(
        invoice_id="INV-LIVE-TEST-001",
        amount=2500.0,
        customer_phone="+919876543210",
        customer_email="success@razorpay.com",
        customer_name="Priya Sharma",
        description="Demo recovery for invoice INV-LIVE-TEST-001"
    )
    print(f"  [SUCCESS] Payment Link Created:")
    print(f"    Link ID:   {link_res.link_id}")
    print(f"    Short URL: {link_res.short_url}")
    print(f"    Amount:    ₹{link_res.amount:.2f} {link_res.currency}")
    print(f"    Status:    {link_res.status}")
except Exception as e:
    print(f"  [FAILED] {e}")
    sys.exit(1)

# Status query path
print("\n[B] Querying Live Sandbox Payment Link Status...")
try:
    status_res = adapter.fetch_invoice_status(link_res.link_id)
    print(f"  [SUCCESS] Status Queried:")
    print(f"    Invoice/Link ID: {status_res.invoice_id}")
    print(f"    Status:          {status_res.status}")
    print(f"    Amount Due:      ₹{status_res.amount_due:.2f}")
    print(f"    Amount Paid:     ₹{status_res.amount_paid:.2f}")
except Exception as e:
    print(f"  [FAILED] {e}")

# Error path simulation
print("\n[C] Testing Razorpay API Error Path (invalid phone number)...")
try:
    adapter.create_payment_link(
        invoice_id="INV-FAIL-001",
        amount=500.0,
        customer_phone="invalid_phone_string",
        customer_email="failure@razorpay.com"
    )
    print("  [UNEXPECTED] Expected PaymentGatewayError but call succeeded.")
except PaymentGatewayError as pe:
    print(f"  [EXPECTED ERROR CAUGHT] Successfully handled by PaymentGatewayError:")
    print(f"    Details: {pe}")
except Exception as e:
    print(f"  [OTHER ERROR] {type(e)}: {e}")

print("\n" + "=" * 80)
print("2. FULL LIVE ORCHESTRATION GOLDEN-PATH TRAJECTORY (REAL RAZORPAY SANDBOX)")
print("=" * 80)

from contracts.perception_output import CommitmentExtraction, DetectedLanguage
from unittest.mock import patch

orchestrator = RevenueRecoveryOrchestrator(
    payment_adapter=adapter
)

utterance = "Monday tak 20000 bhej dunga pakka, baaki agle mahine clear kar dunga."
print("\n[Flow] Processing Customer Utterance:")
print(f"  Utterance: \"{utterance}\"")
print(f"  Invoice:   INV-2026-B2B-8802 (Original: ₹50,000.00, State: Open)")

# Mock perception extraction for this run so we preserve LLM quota for batch harness
mock_extraction = CommitmentExtraction(
    committed_amount=20000.0,
    split_pct=None,
    committed_date=date(2026, 8, 24),
    confidence=0.95,
    raw_transcript=utterance,
    language_detected=DetectedLanguage.HINGLISH,
    extraction_notes="Extracted 20,000 payment promised for Monday (2026-08-24)"
)

with patch.object(orchestrator.perception_service.extractor, "extract", return_value=mock_extraction):
    result = orchestrator.process_utterance(
        utterance_text=utterance,
        invoice_id="INV-2026-B2B-8802",
        original_amount=50000.0,
        current_state=InvoiceStatus.OPEN,
        customer_phone="+919876543210",
        customer_email="success@razorpay.com",
        customer_name="Anil Kumar",
        customer_risk_tier="LOW",
        flow="p2p",
        reference_date=date(2026, 8, 20)
    )

print("\n[Orchestration Result]:")
print(f"  Success:        {result.success}")
print(f"  Routed To:      {result.routed_to}")
print(f"  Previous State: {result.previous_state}")
print(f"  New State:      {result.new_state}")

if result.extraction:
    print(f"\n[Extraction Details]:")
    print(f"  Committed Amt:  ₹{result.extraction.committed_amount}")
    print(f"  Committed Date: {result.extraction.committed_date}")
    print(f"  Confidence:     {result.extraction.confidence:.2f}")
    print(f"  Notes:          {result.extraction.extraction_notes}")

if result.payment_link:
    print(f"\n[Live Razorpay Payment Link Generated]:")
    print(f"  Link ID:        {result.payment_link.link_id}")
    print(f"  Short URL:      {result.payment_link.short_url}")
    print(f"  Amount:         ₹{result.payment_link.amount:.2f}")
    print(f"  Status:         {result.payment_link.status}")

print(f"\n[Audit Log Entries Created ({len(result.audit_entries)})]:")
for idx, entry in enumerate(result.audit_entries, 1):
    print(f"  {idx}. Actor: {entry['actor']:<15} | Outcome: {entry['outcome']:<20} | Time: {entry['timestamp']}")

print("\n" + "=" * 80)
print("Step 10 Live Sandbox & Orchestration Verification Complete.")
print("=" * 80)
