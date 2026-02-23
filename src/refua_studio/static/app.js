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

const state = {
  selectedJobId: null,
  selectedCandidateId: null,
  pollTimer: null,
  examples: {
    objectives: [],
    plan_templates: [],
    portfolio_templates: [],
  },
  ecosystem: null,
  handoff: null,
  drugCandidates: [],
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
  renderDrugSummary(payload.summary || {});
  renderDrugCards(state.drugCandidates);
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
  document.getElementById("generateHandoffButton").addEventListener("click", () =>
    wrapAction(doGenerateHandoff)
  );

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
}

async function init() {
  seedFallbackDefaults();
  bindActions();
  bindKeyboardShortcuts();

  await wrapAction(refreshExamples);
  await wrapAction(refreshEcosystem);
  await wrapAction(refreshHealth);
  await wrapAction(refreshTools);
  await wrapAction(refreshJobs);
  await wrapAction(refreshDrugPortfolio);

  if (state.pollTimer) {
    clearInterval(state.pollTimer);
  }
  state.pollTimer = setInterval(() => {
    wrapAction(refreshHealth);
    wrapAction(refreshJobs);
    wrapAction(refreshDrugPortfolio);
  }, 5000);
}

window.addEventListener("DOMContentLoaded", init);
