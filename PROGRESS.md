# Progress & Context Snapshot — AI Revenue Recovery Agent

**Last Updated**: 2026-08-23  
**Current EDD Step**: Step 11 Completed (Paused at Step 12 Merchant Dashboard)  
**Project Status**: On Track / Approx. 3.5 Days Ahead of 7-Day Schedule  

---

## 1. Executive Summary & Verification Commands

Steps 1 through 11 of the Evaluation-Driven Development (EDD) spec are **100% built, tested, and empirically verified**. The system connects Perception Service, Deterministic Policy Engine, Action Selector, Razorpay Payment Gateway Adapter (live sandbox verified), State Machine, Audit Logger, and Batch Evaluation Harness in an end-to-end operational pipeline.

### Verification Commands (Run from Project Root)
To verify the entire system state from scratch in a fresh session:

```powershell
# 1. Run the full unit and integration test suite (60 tests, all green)
python -m pytest tests/ -v

# 2. Run the batch evaluation harness across all held-out and adversarial sets
python scripts/evaluate_batch.py

# 3. Verify dataset integrity and checksum hashes
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
| **Step 10** | Razorpay API Adapter & Full Orchestration | **DONE** | `src/payment_adapter.py`, `src/orchestrator.py` live sandbox tested (plink creation, status check, error path, golden trajectory) |
| **Step 11** | Evaluation Harness & Held-Out Batch Scoring | **DONE** | `src/evaluation_harness.py`, `scripts/evaluate_batch.py` scored across all 4 held-out/adversarial datasets |
| **Step 12** | Merchant Dashboard / Judge View | **NOT STARTED** | Presentation layer scheduled next |
| **Step 13** | Live Demo Dry-Run & Fallback Preparation | **NOT STARTED** | Final verification step |

---

## 3. What Was Built & Verified Today

- **Batch Evaluation Harness (`src/evaluation_harness.py`, `scripts/evaluate_batch.py`)**:
  - Full evaluation across 70 held-out records + 24 adversarial records.
  - Computes Recovery Rate (with partial payment credit per SPEC §3.4), Naive Baseline Recovery Rate, Absolute Lift, and Cost-Weighted Error Rate ($w_{FP}=1.0, w_{FN}=4.0$).
  - Built-in deduplication cache (`data/.cache_eval_extractions.json`, SHA-256 keyed on transcript + prompt hash) allowing instant zero-quota regression evaluations (<0.01s).
  - Validates dataset SHA-256 checksum integrity against `data/checksums.json` before running.
  - Outputs reproducible `EvaluationResult` JSON artifacts (`data/evaluation_latest.json`).
- **Vendor-Agnostic Payment Adapter (`src/payment_adapter.py`)**: Typed contracts (`PaymentLinkResult`, `InvoiceStatusResult`) decoupling payment gateway APIs from core logic. Implements `RazorpayPaymentAdapter` (REST API with Basic Auth, amount-to-paise conversion, error handling) and `MockPaymentAdapter` (deterministic offline testing), switchable via `PAYMENT_GATEWAY_PROVIDER`.
- **End-to-End Orchestrator (`src/orchestrator.py`)**: Glues Perception Service $\to$ Policy Engine $\to$ Action Selector $\to$ Payment Gateway Adapter $\to$ State Machine $\to$ Audit Logger.
- **Vendor-Agnostic ASR Abstraction (`src/asr_adapter.py`)**: `TranscriptionResult` typed contract decoupling downstream extraction from vendors. Implements `SarvamASRAdapter` (Saaras v3 codemix mode with retries), `MockASRAdapter` (deterministic offline testing), and `WhisperASRAdapter` (swappable fallback via `ASR_PROVIDER` config).
- **Gemini / Groq Structured Commitment Extractor (`src/commitment_extractor.py`)**: Temperature=0.0 structured JSON extraction supporting Gemini (`gemini-3.7-flash` / `gemini-3.6-flash`) for live single-utterance use and Groq (`openai/gpt-oss-120b` / `llama-3.3-70b-versatile`) for high-throughput batch evaluation.
- **Deterministic Policy Engine (`src/policy_engine.py`)**: Network-isolated, LLM-free rule checks. Enforces per-flow discount caps (30% for P2P, 20% for Payment Failure), max retry attempt limits (3), and escalation stopping rules (2 broken promises). Verified zero socket access via mock patch tests.
- **State Machine (`src/state_machine.py`)**: Transition maps for Invoice and Payment Failure lifecycles. Raises `IllegalTransitionError` on illegal moves (e.g. `Paid -> Open`, `Escalated_Human -> P2P_Committed`) and audit-logs rejections.
- **Perception Gateway (`src/perception_gateway.py`)**: Sanitization gate enforcing Pydantic contracts. Rejects negative amounts, out-of-range split %, prompt injection payloads, and strips unrecognised fields.
- **Idempotency & Scheduler (`src/event_consumer.py`, `src/scheduler.py`, `src/store.py`)**: Handles duplicate webhooks via `(invoice_id, event_type, razorpay_event_id)` keying. Executes confirm-then-act checks before running scheduled follow-ups to prevent race conditions against landed payments.
- **Audit Logger (`src/audit_logger.py`)**: Append-only audit logger enforcing valid outcome enums (`VALID_OUTCOMES`).

---

## 4. Locked Decisions & Resolved Ambiguities

1. **Monolith Architecture**: Single Python (FastAPI) monolith. Core vs Perception kept as internal module boundaries (`src/core`, `src/perception_gateway.py`), NOT separate services.
2. **Authoritative Contracts**: EDD §5 contracts supersede SPEC §6.4 schema where they diverge.
3. **Null Amount Handling**: `committed_amount: null` in extraction means full remaining balance, enforced in business logic (Action Selector), not schema.
4. **Per-Flow Discount Caps**: `max_discount_pct_p2p = 30.0`, `max_discount_pct_payment_failure = 20.0` in `PolicyConfig`.
5. **Broken Promises**: `Partially_Paid -> Broken_Promise` increments `broken_promise_count` the same as fully unpaid promises.
6. **Duplicate Event Audit Trail**: Duplicate webhook deliveries produce 2 audit log entries total (1 for initial processing + 1 for duplicate ignored), maximizing judge transparency.
7. **Semantic Validation Gate Rule in Perception Gateway**: Payloads with `raw_transcript` + `confidence` but zero commitment fields (`committed_amount` and `committed_date` are both `None`) are routed to `exception_list` as `schema_validation_failed`.
8. **LLM Primary/Fallback Resilience & Batch Evaluation Provider Split**:
   - Live/interactive single extractions (demo, voice pipeline): Use `gemini-3.7-flash` (with fallback to `gemini-3.6-flash`).
   - High-throughput batch evaluation (Step 11 evaluation harness): Use Groq (`openai/gpt-oss-120b` / `llama-3.3-70b-versatile`) via `LLM_PROVIDER=groq` with local SHA-256 deduplication caching (`data/.cache_eval_extractions.json`).
9. **Vendor-Agnostic Payment Gateway Abstraction (`src/payment_adapter.py`)**: `PaymentLinkResult` and `InvoiceStatusResult` typed contracts decouple Razorpay REST API shapes and paise amount conversions from Action Selector, Policy Engine, and Event Consumer.
10. **State Machine Option 2 (Strict SPEC §6.8)**: `Open` state transitions are strictly `{"P2P_Committed", "Overdue"}`. On policy denial (e.g. over-cap discount), invoice status remains `Open`, while an escalation action and denial decision are append-logged to the audit trail.

---

## 5. What NOT to Touch Without Asking

> [!CAUTION]
> - **`data/p2p_held_out.json` & `data/payment_failure_held_out.json`**: Frozen held-out datasets. Any edits invalidate evaluation metrics and require re-running `scripts/freeze_datasets.py` (EDD §8.1).
> - **`src/policy_engine.py`**: Pure deterministic module. Must remain 100% free of network calls or LLM API calls.
> - **`src/contracts/`**: Frozen interface contracts. Modifications require team confirmation.
> - **`src/perception_gateway.py`**: Contains the adversarial routing logic. Needs review and validation against dev-set data before further tuning.

---

## 6. Empirical Evaluation Results (Scorecard §8.3)

Generated via `python scripts/evaluate_batch.py`:

| Metric | Flow 1 (B2B P2P) | Flow 2 (Payment Failure) |
|---|---|---|
| **Recovery Rate** | **33.5%** | **87.3%** |
| **Naive Baseline Recovery Rate** | **26.9%** | **19.3%** |
| **Absolute Lift over Baseline** | **+6.7%** | **+67.9%** |
| **Cost-Weighted Error Rate** | **0.343** | **0.229** |
| **Exception Count / Held-Out N** | **18 / 35** | **11 / 35** |
| **Guardrail Tests (Adversarial)** | **PASS** (12/12) | **PASS** (12/12) |
| **Idempotency / Race Tests** | **PASS** | **PASS** |
| **PolicyConfig Hash** | `2a8f2e301da7b336...` | `2a8f2e301da7b336...` |
| **Held-Out Checksum** | `e42295d2f02e9890...` | `85626a71b79ca845...` |

### Known Issues & Model Disclosure
- **Independent Live API Verification (Steps 10 & 11 Confirmed Real)**:
  - Razorpay Test-Mode Integration was independently verified via direct live GET calls to `https://api.razorpay.com/v1/payment_links/plink_TTGwFzhJGC5eFC` and `plink_TTGwL5ErAWdjGJ` (both returned HTTP 200 OK with matching short URLs and amounts).
  - Groq Batch Extraction was independently verified via live execution (35 real HTTP API calls completed across `p2p_held_out.json` and cached in `data/.cache_eval_extractions.json`).
- **P2P Exception Rate Calibration (Open Item for Review)**: Flow 1 P2P exception rate is 18/35 (51%) — need to manually review a sample of these tomorrow to confirm the confidence threshold is well-calibrated, not just conservative.
- **Step 11 Model Attribution Disclosure**: Step 11 batch metrics reflect Groq's (`openai/gpt-oss-120b` / `llama-3.3-70b-versatile`) extraction calibration across the 35 P2P held-out records, rather than Gemini 3.7 Flash, due to free-tier Google AI Studio daily quota limits (20 RPD cap on preview models). Single/interactive live tests continue to use Gemini.
- **Unverified Date Parsing on Real Speech**: `committed_date` parsing is **UNVERIFIED against real (non-TTS) speech** — the pilot test used TTS-generated audio, which may not reflect real speaker pacing on day+तक combinations (e.g. 'Wednesday tak'). Must be retested with real recorded voice before demo day, ideally before Day 6.

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

## 9. Tomorrow's Focus & Action Plan

1. **P2P Exception Rate Calibration Review**: Manually inspect the 18 P2P exceptions in `data/evaluation_latest.json` to confirm whether the 0.60 confidence threshold is appropriately filtering genuine ambiguities vs over-rejecting recoverable intent.
2. **Real-Voice Date Parsing Retest**: Record 3-4 real human voice samples for day+तक combinations ('Wednesday tak') to validate Saaras v3 + Gemini date extraction without TTS boundary artifacts.
3. **Step 12: Merchant Dashboard / Judge Evaluation View**: Build the interactive presentation UI showing live recovery metrics, active P2P cases, payment link statuses, and the auditable decision trail.
