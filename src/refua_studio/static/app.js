const connectionChip = document.getElementById("connectionChip");
const resultOutput = document.getElementById("resultOutput");
const toolsOutput = document.getElementById("toolsOutput");
const jobsBody = document.getElementById("jobsBody");
const jobsCountSummary = document.getElementById("jobsCountSummary");

const objectiveInput = document.getElementById("objectiveInput");
const systemPromptInput = document.getElementById("systemPromptInput");
const planInput = document.getElementById("planInput");
const portfolioInput = document.getElementById("portfolioInput");

const objectiveTemplateSelect = document.getElementById("objectiveTemplateSelect");
const planTemplateSelect = document.getElementById("planTemplateSelect");
const portfolioTemplateSelect = document.getElementById("portfolioTemplateSelect");
const jobStatusFilter = document.getElementById("jobStatusFilter");

const dryRunToggle = document.getElementById("dryRunToggle");
const asyncToggle = document.getElementById("asyncToggle");
const maxRoundsInput = document.getElementById("maxRoundsInput");
const maxCallsInput = document.getElementById("maxCallsInput");
const skipValidateFirstToggle = document.getElementById("skipValidateFirstToggle");

const drugMinScoreInput = document.getElementById("drugMinScoreInput");
const drugPortfolioSummary = document.getElementById("drugPortfolioSummary");
const drugPortfolioCards = document.getElementById("drugPortfolioCards");
const drugPortfolioDetail = document.getElementById("drugPortfolioDetail");
const cureDetailHeader = document.getElementById("cureDetailHeader");
const cureAssessment = document.getElementById("cureAssessment");
const cureMetricPills = document.getElementById("cureMetricPills");
const admetKeyMetrics = document.getElementById("admetKeyMetrics");
const admetPropertiesGrid = document.getElementById("admetPropertiesGrid");

const productGrid = document.getElementById("productGrid");
const ecosystemWarnings = document.getElementById("ecosystemWarnings");
const defaultObjectiveText = document.getElementById("defaultObjectiveText");
const defaultPromptPreview = document.getElementById("defaultPromptPreview");
const clawcuresCommandOutput = document.getElementById("clawcuresCommandOutput");
const handoffWriteFileToggle = document.getElementById("handoffWriteFileToggle");
const handoffArtifactNameInput = document.getElementById("handoffArtifactNameInput");
const clinicalTrialSelect = document.getElementById("clinicalTrialSelect");
const clinicalTrialSummary = document.getElementById("clinicalTrialSummary");
const clinicalTrialIdInput = document.getElementById("clinicalTrialIdInput");
const clinicalTrialStatusInput = document.getElementById("clinicalTrialStatusInput");
const clinicalTrialConfigInput = document.getElementById("clinicalTrialConfigInput");
const clinicalPatientInput = document.getElementById("clinicalPatientInput");
const clinicalResultInput = document.getElementById("clinicalResultInput");
const clinicalOpsInput = document.getElementById("clinicalOpsInput");
const clinicalSimCountInput = document.getElementById("clinicalSimCountInput");
const clinicalReplicatesInput = document.getElementById("clinicalReplicatesInput");
const clinicalSeedInput = document.getElementById("clinicalSeedInput");
const widgetRunningJobs = document.getElementById("widgetRunningJobs");
const widgetTrialCount = document.getElementById("widgetTrialCount");
const widgetHumanPatients = document.getElementById("widgetHumanPatients");
const widgetPromisingLeads = document.getElementById("widgetPromisingLeads");
const widgetToolsOnline = document.getElementById("widgetToolsOnline");
const programIdInput = document.getElementById("programIdInput");
const programNameInput = document.getElementById("programNameInput");
const programStageInput = document.getElementById("programStageInput");
const programIndicationInput = document.getElementById("programIndicationInput");
const programOwnerInput = document.getElementById("programOwnerInput");
const programSummaryOutput = document.getElementById("programSummaryOutput");
const datasetIdInput = document.getElementById("datasetIdInput");
const benchSuitePathInput = document.getElementById("benchSuitePathInput");
const benchBaselinePathInput = document.getElementById("benchBaselinePathInput");
const benchPredictionsPathInput = document.getElementById("benchPredictionsPathInput");
const wetlabProviderSelect = document.getElementById("wetlabProviderSelect");
const wetlabProtocolInput = document.getElementById("wetlabProtocolInput");
const regulatoryJobIdInput = document.getElementById("regulatoryJobIdInput");
const regulatoryOutputDirInput = document.getElementById("regulatoryOutputDirInput");
const gateTemplateSelect = document.getElementById("gateTemplateSelect");
const gateMetricsInput = document.getElementById("gateMetricsInput");
const gateTemplateSummary = document.getElementById("gateTemplateSummary");
const gateCriteriaChecklist = document.getElementById("gateCriteriaChecklist");
const commandCenterCapabilities = document.getElementById("commandCenterCapabilities");
const programEventTimeline = document.getElementById("programEventTimeline");

const state = {
  selectedJobId: null,
  selectedCandidateId: null,
  selectedClinicalTrialId: null,
  pollTimer: null,
  examples: {
    objectives: [],
    plan_templates: [],
    portfolio_templates: [],
  },
  ecosystem: null,
  handoff: null,
  drugCandidates: [],
  clinicalTrials: [],
  telemetry: {
    runningJobs: 0,
    trialCount: 0,
    humanPatients: 0,
    promisingLeads: 0,
    toolsOnline: 0,
  },
  commandCenter: {
    capabilities: null,
    programs: [],
    wetlabProviders: [],
    selectedProgram: null,
    gateTemplates: [],
    programCounts: {},
  },
};

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setConnection(ok, text) {
  connectionChip.classList.toggle("online", ok);
  connectionChip.classList.toggle("offline", !ok);
  const node = connectionChip.querySelector(".status-text");
  node.textContent = text;
}

function bootstrapWidgetSparks() {
  const sparks = document.querySelectorAll(".widget-spark");
  for (const spark of sparks) {
    if (spark.children.length > 0) {
      continue;
    }
    for (let idx = 0; idx < 14; idx += 1) {
      const bar = document.createElement("span");
      bar.style.setProperty("--i", String(idx));
      bar.style.height = `${35 + ((idx * 17) % 55)}%`;
      spark.appendChild(bar);
    }
  }
}

function setWidgetValue(node, value) {
  if (!node) {
    return;
  }
  const nextText = String(value);
  if (node.textContent !== nextText) {
    node.classList.remove("flash");
    // Restart animation when value changes.
    node.offsetWidth;
    node.classList.add("flash");
  }
  node.textContent = nextText;
}

function updateTelemetryWidgets() {
  setWidgetValue(widgetRunningJobs, state.telemetry.runningJobs ?? 0);
  setWidgetValue(widgetTrialCount, state.telemetry.trialCount ?? 0);
  setWidgetValue(widgetHumanPatients, state.telemetry.humanPatients ?? 0);
  setWidgetValue(widgetPromisingLeads, state.telemetry.promisingLeads ?? 0);
  setWidgetValue(widgetToolsOnline, state.telemetry.toolsOnline ?? 0);
}

function showOutput(title, payload) {
  const rendered = typeof payload === "string" ? payload : pretty(payload);
  const stamp = new Date().toLocaleTimeString();
  resultOutput.textContent = `[${stamp}] ${title}\n${"=".repeat(title.length + stamp.length + 3)}\n${rendered}`;
}

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  const response = await fetch(path, {
    ...options,
    headers,
  });

  const text = await response.text();
  let payload = {};
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch (_err) {
      payload = { raw: text };
    }
  }

  if (!response.ok) {
    const message = payload.error || `HTTP ${response.status}`;
    throw new Error(message);
  }

  return payload;
}

function parseJsonText(text, label) {
  const raw = text.trim();
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw);
  } catch (_err) {
    throw new Error(`${label} must be valid JSON`);
  }
}

function formatDate(isoString) {
  if (!isoString) {
    return "-";
  }
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return isoString;
  }
  return date.toLocaleString();
}

function formatDuration(ms) {
  if (typeof ms !== "number" || Number.isNaN(ms)) {
    return "-";
  }
  if (ms < 1000) {
    return `${ms}ms`;
  }
  const sec = ms / 1000;
  if (sec < 60) {
    return `${sec.toFixed(1)}s`;
  }
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  return `${min}m ${rem.toFixed(0)}s`;
}

function shortText(value, maxLen = 30) {
  if (!value) {
    return "-";
  }
  const text = String(value);
  if (text.length <= maxLen) {
    return text;
  }
  return `${text.slice(0, maxLen - 1)}...`;
}

function safeStatus(status) {
  const normalized = String(status || "unknown")
    .toLowerCase()
    .replaceAll(/[^a-z0-9_-]/g, "");
  return normalized || "unknown";
}

function statusPill(status) {
  const safe = safeStatus(status);
  return `<span class="status-pill status-${safe}">${escapeHtml(safe)}</span>`;
}

function metricText(value, digits = 3) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(digits);
}

function valueText(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "number") {
    if (Number.isNaN(value)) {
      return "-";
    }
    if (Math.abs(value) >= 1000 || Math.abs(value) < 0.001) {
      return value.toExponential(3);
    }
    return value.toFixed(4).replace(/0+$/, "").replace(/\\.$/, "");
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  return String(value);
}

function normalizedAdmet(candidate) {
  const admet = candidate?.admet;
  if (!admet || typeof admet !== "object") {
    return { key_metrics: {}, properties: {} };
  }
  const keyMetrics = admet.key_metrics && typeof admet.key_metrics === "object" ? admet.key_metrics : {};
  const properties = admet.properties && typeof admet.properties === "object" ? admet.properties : {};
  return {
    key_metrics: keyMetrics,
    properties,
    status: admet.status,
    assessment: admet.assessment,
  };
}

function setSelectOptions(select, options, labelGetter) {
  select.innerHTML = "";
  if (!Array.isArray(options) || options.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No templates available";
    select.appendChild(option);
    return;
  }

  for (const item of options) {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = labelGetter(item);
    select.appendChild(option);
  }
}

function selectedTemplate(select, list) {
  const id = select.value;
  return list.find((item) => item.id === id) || null;
}

function renderWarnings(warnings) {
  if (!Array.isArray(warnings) || warnings.length === 0) {
    ecosystemWarnings.hidden = true;
    ecosystemWarnings.textContent = "";
    return;
  }
  ecosystemWarnings.hidden = false;
  ecosystemWarnings.textContent = warnings.join("\n");
}

function renderProductGrid(products) {
  productGrid.innerHTML = "";

  if (!Array.isArray(products) || products.length === 0) {
    const empty = document.createElement("div");
    empty.className = "summary-item";
    empty.textContent = "No product metadata available.";
    productGrid.appendChild(empty);
    return;
  }

  for (const product of products) {
    const card = document.createElement("article");
    const health = String(product.health || "degraded");
    card.className = `product-card product-card-${health}`;

    const cli = product.cli ? `CLI: ${product.cli}` : "CLI: n/a";
    const version = product.version || "unknown";
    const reqPy = product.requires_python || "n/a";

    card.innerHTML = `
      <div class="product-top">
        <h4 class="product-name">${escapeHtml(product.name || product.id || "unknown")}</h4>
        <span class="health-pill health-${escapeHtml(health)}">${escapeHtml(health)}</span>
      </div>
      <p class="product-role">${escapeHtml(product.role || "")}</p>
      <p class="product-meta"><strong>Version:</strong> ${escapeHtml(version)}</p>
      <p class="product-meta"><strong>Python:</strong> ${escapeHtml(reqPy)}</p>
      <p class="product-meta"><strong>${escapeHtml(cli)}</strong></p>
    `;
    productGrid.appendChild(card);
  }
}

function renderHandoffCommands(handoffPayload) {
  if (!handoffPayload || !Array.isArray(handoffPayload.commands)) {
    clawcuresCommandOutput.textContent = "Generate a handoff to populate commands.";
    return;
  }

  const lines = [];
  if (handoffPayload.artifact_path) {
    lines.push(`# Artifact: ${handoffPayload.artifact_path}`);
  }
  for (const cmd of handoffPayload.commands) {
    lines.push(`# ${cmd.label}`);
    lines.push(cmd.command);
    lines.push("");
  }
  clawcuresCommandOutput.textContent = lines.join("\n").trim();
}

function renderEcosystem(payload) {
  state.ecosystem = payload;
  renderWarnings(payload.warnings || []);

  renderProductGrid(payload.products || []);

  const clawcures = payload.clawcures || {};
  defaultObjectiveText.textContent = clawcures.default_objective || "Unavailable";
  defaultPromptPreview.textContent = clawcures.default_prompt_preview || "Unavailable";

  if (!objectiveInput.value.trim() && clawcures.default_objective) {
    objectiveInput.value = clawcures.default_objective;
  }
}

async function refreshHealth() {
  try {
    const payload = await api("/api/health", { method: "GET" });
    const running = payload.job_counts?.running || 0;
    state.telemetry.runningJobs = Number(running) || 0;
    state.telemetry.toolsOnline = Number(payload.tools_count) || 0;
    updateTelemetryWidgets();
    setConnection(true, `Online (${payload.tools_count} tools, ${running} running)`);
  } catch (err) {
    setConnection(false, `Offline (${err.message})`);
  }
}

async function refreshEcosystem() {
  const payload = await api("/api/ecosystem", { method: "GET" });
  renderEcosystem(payload);
}

async function refreshTools() {
  const [toolsPayload, configPayload] = await Promise.all([
    api("/api/tools", { method: "GET" }),
    api("/api/config", { method: "GET" }),
  ]);
  state.telemetry.toolsOnline = Array.isArray(toolsPayload.tools) ? toolsPayload.tools.length : 0;
  updateTelemetryWidgets();
  toolsOutput.textContent = pretty({
    tools: toolsPayload.tools,
    warnings: toolsPayload.warnings,
    config: configPayload,
  });
}

async function refreshExamples() {
  const payload = await api("/api/examples", { method: "GET" });
  state.examples = {
    objectives: payload.objectives || [],
    plan_templates: payload.plan_templates || [],
    portfolio_templates: payload.portfolio_templates || [],
  };

  setSelectOptions(objectiveTemplateSelect, state.examples.objectives, (item) => item.label);
  setSelectOptions(planTemplateSelect, state.examples.plan_templates, (item) => item.label);
  setSelectOptions(portfolioTemplateSelect, state.examples.portfolio_templates, (item) => item.label);

  if (Array.isArray(payload.warnings) && payload.warnings.length > 0) {
    showOutput("Template Warnings", payload);
  }
}

function renderJobCounts(counts) {
  if (!counts || typeof counts !== "object") {
    jobsCountSummary.textContent = "";
    return;
  }

  const keys = ["queued", "running", "completed", "failed", "cancelled"];
  const parts = keys.map((key) => `${key}: ${counts[key] || 0}`);
  jobsCountSummary.textContent = `Job counts | ${parts.join(" | ")}`;
}

function renderJobsTable(jobs) {
  jobsBody.innerHTML = "";

  if (!Array.isArray(jobs) || jobs.length === 0) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="5">No jobs found for current filter.</td>';
    jobsBody.appendChild(tr);
    return;
  }

  for (const job of jobs) {
    const tr = document.createElement("tr");
    if (job.job_id === state.selectedJobId) {
      tr.classList.add("selected");
    }

    tr.innerHTML = `
      <td title="${escapeHtml(job.job_id)}">${escapeHtml((job.job_id || "").slice(0, 8))}...</td>
      <td>${escapeHtml(job.kind || "-")}</td>
      <td>${statusPill(job.status)}</td>
      <td>${escapeHtml(formatDate(job.updated_at))}</td>
      <td>${escapeHtml(formatDuration(job.duration_ms))}</td>
    `;

    tr.addEventListener("click", async () => {
      state.selectedJobId = job.job_id;
      await loadJob(job.job_id);
      renderJobsTable(jobs);
    });

    jobsBody.appendChild(tr);
  }
}

async function refreshJobs() {
  const statusFilter = jobStatusFilter.value;
  const query = statusFilter ? `?limit=80&status=${encodeURIComponent(statusFilter)}` : "?limit=80";
  const payload = await api(`/api/jobs${query}`, { method: "GET" });
  const jobs = payload.jobs || [];

  renderJobCounts(payload.counts || {});
  renderJobsTable(jobs);
  state.telemetry.runningJobs = Number(payload.counts?.running || 0);
  updateTelemetryWidgets();

  if (!state.selectedJobId && Array.isArray(jobs) && jobs.length > 0) {
    state.selectedJobId = jobs[0].job_id;
  }

  if (state.selectedJobId) {
    const selected = jobs.find((item) => item.job_id === state.selectedJobId);
    if (selected) {
      showOutput("Selected Job", selected);
    }
  }
}

async function loadJob(jobId) {
  const payload = await api(`/api/jobs/${jobId}`, { method: "GET" });
  regulatoryJobIdInput.value = jobId;
  showOutput("Job Detail", payload);
}

function renderDrugSummary(summary) {
  const entries = [
    { label: "Total Found", value: summary.total_candidates ?? 0 },
    { label: "Returned", value: summary.returned_candidates ?? 0 },
    { label: "Promising", value: summary.promising_count ?? 0 },
    { label: "With ADMET", value: summary.with_admet_properties ?? 0 },
    { label: "Min Score", value: summary.min_score ?? 0 },
  ];

  drugPortfolioSummary.innerHTML = entries
    .map(
      (entry) => `
      <div class="summary-item">
        <div class="summary-label">${escapeHtml(entry.label)}</div>
        <div class="summary-value">${escapeHtml(entry.value)}</div>
      </div>
    `
    )
    .join("");
}

function renderDrugDetail(candidate) {
  if (!candidate) {
    cureDetailHeader.textContent = "Select a candidate cure";
    cureAssessment.textContent =
      "Pick a therapeutic card to inspect full ADMET properties and assessment.";
    cureMetricPills.innerHTML = "";
    admetKeyMetrics.innerHTML = '<div class="admet-empty">No ADMET metrics yet.</div>';
    admetPropertiesGrid.innerHTML = '<div class="admet-empty">No ADMET properties yet.</div>';
    drugPortfolioDetail.textContent = "Select a candidate to view full details.";
    return;
  }

  const admet = normalizedAdmet(candidate);
  const metrics = candidate.metrics || {};
  const score = valueText(candidate.score);
  const cureName = candidate.name || candidate.smiles || candidate.candidate_id;
  const admetAssessment = candidate.assessment || admet.assessment || "No explicit assessment provided.";

  cureDetailHeader.innerHTML = `
    <div class="cure-detail-title">${escapeHtml(shortText(cureName, 120))}</div>
    <div class="cure-detail-meta">
      <span>${escapeHtml(candidate.promising ? "Promising" : "Needs optimization")}</span>
      <span>Score ${escapeHtml(score)}</span>
      <span>${escapeHtml(candidate.tool || "unknown_tool")}</span>
    </div>
  `;
  cureAssessment.textContent = admetAssessment;

  const metricEntries = [
    ["pBind", metrics.binding_probability],
    ["ADMET", metrics.admet_score ?? admet.key_metrics?.admet_score],
    ["Affinity", metrics.affinity],
    ["IC50", metrics.ic50],
    ["KD", metrics.kd],
  ];
  cureMetricPills.innerHTML = metricEntries
    .map(
      ([label, value]) =>
        `<span class="metric-chip">${escapeHtml(label)} ${escapeHtml(valueText(value))}</span>`
    )
    .join("");

  const keyMetricEntries = Object.entries(admet.key_metrics || {});
  if (keyMetricEntries.length === 0) {
    admetKeyMetrics.innerHTML = '<div class="admet-empty">No key ADMET metrics available.</div>';
  } else {
    admetKeyMetrics.innerHTML = keyMetricEntries
      .map(
        ([key, value]) => `
        <div class="admet-key-item">
          <div class="admet-key-label">${escapeHtml(key)}</div>
          <div class="admet-key-value">${escapeHtml(valueText(value))}</div>
        </div>
      `
      )
      .join("");
  }

  const propertyEntries = Object.entries(admet.properties || {}).sort((a, b) =>
    String(a[0]).localeCompare(String(b[0]))
  );
  if (propertyEntries.length === 0) {
    admetPropertiesGrid.innerHTML = '<div class="admet-empty">No ADMET property map available.</div>';
  } else {
    admetPropertiesGrid.innerHTML = propertyEntries
      .map(
        ([key, value]) => `
        <div class="admet-prop">
          <div class="admet-prop-key">${escapeHtml(String(key))}</div>
          <div class="admet-prop-value">${escapeHtml(valueText(value))}</div>
        </div>
      `
      )
      .join("");
  }

  drugPortfolioDetail.textContent = pretty(candidate);
}

function renderDrugCards(candidates) {
  drugPortfolioCards.innerHTML = "";

  if (!Array.isArray(candidates) || candidates.length === 0) {
    const empty = document.createElement("div");
    empty.className = "summary-item";
    empty.innerHTML =
      '<div class="summary-label">Cures</div><div class="summary-value">No promising therapeutics yet</div>';
    drugPortfolioCards.appendChild(empty);
    renderDrugDetail(null);
    return;
  }

  for (const candidate of candidates) {
    const card = document.createElement("button");
    card.className = "drug-card";
    if (candidate.candidate_id === state.selectedCandidateId) {
      card.classList.add("selected");
    }

    const metrics = candidate.metrics || {};
    const admet = normalizedAdmet(candidate);
    const admetScore = metrics.admet_score ?? admet.key_metrics?.admet_score;
    card.innerHTML = `
      <div class="drug-card-top">
        <div class="drug-name">${escapeHtml(
          shortText(candidate.name || candidate.smiles || candidate.candidate_id, 46)
        )}</div>
        <div class="drug-score">${escapeHtml(metricText(candidate.score, 1))}</div>
      </div>
      <div class="drug-meta">
        Status: ${escapeHtml(candidate.promising ? "Promising" : "Needs optimization")}<br />
        Target: ${escapeHtml(shortText(candidate.target, 28))}<br />
        Tool: ${escapeHtml(shortText(candidate.tool, 22))}
      </div>
      <div class="metric-row">
        <span class="metric-chip">pBind ${escapeHtml(metricText(metrics.binding_probability, 2))}</span>
        <span class="metric-chip">ADMET ${escapeHtml(metricText(admetScore, 2))}</span>
        <span class="metric-chip">Affinity ${escapeHtml(metricText(metrics.affinity, 2))}</span>
        <span class="metric-chip">IC50 ${escapeHtml(metricText(metrics.ic50, 2))}</span>
      </div>
    `;

    card.addEventListener("click", () => {
      state.selectedCandidateId = candidate.candidate_id;
      renderDrugCards(candidates);
      renderDrugDetail(candidate);
    });

    drugPortfolioCards.appendChild(card);
  }

  if (!state.selectedCandidateId && candidates.length > 0) {
    state.selectedCandidateId = candidates[0].candidate_id;
  }

  const selected = candidates.find((item) => item.candidate_id === state.selectedCandidateId);
  renderDrugDetail(selected || null);
}

async function refreshDrugPortfolio() {
  const minScore = Number(drugMinScoreInput.value || 50);
  const query = `?limit=60&min_score=${encodeURIComponent(minScore)}`;
  const payload = await api(`/api/promising-cures${query}`, { method: "GET" });

  state.drugCandidates = payload.candidates || [];
  state.telemetry.promisingLeads = Number(payload.summary?.promising_count || 0);
  updateTelemetryWidgets();
  renderDrugSummary(payload.summary || {});
  renderDrugCards(state.drugCandidates);
}

function resolveClinicalTrialId() {
  const selected = state.selectedClinicalTrialId || clinicalTrialSelect.value;
  if (selected) {
    return selected;
  }
  const fromInput = clinicalTrialIdInput.value.trim();
  return fromInput || null;
}

function renderClinicalTrialOptions(trials) {
  clinicalTrialSelect.innerHTML = "";

  if (!Array.isArray(trials) || trials.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No managed trials";
    clinicalTrialSelect.appendChild(option);
    clinicalTrialSummary.textContent = "No trial selected.";
    return;
  }

  for (const trial of trials) {
    const option = document.createElement("option");
    option.value = trial.trial_id;
    const human = trial.patient_count_human ?? 0;
    const sim = trial.patient_count_simulated ?? 0;
    option.textContent = `${trial.trial_id} | ${trial.status || "draft"} | H:${human} S:${sim}`;
    if (trial.trial_id === state.selectedClinicalTrialId) {
      option.selected = true;
    }
    clinicalTrialSelect.appendChild(option);
  }

  if (!state.selectedClinicalTrialId && trials.length > 0) {
    state.selectedClinicalTrialId = trials[0].trial_id;
    clinicalTrialSelect.value = state.selectedClinicalTrialId;
  }

  let selected = trials.find((item) => item.trial_id === state.selectedClinicalTrialId) || null;
  if (!selected && trials.length > 0) {
    state.selectedClinicalTrialId = trials[0].trial_id;
    clinicalTrialSelect.value = state.selectedClinicalTrialId;
    selected = trials[0];
  }
  if (selected) {
    clinicalTrialSummary.textContent = pretty(selected);
  }
}

async function refreshClinicalTrials() {
  const payload = await api("/api/clinical/trials", { method: "GET" });
  state.clinicalTrials = payload.trials || [];
  const trials = Array.isArray(payload.trials) ? payload.trials : [];
  state.telemetry.trialCount = trials.length;
  state.telemetry.humanPatients = trials.reduce(
    (sum, trial) => sum + Number(trial?.patient_count_human || 0),
    0
  );
  updateTelemetryWidgets();
  renderClinicalTrialOptions(state.clinicalTrials);
}

function renderCommandCenterProgram(payload) {
  const program = payload?.program || null;
  if (!program) {
    state.commandCenter.selectedProgram = null;
    programSummaryOutput.textContent = "Program not found.";
    programEventTimeline.innerHTML = '<div class="timeline-empty">Load a program to inspect timeline events.</div>';
    renderCommandCenterCapabilities(state.commandCenter.capabilities);
    return;
  }
  state.commandCenter.selectedProgram = program;
  programIdInput.value = program.program_id || "";
  programNameInput.value = program.name || "";
  programStageInput.value = program.stage || "";
  programIndicationInput.value = program.indication || "";
  programOwnerInput.value = program.owner || "";
  programSummaryOutput.textContent = pretty(payload);
  renderProgramTimeline(payload.events || [], payload.approvals || []);
  renderCommandCenterCapabilities(state.commandCenter.capabilities);
}

function selectedGateTemplate() {
  const templateId = gateTemplateSelect.value;
  if (!templateId) {
    return null;
  }
  for (const template of state.commandCenter.gateTemplates) {
    if (String(template.id) === templateId) {
      return template;
    }
  }
  return null;
}

function gateMetricDefaultValue(minimum) {
  const numeric = Number(minimum);
  if (!Number.isFinite(numeric)) {
    return null;
  }
  if (numeric < 1) {
    return Number((numeric + 0.05).toFixed(3));
  }
  return Number((numeric * 1.05).toFixed(2));
}

function gateTemplateDefaultMetrics(template) {
  if (!template || !Array.isArray(template.criteria)) {
    return {};
  }
  const metrics = {};
  for (const criterion of template.criteria) {
    const metric = String(criterion.metric || "").trim();
    if (!metric) {
      continue;
    }
    metrics[metric] = gateMetricDefaultValue(criterion.minimum);
  }
  return metrics;
}

function parseGateMetricsForPreview() {
  const raw = gateMetricsInput.value.trim();
  if (!raw) {
    return { metrics: null, error: null };
  }
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { metrics: null, error: "Metrics JSON must be an object." };
    }
    return { metrics: parsed, error: null };
  } catch (_err) {
    return { metrics: null, error: "Metrics JSON is invalid." };
  }
}

function applyGateTemplateDefaults({ force } = { force: false }) {
  const template = selectedGateTemplate();
  if (!template) {
    return;
  }
  const defaults = gateTemplateDefaultMetrics(template);
  if (Object.keys(defaults).length === 0) {
    return;
  }

  if (force) {
    gateMetricsInput.value = pretty(defaults);
    return;
  }

  const { metrics, error } = parseGateMetricsForPreview();
  if (error) {
    return;
  }
  if (!metrics) {
    gateMetricsInput.value = pretty(defaults);
    return;
  }

  const merged = { ...metrics };
  let changed = false;
  for (const [metric, value] of Object.entries(defaults)) {
    if (!(metric in merged) || merged[metric] === null || merged[metric] === "") {
      merged[metric] = value;
      changed = true;
    }
  }
  if (changed) {
    gateMetricsInput.value = pretty(merged);
  }
}

function timelineStatusClass(status) {
  const normalized = String(status || "").toLowerCase();
  if (["approved", "completed", "success", "passed"].includes(normalized)) {
    return "timeline-status-pass";
  }
  if (["rejected", "failed", "cancelled", "error"].includes(normalized)) {
    return "timeline-status-fail";
  }
  if (["running", "queued", "needs_changes", "warning"].includes(normalized)) {
    return "timeline-status-warn";
  }
  return "timeline-status-neutral";
}

function renderGateTemplatePreview() {
  const template = selectedGateTemplate();
  if (!template) {
    gateTemplateSummary.textContent = "No gate template selected.";
    gateCriteriaChecklist.innerHTML =
      '<div class="gate-criterion gate-criterion-empty">Choose a template to preview criteria.</div>';
    return;
  }

  const { metrics, error } = parseGateMetricsForPreview();
  if (error) {
    gateTemplateSummary.textContent = `${template.label || template.id}: ${error}`;
  } else {
    gateTemplateSummary.textContent =
      template.description || `${template.label || template.id} gate criteria`;
  }

  const criteria = Array.isArray(template.criteria) ? template.criteria : [];
  if (criteria.length === 0) {
    gateCriteriaChecklist.innerHTML =
      '<div class="gate-criterion gate-criterion-empty">This template has no criteria.</div>';
    return;
  }

  let passed = 0;
  gateCriteriaChecklist.innerHTML = criteria
    .map((criterion) => {
      const metric = String(criterion.metric || "");
      const label = String(criterion.label || metric);
      const minimum = Number(criterion.minimum || 0);
      const observedRaw = metrics ? metrics[metric] : null;
      const observed = Number(observedRaw);
      const hasObserved = observedRaw !== null && observedRaw !== undefined && Number.isFinite(observed);
      const ok = hasObserved && observed >= minimum;
      if (ok) {
        passed += 1;
      }
      const statusClass = hasObserved ? (ok ? "gate-criterion-pass" : "gate-criterion-fail") : "gate-criterion-missing";
      const statusText = hasObserved ? (ok ? "pass" : "below") : "missing";
      const observedLabel = hasObserved ? String(observedRaw) : "n/a";
      return `
        <article class="gate-criterion ${statusClass}">
          <div class="gate-criterion-top">
            <span class="gate-criterion-label">${escapeHtml(label)}</span>
            <span class="gate-criterion-status">${escapeHtml(statusText)}</span>
          </div>
          <div class="gate-criterion-meta">
            <span>${escapeHtml(metric)}</span>
            <span>min ${escapeHtml(minimum)}</span>
            <span>observed ${escapeHtml(observedLabel)}</span>
          </div>
        </article>
      `;
    })
    .join("");

  if (!error) {
    gateTemplateSummary.textContent = `${template.label || template.id}: ${passed}/${criteria.length} checks passing`;
  }
}

function renderCommandCenterCapabilities(payload) {
  state.commandCenter.capabilities = payload || null;
  const integrations = Array.isArray(payload?.integrations) ? payload.integrations : [];
  const counts = state.commandCenter.programCounts || {};
  const programCount = Number(counts.programs || 0);
  const eventCount = Number(counts.events || 0);
  const approvalCount = Number(counts.approvals || 0);
  const online = integrations.filter((item) => item.available).length;
  const readiness = online >= 3 ? "operational" : online >= 2 ? "degraded" : "critical";
  const warnings = Array.isArray(payload?.warnings) ? payload.warnings : [];
  const cards = [
    {
      label: "Integrations Online",
      value: `${online}/${integrations.length || 0}`,
      note: warnings.length ? `${warnings.length} warning(s)` : "All core packages visible",
      tone: online >= 3 ? "good" : "warn",
    },
    {
      label: "Programs Tracked",
      value: String(programCount),
      note: `${eventCount} timeline events`,
      tone: programCount > 0 ? "neutral" : "warn",
    },
    {
      label: "Active Stage",
      value: state.commandCenter.selectedProgram?.stage || "unassigned",
      note: `${approvalCount} approvals recorded`,
      tone: state.commandCenter.selectedProgram?.stage ? "neutral" : "warn",
    },
    {
      label: "Regulatory Readiness",
      value: readiness,
      note: payload?.generated_at ? `Updated ${formatDate(payload.generated_at)}` : "",
      tone: readiness === "operational" ? "good" : readiness === "degraded" ? "warn" : "alert",
    },
  ];
  commandCenterCapabilities.innerHTML = cards
    .map(
      (item) => `
        <article class="command-cap command-cap-${escapeHtml(item.tone || "neutral")}">
          <p class="command-cap-label">${escapeHtml(item.label)}</p>
          <p class="command-cap-value">${escapeHtml(item.value)}</p>
          ${item.note ? `<p class="command-note">${escapeHtml(item.note)}</p>` : ""}
        </article>
      `
    )
    .join("");
}

function renderProgramTimeline(events, approvals) {
  const timeline = [];
  for (const event of Array.isArray(events) ? events : []) {
    timeline.push({
      kind: "event",
      title: event.title || event.event_type || "event",
      status: event.status || "recorded",
      at: event.created_at || "",
      meta: event.source || "refua-studio",
      runId: event.run_id || "",
    });
  }
  for (const approval of Array.isArray(approvals) ? approvals : []) {
    timeline.push({
      kind: "approval",
      title: `Gate ${approval.gate || "stage_gate"}`,
      status: approval.decision || "recorded",
      at: approval.created_at || "",
      meta: approval.signer || "unknown",
    });
  }

  timeline.sort((a, b) => String(b.at).localeCompare(String(a.at)));
  if (timeline.length === 0) {
    programEventTimeline.innerHTML = '<div class="timeline-empty">No timeline events yet.</div>';
    return;
  }

  programEventTimeline.innerHTML = timeline
    .slice(0, 40)
    .map(
      (item) => `
        <article class="timeline-item">
          <div class="timeline-top">
            <div class="timeline-title">${escapeHtml(item.title)}</div>
            <span class="timeline-status ${timelineStatusClass(item.status)}">${escapeHtml(item.status)}</span>
          </div>
          <div class="timeline-meta">${escapeHtml(formatDate(item.at))} · ${escapeHtml(item.meta)}${item.runId ? ` · ${escapeHtml(item.runId)}` : ""}</div>
        </article>
      `
    )
    .join("");
}

function wetlabProviderId() {
  return wetlabProviderSelect.value || "opentrons";
}

function parseWetlabProtocol() {
  const protocol = parseJsonText(wetlabProtocolInput.value, "WetLab protocol");
  if (!protocol || typeof protocol !== "object" || Array.isArray(protocol)) {
    throw new Error("WetLab protocol must be a JSON object");
  }
  return protocol;
}

async function refreshCommandCenter() {
  try {
    await api("/api/programs/sync-jobs", {
      method: "POST",
      body: JSON.stringify({ limit: 500 }),
    });
  } catch (_err) {
    // Keep UI responsive if sync fails due to transient runtime issues.
  }

  const [capabilities, wetlabProviders, gateTemplates, programsPayload] = await Promise.all([
    api("/api/command-center/capabilities", { method: "GET" }),
    api("/api/wetlab/providers", { method: "GET" }),
    api("/api/program-gates/templates", { method: "GET" }),
    api("/api/programs?limit=1", { method: "GET" }),
  ]);

  state.commandCenter.wetlabProviders = wetlabProviders.providers || [];
  state.commandCenter.gateTemplates = gateTemplates.templates || [];
  state.commandCenter.programCounts = programsPayload.counts || {};
  renderCommandCenterCapabilities(capabilities);

  const selectedTemplate = gateTemplateSelect.value;
  gateTemplateSelect.innerHTML = "";
  for (const template of state.commandCenter.gateTemplates) {
    const option = document.createElement("option");
    option.value = template.id;
    option.textContent = `${template.label} (${template.criteria?.length || 0} checks)`;
    if (selectedTemplate && selectedTemplate === template.id) {
      option.selected = true;
    }
    gateTemplateSelect.appendChild(option);
  }
  if (gateTemplateSelect.options.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No templates";
    gateTemplateSelect.appendChild(option);
  }
  applyGateTemplateDefaults({ force: false });
  renderGateTemplatePreview();

  const selectedProvider = wetlabProviderSelect.value;
  wetlabProviderSelect.innerHTML = "";
  for (const provider of state.commandCenter.wetlabProviders) {
    const option = document.createElement("option");
    option.value = provider.provider_id;
    option.textContent = `${provider.provider_id} (${provider.provider_name || "provider"})`;
    if (selectedProvider && selectedProvider === provider.provider_id) {
      option.selected = true;
    }
    wetlabProviderSelect.appendChild(option);
  }
  if (wetlabProviderSelect.options.length === 0) {
    const option = document.createElement("option");
    option.value = "opentrons";
    option.textContent = "opentrons";
    wetlabProviderSelect.appendChild(option);
  }

  const current = currentProgramId();
  if (current) {
    try {
      const payload = await api(`/api/programs/${encodeURIComponent(current)}`, { method: "GET" });
      renderCommandCenterProgram(payload);
    } catch (_err) {
      // Keep command center refresh resilient when program does not exist yet.
      renderCommandCenterProgram(null);
    }
  }
}

function currentProgramId() {
  return programIdInput.value.trim() || null;
}

async function doUpsertProgram() {
  const payload = {
    program_id: currentProgramId(),
    name: programNameInput.value.trim() || null,
    stage: programStageInput.value.trim() || null,
    indication: programIndicationInput.value.trim() || null,
    owner: programOwnerInput.value.trim() || null,
    metadata: {
      source: "refua-studio",
    },
  };
  const result = await api("/api/programs/upsert", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  renderCommandCenterProgram(result);
  showOutput("Program Upserted", result);
}

async function doLoadProgram() {
  const programId = currentProgramId();
  if (!programId) {
    throw new Error("Program ID is required");
  }
  const payload = await api(`/api/programs/${encodeURIComponent(programId)}`, { method: "GET" });
  renderCommandCenterProgram(payload);
  showOutput("Program Loaded", payload);
}

async function doApproveProgram() {
  const programId = currentProgramId();
  if (!programId) {
    throw new Error("Program ID is required");
  }
  const payload = await api(`/api/programs/${encodeURIComponent(programId)}/approve`, {
    method: "POST",
    body: JSON.stringify({
      gate: "stage_gate",
      decision: "approved",
      signer: programOwnerInput.value.trim() || "refua-studio",
      signature: `studio:${new Date().toISOString()}`,
      rationale: "Recorded from Studio command center",
      metadata: {
        stage: programStageInput.value.trim() || null,
      },
    }),
  });
  showOutput("Program Approval Recorded", payload);
  await doLoadProgram();
}

function parseGateMetrics() {
  const { metrics, error } = parseGateMetricsForPreview();
  if (error || !metrics) {
    throw new Error("Gate metrics must be a JSON object");
  }
  return metrics;
}

async function doEvaluateProgramGate() {
  const programId = currentProgramId();
  if (!programId) {
    throw new Error("Program ID is required");
  }
  const templateId = gateTemplateSelect.value;
  if (!templateId) {
    throw new Error("Select a gate template");
  }
  const payload = await api(`/api/programs/${encodeURIComponent(programId)}/gate-evaluate`, {
    method: "POST",
    body: JSON.stringify({
      template_id: templateId,
      metrics: parseGateMetrics(),
      auto_record: true,
      signer: programOwnerInput.value.trim() || "refua-studio",
    }),
  });
  showOutput("Stage Gate Evaluation", payload);
  await doLoadProgram();
}

async function doSyncProgramJobs() {
  const payload = await api("/api/programs/sync-jobs", {
    method: "POST",
    body: JSON.stringify({ limit: 500 }),
  });
  showOutput("Program Job Sync", payload);
  if (currentProgramId()) {
    await doLoadProgram();
  }
}

async function doListDatasets() {
  const payload = await api("/api/data/datasets?limit=60", { method: "GET" });
  showOutput("Dataset Catalog", payload);
}

async function doMaterializeDataset() {
  const datasetId = datasetIdInput.value.trim();
  if (!datasetId) {
    throw new Error("Dataset ID is required");
  }
  const payload = await api("/api/data/materialize", {
    method: "POST",
    body: JSON.stringify({
      dataset_id: datasetId,
      async_mode: asyncToggle.checked,
    }),
  });
  showOutput("Dataset Materialize", payload);
  if (asyncToggle.checked) {
    await refreshJobs();
  }
}

async function doRunBenchmarkGate() {
  const suitePath = benchSuitePathInput.value.trim();
  const baselinePath = benchBaselinePathInput.value.trim();
  const predictionsPath = benchPredictionsPathInput.value.trim();
  if (!suitePath || !baselinePath || !predictionsPath) {
    throw new Error("Suite path, baseline path, and predictions path are required");
  }
  const payload = await api("/api/bench/gate", {
    method: "POST",
    body: JSON.stringify({
      suite_path: suitePath,
      baseline_run_path: baselinePath,
      adapter_spec: "file",
      adapter_config: {
        predictions_path: predictionsPath,
      },
      async_mode: asyncToggle.checked,
      model_name: "studio-gate",
      model_version: new Date().toISOString(),
    }),
  });
  showOutput("Benchmark Gate", payload);
  if (asyncToggle.checked) {
    await refreshJobs();
  }
}

async function doValidateWetlabProtocol() {
  const payload = await api("/api/wetlab/protocol/validate", {
    method: "POST",
    body: JSON.stringify({ protocol: parseWetlabProtocol() }),
  });
  showOutput("WetLab Protocol Validation", payload);
}

async function doRunWetlabProtocol() {
  const payload = await api("/api/wetlab/run", {
    method: "POST",
    body: JSON.stringify({
      provider: wetlabProviderId(),
      protocol: parseWetlabProtocol(),
      dry_run: true,
      async_mode: asyncToggle.checked,
      program_id: currentProgramId(),
      metadata: {
        objective: objectiveInput.value.trim() || null,
      },
    }),
  });
  showOutput("WetLab Run", payload);
  if (asyncToggle.checked) {
    await refreshJobs();
  } else if (currentProgramId()) {
    await doLoadProgram();
  }
}

async function doBuildRegulatoryBundle() {
  const jobId = regulatoryJobIdInput.value.trim() || state.selectedJobId || null;
  const outputDir = regulatoryOutputDirInput.value.trim() || null;
  const fallbackPlan = parseJsonText(planInput.value, "Plan");
  const fallbackCampaignRun = {
    objective: objectiveInput.value.trim() || null,
    plan: fallbackPlan,
    dry_run: dryRunToggle.checked,
    source: "refua-studio-ui",
  };
  const payload = await api("/api/regulatory/bundle/build", {
    method: "POST",
    body: JSON.stringify({
      job_id: jobId,
      campaign_run: jobId ? null : fallbackCampaignRun,
      output_dir: outputDir,
      async_mode: asyncToggle.checked,
      overwrite: true,
      program_id: currentProgramId(),
    }),
  });
  showOutput("Regulatory Bundle Build", payload);
  if (asyncToggle.checked) {
    await refreshJobs();
  } else {
    const bundleDir = payload.result?.bundle_dir;
    if (bundleDir) {
      regulatoryOutputDirInput.value = bundleDir;
    }
    if (currentProgramId()) {
      await doLoadProgram();
    }
  }
}

async function doVerifyRegulatoryBundle() {
  const bundleDir = regulatoryOutputDirInput.value.trim();
  if (!bundleDir) {
    throw new Error("Bundle output directory is required");
  }
  const payload = await api("/api/regulatory/bundle/verify", {
    method: "POST",
    body: JSON.stringify({ bundle_dir: bundleDir }),
  });
  showOutput("Regulatory Bundle Verify", payload);
}

async function loadClinicalTrial() {
  const trialId = resolveClinicalTrialId();
  if (!trialId) {
    throw new Error("Select a trial first");
  }

  const payload = await api(`/api/clinical/trials/${encodeURIComponent(trialId)}`, { method: "GET" });
  const trial = payload.trial || {};
  state.selectedClinicalTrialId = trial.trial_id || trialId;
  clinicalTrialSelect.value = state.selectedClinicalTrialId;

  clinicalTrialIdInput.value = state.selectedClinicalTrialId;
  if (trial.status) {
    clinicalTrialStatusInput.value = trial.status;
  }
  if (trial.config) {
    clinicalTrialConfigInput.value = pretty(trial.config);
  }

  clinicalTrialSummary.textContent = pretty(trial);
  showOutput("Clinical Trial Detail", payload);
}

async function doAddClinicalTrial() {
  const trialId = clinicalTrialIdInput.value.trim() || null;
  const configPatch = parseJsonText(clinicalTrialConfigInput.value, "Clinical config");
  if (
    configPatch !== null &&
    (typeof configPatch !== "object" || Array.isArray(configPatch))
  ) {
    throw new Error("Clinical config patch must be a JSON object");
  }

  const payload = {
    trial_id: trialId,
    status: clinicalTrialStatusInput.value || "planned",
    config: null,
  };
  const result = await api("/api/clinical/trials/add", {
    method: "POST",
    body: JSON.stringify(payload),
  });

  const resolvedTrialId = result.trial?.trial_id || trialId;
  if (!resolvedTrialId) {
    throw new Error("Could not resolve created trial id");
  }

  if (configPatch && Object.keys(configPatch).length > 0) {
    await api("/api/clinical/trials/update", {
      method: "POST",
      body: JSON.stringify({
        trial_id: resolvedTrialId,
        updates: { config: configPatch },
      }),
    });
  }

  state.selectedClinicalTrialId = resolvedTrialId;
  showOutput("Clinical Trial Added", result);
  await refreshClinicalTrials();
  await loadClinicalTrial();
}

async function doUpdateClinicalTrial() {
  const trialId = resolveClinicalTrialId();
  if (!trialId) {
    throw new Error("Select or enter a trial id");
  }
  const config = parseJsonText(clinicalTrialConfigInput.value, "Clinical config");
  if (config !== null && (typeof config !== "object" || Array.isArray(config))) {
    throw new Error("Clinical config must be a JSON object");
  }

  const updates = {
    status: clinicalTrialStatusInput.value || null,
  };
  if (config) {
    updates.config = config;
  }

  const result = await api("/api/clinical/trials/update", {
    method: "POST",
    body: JSON.stringify({
      trial_id: trialId,
      updates,
    }),
  });
  state.selectedClinicalTrialId = trialId;
  showOutput("Clinical Trial Updated", result);
  await refreshClinicalTrials();
  await loadClinicalTrial();
}

async function doRemoveClinicalTrial() {
  const trialId = resolveClinicalTrialId();
  if (!trialId) {
    throw new Error("Select a trial to remove");
  }

  const result = await api("/api/clinical/trials/remove", {
    method: "POST",
    body: JSON.stringify({ trial_id: trialId }),
  });
  showOutput("Clinical Trial Removed", result);
  state.selectedClinicalTrialId = null;
  clinicalTrialSummary.textContent = "No trial selected.";
  await refreshClinicalTrials();
}

async function doEnrollClinicalPatient() {
  const trialId = resolveClinicalTrialId();
  if (!trialId) {
    throw new Error("Select a trial first");
  }
  const patient = parseJsonText(clinicalPatientInput.value, "Patient payload");
  if (!patient || typeof patient !== "object") {
    throw new Error("Patient payload must be a JSON object");
  }

  const result = await api("/api/clinical/trials/enroll", {
    method: "POST",
    body: JSON.stringify({
      trial_id: trialId,
      patient_id: patient.patient_id || null,
      source: patient.source || "human",
      arm_id: patient.arm_id || null,
      site_id: patient.site_id || null,
      demographics: patient.demographics || {},
      baseline: patient.baseline || {},
      metadata: patient.metadata || {},
    }),
  });
  showOutput("Clinical Patient Enrolled", result);
  await refreshClinicalTrials();
  await loadClinicalTrial();
}

async function doEnrollClinicalSimulated() {
  const trialId = resolveClinicalTrialId();
  if (!trialId) {
    throw new Error("Select a trial first");
  }
  const count = Number(clinicalSimCountInput.value || 0);
  if (!Number.isFinite(count) || count < 1) {
    throw new Error("Simulated patient count must be >= 1");
  }
  const seedValue = clinicalSeedInput.value.trim();

  const result = await api("/api/clinical/trials/enroll-simulated", {
    method: "POST",
    body: JSON.stringify({
      trial_id: trialId,
      count: Number(count),
      seed: seedValue ? Number(seedValue) : null,
    }),
  });
  showOutput("Simulated Patients Enrolled", result);
  await refreshClinicalTrials();
  await loadClinicalTrial();
}

async function doAddClinicalResult() {
  const trialId = resolveClinicalTrialId();
  if (!trialId) {
    throw new Error("Select a trial first");
  }
  const rawResult = parseJsonText(clinicalResultInput.value, "Result payload");
  if (!rawResult || typeof rawResult !== "object") {
    throw new Error("Result payload must be a JSON object");
  }

  const patientId = rawResult.patient_id;
  if (!patientId || typeof patientId !== "string") {
    throw new Error("Result payload must include patient_id");
  }

  let values = rawResult.values;
  if (!values || typeof values !== "object") {
    const clone = { ...rawResult };
    delete clone.patient_id;
    delete clone.result_type;
    delete clone.visit;
    delete clone.source;
    values = clone;
  }

  const result = await api("/api/clinical/trials/result", {
    method: "POST",
    body: JSON.stringify({
      trial_id: trialId,
      patient_id: patientId,
      result_type: rawResult.result_type || "endpoint",
      visit: rawResult.visit || null,
      source: rawResult.source || null,
      site_id: rawResult.site_id || null,
      values,
    }),
  });
  showOutput("Clinical Result Added", result);
  await refreshClinicalTrials();
  await loadClinicalTrial();
}

async function doSimulateClinicalTrial() {
  const trialId = resolveClinicalTrialId();
  if (!trialId) {
    throw new Error("Select a trial first");
  }

  const replicates = Number(clinicalReplicatesInput.value || 0);
  if (!Number.isFinite(replicates) || replicates < 1) {
    throw new Error("Replicates must be >= 1");
  }
  const seedValue = clinicalSeedInput.value.trim();

  const result = await api("/api/clinical/trials/simulate", {
    method: "POST",
    body: JSON.stringify({
      trial_id: trialId,
      replicates: Number(replicates),
      seed: seedValue ? Number(seedValue) : null,
      async_mode: asyncToggle.checked,
    }),
  });

  showOutput("Clinical Simulation", result);
  await refreshClinicalTrials();
  if (asyncToggle.checked) {
    await refreshJobs();
  } else {
    await loadClinicalTrial();
  }
}

function parseClinicalOpsPayload() {
  const raw = parseJsonText(clinicalOpsInput.value, "ClinOps payload");
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("ClinOps payload must be a JSON object");
  }
  return raw;
}

async function doUpsertClinicalSite() {
  const trialId = resolveClinicalTrialId();
  if (!trialId) {
    throw new Error("Select a trial first");
  }
  const raw = parseClinicalOpsPayload();
  if (!raw.site_id || typeof raw.site_id !== "string") {
    throw new Error("ClinOps payload must include site_id");
  }
  const result = await api("/api/clinical/trials/site/upsert", {
    method: "POST",
    body: JSON.stringify({
      trial_id: trialId,
      site_id: raw.site_id,
      name: raw.name || null,
      country_id: raw.country_id || null,
      status: raw.status || null,
      principal_investigator: raw.principal_investigator || null,
      target_enrollment:
        raw.target_enrollment === undefined || raw.target_enrollment === null
          ? null
          : Number(raw.target_enrollment),
      metadata: raw.metadata || {},
    }),
  });
  showOutput("Clinical Site Upserted", result);
  await refreshClinicalTrials();
  await loadClinicalTrial();
}

async function doScreenClinicalPatient() {
  const trialId = resolveClinicalTrialId();
  if (!trialId) {
    throw new Error("Select a trial first");
  }
  const raw = parseClinicalOpsPayload();
  if (!raw.site_id || typeof raw.site_id !== "string") {
    throw new Error("ClinOps payload must include site_id");
  }
  const result = await api("/api/clinical/trials/screen", {
    method: "POST",
    body: JSON.stringify({
      trial_id: trialId,
      site_id: raw.site_id,
      patient_id: raw.patient_id || null,
      status: raw.status || null,
      arm_id: raw.arm_id || null,
      source: raw.source || null,
      failure_reason: raw.failure_reason || null,
      demographics: raw.demographics || {},
      baseline: raw.baseline || {},
      metadata: raw.metadata || {},
      auto_enroll: Boolean(raw.auto_enroll),
    }),
  });
  showOutput("Clinical Screening Added", result);
  await refreshClinicalTrials();
  await loadClinicalTrial();
}

async function doRecordClinicalVisit() {
  const trialId = resolveClinicalTrialId();
  if (!trialId) {
    throw new Error("Select a trial first");
  }
  const raw = parseClinicalOpsPayload();
  if (!raw.site_id || typeof raw.site_id !== "string") {
    throw new Error("ClinOps payload must include site_id");
  }
  const result = await api("/api/clinical/trials/monitoring/visit", {
    method: "POST",
    body: JSON.stringify({
      trial_id: trialId,
      site_id: raw.site_id,
      visit_type: raw.visit_type || null,
      findings: Array.isArray(raw.findings) ? raw.findings : [],
      action_items: Array.isArray(raw.action_items) ? raw.action_items : [],
      risk_score:
        raw.risk_score === undefined || raw.risk_score === null ? null : Number(raw.risk_score),
      outcome: raw.outcome || null,
      metadata: raw.metadata || {},
    }),
  });
  showOutput("Clinical Monitoring Visit Added", result);
  await refreshClinicalTrials();
  await loadClinicalTrial();
}

async function doAddClinicalQuery() {
  const trialId = resolveClinicalTrialId();
  if (!trialId) {
    throw new Error("Select a trial first");
  }
  const raw = parseClinicalOpsPayload();
  if (!raw.description || typeof raw.description !== "string") {
    throw new Error("ClinOps payload must include description for query");
  }
  const result = await api("/api/clinical/trials/query/add", {
    method: "POST",
    body: JSON.stringify({
      trial_id: trialId,
      patient_id: raw.patient_id || null,
      site_id: raw.site_id || null,
      field_name: raw.field_name || null,
      description: raw.description,
      status: raw.status || null,
      severity: raw.severity || null,
      assignee: raw.assignee || null,
      due_at: raw.due_at || null,
      metadata: raw.metadata || {},
    }),
  });
  showOutput("Clinical Query Added", result);
  await refreshClinicalTrials();
  await loadClinicalTrial();
}

async function doUpdateClinicalQuery() {
  const trialId = resolveClinicalTrialId();
  if (!trialId) {
    throw new Error("Select a trial first");
  }
  const raw = parseClinicalOpsPayload();
  if (!raw.query_id || typeof raw.query_id !== "string") {
    throw new Error("ClinOps payload must include query_id");
  }
  const updates =
    raw.updates && typeof raw.updates === "object" && !Array.isArray(raw.updates)
      ? raw.updates
      : {
          status: raw.status || null,
          assignee: raw.assignee || null,
          resolution: raw.resolution || null,
        };
  const result = await api("/api/clinical/trials/query/update", {
    method: "POST",
    body: JSON.stringify({
      trial_id: trialId,
      query_id: raw.query_id,
      updates,
    }),
  });
  showOutput("Clinical Query Updated", result);
  await refreshClinicalTrials();
  await loadClinicalTrial();
}

async function doAddClinicalDeviation() {
  const trialId = resolveClinicalTrialId();
  if (!trialId) {
    throw new Error("Select a trial first");
  }
  const raw = parseClinicalOpsPayload();
  if (!raw.description || typeof raw.description !== "string") {
    throw new Error("ClinOps payload must include description for deviation");
  }
  const result = await api("/api/clinical/trials/deviation/add", {
    method: "POST",
    body: JSON.stringify({
      trial_id: trialId,
      description: raw.description,
      site_id: raw.site_id || null,
      patient_id: raw.patient_id || null,
      category: raw.category || null,
      severity: raw.severity || null,
      status: raw.status || null,
      corrective_action: raw.corrective_action || null,
      preventive_action: raw.preventive_action || null,
      metadata: raw.metadata || {},
    }),
  });
  showOutput("Clinical Deviation Added", result);
  await refreshClinicalTrials();
  await loadClinicalTrial();
}

async function doAddClinicalSafetyEvent() {
  const trialId = resolveClinicalTrialId();
  if (!trialId) {
    throw new Error("Select a trial first");
  }
  const raw = parseClinicalOpsPayload();
  if (!raw.patient_id || typeof raw.patient_id !== "string") {
    throw new Error("ClinOps payload must include patient_id for safety event");
  }
  if (!raw.event_term || typeof raw.event_term !== "string") {
    throw new Error("ClinOps payload must include event_term for safety event");
  }
  const result = await api("/api/clinical/trials/safety/add", {
    method: "POST",
    body: JSON.stringify({
      trial_id: trialId,
      patient_id: raw.patient_id,
      event_term: raw.event_term,
      site_id: raw.site_id || null,
      seriousness: raw.seriousness || null,
      expected:
        raw.expected === undefined || raw.expected === null ? null : Boolean(raw.expected),
      relatedness: raw.relatedness || null,
      outcome: raw.outcome || null,
      action_taken: raw.action_taken || null,
      metadata: raw.metadata || {},
    }),
  });
  showOutput("Clinical Safety Event Added", result);
  await refreshClinicalTrials();
  await loadClinicalTrial();
}

async function doUpsertClinicalMilestone() {
  const trialId = resolveClinicalTrialId();
  if (!trialId) {
    throw new Error("Select a trial first");
  }
  const raw = parseClinicalOpsPayload();
  const result = await api("/api/clinical/trials/milestone/upsert", {
    method: "POST",
    body: JSON.stringify({
      trial_id: trialId,
      milestone_id: raw.milestone_id || null,
      name: raw.name || null,
      target_date: raw.target_date || null,
      status: raw.status || null,
      owner: raw.owner || null,
      actual_date: raw.actual_date || null,
      metadata: raw.metadata || {},
    }),
  });
  showOutput("Clinical Milestone Upserted", result);
  await refreshClinicalTrials();
  await loadClinicalTrial();
}

async function doRefreshClinicalOps() {
  const trialId = resolveClinicalTrialId();
  if (!trialId) {
    throw new Error("Select a trial first");
  }
  const [ops, sites] = await Promise.all([
    api(`/api/clinical/trials/${encodeURIComponent(trialId)}/ops`, { method: "GET" }),
    api(`/api/clinical/trials/${encodeURIComponent(trialId)}/sites`, { method: "GET" }),
  ]);
  const payload = {
    trial_id: trialId,
    ops,
    sites,
  };
  clinicalTrialSummary.textContent = pretty(payload);
  showOutput("Clinical Ops Snapshot", payload);
}

function currentRunPayload() {
  const plan = parseJsonText(planInput.value, "Plan");
  const prompt = systemPromptInput.value.trim();
  return {
    objective: objectiveInput.value,
    system_prompt: prompt || null,
    dry_run: dryRunToggle.checked,
    async_mode: asyncToggle.checked,
    autonomous: false,
    max_rounds: Number(maxRoundsInput.value || 3),
    max_calls: Number(maxCallsInput.value || 10),
    allow_skip_validate_first: skipValidateFirstToggle.checked,
    plan,
    program_id: currentProgramId(),
  };
}

function formatJsonTextarea(textarea, label) {
  const parsed = parseJsonText(textarea.value, label);
  if (!parsed) {
    throw new Error(`${label} is empty`);
  }
  textarea.value = pretty(parsed);
}

function loadObjectiveTemplate() {
  const template = selectedTemplate(objectiveTemplateSelect, state.examples.objectives);
  if (!template) {
    throw new Error("No objective template selected");
  }
  objectiveInput.value = template.objective;
  showOutput("Objective Template Loaded", template);
}

function loadPlanTemplate() {
  const template = selectedTemplate(planTemplateSelect, state.examples.plan_templates);
  if (!template) {
    throw new Error("No plan template selected");
  }
  planInput.value = pretty(template.plan);
  showOutput("Plan Template Loaded", template);
}

function loadPortfolioTemplate() {
  const template = selectedTemplate(portfolioTemplateSelect, state.examples.portfolio_templates);
  if (!template) {
    throw new Error("No portfolio template selected");
  }
  portfolioInput.value = pretty(template.programs);
  showOutput("Portfolio Template Loaded", template);
}

function loadClawCuresObjective() {
  const objective = state.ecosystem?.clawcures?.default_objective;
  if (!objective) {
    throw new Error("ClawCures objective is not available yet");
  }
  objectiveInput.value = objective;
  showOutput("ClawCures Objective Loaded", { objective });
}

async function doPlan() {
  const prompt = systemPromptInput.value.trim();
  const payload = {
    objective: objectiveInput.value,
    system_prompt: prompt || null,
  };
  const result = await api("/api/plan", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (result.plan) {
    planInput.value = pretty(result.plan);
  }
  showOutput("Planner Response", result);
}

async function doRun({ autonomous }) {
  const payload = currentRunPayload();
  payload.autonomous = autonomous;

  const result = await api("/api/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  showOutput(autonomous ? "Autonomous Run Submitted" : "Run Submitted", result);
  await refreshJobs();
  await refreshDrugPortfolio();
}

async function doValidatePlan() {
  const plan = parseJsonText(planInput.value, "Plan");
  if (!plan) {
    throw new Error("Plan must not be empty");
  }

  const payload = {
    plan,
    max_calls: Number(maxCallsInput.value || 10),
    allow_skip_validate_first: skipValidateFirstToggle.checked,
  };
  const result = await api("/api/plan/validate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  showOutput("Plan Validation", result);
}

async function doExecutePlan() {
  const plan = parseJsonText(planInput.value, "Plan");
  if (!plan) {
    throw new Error("Plan must not be empty");
  }

  const payload = {
    plan,
    async_mode: asyncToggle.checked,
    program_id: currentProgramId(),
  };
  const result = await api("/api/plan/execute", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  showOutput("Plan Execution", result);
  await refreshJobs();
  await refreshDrugPortfolio();
}

async function doRankPortfolio() {
  const programs = parseJsonText(portfolioInput.value, "Portfolio");
  if (!Array.isArray(programs)) {
    throw new Error("Portfolio input must be a JSON array");
  }

  const payload = {
    programs,
  };
  const result = await api("/api/portfolio/rank", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  showOutput("Portfolio Ranking", result);
}

async function doCancelSelectedJob() {
  if (!state.selectedJobId) {
    throw new Error("No job selected");
  }
  const result = await api(`/api/jobs/${state.selectedJobId}/cancel`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  showOutput("Cancel Job", result);
  await refreshJobs();
}

async function doClearFinishedJobs() {
  const result = await api("/api/jobs/clear", {
    method: "POST",
    body: JSON.stringify({ statuses: ["completed", "failed", "cancelled"] }),
  });
  state.selectedJobId = null;
  showOutput("Cleared Finished Jobs", result);
  await refreshJobs();
}

async function doGenerateHandoff() {
  const plan = parseJsonText(planInput.value, "Plan");
  const payload = {
    objective: objectiveInput.value,
    system_prompt: systemPromptInput.value.trim() || null,
    plan,
    autonomous: false,
    dry_run: dryRunToggle.checked,
    max_calls: Number(maxCallsInput.value || 10),
    allow_skip_validate_first: skipValidateFirstToggle.checked,
    write_file: handoffWriteFileToggle.checked,
    artifact_name: handoffArtifactNameInput.value.trim() || null,
  };

  const result = await api("/api/clawcures/handoff", {
    method: "POST",
    body: JSON.stringify(payload),
  });

  state.handoff = result;
  renderHandoffCommands(result);
  showOutput("ClawCures Handoff", result);
}

function bindKeyboardShortcuts() {
  document.addEventListener("keydown", (event) => {
    if (!event.metaKey && !event.ctrlKey) {
      return;
    }
    if (event.key === "Enter" && event.shiftKey) {
      event.preventDefault();
      wrapAction(() => doRun({ autonomous: true }));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      wrapAction(() => doRun({ autonomous: false }));
    }
  });
}

function bindActions() {
  document.getElementById("planButton").addEventListener("click", () => wrapAction(doPlan));
  document.getElementById("runButton").addEventListener("click", () =>
    wrapAction(() => doRun({ autonomous: false }))
  );
  document.getElementById("autonomousButton").addEventListener("click", () =>
    wrapAction(() => doRun({ autonomous: true }))
  );

  document.getElementById("validatePlanButton").addEventListener("click", () =>
    wrapAction(doValidatePlan)
  );
  document.getElementById("executePlanButton").addEventListener("click", () =>
    wrapAction(doExecutePlan)
  );
  document.getElementById("rankPortfolioButton").addEventListener("click", () =>
    wrapAction(doRankPortfolio)
  );

  document.getElementById("loadObjectiveTemplateButton").addEventListener("click", () =>
    wrapAction(loadObjectiveTemplate)
  );
  document.getElementById("loadPlanTemplateButton").addEventListener("click", () =>
    wrapAction(loadPlanTemplate)
  );
  document.getElementById("loadPortfolioTemplateButton").addEventListener("click", () =>
    wrapAction(loadPortfolioTemplate)
  );
  document.getElementById("loadClawCuresObjectiveButton").addEventListener("click", () =>
    wrapAction(loadClawCuresObjective)
  );

  document.getElementById("formatPlanButton").addEventListener("click", () =>
    wrapAction(() => formatJsonTextarea(planInput, "Plan"))
  );
  document.getElementById("formatPortfolioButton").addEventListener("click", () =>
    wrapAction(() => formatJsonTextarea(portfolioInput, "Portfolio"))
  );

  document.getElementById("refreshJobsButton").addEventListener("click", () => wrapAction(refreshJobs));
  document.getElementById("cancelJobButton").addEventListener("click", () =>
    wrapAction(doCancelSelectedJob)
  );
  document.getElementById("clearFinishedJobsButton").addEventListener("click", () =>
    wrapAction(doClearFinishedJobs)
  );
  document.getElementById("jobStatusFilter").addEventListener("change", () => {
    wrapAction(refreshJobs);
  });

  document.getElementById("refreshToolsButton").addEventListener("click", () =>
    wrapAction(refreshTools)
  );
  document.getElementById("refreshDrugPortfolioButton").addEventListener("click", () =>
    wrapAction(refreshDrugPortfolio)
  );
  document.getElementById("refreshEcosystemButton").addEventListener("click", () =>
    wrapAction(async () => {
      await refreshEcosystem();
      await refreshHealth();
    })
  );
  document.getElementById("refreshCommandCenterButton").addEventListener("click", () =>
    wrapAction(refreshCommandCenter)
  );
  document.getElementById("syncProgramJobsButton").addEventListener("click", () =>
    wrapAction(doSyncProgramJobs)
  );
  document.getElementById("loadProgramButton").addEventListener("click", () =>
    wrapAction(doLoadProgram)
  );
  document.getElementById("upsertProgramButton").addEventListener("click", () =>
    wrapAction(doUpsertProgram)
  );
  document.getElementById("approveProgramButton").addEventListener("click", () =>
    wrapAction(doApproveProgram)
  );
  document.getElementById("evaluateProgramGateButton").addEventListener("click", () =>
    wrapAction(doEvaluateProgramGate)
  );
  gateTemplateSelect.addEventListener("change", () => {
    applyGateTemplateDefaults({ force: false });
    renderGateTemplatePreview();
  });
  gateMetricsInput.addEventListener("input", () => {
    renderGateTemplatePreview();
  });
  document.getElementById("loadGateTemplateDefaultsButton").addEventListener("click", () => {
    applyGateTemplateDefaults({ force: true });
    renderGateTemplatePreview();
  });
  document.getElementById("listDatasetsButton").addEventListener("click", () =>
    wrapAction(doListDatasets)
  );
  document.getElementById("materializeDatasetButton").addEventListener("click", () =>
    wrapAction(doMaterializeDataset)
  );
  document.getElementById("runBenchmarkGateButton").addEventListener("click", () =>
    wrapAction(doRunBenchmarkGate)
  );
  document.getElementById("validateWetlabProtocolButton").addEventListener("click", () =>
    wrapAction(doValidateWetlabProtocol)
  );
  document.getElementById("runWetlabProtocolButton").addEventListener("click", () =>
    wrapAction(doRunWetlabProtocol)
  );
  document.getElementById("buildRegulatoryBundleButton").addEventListener("click", () =>
    wrapAction(doBuildRegulatoryBundle)
  );
  document.getElementById("verifyRegulatoryBundleButton").addEventListener("click", () =>
    wrapAction(doVerifyRegulatoryBundle)
  );
  document.getElementById("generateHandoffButton").addEventListener("click", () =>
    wrapAction(doGenerateHandoff)
  );
  document.getElementById("refreshClinicalTrialsButton").addEventListener("click", () =>
    wrapAction(refreshClinicalTrials)
  );
  document.getElementById("loadClinicalTrialButton").addEventListener("click", () =>
    wrapAction(loadClinicalTrial)
  );
  document.getElementById("addClinicalTrialButton").addEventListener("click", () =>
    wrapAction(doAddClinicalTrial)
  );
  document.getElementById("updateClinicalTrialButton").addEventListener("click", () =>
    wrapAction(doUpdateClinicalTrial)
  );
  document.getElementById("removeClinicalTrialButton").addEventListener("click", () =>
    wrapAction(doRemoveClinicalTrial)
  );
  document.getElementById("enrollClinicalPatientButton").addEventListener("click", () =>
    wrapAction(doEnrollClinicalPatient)
  );
  document.getElementById("enrollClinicalSimulatedButton").addEventListener("click", () =>
    wrapAction(doEnrollClinicalSimulated)
  );
  document.getElementById("addClinicalResultButton").addEventListener("click", () =>
    wrapAction(doAddClinicalResult)
  );
  document.getElementById("upsertClinicalSiteButton").addEventListener("click", () =>
    wrapAction(doUpsertClinicalSite)
  );
  document.getElementById("screenClinicalPatientButton").addEventListener("click", () =>
    wrapAction(doScreenClinicalPatient)
  );
  document.getElementById("recordClinicalVisitButton").addEventListener("click", () =>
    wrapAction(doRecordClinicalVisit)
  );
  document.getElementById("addClinicalQueryButton").addEventListener("click", () =>
    wrapAction(doAddClinicalQuery)
  );
  document.getElementById("updateClinicalQueryButton").addEventListener("click", () =>
    wrapAction(doUpdateClinicalQuery)
  );
  document.getElementById("addClinicalDeviationButton").addEventListener("click", () =>
    wrapAction(doAddClinicalDeviation)
  );
  document.getElementById("addClinicalSafetyEventButton").addEventListener("click", () =>
    wrapAction(doAddClinicalSafetyEvent)
  );
  document.getElementById("upsertClinicalMilestoneButton").addEventListener("click", () =>
    wrapAction(doUpsertClinicalMilestone)
  );
  document.getElementById("refreshClinicalOpsButton").addEventListener("click", () =>
    wrapAction(doRefreshClinicalOps)
  );
  document.getElementById("simulateClinicalTrialButton").addEventListener("click", () =>
    wrapAction(doSimulateClinicalTrial)
  );
  clinicalTrialSelect.addEventListener("change", () => {
    state.selectedClinicalTrialId = clinicalTrialSelect.value || null;
    if (state.selectedClinicalTrialId) {
      clinicalTrialIdInput.value = state.selectedClinicalTrialId;
    }
  });

  document.getElementById("clearOutputButton").addEventListener("click", () => {
    resultOutput.textContent = "";
  });
}

async function wrapAction(fn) {
  try {
    await fn();
  } catch (err) {
    showOutput("Error", { message: err.message });
  }
}

function seedFallbackDefaults() {
  if (!objectiveInput.value.trim()) {
    objectiveInput.value =
      "Design an initial campaign against KRAS G12D with ranked candidates and clear validation milestones.";
  }

  if (!systemPromptInput.value.trim()) {
    systemPromptInput.value = "";
  }

  if (!planInput.value.trim()) {
    planInput.value = pretty({
      calls: [
        {
          tool: "refua_validate_spec",
          args: {
            action: "fold",
            name: "initial_kras_probe",
            entities: [
              {
                type: "protein",
                id: "A",
                sequence: "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQ",
              },
              {
                type: "ligand",
                id: "lig",
                smiles: "CCO",
              },
            ],
            affinity: {
              binder: "lig",
            },
          },
        },
      ],
    });
  }

  if (!portfolioInput.value.trim()) {
    portfolioInput.value = pretty([
      {
        name: "Pancreatic cancer",
        burden: 0.92,
        tractability: 0.45,
        unmet_need: 0.95,
        translational_readiness: 0.62,
        novelty: 0.7,
      },
      {
        name: "Tuberculosis",
        burden: 0.88,
        tractability: 0.68,
        unmet_need: 0.9,
        translational_readiness: 0.58,
        novelty: 0.66,
      },
    ]);
  }

  if (!clinicalTrialIdInput.value.trim()) {
    clinicalTrialIdInput.value = "studio-clinical-demo";
  }

  if (!clinicalTrialConfigInput.value.trim()) {
    clinicalTrialConfigInput.value = pretty({
      replicates: 8,
      enrollment: {
        total_n: 80,
      },
      adaptive: {
        burn_in_n: 20,
        interim_every: 20,
      },
    });
  }

  if (!clinicalPatientInput.value.trim()) {
    clinicalPatientInput.value = pretty({
      patient_id: "human-001",
      source: "human",
      arm_id: "control",
      site_id: "site-01",
      demographics: {
        age: 62,
        weight: 76,
      },
      baseline: {
        endpoint_value: 48.1,
      },
      metadata: {
        site_id: "site-01",
      },
    });
  }

  if (!clinicalResultInput.value.trim()) {
    clinicalResultInput.value = pretty({
      patient_id: "human-001",
      site_id: "site-01",
      result_type: "endpoint",
      visit: "week-12",
      source: "human",
      values: {
        arm_id: "control",
        change: 4.6,
        responder: false,
        safety_event: false,
      },
    });
  }

  if (!clinicalOpsInput.value.trim()) {
    clinicalOpsInput.value = pretty({
      site_id: "site-01",
      name: "Boston General",
      country_id: "US",
      status: "active",
      principal_investigator: "Dr. Rivera",
      target_enrollment: 24,
      patient_id: "human-001",
      description: "Missing week-4 lab panel",
      event_term: "grade_2_neutropenia",
      seriousness: "non_serious",
      expected: true,
      visit_type: "interim",
      findings: ["Source docs complete"],
      action_items: ["Continue weekly QC checks"],
      risk_score: 0.35,
      milestone_id: "ms-lpi",
      target_date: "2026-08-30T00:00:00+00:00",
    });
  }

  if (!programIdInput.value.trim()) {
    programIdInput.value = "kras-g12d-program";
  }
  if (!programNameInput.value.trim()) {
    programNameInput.value = "KRAS G12D Lead Program";
  }
  if (!programStageInput.value.trim()) {
    programStageInput.value = "lead_optimization";
  }
  if (!programIndicationInput.value.trim()) {
    programIndicationInput.value = "Pancreatic cancer";
  }
  if (!programOwnerInput.value.trim()) {
    programOwnerInput.value = "oncology-team";
  }
  if (!datasetIdInput.value.trim()) {
    datasetIdInput.value = "chembl_activity_ki_human";
  }
  if (!benchSuitePathInput.value.trim()) {
    benchSuitePathInput.value = "refua-bench/benchmarks/sample_suite.yaml";
  }
  if (!benchBaselinePathInput.value.trim()) {
    benchBaselinePathInput.value = "refua-bench/benchmarks/sample_baseline_run.json";
  }
  if (!benchPredictionsPathInput.value.trim()) {
    benchPredictionsPathInput.value = "refua-bench/benchmarks/sample_predictions_candidate.json";
  }
  if (!wetlabProtocolInput.value.trim()) {
    wetlabProtocolInput.value = pretty({
      name: "serial-dilution-screen",
      steps: [
        {
          type: "transfer",
          source: "plate:A1",
          destination: "plate:B1",
          volume_ul: 50,
        },
        {
          type: "mix",
          well: "plate:B1",
          volume_ul: 40,
          cycles: 5,
        },
        {
          type: "incubate",
          duration_s: 300,
          temperature_c: 37,
        },
        {
          type: "read_absorbance",
          plate: "plate",
          wavelength_nm: 450,
        },
      ],
    });
  }
  if (!regulatoryOutputDirInput.value.trim()) {
    regulatoryOutputDirInput.value = ".refua-studio/regulatory/bundle_studio";
  }
  if (!gateMetricsInput.value.trim()) {
    gateMetricsInput.value = pretty({});
  }
  if (!programEventTimeline.innerHTML.trim()) {
    programEventTimeline.innerHTML = '<div class="timeline-empty">Load a program to inspect timeline events.</div>';
  }
}

async function init() {
  seedFallbackDefaults();
  bootstrapWidgetSparks();
  updateTelemetryWidgets();
  bindActions();
  bindKeyboardShortcuts();

  await wrapAction(refreshExamples);
  await wrapAction(refreshEcosystem);
  await wrapAction(refreshHealth);
  await wrapAction(refreshTools);
  await wrapAction(refreshJobs);
  await wrapAction(refreshDrugPortfolio);
  await wrapAction(refreshClinicalTrials);
  await wrapAction(refreshCommandCenter);

  if (state.pollTimer) {
    clearInterval(state.pollTimer);
  }
  state.pollTimer = setInterval(() => {
    wrapAction(refreshHealth);
    wrapAction(refreshJobs);
    wrapAction(refreshDrugPortfolio);
    wrapAction(refreshClinicalTrials);
    wrapAction(refreshCommandCenter);
  }, 5000);
}

window.addEventListener("DOMContentLoaded", init);
