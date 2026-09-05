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

![AI Revenue Recovery Agent — System Architecture (as built)](System%20Architecture%20%28Built%29.png)

> **Key architectural boundary**: Everything above the "LLM boundary" line is non-deterministic (ASR, LLM extraction). Everything below is **pure deterministic** — zero network calls, zero LLM calls, fully unit-testable. This is the system's core safety claim.

<details>
<summary>Original spec diagram (conceptual reference — does not match implementation stack)</summary>

The [original spec diagram](System%20Architecture.png) shows the idealized dual-service architecture (Java/Spring Boot core, React frontend, normalized SQL). The actual build is a **Python/FastAPI monolith** with vanilla HTML/JS/CSS and in-memory state. Retained for conceptual layer comparison only.

</details>

---

## Quickstart

### Prerequisites

- Python ≥ 3.11

### Setup

```bash
git clone https://github.com/SSuriyaa26/Revenue_Recovery_Agent.git
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

### Run the Demo Runner & Reset

To run the scripted golden-trajectory demo sequence end-to-end without manual typing:

```bash
# Reset in-memory state before a demo take
python scripts/reset_demo_state.py

# Run demo with interactive pauses for narration (press Enter between beats)
python scripts/run_demo.py

# Run automated playback (hands-free)
python scripts/run_demo.py --auto --timed 2.0

# Run with live APIs (Sarvam / Groq / Razorpay)
python scripts/run_demo.py --live
```

### Environment Variables

Copy `.env.example` to `.env` in the project root (`.env` is gitignored):

```bash
cp .env.example .env
```

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | LLM backend for commitment extraction (`gemini`, `groq`, or `mock`) |
| `GEMINI_API_KEY` | *(none)* | Google AI Studio API key for Gemini 3.7 Flash |
| `GROQ_API_KEY` | *(none)* | Groq API key for batch evaluation |
| `ASR_PROVIDER` | `sarvam` | Speech-to-text backend (`sarvam`, `mock`, or `whisper`) |
| `SARVAM_API_KEY` | *(none)* | Sarvam AI API key for Hinglish ASR |
| `PAYMENT_GATEWAY_PROVIDER` | `mock` | Payment backend (`razorpay` or `mock`) |
| `RAZORPAY_KEY_ID` | *(none)* | Razorpay test-mode key ID |
| `RAZORPAY_KEY_SECRET` | *(none)* | Razorpay test-mode key secret |
| `RAZORPAY_WEBHOOK_SECRET` | *(none)* | Webhook secret for HMAC-SHA256 signature verification |

#### Graceful degradation behavior

| Component | No API key set | Behavior |
|---|---|---|
| **ASR** (`sarvam`) | Missing `SARVAM_API_KEY` | ✅ Falls back to `MockASRAdapter` silently |
| **Payment** (`razorpay`) | Missing `RAZORPAY_KEY_ID/SECRET` | ✅ Falls back to `MockPaymentAdapter` with warning |
| **LLM** (`gemini` or `groq`) | Missing API key / Rehearsal | ✅ Falls back to `MockOffline` extraction or cached responses (`.cache_eval_extractions.json`) |

---

## Live Evaluation Results

Scored on **frozen held-out datasets** (SHA-256 checksummed, never used for tuning) via the batch evaluation harness. Numbers pulled from [`data/evaluation_latest.json`](data/evaluation_latest.json):

```bash
python scripts/evaluate_batch.py
```

| Metric | Flow 1: P2P (Pre-Cal)* | Flow 1: P2P (Post-Cal)* | Flow 2: Payment Failure |
|---|---|---|---|
| **Recovery Rate** | 33.5% | 41.9% | 87.3% |
| **Naive Baseline** | 26.9% | 26.9% | 19.3% |
| **Absolute Lift** | **+6.7 pp** | **+15.0 pp** | **+67.9 pp** |
| **95% CI (paired bootstrap, B=2000)** | [+0.0%, +15.5%] | [+5.8%, +28.0%] | [+37.7%, +82.6%] |
| **Cost-Weighted Error Rate** (w_FP=1.0, w_FN=4.0) | 0.343 | 0.000 | 0.229 |
| **Exception Count / N** | 18 / 35 | 15 / 35 | 11 / 35 |
| **Guardrail Tests (adversarial)** | PASS (12/12) | PASS (12/12) | PASS (12/12) |
| **Idempotency / Race Tests** | PASS | PASS | PASS |
| **Held-Out Checksum** | `e42295d2...` | `e42295d2...` | `85626a71...` |
| **PolicyConfig Hash** | `2a8f2e30...` | `2a8f2e30...` | `2a8f2e30...` |
| **LLM Provider** | Groq (`llama-3.3-70b`) | Groq (`llama-3.3-70b`) | *(deterministic — no LLM)* |

*\* **Change Control Disclosure (EDD §8.1)**: Pre-calibration metrics reflect an initial evaluation harness regex bug that treated split percentages ("60% abhi") as discount requests (3 False Negatives). Scoping the regex to discount keywords resolved the issue. Both pre- and post-calibration metrics are reported for full transparency (see EDD §8.1 Change Control Log `CC-2026-08-24-01`).*

> **Note on LLM Provider**: P2P batch metrics reflect Groq extraction calibration, not Gemini 3.7 Flash, due to Google AI Studio free-tier daily quota limits. Single/interactive live tests use Gemini.

---

## Known Limitations

**Stated honestly — these are real, not hedged.**

### 1. P2P "No Extraction" / Unrecovered Exception Rate: 15/35 (42.8%)

Fifteen of 35 held-out P2P records ended in unrecovered status or exception routing:
- **Genuinely ambiguous stalls & refusals** (9 records): Vague phrases ("Monday ya agle hafte", "dekh ke batata hoon"), self-contradicting amounts ("5000... wait 9000... confuse ho gaya"), or outright refusals ("business down hai"). Correctly routed to exception list (0 False Positives).
- **Over-cap discount requests** (2 records): 70% and 50% discount demands exceed the 30% P2P cap and are correctly denied by the Policy Engine.
- **Broken promises escalated without recovery** (4 records): e.g. "2 lakh de dunga Thursday tak" (INV-HO-021) — commitment was extracted, but customer repeatedly missed promises in simulation and escalated to human collection per policy stopping rules ($0 recovery credit).

The 42.8% exception rate reflects defensive policy bounding and realistic unrecovered debt rather than system hallucination.

### 2. `committed_date` Parsing on Real Speech

Date parsing (e.g., "Wednesday tak" → next Wednesday) has been tested against TTS and audio test fixtures. Extreme speaker pacing and disfluencies on complex multi-clause sentences may produce varying ASR transcripts that require clarification.

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

### Why Python Instead of Java?

The [original spec](revenue-recovery-spec.md) calls for a Java/Spring Boot core service with a separate Python/FastAPI perception microservice. We deliberately built the entire system as a **Python/FastAPI monolith** instead. Here's why:

1. **AI-native ecosystem fit**: The core value of this system is Hinglish speech → structured intent extraction → policy-gated recovery. Every external AI dependency — Gemini (`google-genai`), Groq (`groq`), Sarvam ASR, Pydantic schema validation — ships Python-first SDKs. Wrapping these behind a Java REST layer would add an entire serialization/deserialization boundary with zero business value, just plumbing.

2. **Hackathon velocity over enterprise ceremony**: Spring Boot's annotation-driven DI, DTO mapping, and build toolchain (`Maven`/`Gradle` → JAR → JVM startup) optimizes for long-lived production services. For a 7-day buildathon with a single developer, FastAPI's zero-boilerplate route declarations (`@app.get`, `@app.post`) and instant `uvicorn --reload` iteration loop compress the feedback cycle from minutes to seconds.

3. **The spec's split was solving the wrong problem for this scope**: The dual-service architecture (Java core + Python perception) exists to isolate non-deterministic LLM calls from deterministic business logic at the *deployment* boundary. We achieve the same isolation at the *module* boundary — `src/policy_engine.py` is pure-function, zero-network, zero-LLM, verified by unit tests that mock-patch `socket.socket`. The architectural safety guarantee is identical; the service boundary is just unnecessary at this scale.

4. **Pydantic v2 as the type safety substitute**: Java's compile-time type checking is its main advantage over Python for financial logic. Pydantic v2's runtime validation across all 8 contract schemas (`src/contracts/`) provides equivalent guarantees — every field is typed, constrained, and validated at ingestion. The Perception Gateway rejects malformed payloads before they reach any business logic, exactly as a Java DTO validator would.

5. **Single-process testability**: 67 tests run in ~14 seconds with `pytest` against a single process. No Docker Compose, no inter-service HTTP mocking, no port conflicts. The entire system is testable from a cold `git clone` with just `pip install -r requirements.txt`.

> **Bottom line**: Python was chosen because this project's value is in its AI perception pipeline and evaluation rigor, not in its HTTP framework. The deterministic safety guarantees that Java would provide at the type level are achieved through Pydantic contracts, pure-function module isolation, and a 67-test suite that enforces them.

---

## Repository Structure

```
├── src/
│   ├── contracts/          # 8 Pydantic data models (frozen interfaces)
│   ├── orchestrator.py     # End-to-end pipeline glue
│   ├── perception_service.py
│   ├── commitment_extractor.py  # Gemini / Groq / Mock structured extraction
│   ├── asr_adapter.py      # Sarvam / Mock / Whisper ASR
│   ├── perception_gateway.py    # Validation + injection filtering gate
│   ├── policy_engine.py    # Pure deterministic rules (zero network)
│   ├── state_machine.py    # Formal lifecycle transitions
│   ├── payment_adapter.py  # Razorpay live (with backoff retry) / Mock adapter
│   ├── audit_logger.py     # Append-only audit trail
│   ├── evaluation_harness.py
│   ├── event_consumer.py   # Idempotent webhook handler + HMAC verification
│   ├── scheduler.py        # Confirm-then-act follow-up executor
│   ├── store.py            # In-memory state + audit store
│   └── dashboard_api.py    # FastAPI REST + static file server
├── ui/                     # Frontend (index.html, style.css, app.js)
├── tests/                  # 67 tests (12 test files)
├── scripts/                # evaluate_batch.py, freeze_datasets.py, reset_demo_state.py, run_demo.py, secret_scanner.py
├── data/                   # Frozen datasets, checksums, evaluation results
├── verification/           # Independent live API verification scripts
├── revenue-recovery-spec.md   # Full 52K-word project specification
├── evaluation-spec.md         # Evaluation-Driven Development spec
├── PROGRESS.md                # Detailed build status & decisions
├── requirements.txt
└── .env.example
```

---

## License

Built for the Razorpay AI Buildathon 2026. Not licensed for production use.
