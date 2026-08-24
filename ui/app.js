/**
 * AI Revenue Recovery Agent — Dashboard & Judge Evaluation Application Logic
 * Vanilla JavaScript (EDD Step 12)
 */

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initPresetButtons();
  initSimulationForm();
  initEvaluationButton();
  initExceptionCollapsible();
  
  // Load initial data from backend API
  loadMetrics();
  loadInvoices();
  loadAuditTrail();
});

// -----------------------------------------------------------------------------
// Tab Switching
// -----------------------------------------------------------------------------

function initTabs() {
  const tabs = document.querySelectorAll(".nav-tab");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");

      const targetId = tab.getAttribute("data-tab");
      document.querySelectorAll(".tab-pane").forEach(pane => {
        pane.classList.remove("active");
      });
      const targetPane = document.getElementById(targetId);
      if (targetPane) {
        targetPane.classList.add("active");
      }
    });
  });
}

// -----------------------------------------------------------------------------
// Exception List Collapsible & Sub-tabs
// -----------------------------------------------------------------------------

function initExceptionCollapsible() {
  const header = document.getElementById("btn-toggle-exceptions");
  const body = document.getElementById("body-exceptions");
  if (header && body) {
    header.addEventListener("click", () => {
      body.classList.toggle("hidden");
    });
  }

  const p2pSubBtn = document.getElementById("btn-subtab-p2p");
  const pfSubBtn = document.getElementById("btn-subtab-pf");
  const p2pContainer = document.getElementById("container-p2p-exceptions");
  const pfContainer = document.getElementById("container-pf-exceptions");

  if (p2pSubBtn && pfSubBtn && p2pContainer && pfContainer) {
    p2pSubBtn.addEventListener("click", () => {
      p2pSubBtn.classList.add("active");
      pfSubBtn.classList.remove("active");
      p2pContainer.classList.remove("hidden");
      pfContainer.classList.add("hidden");
    });

    pfSubBtn.addEventListener("click", () => {
      pfSubBtn.classList.add("active");
      p2pSubBtn.classList.remove("active");
      pfContainer.classList.remove("hidden");
      p2pContainer.classList.add("hidden");
    });
  }
}

// -----------------------------------------------------------------------------
// Load Metrics & Scorecard
// -----------------------------------------------------------------------------

async function loadMetrics() {
  try {
    const res = await fetch("/api/metrics");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderScorecard(data);
  } catch (err) {
    console.error("Failed to load metrics:", err);
  }
}

function renderScorecard(data) {
  const p2p = data.p2p || {};
  const pf = data.payment_failure || {};

  // KPI Card Ribbon
  const p2pRec = (p2p.recovery_rate * 100).toFixed(1) + "%";
  const p2pLift = (p2p.lift >= 0 ? "+" : "") + (p2p.lift * 100).toFixed(1) + "% Lift";
  const p2pCi = `[${(p2p.lift_ci_lower * 100).toFixed(1)}%, ${(p2p.lift_ci_upper * 100).toFixed(1)}%]`;
  
  const pfRec = (pf.recovery_rate * 100).toFixed(1) + "%";
  const pfLift = (pf.lift >= 0 ? "+" : "") + (pf.lift * 100).toFixed(1) + "% Lift";
  const pfCi = `[${(pf.lift_ci_lower * 100).toFixed(1)}%, ${(pf.lift_ci_upper * 100).toFixed(1)}%]`;

  document.getElementById("kpi-p2p-recovery").innerText = p2pRec;
  document.getElementById("kpi-p2p-lift").innerText = p2pLift;
  document.getElementById("kpi-p2p-ci").innerHTML = `95% CI: <strong class="ci-val">${p2pCi}</strong> (Paired Bootstrap)`;

  document.getElementById("kpi-pf-recovery").innerText = pfRec;
  document.getElementById("kpi-pf-lift").innerText = pfLift;
  document.getElementById("kpi-pf-ci").innerHTML = `95% CI: <strong class="ci-val">${pfCi}</strong> (Paired Bootstrap)`;

  // Benchmark Table Cells
  document.getElementById("cell-p2p-rec").innerText = p2pRec;
  document.getElementById("cell-pf-rec").innerText = pfRec;
  document.getElementById("cell-p2p-base").innerText = (p2p.naive_baseline_recovery_rate * 100).toFixed(1) + "%";
  document.getElementById("cell-pf-base").innerText = (pf.naive_baseline_recovery_rate * 100).toFixed(1) + "%";
  document.getElementById("cell-p2p-lift").innerText = p2pLift;
  document.getElementById("cell-pf-lift").innerText = pfLift;
  document.getElementById("cell-p2p-ci").innerText = p2pCi;
  document.getElementById("cell-pf-ci").innerText = pfCi;
  document.getElementById("cell-p2p-cwer").innerText = (p2p.cost_weighted_error_rate || 0).toFixed(3);
  document.getElementById("cell-pf-cwer").innerText = (pf.cost_weighted_error_rate || 0).toFixed(3);

  const p2pExc = (p2p.exception_list || []).length;
  const pfExc = (pf.exception_list || []).length;
  document.getElementById("cell-p2p-exc").innerText = `${p2pExc} / ${p2p.n_records || 35}`;
  document.getElementById("cell-pf-exc").innerText = `${pfExc} / ${pf.n_records || 35}`;
  document.getElementById("count-exceptions").innerText = p2pExc + pfExc;

  // Hashes & Manifest
  if (p2p.policy_config_hash) {
    document.getElementById("hash-policy").innerText = p2p.policy_config_hash;
  }
  if (p2p.held_out_set_checksum) {
    document.getElementById("hash-p2p").innerText = p2p.held_out_set_checksum;
  }
  if (pf.held_out_set_checksum) {
    document.getElementById("hash-pf").innerText = pf.held_out_set_checksum;
  }

  // Populate Exception Drawer
  renderExceptionList("container-p2p-exceptions", p2p.exception_list || []);
  renderExceptionList("container-pf-exceptions", pf.exception_list || []);
}

function renderExceptionList(containerId, exceptions) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = "";

  if (exceptions.length === 0) {
    container.innerHTML = "<div class='trace-placeholder'>Zero exceptions recorded.</div>";
    return;
  }

  exceptions.forEach((entry, idx) => {
    const div = document.createElement("div");
    div.className = "exception-entry";
    div.innerHTML = `
      <div class="exception-entry-header">
        <span>#${idx + 1} Record: ${escapeHtml(entry.record_id)}</span>
        <span class="status-pill open">Routed to Review</span>
      </div>
      <div class="exception-entry-raw">"${escapeHtml(entry.raw_input || '')}"</div>
      <div class="exception-entry-reason"><strong>Reason:</strong> ${escapeHtml(entry.reason || '')}</div>
    `;
    container.appendChild(div);
  });
}

// -----------------------------------------------------------------------------
// Evaluation Button Action
// -----------------------------------------------------------------------------

function initEvaluationButton() {
  const btn = document.getElementById("btn-run-eval");
  if (!btn) return;

  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.innerHTML = `<span class="btn-icon">⏳</span> Evaluating Batch...`;
    try {
      const res = await fetch("/api/evaluate", { method: "POST" });
      const data = await res.json();
      renderScorecard(data);
      alert("Batch Evaluation Complete! Metrics and Confidence Intervals Updated.");
    } catch (err) {
      alert("Evaluation failed: " + err.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<span class="btn-icon">⚡</span> Run Live Evaluation Harness`;
    }
  });
}

// -----------------------------------------------------------------------------
// Interactive Playground & Simulation
// -----------------------------------------------------------------------------

function initPresetButtons() {
  const presetBtns = document.querySelectorAll(".preset-btn");
  presetBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const text = btn.getAttribute("data-text");
      const amt = btn.getAttribute("data-amt");
      const disc = btn.getAttribute("data-disc");

      document.getElementById("input-transcript").value = text;
      if (amt) document.getElementById("input-amount").value = amt;
      document.getElementById("input-discount").value = disc || "";
    });
  });
}

function initSimulationForm() {
  const form = document.getElementById("form-simulate");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const submitBtn = document.getElementById("btn-submit-simulate");
    submitBtn.disabled = true;
    submitBtn.innerHTML = `<span class="btn-icon">⏳</span> Processing Perception & Policy...`;

    const payload = {
      utterance_text: document.getElementById("input-transcript").value.trim(),
      original_amount: parseFloat(document.getElementById("input-amount").value) || 100000.0,
      requested_discount_pct: document.getElementById("input-discount").value ? parseFloat(document.getElementById("input-discount").value) : null,
      invoice_id: document.getElementById("input-invoice-id").value.trim() || "INV-DEMO-001",
      flow: document.getElementById("input-flow").value,
      current_state: "Open"
    };

    if (!payload.utterance_text) {
      alert("Please enter a customer utterance transcript.");
      submitBtn.disabled = false;
      submitBtn.innerHTML = `<span class="btn-icon">▶</span> Execute Pipeline (Perception → Policy → Razorpay)`;
      return;
    }

    resetPipelineSteps();

    try {
      const res = await fetch("/api/simulate-call", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      renderPipelineTrace(data);
      loadAuditTrail(); // Refresh live audit trail
    } catch (err) {
      alert("Simulation failed: " + err.message);
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerHTML = `<span class="btn-icon">▶</span> Execute Pipeline (Perception → Policy → Razorpay)`;
    }
  });
}

function resetPipelineSteps() {
  const steps = ["perception", "gateway", "policy", "action", "audit"];
  steps.forEach(s => {
    const badge = document.getElementById(`badge-${s}`);
    const content = document.getElementById(`content-${s}`);
    if (badge) {
      badge.className = "step-badge";
      badge.innerText = "Evaluating...";
    }
    if (content) content.innerHTML = "<div class='trace-placeholder'>Processing...</div>";
  });
}

function renderPipelineTrace(res) {
  // 1. Perception Service
  const ext = res.extraction || {};
  const badgePerception = document.getElementById("badge-perception");
  const contentPerception = document.getElementById("content-perception");
  
  if (badgePerception && contentPerception) {
    badgePerception.className = "step-badge badge-success";
    badgePerception.innerText = `Confidence: ${(ext.confidence || 0).toFixed(2)}`;
    contentPerception.innerHTML = `
      <div><strong>Committed Amount:</strong> ${ext.committed_amount ? '₹' + ext.committed_amount.toLocaleString() : 'null (Full Balance)'}</div>
      <div><strong>Committed Date:</strong> ${ext.committed_date || 'null (Not specified)'}</div>
      <div><strong>Language Detected:</strong> ${ext.language_detected || 'hinglish'}</div>
      <div><strong>Notes:</strong> ${escapeHtml(ext.extraction_notes || 'Extracted structured commitment')}</div>
    `;
  }

  // 2. Perception Gateway
  const badgeGateway = document.getElementById("badge-gateway");
  const contentGateway = document.getElementById("content-gateway");
  if (badgeGateway && contentGateway) {
    if (res.routed_to === "exception_list") {
      badgeGateway.className = "step-badge badge-exception";
      badgeGateway.innerText = "Routed to Exception";
      contentGateway.innerHTML = `
        <div style="color: #f59e0b;"><strong>Gate Decision:</strong> Routed to human exception list due to low confidence (<0.60) or vague commitment.</div>
      `;
    } else {
      badgeGateway.className = "step-badge badge-success";
      badgeGateway.innerText = "Passed Sanitization";
      contentGateway.innerHTML = `
        <div><strong>Type Validation:</strong> Positive numbers verified, injection payloads sanitized, typed Pydantic contract validated.</div>
      `;
    }
  }

  // 3. Policy Engine
  const badgePolicy = document.getElementById("badge-policy");
  const contentPolicy = document.getElementById("content-policy");
  const pol = res.policy_decision || {};
  if (badgePolicy && contentPolicy) {
    if (pol.decision === "DENIED") {
      badgePolicy.className = "step-badge badge-denied";
      badgePolicy.innerText = "DENIED (Policy Cap)";
      contentPolicy.innerHTML = `
        <div style="color: #f43f5e;"><strong>Policy Decision:</strong> ${pol.decision} (${escapeHtml(pol.reason_code || 'Cap exceeded')})</div>
        <div><strong>Alternative Offer:</strong> ${escapeHtml(pol.alternative_offer?.description || 'Escalate to human agent')}</div>
      `;
    } else {
      badgePolicy.className = "step-badge badge-success";
      badgePolicy.innerText = "APPROVED / ELIGIBLE";
      contentPolicy.innerHTML = `
        <div><strong>Policy Checks:</strong> Discount within cap (≤30%), Retry attempt count within limit (≤3), zero broken promise escalation triggered.</div>
      `;
    }
  }

  // 4. Action Selector & Razorpay Payment Adapter
  const badgeAction = document.getElementById("badge-action");
  const contentAction = document.getElementById("content-action");
  const act = res.recovery_action || {};
  const plink = res.payment_link || {};

  if (badgeAction && contentAction) {
    badgeAction.className = "step-badge badge-success";
    badgeAction.innerText = act.action_type || "CREATE_PAYMENT_LINK";

    let plinkHtml = "";
    if (plink.short_url) {
      plinkHtml = `
        <div class="plink-card">
          <div style="font-weight: 700; color: #34d399; margin-bottom: 0.2rem;">✓ Razorpay Payment Link Created:</div>
          <div><a href="${plink.short_url}" target="_blank" class="plink-url">${plink.short_url}</a></div>
          <div style="font-size: 0.75rem; color: #94a3b8; margin-top: 0.2rem;">Amount: ₹${(plink.amount || 0).toLocaleString()} • ID: ${plink.link_id || 'plink_live'}</div>
        </div>
      `;
    }

    contentAction.innerHTML = `
      <div><strong>Action:</strong> ${act.action_type || 'N/A'} (Scheduled: ${act.scheduled_at || 'Immediate'})</div>
      ${plinkHtml}
    `;
  }

  // 5. State Machine & Audit
  const badgeAudit = document.getElementById("badge-audit");
  const contentAudit = document.getElementById("content-audit");
  if (badgeAudit && contentAudit) {
    const finalState = res.new_state || res.final_state || 'P2P_Committed';
    badgeAudit.className = "step-badge badge-success";
    badgeAudit.innerText = `State: ${finalState}`;
    contentAudit.innerHTML = `
      <div><strong>State Transition:</strong> Open → ${finalState}</div>
      <div><strong>Audit Trail:</strong> Append-logged to <code>data/audit_log.jsonl</code> with SHA-256 integrity hash.</div>
    `;
  }
}

// -----------------------------------------------------------------------------
// Load Invoices & Audit Stream
// -----------------------------------------------------------------------------

async function loadInvoices() {
  try {
    const res = await fetch("/api/invoices");
    const data = await res.json();
    const tbody = document.getElementById("tbody-invoices");
    if (!tbody) return;
    tbody.innerHTML = "";

    const items = (data.p2p_invoices || []).concat(data.payment_failures || []);
    items.slice(0, 15).forEach(inv => {
      const tr = document.createElement("tr");
      const id = inv.invoice_id || inv.event_id || "INV-MOCK";
      const amt = inv.original_amount || inv.amount || 0;
      const raw = inv.raw_input || (inv.failure_code ? `Failure: ${inv.failure_code}` : "Invoice Open");
      
      tr.innerHTML = `
        <td><strong>${escapeHtml(id)}</strong></td>
        <td>₹${Number(amt).toLocaleString()}</td>
        <td style="font-style: italic; color: #cbd5e1;">"${escapeHtml(raw)}"</td>
        <td><span class="status-pill open">Active</span></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Failed to load invoices:", err);
  }
}

async function loadAuditTrail() {
  try {
    const res = await fetch("/api/audit-trail");
    const data = await res.json();
    const container = document.getElementById("stream-audit-logs");
    if (!container) return;
    container.innerHTML = "";

    const entries = data.entries || [];
    if (entries.length === 0) {
      container.innerHTML = "<div class='trace-placeholder'>No audit events recorded yet. Run a simulation to generate live audit records.</div>";
      return;
    }

    entries.slice(-15).reverse().forEach(entry => {
      const card = document.createElement("div");
      card.className = "audit-entry-card";
      card.innerHTML = `
        <div class="audit-entry-top">
          <span class="audit-event-tag">${escapeHtml(entry.event_type || 'SYSTEM_ACTION')}</span>
          <span class="audit-time">${entry.timestamp || ''}</span>
        </div>
        <pre class="audit-json">${escapeHtml(JSON.stringify(entry.payload || entry, null, 2))}</pre>
      `;
      container.appendChild(card);
    });
  } catch (err) {
    console.error("Failed to load audit trail:", err);
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
