# AI Revenue Recovery Agent

> **Razorpay AI Buildathon 2026**

Razorpay merchants lose revenue through three failure modes that today's generic dunning tools handle poorly: informal B2B payment promises made over WhatsApp voice notes in Hinglish ("Monday tak 50 hazaar de dunga"), abandoned checkouts during bank peak-hour outages, and failed UPI mandate retries on blind 24-hour intervals that ignore salary-cycle liquidity. This project is a bounded, policy-gated recovery agent — not a free-form LLM — that detects revenue at risk, extracts structured intent from colloquial Indian speech, and executes auditable recovery workflows through Razorpay's payment APIs, with every money-affecting decision made by deterministic rules rather than model output.

---

## Why This Isn't a Thin LLM Wrapper

> *This is the project's core architectural claim, pulled from [spec §6.7](revenue-recovery-spec.md).*

Most AI recovery demos are an LLM prompted to sound like a collections agent, wired to one or two API calls, evaluated on a handful of hand-picked examples. That's a demo, not a system.

The LLM in this system has exactly **two jobs**:

1. **Extract** structured fields (amount, date, split %) from unstructured Hinglish input.
2. **Generate** natural-language customer-facing text from an *already-decided* action.

It **never decides** *whether* to retry, *how much* discount to offer, or *when* to escalate. Those are outputs of the deterministic Policy Engine operating on the LLM's extracted fields. The money-affecting decision surface is fully independent of the model and is unit-testable without ever calling an LLM.

This separation is the architectural answer to the most obvious skeptical question: *"Couldn't this just be a ChatGPT prompt?"* No — because:

- The **Policy Engine** ([`policy_engine.py`](src/policy_engine.py)) is pure-function, zero-network, zero-LLM. Discount caps (30% P2P, 20% Payment Failure), retry caps (3), and escalation stop rules (2 broken promises) are enforced deterministically. This is verified by unit tests that mock-patch `socket.socket` to confirm zero network access.
- The **State Machine** ([`state_machine.py`](src/state_machine.py)) enforces legal transitions with `IllegalTransitionError` on invalid moves (e.g., `Paid → Open`).
- The **Perception Gateway** ([`perception_gateway.py`](src/perception_gateway.py)) sits between the LLM and core services as a sanitization gate — rejecting negative amounts, out-of-range splits, and prompt injection payloads before they reach any business logic.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         INPUT LAYER                                │
│   Voice Note (.m4a/.wav)  │  Text Transcript  │  Webhook Event     │
└──────────────┬────────────┴────────┬──────────┴────────┬───────────┘
               │                     │                   │
       ┌───────▼────────┐    ┌───────▼────────┐   ┌──────▼──────────┐
       │   ASR Adapter   │    │  (text bypass) │   │ Event Consumer  │
       │ ┌─────────────┐ │    │                │   │ (idempotent,    │
       │ │Sarvam Saaras│ │    │                │   │  composite-key  │
       │ │  v3 (live)  │ │    │                │   │  deduplication) │
       │ └─────────────┘ │    │                │   └──────┬──────────┘
       └───────┬─────────┘    └───────┬────────┘          │
               │                      │                   │
       ┌───────▼──────────────────────▼──┐                │
       │  🤖 Commitment Extractor (LLM)  │                │
       │  Gemini 3.7 Flash / Groq        │                │
       │  (temperature=0.0, structured   │                │
       │   JSON output, with fallback)   │                │
       └───────────────┬─────────────────┘                │
                       │                                  │
       ┌───────────────▼──────────────┐                   │
       │  Perception Gateway          │                   │
       │  (Pydantic validation,       │                   │
       │   injection filtering,       │                   │
       │   confidence threshold)      │                   │
       └───────────────┬──────────────┘                   │
                       │                                  │
       ════════════════╪══════════════════════════════════╪══════════
        LLM-driven ↑   │   ↓ Deterministic from here     │
       ════════════════╪══════════════════════════════════╪══════════
                       │                                  │
       ┌───────────────▼──────────────────────────────────▼──┐
       │           Deterministic Policy Engine               │
       │  • Discount caps (30% P2P / 20% PF)                │
       │  • Retry caps (max 3 attempts)                      │
       │  • Escalation stop (2 broken promises → human)      │
       │  • Zero network calls, zero LLM calls               │
       └───────────────┬────────────────────────────────────-┘
                       │
       ┌───────────────▼──────────────┐
       │      State Machine           │
       │  (formal lifecycle guards,   │
       │   IllegalTransitionError)    │
       └───────────────┬──────────────┘
                       │
       ┌───────────────▼──────────────┐
       │  Payment Adapter (Razorpay)  │
       │  • Payment link creation     │
       │  • Invoice status lookup     │
       │  • Amount → paise conversion │
       │  • Test-mode sandbox (live)  │
       └───────────────┬──────────────┘
                       │
       ┌───────────────▼──────────────┐
       │     Audit Logger             │
       │  (append-only, typed         │
       │   outcomes, every action     │
       │   + trigger + rule logged)   │
       └──────────────────────────────┘
```

> **Note on `System Architecture.png`**: The [existing diagram](System%20Architecture.png) in the repo shows the spec's idealized dual-service architecture (Java/Spring Boot core, React frontend). The actual build is a **Python/FastAPI monolith** with vanilla HTML/JS/CSS. The diagram is useful for understanding the conceptual layer separation but does not reflect the implementation stack. It needs updating to match the built system.

---

## Quickstart

### Prerequisites

- Python ≥ 3.11

### Setup

```bash
git clone <repo-url>
cd Revenue_Recovery_Agent

python -m venv venv

# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### Run Tests

```bash
python -m pytest tests/ -v
```

All 67 tests should pass. Tests use mocks for external APIs — no API keys required.

### Launch the Dashboard

The dashboard server **must** be run with `--app-dir src` because `dashboard_api.py` imports from `contracts`, `orchestrator`, etc. as top-level modules relative to `src/`. Running without `--app-dir` fails with `ModuleNotFoundError: No module named 'contracts'`.

```bash
uvicorn dashboard_api:app --app-dir src --port 8000 --reload
```

Then open [http://localhost:8000](http://localhost:8000).

### Environment Variables

Create a `.env` file in the project root (`.env` is gitignored):

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | LLM backend for commitment extraction (`gemini` or `groq`) |
| `GEMINI_API_KEY` | *(none)* | Google AI Studio API key for Gemini 3.7 Flash |
| `GROQ_API_KEY` | *(none)* | Groq API key for batch evaluation |
| `ASR_PROVIDER` | `sarvam` | Speech-to-text backend (`sarvam`, `mock`, or `whisper`) |
| `SARVAM_API_KEY` | *(none)* | Sarvam AI API key for Hinglish ASR |
| `PAYMENT_GATEWAY_PROVIDER` | `mock` | Payment backend (`razorpay` or `mock`) |
| `RAZORPAY_KEY_ID` | *(none)* | Razorpay test-mode key ID |
| `RAZORPAY_KEY_SECRET` | *(none)* | Razorpay test-mode key secret |

#### Graceful degradation behavior

| Component | No API key set | Behavior |
|---|---|---|
| **ASR** (`sarvam`) | Missing `SARVAM_API_KEY` | ✅ Falls back to `MockASRAdapter` silently |
| **Payment** (`razorpay`) | Missing `RAZORPAY_KEY_ID/SECRET` | ✅ Falls back to `MockPaymentAdapter` with warning |
| **LLM** (`gemini` or `groq`) | Missing API key | ⚠️ **Raises `ValueError` — does NOT degrade gracefully.** There is no mock LLM provider. The interactive playground (`POST /api/simulate-call`) and batch evaluation both require a valid LLM API key. Set `GEMINI_API_KEY` or `GROQ_API_KEY` before using these features. |

---

## Live Evaluation Results

Scored on **frozen held-out datasets** (SHA-256 checksummed, never used for tuning) via the batch evaluation harness. Numbers pulled from [`data/evaluation_latest.json`](data/evaluation_latest.json), generated `2026-08-24T10:47:30`.

| Metric | Flow 1: B2B P2P | Flow 2: Payment Failure |
|---|---|---|
| **Recovery Rate** | 41.9% | 87.3% |
| **Naive Baseline** | 26.9% | 19.3% |
| **Absolute Lift** | **+15.0 pp** | **+67.9 pp** |
| **95% CI (paired bootstrap, B=2000)** | [+5.8%, +28.0%] | [+37.7%, +82.6%] |
| **Cost-Weighted Error Rate** (w_FP=1.0, w_FN=4.0) | 0.000 | 0.229 |
| **Exception Count / N** | 15 / 35 | 11 / 35 |
| **Guardrail Tests (adversarial)** | PASS (12/12) | PASS (12/12) |
| **Idempotency / Race Tests** | PASS | PASS |
| **Held-Out Checksum** | `e42295d2...` | `85626a71...` |
| **PolicyConfig Hash** | `2a8f2e30...` | `2a8f2e30...` |
| **LLM Provider** | Groq (`openai/gpt-oss-120b`) | *(deterministic — no LLM)* |

> **Note**: P2P batch metrics reflect Groq extraction calibration, not Gemini 3.7 Flash, due to Google AI Studio free-tier daily quota limits. Single/interactive live tests use Gemini.

---

## Known Limitations

**Stated honestly — these are real, not hedged.**

### 1. P2P "No Extraction" Exception Rate: 15/35 (42.8%)

Fifteen of 35 held-out P2P records produced no actionable extraction. After auditing, these break down as:
- **Genuinely ambiguous stalls** (8 records): Vague date phrases like "Monday ya agle hafte", "dekh ke batata hoon", self-contradicting amounts ("5000... wait 9000... actually 90000?"), or outright refusals ("business down hai").
- **Over-cap discount requests** (2 records): 70% and 50% discounts exceed the 30% P2P cap and are correctly denied by the Policy Engine.
- **Records with clear commitments that the LLM failed to extract** (5 records): e.g. "2 lakh de dunga Thursday tak" — the LLM returned extraction data but the Perception Gateway routed them to exception_list. These represent genuine extraction/routing calibration gaps.

The 42.8% exception rate is high. It reflects both genuinely unrecoverable inputs (correct behavior) and extraction gaps (improvable).

### 2. No Mock LLM Provider

The `CommitmentExtractor` requires either a Gemini or Groq API key. Unlike the ASR and Payment adapters, there is **no `LLM_PROVIDER=mock` fallback**. This means:
- The Interactive Recovery Playground tab in the dashboard does not work without a valid API key.
- `python -m pytest` passes without keys (tests mock the extractor internally), but the live dashboard's `/api/simulate-call` endpoint will error.

### 3. `committed_date` Parsing Unverified on Real Speech

Date parsing (e.g., "Wednesday tak" → next Wednesday) has only been tested against TTS-generated audio, not real recorded human speech. Real speaker pacing and disfluencies on day+तक combinations may produce different ASR transcripts that break date resolution.

### 4. `System Architecture.png` Out of Date

The diagram shows Java/Spring Boot and React — the actual build is Python/FastAPI with vanilla HTML/JS/CSS. The conceptual layer separation is accurate; the technology labels are not.

### 5. Step 13 (Live Demo Dry-Run) Not Started

Per [PROGRESS.md](PROGRESS.md), Steps 1–12 are complete. Step 13 (live demo dry-run and fallback preparation) has not been started.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **API Server** | FastAPI + Uvicorn |
| **Data Contracts** | Pydantic v2 (8 schema models in `src/contracts/`) |
| **LLM Extraction** | Gemini 3.7 Flash (live/interactive) / Groq `openai/gpt-oss-120b` (batch), temperature=0.0, structured JSON output |
| **ASR** | Sarvam AI Saaras v3 (Hinglish codemix mode) |
| **Payment Gateway** | Razorpay Payment Links API (test mode) — **independently verified against the live sandbox** via direct HTTP GET calls returning 200 OK with matching amounts and short URLs (not just simulated) |
| **Frontend** | Vanilla HTML / CSS / JavaScript (dark-theme dashboard with 3 tabs) |
| **Tests** | pytest (67 tests: unit, integration, adversarial, idempotency) |
| **Evaluation** | Custom batch harness with SHA-256 dataset checksums, paired bootstrap CIs, cost-weighted error rates |

---

## Repository Structure

```
├── src/
│   ├── contracts/          # 8 Pydantic data models (frozen interfaces)
│   ├── orchestrator.py     # End-to-end pipeline glue
│   ├── perception_service.py
│   ├── commitment_extractor.py  # Gemini / Groq structured extraction
│   ├── asr_adapter.py      # Sarvam / Mock / Whisper ASR
│   ├── perception_gateway.py    # Validation + injection filtering gate
│   ├── policy_engine.py    # Pure deterministic rules (zero network)
│   ├── state_machine.py    # Formal lifecycle transitions
│   ├── payment_adapter.py  # Razorpay live / Mock adapter
│   ├── audit_logger.py     # Append-only audit trail
│   ├── evaluation_harness.py
│   ├── event_consumer.py   # Idempotent webhook handler
│   ├── scheduler.py        # Confirm-then-act follow-up executor
│   ├── store.py            # In-memory state + audit store
│   └── dashboard_api.py    # FastAPI REST + static file server
├── ui/                     # Frontend (index.html, style.css, app.js)
├── tests/                  # 67 tests (13 test files)
├── scripts/                # evaluate_batch.py, freeze_datasets.py, secret_scanner.py
├── data/                   # Frozen datasets, checksums, evaluation results
├── verification/           # Independent live API verification scripts
├── revenue-recovery-spec.md   # Full 52K-word project specification
├── evaluation-spec.md         # Evaluation-Driven Development spec
├── PROGRESS.md                # Detailed build status & decisions
└── requirements.txt
```

---

## License

Built for the Razorpay AI Buildathon 2026. Not licensed for production use.
