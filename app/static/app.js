const state = {
  patients: [],
  cancerTypes: [],
  selectedCancerType: null,
  runtime: null,
  response: null,
  filter: "candidates",
  openTrialId: null,
  refreshTimer: null,
  actionsExpanded: false,
  guidedActive: false,
  guidedSubmitting: false,
  guidedMessage: "",
  guidedHistory: [],
};

const elements = {
  cancerSelect: document.querySelector("#cancer-select"),
  retrievalLimit: document.querySelector("#retrieval-limit"),
  patientSelect: document.querySelector("#patient-select"),
  chartNote: document.querySelector("#chart-note"),
  characterCount: document.querySelector("#character-count"),
  screenButton: document.querySelector("#screen-button"),
  resultsPanel: document.querySelector(".results-panel"),
  loading: document.querySelector("#loading-state"),
  error: document.querySelector("#error-state"),
  errorMessage: document.querySelector("#error-message"),
  content: document.querySelector("#results-content"),
  candidateCount: document.querySelector("#candidate-count"),
  unknownCount: document.querySelector("#unknown-count"),
  excludedCount: document.querySelector("#excluded-count"),
  actionList: document.querySelector("#action-list"),
  actionsMore: document.querySelector("#actions-more"),
  guidedStart: document.querySelector("#guided-start"),
  guidedPanel: document.querySelector("#guided-panel"),
  guidedStop: document.querySelector("#guided-stop"),
  guidedQuestion: document.querySelector("#guided-question"),
  guidedImpact: document.querySelector("#guided-impact"),
  guidedForm: document.querySelector("#guided-form"),
  guidedAnswer: document.querySelector("#guided-answer"),
  guidedSubmit: document.querySelector("#guided-submit"),
  guidedStatus: document.querySelector("#guided-status"),
  guidedHistory: document.querySelector("#guided-history"),
  factList: document.querySelector("#fact-list"),
  factsToggle: document.querySelector("#facts-toggle"),
  trialList: document.querySelector("#trial-list"),
  trialCountLabel: document.querySelector("#trial-count-label"),
  disclaimer: document.querySelector("#disclaimer"),
  timestamp: document.querySelector("#result-timestamp"),
  runtimeStatus: document.querySelector("#runtime-status"),
  dataSource: document.querySelector("#data-source"),
  runtimeDetail: document.querySelector("#runtime-detail"),
  refreshButton: document.querySelector("#refresh-button"),
  refreshLabel: document.querySelector("#refresh-label"),
  refreshTime: document.querySelector("#refresh-time"),
};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showView(view) {
  elements.loading.classList.toggle("hidden", view !== "loading");
  elements.error.classList.toggle("hidden", view !== "error");
  elements.content.classList.toggle("hidden", view !== "content");
  elements.resultsPanel.setAttribute("aria-busy", view === "loading" ? "true" : "false");
}

function updateCharacterCount() {
  const count = elements.chartNote.value.length;
  elements.characterCount.textContent = `${count.toLocaleString()} characters`;
}

async function loadPatients() {
  const response = await fetch("/api/patients");
  if (!response.ok) throw new Error("Could not load demo patients.");
  state.patients = await response.json();
}

async function loadCancerTypes(preferredCancerType = null) {
  const response = await fetch("/api/cancer-types");
  if (!response.ok) throw new Error("Could not load cancer cohorts.");
  state.cancerTypes = await response.json();
  const defaultCohort =
    state.cancerTypes.find((cohort) => cohort.default) ?? state.cancerTypes[0];
  const preferredCohort = state.cancerTypes.find(
    (cohort) => cohort.cancer_type === preferredCancerType,
  );
  state.selectedCancerType =
    preferredCohort?.cancer_type ?? defaultCohort?.cancer_type ?? null;
  elements.cancerSelect.innerHTML = state.cancerTypes
    .map(
      (cohort) =>
        `<option value="${escapeHtml(cohort.cancer_type)}">${escapeHtml(cohort.label)} · ${cohort.trial_count} trials</option>`,
    )
    .join("");
  elements.cancerSelect.value = state.selectedCancerType;
}

function selectCancerType(cancerType) {
  state.selectedCancerType = cancerType;
  elements.cancerSelect.value = cancerType;
  const patients = state.patients.filter(
    (patient) => patient.cancer_type === cancerType,
  );
  elements.patientSelect.innerHTML = state.patients
    .filter((patient) => patient.cancer_type === cancerType)
    .map(
      (patient) =>
        `<option value="${escapeHtml(patient.patient_id)}">${escapeHtml(patient.name)} · ${escapeHtml(patient.label)}</option>`,
    )
    .join("");
  if (patients.length) {
    selectPatient(patients[0].patient_id);
  }
  updateRuntimeDetail();
}

async function loadRuntime() {
  const response = await fetch("/health");
  if (!response.ok) throw new Error("Could not read the screening runtime.");
  const runtime = await response.json();
  state.runtime = runtime;
  elements.runtimeStatus.textContent = runtime.live
    ? `${runtime.model} connected`
    : `${runtime.extractor} ready`;
  elements.dataSource.textContent = runtime.data_source;
}

function renderRefreshStatus(payload) {
  const running = payload.status === "running";
  elements.refreshButton.disabled = running;
  elements.refreshButton.classList.toggle("syncing", running);
  elements.refreshButton.title = payload.message;
  elements.refreshTime.textContent = formatRefreshTime(payload.last_refreshed_at);

  if (running) {
    elements.refreshLabel.textContent = "Refreshing…";
  } else if (payload.status === "succeeded") {
    elements.refreshLabel.textContent = "Trials updated";
  } else if (payload.status === "failed") {
    elements.refreshLabel.textContent = "Refresh failed";
  } else {
    elements.refreshLabel.textContent = "Refresh trials";
  }
}

async function pollTrialRefresh() {
  const response = await fetch("/api/trial-refresh");
  if (!response.ok) throw new Error("Could not read trial refresh status.");
  const payload = await response.json();
  renderRefreshStatus(payload);

  if (payload.status === "running") {
    state.refreshTimer = window.setTimeout(pollTrialRefresh, 2000);
    return;
  }

  state.refreshTimer = null;
  if (payload.status === "succeeded") {
    const selectedCancerType = state.selectedCancerType;
    await Promise.all([
      loadRuntime(),
      loadCancerTypes(selectedCancerType),
    ]);
    updateRuntimeDetail();
  }
}

async function refreshTrials() {
  window.clearTimeout(state.refreshTimer);
  elements.refreshButton.disabled = true;
  elements.refreshButton.classList.add("syncing");
  elements.refreshLabel.textContent = "Starting…";

  try {
    const response = await fetch("/api/trial-refresh", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Could not start trial refresh.");
    }
    renderRefreshStatus(payload);
    state.refreshTimer = window.setTimeout(pollTrialRefresh, 1000);
  } catch (error) {
    elements.refreshButton.disabled = false;
    elements.refreshButton.classList.remove("syncing");
    elements.refreshLabel.textContent = "Refresh failed";
    elements.refreshButton.title = error.message;
  }
}

function updateRuntimeDetail() {
  const cohort = state.cancerTypes.find(
    (item) => item.cancer_type === state.selectedCancerType,
  );
  if (!cohort) return;
  elements.runtimeDetail.textContent =
    `${cohort.trial_count} treatment trials · ${cohort.rule_count} compiled rules`;
}

function selectPatient(patientId) {
  const patient = state.patients.find((item) => item.patient_id === patientId);
  if (!patient) return;
  elements.patientSelect.value = patient.patient_id;
  elements.chartNote.value = patient.note;
  updateCharacterCount();
}

async function screenPatient() {
  const note = elements.chartNote.value.trim();
  if (note.length < 10) {
    elements.errorMessage.textContent = "Add a clinical note of at least 10 characters.";
    showView("error");
    return;
  }

  elements.screenButton.disabled = true;
  resetGuidedScreening();
  elements.screenButton.querySelector("span").textContent = "Finding relevant trials…";
  showView("loading");

  try {
    const response = await fetch("/api/screen", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        note,
        cancer_type: state.selectedCancerType,
        retrieval_limit: Number(elements.retrievalLimit.value),
      }),
    });
    const responseText = await response.text();
    let payload;
    try {
      payload = JSON.parse(responseText);
    } catch {
      throw new Error(
        response.ok
          ? "The screening service returned an unreadable result."
          : "The screening service returned an unexpected error. Please retry.",
      );
    }
    if (!response.ok) {
      const detail = Array.isArray(payload.detail)
        ? payload.detail.map((item) => item.msg).join(" ")
        : payload.detail;
      throw new Error(detail || "The screening request failed.");
    }
    state.response = payload;
    state.filter = payload.candidate_count ? "candidates" : "excluded";
    state.actionsExpanded = false;
    state.openTrialId =
      payload.results.find((result) => result.fail_count === 0)?.trial_id ??
      payload.results[0]?.trial_id ??
      null;
    renderResults();
    showView("content");
  } catch (error) {
    elements.errorMessage.textContent = error.message;
    showView("error");
  } finally {
    elements.screenButton.disabled = false;
    elements.screenButton.querySelector("span").textContent =
      "Screen selected cancer trials";
  }
}

function renderResults() {
  const payload = state.response;
  elements.candidateCount.textContent = payload.candidate_count;
  elements.unknownCount.textContent = payload.actions.length;
  elements.excludedCount.textContent = payload.excluded_count;
  elements.disclaimer.textContent = payload.disclaimer;
  elements.timestamp.textContent =
    `Evaluated ${payload.screened_trial_count} of ${payload.total_trial_count} · ${new Intl.DateTimeFormat("en", {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date())}`;

  renderActions(payload.actions);
  renderGuidedScreening();
  renderFacts(payload.facts);
  setFilter(state.filter);
}

function renderGuidedScreening() {
  elements.guidedStart.classList.toggle("hidden", state.guidedActive);
  elements.guidedPanel.classList.toggle("hidden", !state.guidedActive);
  if (!state.guidedActive) return;

  const action = state.response?.actions?.[0];
  const complete = !action;
  elements.guidedForm.classList.toggle("hidden", complete);
  elements.guidedQuestion.textContent = complete
    ? "The guided review has no remaining evidence requests."
    : `Next evidence request: ${action.label}.`;
  elements.guidedImpact.textContent = complete
    ? "The study team must still verify final eligibility."
    : `Highest-impact next step · could clarify ${action.trial_count} ${action.trial_count === 1 ? "trial" : "trials"}`;
  elements.guidedAnswer.placeholder = guidedPlaceholder(action?.field);
  elements.guidedSubmit.disabled = state.guidedSubmitting;
  elements.guidedSubmit.textContent = state.guidedSubmitting
    ? "Bedrock is reviewing…"
    : "Apply & re-screen";
  elements.guidedStatus.textContent =
    state.guidedMessage ||
    "Bedrock structures the answer. Deterministic rules decide.";
  elements.guidedStatus.classList.toggle(
    "error",
    state.guidedMessage.startsWith("Could not"),
  );
  elements.guidedHistory.innerHTML = state.guidedHistory
    .map(
      (item) => `
        <div class="guided-history-item">
          <span aria-hidden="true">✓</span>
          <span><strong>${escapeHtml(item.label)}</strong> · ${escapeHtml(item.value)}</span>
        </div>`,
    )
    .join("");
}

function guidedPlaceholder(field) {
  const examples = {
    creatinine_clearance_ml_min: "e.g. 72 mL/min",
    lvef_pct: "e.g. 60%",
    ecog: "e.g. ECOG 1",
    age_years: "e.g. 58 years",
    life_expectancy_months: "e.g. 6 months",
    pd_l1_expression_pct: "e.g. TPS 40%",
  };
  return examples[field] ?? "Enter yes/no, a value, or a brief chart fact";
}

function resetGuidedScreening() {
  state.guidedActive = false;
  state.guidedSubmitting = false;
  state.guidedMessage = "";
  state.guidedHistory = [];
}

async function submitGuidedAnswer(event) {
  event.preventDefault();
  const answer = elements.guidedAnswer.value.trim();
  if (!answer || !state.response || state.guidedSubmitting) return;

  state.guidedSubmitting = true;
  state.guidedMessage = "";
  renderGuidedScreening();
  try {
    const response = await fetch("/api/guided-answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cancer_type: state.response.cancer_type,
        note: state.response.patient_note,
        facts: state.response.facts,
        answer,
        retrieval_limit: Number(elements.retrievalLimit.value),
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "The guided review could not use that answer.");
    }

    state.response = payload.screening;
    state.filter = payload.screening.candidate_count ? "candidates" : "excluded";
    state.openTrialId =
      payload.screening.results.find((result) => result.fail_count === 0)?.trial_id ??
      payload.screening.results[0]?.trial_id ??
      null;
    state.guidedHistory.unshift({
      label: payload.resolved_action.label,
      value: answer,
    });
    state.guidedMessage = `Added ${formatField(payload.resolved_fact.field)} evidence and re-screened ${payload.screening.screened_trial_count} trials.`;
    elements.chartNote.value = payload.screening.patient_note;
    elements.guidedAnswer.value = "";
    updateCharacterCount();
    renderResults();
  } catch (error) {
    state.guidedMessage = `Could not apply that answer. ${error.message}`;
  } finally {
    state.guidedSubmitting = false;
    renderGuidedScreening();
  }
}

function renderActions(actions) {
  if (!actions.length) {
    elements.actionList.innerHTML =
      '<p class="empty-actions">No missing facts across the top candidate trials.</p>';
    elements.actionsMore.classList.add("hidden");
    return;
  }
  const visibleActions = state.actionsExpanded ? actions : actions.slice(0, 5);
  elements.actionList.innerHTML = visibleActions
    .map(
      (action, index) => `
        <div class="action-item">
          <span class="action-rank">${index + 1}</span>
          <span class="action-name">${escapeHtml(action.label)}</span>
          <span class="action-impact">Unlocks ${action.trial_count} ${action.trial_count === 1 ? "trial" : "trials"}</span>
        </div>`,
    )
    .join("");
  elements.actionsMore.classList.toggle("hidden", actions.length <= 5);
  elements.actionsMore.innerHTML = state.actionsExpanded
    ? 'Show top 5 <span aria-hidden="true">↑</span>'
    : `Show all ${actions.length} actions <span aria-hidden="true">↓</span>`;
}

function renderFacts(facts) {
  elements.factList.innerHTML = facts
    .map(
      (fact) =>
        `<span class="fact-chip" title="${escapeHtml(fact.source_text)}"><strong>${escapeHtml(formatField(fact.field))}</strong> ${escapeHtml(formatValue(fact.value))}</span>`,
    )
    .join("");
}

function setFilter(filter) {
  state.filter = filter;
  document.querySelectorAll(".filter-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.filter === filter);
  });
  renderTrials();
}

function renderTrials() {
  let results = state.response?.results ?? [];
  if (state.filter === "candidates") {
    results = results.filter((trial) => trial.fail_count === 0);
  } else if (state.filter === "excluded") {
    results = results.filter((trial) => trial.fail_count > 0);
  }

  elements.trialCountLabel.textContent = `${results.length} ${results.length === 1 ? "trial" : "trials"}`;
  if (!results.length) {
    elements.trialList.innerHTML =
      '<div class="state-card"><p>No trials in this view.</p></div>';
    return;
  }

  elements.trialList.innerHTML = results
    .map((trial) => renderTrialCard(trial, state.response.results.indexOf(trial) + 1))
    .join("");
}

function renderTrialCard(trial, rank) {
  const isOpen = state.openTrialId === trial.trial_id;
  const excluded = trial.fail_count > 0;
  const location = trial.locations[0];
  const locationLabel = location
    ? [location.facility, location.city, location.state].filter(Boolean).join(" · ")
    : "Location not listed";
  return `
    <article class="trial-card ${isOpen ? "open" : ""}" data-trial-id="${escapeHtml(trial.trial_id)}">
      <button class="trial-summary" type="button" aria-expanded="${isOpen}" aria-controls="details-${escapeHtml(trial.trial_id)}">
        <div>
          <div class="trial-rank-row">
            <span class="trial-rank">#${String(rank).padStart(2, "0")}</span>
            <span class="trial-id">${escapeHtml(trial.trial_id)}</span>
            <span class="trial-phase">${escapeHtml(trial.phase)}</span>
            ${trial.intervention_types.length ? `<span class="trial-phase">${escapeHtml(trial.intervention_types.join(" / "))}</span>` : ""}
          </div>
          <h3>${escapeHtml(trial.title)}</h3>
          <p class="trial-location">${escapeHtml(locationLabel)}</p>
        </div>
        <div class="trial-score">
          <span class="disposition ${excluded ? "excluded" : ""}">${escapeHtml(trial.disposition)}</span>
          <div class="score-counts">
            <span class="pass">${trial.pass_count} pass</span>
            <span class="unknown">${trial.unknown_count} unknown</span>
            ${trial.fail_count ? `<span class="fail">${trial.fail_count} fail</span>` : ""}
          </div>
        </div>
      </button>
      ${
        isOpen
          ? `<div class="trial-details" id="details-${escapeHtml(trial.trial_id)}">
              <div class="trial-description-row">
                <div>
                  <p class="trial-description">${escapeHtml(trial.summary)}</p>
                  ${
                    trial.intervention_names.length
                      ? `<div class="intervention-list">${trial.intervention_names
                          .slice(0, 8)
                          .map(
                            (name) =>
                              `<span class="intervention-chip">${escapeHtml(name)}</span>`,
                          )
                          .join("")}</div>`
                      : ""
                  }
                </div>
                <a class="registry-link" href="https://clinicaltrials.gov/study/${encodeURIComponent(trial.trial_id)}" target="_blank" rel="noreferrer">Registry record ↗</a>
              </div>
              ${renderTrialExplanation(trial)}
              ${renderCriteriaTable(trial.criteria)}
            </div>`
          : ""
      }
    </article>`;
}

function renderTrialExplanation(trial) {
  const matches = uniqueCriteria(trial.criteria, "pass");
  const blockers = uniqueCriteria(trial.criteria, "fail");
  const missing = uniqueCriteria(trial.criteria, "unknown");
  return `
    <section class="trial-explanation" aria-label="Why this trial">
      <div class="explanation-heading">
        <h4>Why this trial?</h4>
        <span>Fast read · full rule audit below</span>
      </div>
      <div class="explanation-grid">
        ${renderExplanationGroup("Strongest matches", "pass", matches, trial.pass_count, "No confirmed matches yet")}
        ${renderExplanationGroup("Potential blockers", "fail", blockers, trial.fail_count, "No known blockers")}
        ${renderExplanationGroup("Still needed", "unknown", missing, trial.unknown_count, "No unresolved criteria")}
      </div>
    </section>`;
}

function renderExplanationGroup(title, verdict, items, totalCount, emptyText) {
  const content = items.length
    ? `<ul>${items
        .map((item) => {
          const detail =
            verdict === "unknown"
              ? truncateText(item.criterion, 105)
              : truncateText(item.evidence || item.criterion, 105);
          return `<li title="${escapeHtml(item.criterion)}">
              <strong>${escapeHtml(formatField(item.field))}</strong>
              <span>${escapeHtml(detail)}</span>
            </li>`;
        })
        .join("")}</ul>`
    : `<p>${escapeHtml(emptyText)}</p>`;
  return `
    <div class="explanation-group ${verdict}">
      <div class="explanation-label">
        <span>${escapeHtml(title)}</span>
        <span class="explanation-count">${totalCount}</span>
      </div>
      ${content}
    </div>`;
}

function uniqueCriteria(criteria, verdict, limit = 3) {
  const seen = new Set();
  return criteria
    .filter((item) => item.verdict === verdict)
    .filter((item) => {
      const key = `${item.field}:${item.criterion}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, limit);
}

function truncateText(value, maxLength) {
  const text = String(value);
  return text.length > maxLength
    ? `${text.slice(0, maxLength - 1).trimEnd()}…`
    : text;
}

function renderCriteriaTable(criteria) {
  const rows = criteria
    .map((item) => {
      const evidence = item.evidence
        ? `<span class="evidence">“${escapeHtml(item.evidence)}”</span>`
        : '<span class="missing-evidence">Not found in record</span>';
      return `
        <tr>
          <td>${escapeHtml(item.criterion)}</td>
          <td>
            <span class="criterion-type">${escapeHtml(item.type)}</span>
            ${item.manual_review ? '<span class="manual-badge">Manual review</span>' : ""}
          </td>
          <td><span class="verdict ${escapeHtml(item.verdict)}">${escapeHtml(item.verdict)}</span></td>
          <td>${evidence}</td>
        </tr>`;
    })
    .join("");

  return `
    <table class="criteria-table">
      <thead>
        <tr>
          <th>Criterion</th>
          <th>Type</th>
          <th>Verdict</th>
          <th>Evidence from chart</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function formatField(field) {
  const labels = {
    age_years: "Age",
    creatinine_mg_dl: "Creatinine",
    creatinine_clearance_ml_min: "Creatinine clearance",
    bilirubin_mg_dl: "Bilirubin",
    bilirubin_uln_multiple: "Bilirubin vs. ULN",
    alt_uln_multiple: "ALT vs. ULN",
    ast_uln_multiple: "AST vs. ULN",
    alp_uln_multiple: "ALP vs. ULN",
    lvef_pct: "LVEF",
    prior_systemic_therapy: "Prior therapy",
    brain_mets_active: "Active brain mets",
  };
  return labels[field] ?? field.replaceAll("_", " ");
}

function formatValue(value) {
  if (Array.isArray(value)) return value.length ? value.join(", ") : "none detected";
  if (value === true) return "yes";
  if (value === false) return "no";
  return value;
}

function formatRefreshTime(value) {
  if (!value) return "No refresh recorded";
  const refreshedAt = new Date(value);
  if (Number.isNaN(refreshedAt.getTime())) return "Refresh time unavailable";
  const formatted = new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(refreshedAt);
  return `Updated ${formatted}`;
}

elements.patientSelect.addEventListener("change", (event) => {
  selectPatient(event.target.value);
});

elements.cancerSelect.addEventListener("change", async (event) => {
  selectCancerType(event.target.value);
  await screenPatient();
});

elements.retrievalLimit.addEventListener("change", screenPatient);
elements.refreshButton.addEventListener("click", refreshTrials);
elements.actionsMore.addEventListener("click", () => {
  if (!state.response) return;
  state.actionsExpanded = !state.actionsExpanded;
  renderActions(state.response.actions);
});
elements.guidedStart.addEventListener("click", () => {
  state.guidedActive = true;
  state.guidedMessage = "";
  renderGuidedScreening();
  elements.guidedAnswer.focus();
});
elements.guidedStop.addEventListener("click", resetGuidedScreening);
elements.guidedStop.addEventListener("click", renderGuidedScreening);
elements.guidedForm.addEventListener("submit", submitGuidedAnswer);

elements.chartNote.addEventListener("input", updateCharacterCount);
elements.screenButton.addEventListener("click", screenPatient);
elements.factsToggle.addEventListener("click", () => {
  const expanded = elements.factsToggle.getAttribute("aria-expanded") === "true";
  elements.factsToggle.setAttribute("aria-expanded", String(!expanded));
  elements.factList.classList.toggle("hidden", expanded);
});

document.querySelector(".filter-tabs").addEventListener("click", (event) => {
  const button = event.target.closest("[data-filter]");
  if (button) setFilter(button.dataset.filter);
});

elements.trialList.addEventListener("click", (event) => {
  const summary = event.target.closest(".trial-summary");
  if (!summary) return;
  const card = summary.closest(".trial-card");
  state.openTrialId =
    state.openTrialId === card.dataset.trialId ? null : card.dataset.trialId;
  renderTrials();
});

async function initialize() {
  try {
    await Promise.all([loadRuntime(), loadCancerTypes(), loadPatients()]);
    selectCancerType(state.selectedCancerType);
    await screenPatient();
    await pollTrialRefresh();
  } catch (error) {
    elements.errorMessage.textContent = error.message;
    showView("error");
  }
}

initialize();
