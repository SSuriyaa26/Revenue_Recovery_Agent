"""Dashboard API Server — EDD Step 12, SPEC §7 & §8.3.

Provides REST endpoints for Merchant Dashboard & Judge Evaluation View:
- GET /api/metrics: Evaluation scorecard, 95% bootstrap CIs, dataset checksums, policy hashes
- GET /api/invoices: Current invoices and payment failure events with states & plinks
- GET /api/audit-trail: Append-only audit trail
- POST /api/evaluate: Triggers batch evaluation harness on demand
- POST /api/simulate-call: Interactive Hinglish utterance tester (Perception -> Policy -> Razorpay)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from contracts.invoice import InvoiceStatus
from evaluation_harness import EvaluationHarness
from event_consumer import handle_event, verify_razorpay_webhook_signature
from orchestrator import RevenueRecoveryOrchestrator
from payment_adapter import get_payment_adapter
from perception_service import PerceptionService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard_api")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
UI_DIR = PROJECT_ROOT / "ui"
EVAL_LATEST_PATH = DATA_DIR / "evaluation_latest.json"

app = FastAPI(
    title="AI Revenue Recovery Agent — Merchant Dashboard & Judge View",
    version="1.0.0",
    description="Evaluation-Driven Revenue Recovery Agent for Razorpay Merchants"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global evaluation harness instance
harness = EvaluationHarness()


class SimulateUtteranceRequest(BaseModel):
    utterance_text: str = Field(..., min_length=1, description="Hinglish / Hindi / English transcript")
    flow: str = Field(default="p2p", pattern=r"^(p2p|payment_failure)$")
    invoice_id: str = Field(default="INV-DEMO-001")
    original_amount: float = Field(default=100000.0, gt=0.0)
    current_state: str = Field(default="Open")
    reference_date_str: Optional[str] = Field(default=None, description="YYYY-MM-DD reference date")
    requested_discount_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)


# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------

@app.get("/api/metrics")
def get_metrics() -> dict[str, Any]:
    """Returns the latest evaluation scorecard metrics, 95% CIs, and checksums."""
    if not EVAL_LATEST_PATH.exists():
        # Run evaluation if not cached yet
        p2p_res = harness.evaluate_flow("p2p")
        pf_res = harness.evaluate_flow("payment_failure")
        harness.report(p2p_res, pf_res)

    with open(EVAL_LATEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/invoices")
def get_invoices() -> dict[str, Any]:
    """Returns sample active B2B invoices and payment failure events."""
    p2p_path = DATA_DIR / "p2p_held_out.json"
    pf_path = DATA_DIR / "payment_failure_held_out.json"

    p2p_items = []
    if p2p_path.exists():
        with open(p2p_path, "r", encoding="utf-8") as f:
            p2p_items = json.load(f)[:15]

    pf_items = []
    if pf_path.exists():
        with open(pf_path, "r", encoding="utf-8") as f:
            pf_items = json.load(f)[:15]

    return {
        "p2p_invoices": p2p_items,
        "payment_failures": pf_items,
    }


from store import get_audit_log


@app.get("/api/audit-trail")
def get_audit_trail() -> dict[str, Any]:
    """Returns the live audit log entries from the core in-memory store."""
    entries = get_audit_log()
    return {
        "total_entries": len(entries),
        "entries": entries[-50:],  # Return latest 50 entries
    }


@app.post("/api/evaluate")
def run_evaluation() -> dict[str, Any]:
    """Triggers an on-demand batch evaluation across held-out datasets."""
    try:
        p2p_res = harness.evaluate_flow("p2p")
        pf_res = harness.evaluate_flow("payment_failure")
        scorecard_text = harness.report(p2p_res, pf_res)
        return {
            "status": "success",
            "scorecard": scorecard_text,
            "p2p": p2p_res.model_dump(mode="json"),
            "payment_failure": pf_res.model_dump(mode="json"),
        }
    except Exception as e:
        logger.exception("Evaluation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/simulate-call")
def simulate_recovery_call(req: SimulateUtteranceRequest) -> dict[str, Any]:
    """Simulates an interactive Hinglish call utterance through the end-to-end pipeline."""
    ref_date = date.today()
    if req.reference_date_str:
        try:
            ref_date = datetime.strptime(req.reference_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    # Initialize perception service & live/mock payment adapter
    perception_svc = PerceptionService()
    payment_adapter = get_payment_adapter()

    orchestrator = RevenueRecoveryOrchestrator(
        perception_service=perception_svc,
        payment_adapter=payment_adapter,
    )

    try:
        inv_status = InvoiceStatus(req.current_state)
    except ValueError:
        inv_status = InvoiceStatus.OPEN

    result = orchestrator.process_utterance(
        utterance_text=req.utterance_text,
        invoice_id=req.invoice_id,
        original_amount=req.original_amount,
        current_state=inv_status,
        flow=req.flow,
        reference_date=ref_date,
        requested_discount_pct=req.requested_discount_pct
    )

    return result.model_dump(mode="json")


@app.post("/api/webhook")
async def receive_webhook(request: Request) -> dict[str, Any]:
    """Receives incoming Razorpay webhook notifications with HMAC-SHA256 signature verification."""
    body_bytes = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    # Webhook signature verification annotation:
    # Verifies HMAC-SHA256 signature before processing payload
    if not verify_razorpay_webhook_signature(body_bytes, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")

    event_data = {
        "invoice_id": payload.get("payload", {}).get("payment", {}).get("entity", {}).get("notes", {}).get("invoice_id")
        or payload.get("invoice_id")
        or "INV-UNKNOWN",
        "event_type": payload.get("event", "payment.captured"),
        "razorpay_event_id": payload.get("id") or payload.get("razorpay_event_id") or "evt_unknown",
    }

    actions = handle_event(event_data)
    return {
        "status": "processed" if actions else "duplicate_ignored",
        "actions_produced": len(actions),
        "actions": actions,
    }


# -----------------------------------------------------------------------------
# Static UI Assets
# -----------------------------------------------------------------------------

if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(str(UI_DIR / "index.html"))
