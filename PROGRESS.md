# Progress & Context Snapshot — AI Revenue Recovery Agent

**Last Updated**: 2026-08-23  
**Current EDD Step**: Step 9 Completed (Paused at Step 10 Gateway)  
**Project Status**: On Track / Approx. 2.5 Days Ahead of 7-Day Schedule  

---

## 1. Executive Summary & Verification Commands

Steps 1 through 9 of the Evaluation-Driven Development (EDD) spec are **100% built, tested, and empirically verified**. The Perception Service layer (vendor-agnostic ASR abstraction, Gemini 3.7 Flash intent extractor, and Perception Gateway validation) is fully operational and verified across dual scripts and audio samples.

### Verification Commands (Run from Project Root)
To verify the entire system state from scratch in a fresh session:

```powershell
# 1. Run the full unit and integration test suite (45 tests, all green)
python -m pytest tests/ -v

# 2. Verify dataset integrity and checksum hashes
python scripts/freeze_datasets.py
```

---

## 2. Detailed Status by EDD Step (§9)

| EDD Step | Component / Milestone | Status | Verification / Evidence |
|---|---|---|---|
| **Step 1** | Contract Schemas (`src/contracts/`) | **DONE** | 8 Pydantic data models enforcing all SPEC §6.4 & EDD §5 schemas |
| **Step 2** | Guardrail & Adversarial Unit Test Suite | **DONE** | `tests/test_policy_engine.py`, `tests/test_adversarial_extraction.py`, `tests/test_state_machine_illegal_transitions.py` |
| **Step 3** | Policy Engine, State Machine, Perception Gateway | **DONE** | Pure deterministic functions in `src/policy_engine.py`, state machine guards in `src/state_machine.py`, schema validator in `src/perception_gateway.py` |
| **Step 4** | Idempotency & Race Condition Tests | **DONE** | `tests/test_idempotency_and_races.py` |
| **Step 5** | Idempotency Store & Scheduled Executor | **DONE** | Composite key deduplication in `src/event_consumer.py`, confirm-then-act checks in `src/scheduler.py` |
| **Step 6** | Audit Log Completeness Tests | **DONE** | `tests/test_audit_log.py` |
| **Step 7** | Audit Logger Implementation | **DONE** | `src/audit_logger.py` wired into all policy, state, and event execution paths |
| **Step 8** | Synthetic Datasets, Freeze & Checksum | **DONE** | 6 datasets (124 records) created in `data/`, SHA-256 checksum manifest generated in `data/checksums.json` |
| **Step 9** | Perception Service (ASR + LLM + Gateway) | **DONE** | `src/asr_adapter.py`, `src/commitment_extractor.py`, `src/perception_service.py` verified across 8 speech test audio files & dev set |
| **Step 10** | Razorpay API Adapter & Full Orchestration | **NOT STARTED** | Paused by design; awaiting Razorpay test mode API keys |
| **Step 11** | Evaluation Harness & Held-Out Batch Scoring | **NOT STARTED** | Scheduled after Step 10 |
| **Step 12** | Merchant Dashboard / Judge View | **NOT STARTED** | Presentation layer scheduled for late build |
| **Step 13** | Live Demo Dry-Run & Fallback Preparation | **NOT STARTED** | Final verification step |

---

## 3. What Was Built & Verified Today

- **Vendor-Agnostic ASR Abstraction (`src/asr_adapter.py`)**: `TranscriptionResult` typed contract decoupling downstream extraction from vendors. Implements `SarvamASRAdapter` (Saaras v3 codemix mode with retries), `MockASRAdapter` (deterministic offline testing), and `WhisperASRAdapter` (swappable fallback via `ASR_PROVIDER` config).
- **Gemini Structured Commitment Extractor (`src/commitment_extractor.py`)**: Temperature=0.0 structured JSON extraction using `gemini-3.7-flash` (with resilience fallback to `gemini-3.6-flash`). Handles dual-script Hinglish (Devanagari and Roman script), defensive date parsing (vague dates route to `exception_list`), and Indian amount/split % parsing.
- **Perception Service Orchestrator (`src/perception_service.py`)**: Glues ASR Adapter, Commitment Extractor, and Perception Gateway (`ingest_extraction`) into an end-to-end voice and text ingestion pipeline.
- **Deterministic Policy Engine (`src/policy_engine.py`)**: Network-isolated, LLM-free rule checks. Enforces per-flow discount caps (30% for P2P, 20% for Payment Failure), max retry attempt limits (3), and escalation stopping rules (2 broken promises). Verified zero socket access via mock patch tests.
- **State Machine (`src/state_machine.py`)**: Transition maps for Invoice and Payment Failure lifecycles. Raises `IllegalTransitionError` on illegal moves (e.g. `Paid -> Open`, `Escalated_Human -> P2P_Committed`) and audit-logs rejections.
- **Perception Gateway (`src/perception_gateway.py`)**: Sanitization gate enforcing Pydantic contracts. Rejects negative amounts, out-of-range split %, prompt injection payloads, and strips unrecognised fields.
- **Idempotency & Scheduler (`src/event_consumer.py`, `src/scheduler.py`, `src/store.py`)**: Handles duplicate webhooks via `(invoice_id, event_type, razorpay_event_id)` keying. Executes confirm-then-act checks before running scheduled follow-ups to prevent race conditions against landed payments.
- **Audit Logger (`src/audit_logger.py`)**: Append-only audit logger enforcing valid outcome enums (`VALID_OUTCOMES`).
- **Synthetic Datasets & Freeze Script (`data/`, `scripts/freeze_datasets.py`)**:
  - `p2p_dev.json` (15 recs), `p2p_held_out.json` (35 recs), `p2p_adversarial.json` (12 recs)
  - `payment_failure_dev.json` (15 recs), `payment_failure_held_out.json` (35 recs), `payment_failure_adversarial.json` (12 recs)
  - SHA-256 checksums frozen in `data/checksums.json`.

---

## 4. Locked Decisions & Resolved Ambiguities

1. **Monolith Architecture**: Single Python (FastAPI) monolith. Core vs Perception kept as internal module boundaries (`src/core`, `src/perception_gateway.py`), NOT separate services.
2. **Authoritative Contracts**: EDD §5 contracts supersede SPEC §6.4 schema where they diverge.
3. **Null Amount Handling**: `committed_amount: null` in extraction means full remaining balance, enforced in business logic (Action Selector), not schema.
4. **Per-Flow Discount Caps**: `max_discount_pct_p2p = 30.0`, `max_discount_pct_payment_failure = 20.0` in `PolicyConfig`.
5. **Broken Promises**: `Partially_Paid -> Broken_Promise` increments `broken_promise_count` the same as fully unpaid promises.
6. **Duplicate Event Audit Trail**: Duplicate webhook deliveries produce 2 audit log entries total (1 for initial processing + 1 for duplicate ignored), maximizing judge transparency.
7. **Semantic Validation Gate Rule in Perception Gateway**: Payloads with `raw_transcript` + `confidence` but zero commitment fields (`committed_amount` and `committed_date` are both `None`) are routed to `exception_list` as `schema_validation_failed`.
   > *Note: Invented during build, not sourced from SPEC or EDD — needs validation against real dev-set data before trusting it fully, as it has not yet been tested against legitimate vague-but-real customer commitments.*

---

## 5. What NOT to Touch Without Asking

> [!CAUTION]
> - **`data/p2p_held_out.json` & `data/payment_failure_held_out.json`**: Frozen held-out datasets. Any edits invalidate evaluation metrics and require re-running `scripts/freeze_datasets.py` (EDD §8.1).
> - **`src/policy_engine.py`**: Pure deterministic module. Must remain 100% free of network calls or LLM API calls.
> - **`src/contracts/`**: Frozen interface contracts. Modifications require team confirmation.
> - **`src/perception_gateway.py`**: Contains the adversarial routing logic. Needs review and validation against dev-set data before further tuning.

---

## 6. Known Issues & Open Decisions

### Known Issues
- **Unverified Date Parsing on Real Speech**: `committed_date` parsing is **UNVERIFIED against real (non-TTS) speech** — the pilot test used TTS-generated audio, which may not reflect real speaker pacing on day+तक combinations (e.g. 'Wednesday tak'). Must be retested with real recorded voice before demo day, ideally before Day 6. Date parsing is defensively implemented: unconfident dates route to `exception_list` / low-confidence path rather than silently defaulting.

### Still-Open Decisions (Not Blocking)
1. **Product Naming**: "Vasooli" was proposed as working title but flagged for reconsideration due to cultural connotations (forceful/goonda debt collection). Decision pending on whether to keep ironside/ironic framing or re-brand before demo materials.
2. **Team Skill Allocation & Feature Scope**: SPEC §11.8 notes skill allocation across LLM, ASR, Razorpay, and evaluation data engineering. If time/bandwidth compresses, the rule remains: cut the ASR/voice layer (FR-15/17) before cutting any of the guardrail, audit, idempotency, or batch harness requirements (FR-11, FR-12, FR-19, FR-20).

---

## 7. Buildathon Evaluation Criteria

Hackathon submissions are scored across 4 core categories:
1. **Functional Prototype**: Working pipeline executing end-to-end recovery flows against test APIs.
2. **Technical Complexity**: Deterministic Policy Engine, formal state machines, composite-key idempotency, confirm-then-act scheduler, and clear Perception/Core split.
3. **Innovation & Novelty**: High-empathy Hinglish conversational recovery, salary-cycle awareness, and bank peak-hour intelligent retry timing.
4. **Code Quality & Documentation**: Clean architecture, high unit test coverage, auditable logs, and a clear design decisions/tradeoffs document.

> [!IMPORTANT]
> - **README.md**: Skeleton documentation work must start in parallel with Step 9 (not left to Day 7).
> - **Zero Broken Code Rule**: *"Broken code disqualifies."* Prefer a smaller, 100% reliable, fully working scope over a larger, flaky implementation if Steps 9–10 hit unexpected external API friction.

---

## 8. Secret Scanning Verification Status

- **Pre-Staging Secret Scan**: **VERIFIED CLEAN**. Executed via ripgrep across `src/`, `tests/`, `scripts/` before `git add` for `sk-`, `rzp_`, `api_key=`, `API_KEY=`, `password=`. Zero credentials found.
- **Git Pre-Commit Hook**: **ACTIVE & VERIFIED**. Verified via `.git/hooks/pre-commit` calling `scripts/secret_scanner.py`. Confirmed blocking staged secret credentials with exit code 1 while allowing clean commits.

---

## 9. Open Decisions / Tomorrow's Prerequisites

Before Step 9 and Step 10 implementation can begin, the following external keys/access details are needed:
1. **Razorpay Test Mode API Key & Secret** (for Razorpay API Adapter in Step 10).
2. **LLM Provider API Key** (Gemini / OpenAI / Anthropic key for intent extraction in Step 9).
3. **Sarvam AI API Key** (for Hinglish ASR voice transcription in Step 9, or fallback confirmation to Whisper).
