const state = {
  patients: [],
  response: null,
  filter: "candidates",
  openTrialId: null,
};

const elements = {
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
  factList: document.querySelector("#fact-list"),
  factsToggle: document.querySelector("#facts-toggle"),
  trialList: document.querySelector("#trial-list"),
  trialCountLabel: document.querySelector("#trial-count-label"),
  disclaimer: document.querySelector("#disclaimer"),
  timestamp: document.querySelector("#result-timestamp"),
  runtimeStatus: document.querySelector("#runtime-status"),
  dataSource: document.querySelector("#data-source"),
  runtimeDetail: document.querySelector("#runtime-detail"),
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
  elements.patientSelect.innerHTML = state.patients
    .map(
      (patient) =>
        `<option value="${escapeHtml(patient.patient_id)}">${escapeHtml(patient.name)} · ${escapeHtml(patient.label)}</option>`,
    )
    .join("");
  selectPatient(state.patients[0]?.patient_id);
}

async function loadRuntime() {
  const response = await fetch("/health");
  if (!response.ok) throw new Error("Could not read the screening runtime.");
  const runtime = await response.json();
  elements.runtimeStatus.textContent = runtime.live
    ? `${runtime.model} connected`
    : `${runtime.extractor} ready`;
  elements.dataSource.textContent = runtime.data_source;
  elements.runtimeDetail.textContent =
    `${runtime.trial_count} trials · ${runtime.rule_count} compiled rules`;
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
  elements.screenButton.querySelector("span").textContent = "Screening all trials…";
  showView("loading");

  try {
    const response = await fetch("/api/screen", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    });
    const payload = await response.json();
    if (!response.ok) {
      const detail = Array.isArray(payload.detail)
        ? payload.detail.map((item) => item.msg).join(" ")
        : payload.detail;
      throw new Error(detail || "The screening request failed.");
    }
    state.response = payload;
    state.filter = payload.candidate_count ? "candidates" : "excluded";
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
    elements.screenButton.querySelector("span").textContent = "Screen against all trials";
  }
}

function renderResults() {
  const payload = state.response;
  elements.candidateCount.textContent = payload.candidate_count;
  elements.unknownCount.textContent = payload.actions.length;
  elements.excludedCount.textContent = payload.excluded_count;
  elements.disclaimer.textContent = payload.disclaimer;
  elements.timestamp.textContent = `Screened ${new Intl.DateTimeFormat("en", {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date())}`;

  renderActions(payload.actions);
  renderFacts(payload.facts);
  setFilter(state.filter);
}

function renderActions(actions) {
  if (!actions.length) {
    elements.actionList.innerHTML =
      '<p class="empty-actions">No missing facts across the top candidate trials.</p>';
    return;
  }
  elements.actionList.innerHTML = actions
    .map(
      (action, index) => `
        <div class="action-item">
          <span class="action-rank">${index + 1}</span>
          <span class="action-name">${escapeHtml(action.label)}</span>
          <span class="action-impact">Unlocks ${action.trial_count} ${action.trial_count === 1 ? "trial" : "trials"}</span>
        </div>`,
    )
    .join("");
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
                <p class="trial-description">${escapeHtml(trial.summary)}</p>
                <a class="registry-link" href="https://clinicaltrials.gov/study/${encodeURIComponent(trial.trial_id)}" target="_blank" rel="noreferrer">Registry record ↗</a>
              </div>
              ${renderCriteriaTable(trial.criteria)}
            </div>`
          : ""
      }
    </article>`;
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
          <td><span class="criterion-type">${escapeHtml(item.type)}</span></td>
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
    bilirubin_mg_dl: "Bilirubin",
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

elements.patientSelect.addEventListener("change", (event) => {
  selectPatient(event.target.value);
});

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
    await Promise.all([loadRuntime(), loadPatients()]);
    await screenPatient();
  } catch (error) {
    elements.errorMessage.textContent = error.message;
    showView("error");
  }
}

initialize();
