const connectionChip = document.getElementById("connectionChip");
const resultOutput = document.getElementById("resultOutput");
const jobsBody = document.getElementById("jobsBody");
const jobsCountSummary = document.getElementById("jobsCountSummary");

const objectiveInput = document.getElementById("objectiveInput");
const systemPromptInput = document.getElementById("systemPromptInput");
const planInput = document.getElementById("planInput");
const objectiveTemplateSelect = document.getElementById("objectiveTemplateSelect");
const advancedOptions = document.getElementById("advancedOptions");

const dryRunToggle = document.getElementById("dryRunToggle");
const asyncToggle = document.getElementById("asyncToggle");
const maxRoundsInput = document.getElementById("maxRoundsInput");
const maxCallsInput = document.getElementById("maxCallsInput");
const skipValidateFirstToggle = document.getElementById("skipValidateFirstToggle");
const jobStatusFilter = document.getElementById("jobStatusFilter");

const viewTabs = Array.from(document.querySelectorAll("[data-view-target]"));
const viewPanels = Array.from(document.querySelectorAll("[data-view-panel]"));

const promisingDrugsSummary = document.getElementById("promisingDrugsSummary");
const drugSearchInput = document.getElementById("drugSearchInput");
const drugPromisingFilter = document.getElementById("drugPromisingFilter");
const drugTargetFilter = document.getElementById("drugTargetFilter");
const drugToolFilter = document.getElementById("drugToolFilter");
const drugCards = document.getElementById("drugCards");
const drugDetail = document.getElementById("drugDetail");

const DEFAULT_CAMPAIGN_OBJECTIVE =
  "Find cures for all diseases by prioritizing the highest-burden conditions and researching the best drug design strategies for each.";

const DRUG_METRIC_LABELS = {
  binding_probability: "Binding Probability",
  admet_score: "ADMET Score",
  safety_score: "Safety Score",
  adme_score: "ADME Score",
  rdkit_score: "RDKit Score",
  affinity: "Affinity",
  ic50: "IC50",
  kd: "Kd",
};

const state = {
  activeView: "campaign",
  selectedJobId: null,
  selectedDrugId: null,
  jobs: [],
  examples: {
    objectives: [],
  },
  ecosystem: null,
  promisingDrugs: [],
  promisingSummary: {},
  promisingFacets: {
    targets: [],
    tools: [],
  },
  pollTimer: null,
};

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function clearNode(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

function createElement(tagName, className, text) {
  const node = document.createElement(tagName);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

function pluralize(count, singular, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

function truncate(text, limit = 180) {
  const value = String(text || "").trim();
  if (!value || value.length <= limit) {
    return value;
  }
  return `${value.slice(0, Math.max(limit - 1, 1)).trimEnd()}…`;
}

function setConnection(ok, text) {
  connectionChip.classList.toggle("online", ok);
  connectionChip.classList.toggle("offline", !ok);
  const label = connectionChip.querySelector(".status-text");
  label.textContent = text;
}

function showOutput(title, payload) {
  const body = typeof payload === "string" ? payload : pretty(payload);
  const stamp = new Date().toLocaleTimeString();
  resultOutput.textContent = `[${stamp}] ${title}\n\n${body}`;
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

function requireObjective() {
  const value = objectiveInput.value.trim();
  if (!value) {
    throw new Error("Objective is required");
  }
  return value;
}

function positiveInt(value, fallback) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return fallback;
  }
  return Math.round(parsed);
}

function setSelectOptions(select, options, labelGetter) {
  clearNode(select);
  if (!Array.isArray(options) || options.length === 0) {
    select.appendChild(new Option("No templates available", ""));
    return;
  }
  for (const item of options) {
    select.appendChild(new Option(labelGetter(item), item.id));
  }
}

function setFacetOptions(select, values, allLabel) {
  const previousValue = select.value;
  clearNode(select);
  select.appendChild(new Option(allLabel, ""));
  for (const item of values) {
    select.appendChild(new Option(item, item));
  }
  if (values.includes(previousValue)) {
    select.value = previousValue;
    return;
  }
  select.value = "";
}

function selectedTemplate(select, list) {
  return list.find((item) => item.id === select.value) || null;
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function formatDuration(value) {
  const total = Number(value);
  if (!Number.isFinite(total) || total <= 0) {
    return "-";
  }
  if (total < 1000) {
    return `${total} ms`;
  }
  const seconds = Math.round(total / 1000);
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return `${minutes}m ${remaining}s`;
}

function formatJobProgress(job) {
  if (!job || typeof job !== "object") {
    return "-";
  }
  if (Number.isFinite(Number(job.progress_percent))) {
    return `${Math.round(Number(job.progress_percent))}%`;
  }
  const completed = Number(job.completed_calls || 0);
  const total = Number(job.total_calls || 0);
  if (total > 0) {
    return `${completed}/${total}`;
  }
  if (job.status === "completed") {
    return "done";
  }
  return "-";
}

function formatScore(value) {
  const score = Number(value);
  if (!Number.isFinite(score)) {
    return "-";
  }
  return score.toFixed(score >= 100 ? 0 : 1);
}

function formatMetricValue(key, value) {
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    const text = String(value || "").trim();
    return text || "-";
  }

  if (key === "binding_probability" || key.endsWith("_score")) {
    const normalized = numeric >= 0 && numeric <= 1 ? numeric * 100 : numeric;
    return `${Math.round(normalized)}%`;
  }
  if (key === "ic50" || key === "kd") {
    return `${numeric.toFixed(2)} nM`;
  }
  if (key === "affinity") {
    return numeric.toFixed(2);
  }
  return numeric.toFixed(2);
}

function metricLabel(key) {
  return DRUG_METRIC_LABELS[key] || key.replaceAll("_", " ");
}

function drugStatus(drug) {
  return drug?.promising ? "promising" : "watchlist";
}

function statusBadge(status) {
  const normalized = String(status || "unknown");
  return createElement("span", `status-pill is-${normalized}`, normalized);
}

function metricChip(text, className = "") {
  return createElement("span", `metric-chip ${className}`.trim(), text);
}

function renderEcosystem(payload) {
  state.ecosystem = payload;

  const clawcures = payload.clawcures || {};
  if (!objectiveInput.value.trim() && clawcures.default_objective) {
    objectiveInput.value = clawcures.default_objective;
  }
}

async function refreshExamples() {
  const payload = await api("/api/examples", { method: "GET" });
  state.examples.objectives = payload.objectives || [];
  setSelectOptions(objectiveTemplateSelect, state.examples.objectives, (item) => item.label);
}

async function refreshEcosystem() {
  const payload = await api("/api/ecosystem", { method: "GET" });
  renderEcosystem(payload);
}

async function refreshHealth() {
  try {
    const payload = await api("/api/health", { method: "GET" });
    const running = Number(payload.job_counts?.running || 0);
    const queued = Number(payload.job_counts?.queued || 0);
    const tools = Number(payload.tools_count || 0);
    setConnection(true, `Online · ${running} running · ${queued} queued · ${tools} tools`);
    return payload;
  } catch (err) {
    setConnection(false, `Offline · ${err.message}`);
    throw err;
  }
}

function renderJobCounts(counts) {
  const keys = ["queued", "running", "completed", "failed", "cancelled"];
  const parts = keys.map((key) => `${key}: ${counts?.[key] || 0}`);
  jobsCountSummary.textContent = parts.join(" | ");
}

async function loadJob(jobId) {
  const payload = await api(`/api/jobs/${jobId}`, { method: "GET" });
  showOutput("Job Detail", payload);
}

function renderJobsTable(jobs) {
  clearNode(jobsBody);

  if (!Array.isArray(jobs) || jobs.length === 0) {
    const row = createElement("tr");
    const cell = createElement("td", null, "No jobs found for the current filter.");
    cell.colSpan = 6;
    row.appendChild(cell);
    jobsBody.appendChild(row);
    return;
  }

  for (const job of jobs) {
    const row = createElement("tr");
    if (job.job_id === state.selectedJobId) {
      row.classList.add("is-selected");
    }

    const jobIdCell = createElement(
      "td",
      "cell-mono",
      job.job_id ? `${job.job_id.slice(0, 8)}...` : "-"
    );
    jobIdCell.title = job.job_id || "";
    row.appendChild(jobIdCell);
    row.appendChild(createElement("td", null, job.kind || "-"));

    const statusCell = createElement("td");
    statusCell.appendChild(statusBadge(job.status || "unknown"));
    row.appendChild(statusCell);

    row.appendChild(createElement("td", null, formatJobProgress(job)));
    row.appendChild(createElement("td", null, formatDate(job.updated_at)));
    row.appendChild(createElement("td", null, formatDuration(job.duration_ms)));

    row.addEventListener("click", async () => {
      state.selectedJobId = job.job_id;
      renderJobsTable(state.jobs);
      await wrapAction(() => loadJob(job.job_id));
    });

    jobsBody.appendChild(row);
  }
}

async function refreshJobs() {
  const status = jobStatusFilter.value;
  const query = status ? `?limit=80&status=${encodeURIComponent(status)}` : "?limit=80";
  const payload = await api(`/api/jobs${query}`, { method: "GET" });
  const jobs = Array.isArray(payload.jobs) ? payload.jobs : [];

  state.jobs = jobs;
  if (state.selectedJobId && !jobs.some((job) => job.job_id === state.selectedJobId)) {
    state.selectedJobId = null;
  }

  renderJobCounts(payload.counts || {});
  renderJobsTable(jobs);
}

function currentRunPayload() {
  return {
    objective: requireObjective(),
    system_prompt: systemPromptInput.value.trim() || null,
    dry_run: dryRunToggle.checked,
    async_mode: asyncToggle.checked,
    autonomous: false,
    max_rounds: positiveInt(maxRoundsInput.value, 3),
    max_calls: positiveInt(maxCallsInput.value, 10),
    allow_skip_validate_first: skipValidateFirstToggle.checked,
    plan: parseJsonText(planInput.value, "Plan"),
  };
}

function loadObjectiveTemplate() {
  const template = selectedTemplate(objectiveTemplateSelect, state.examples.objectives);
  if (!template) {
    throw new Error("No objective template selected");
  }
  objectiveInput.value = template.objective || "";
  showOutput("Objective Template Loaded", template);
}

function loadClawCuresObjective() {
  const objective = state.ecosystem?.clawcures?.default_objective;
  if (!objective) {
    throw new Error("Default ClawCures objective is not available");
  }
  objectiveInput.value = objective;
  showOutput("Default Objective Loaded", { objective });
}

async function doPlan() {
  const payload = {
    objective: requireObjective(),
    system_prompt: systemPromptInput.value.trim() || null,
  };
  const result = await api("/api/plan", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (result.plan) {
    planInput.value = pretty(result.plan);
    advancedOptions.open = true;
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

  const jobId = result.job?.job_id || result.job_id || null;
  if (jobId) {
    state.selectedJobId = jobId;
  }

  showOutput(autonomous ? "Autonomous Run Submitted" : "Run Submitted", result);
  await Promise.all([refreshJobs(), refreshPromisingDrugs()]);
}

async function doValidatePlan() {
  const plan = parseJsonText(planInput.value, "Plan");
  if (!plan) {
    throw new Error("Plan must not be empty");
  }
  const result = await api("/api/plan/validate", {
    method: "POST",
    body: JSON.stringify({
      plan,
      max_calls: positiveInt(maxCallsInput.value, 10),
      allow_skip_validate_first: skipValidateFirstToggle.checked,
    }),
  });
  advancedOptions.open = true;
  showOutput("Plan Validation", result);
}

async function doExecutePlan() {
  const plan = parseJsonText(planInput.value, "Plan");
  if (!plan) {
    throw new Error("Plan must not be empty");
  }
  const result = await api("/api/plan/execute", {
    method: "POST",
    body: JSON.stringify({
      plan,
      async_mode: asyncToggle.checked,
    }),
  });
  const jobId = result.job?.job_id || result.job_id || null;
  if (jobId) {
    state.selectedJobId = jobId;
  }
  advancedOptions.open = true;
  showOutput("Plan Execution", result);
  await Promise.all([refreshJobs(), refreshPromisingDrugs()]);
}

async function doCancelSelectedJob() {
  if (!state.selectedJobId) {
    throw new Error("Select a job before cancelling");
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
  await Promise.all([refreshJobs(), refreshPromisingDrugs()]);
}

function setActiveView(viewName) {
  state.activeView = viewName;

  for (const button of viewTabs) {
    const isActive = button.dataset.viewTarget === viewName;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  }

  for (const panel of viewPanels) {
    const isActive = panel.dataset.viewPanel === viewName;
    panel.classList.toggle("is-active", isActive);
    panel.hidden = !isActive;
  }
}

function drugSearchIndex(drug) {
  const sourceText = Array.isArray(drug.sources)
    ? drug.sources
        .map((item) => `${item.objective || ""} ${item.job_kind || ""} ${item.tool || ""}`)
        .join(" ")
    : "";

  return [
    drug.drug_id,
    drug.name,
    drug.target,
    drug.smiles,
    drug.tool,
    Array.isArray(drug.tools) ? drug.tools.join(" ") : "",
    drug.assessment,
    sourceText,
  ]
    .join(" ")
    .toLowerCase();
}

function filteredPromisingDrugs() {
  const query = drugSearchInput.value.trim().toLowerCase();
  const status = drugPromisingFilter.value;
  const target = drugTargetFilter.value;
  const tool = drugToolFilter.value;

  return state.promisingDrugs.filter((drug) => {
    if (status === "promising" && !drug.promising) {
      return false;
    }
    if (status === "watchlist" && drug.promising) {
      return false;
    }
    if (target && drug.target !== target) {
      return false;
    }
    if (tool) {
      const tools = Array.isArray(drug.tools) ? drug.tools : [];
      if (!tools.includes(tool) && drug.tool !== tool) {
        return false;
      }
    }
    if (query && !drugSearchIndex(drug).includes(query)) {
      return false;
    }
    return true;
  });
}

function renderPromisingDrugsSummary(visibleCount) {
  const summary = state.promisingSummary || {};
  const parts = [
    `${visibleCount} shown`,
    `${summary.total_drugs || 0} tracked`,
    `${summary.promising_count || 0} promising`,
    `${summary.watchlist_count || 0} watchlist`,
    `${summary.source_jobs_count || 0} source jobs`,
  ];
  promisingDrugsSummary.textContent = parts.join(" | ");
}

function appendDetailRow(container, label, value, { mono = false } = {}) {
  if (value === null || value === undefined || value === "") {
    return;
  }
  const row = createElement("div", "detail-item");
  row.appendChild(createElement("span", "mini-label", label));
  row.appendChild(
    createElement("span", mono ? "detail-value detail-mono" : "detail-value", value)
  );
  container.appendChild(row);
}

function renderMetricSection(title, metrics, { limit = null } = {}) {
  const entries = Object.entries(metrics || {}).filter(([, value]) => {
    return value !== null && value !== undefined && String(value).trim() !== "";
  });
  if (entries.length === 0) {
    return null;
  }

  const section = createElement("section", "detail-section");
  section.appendChild(createElement("h3", null, title));

  const grid = createElement("div", "metric-grid");
  const visibleEntries = limit ? entries.slice(0, limit) : entries;
  for (const [key, value] of visibleEntries) {
    const card = createElement("div", "metric-card");
    card.appendChild(createElement("span", "mini-label", metricLabel(key)));
    card.appendChild(createElement("strong", "metric-value", formatMetricValue(key, value)));
    grid.appendChild(card);
  }
  section.appendChild(grid);
  return section;
}

function renderSourceList(sources) {
  if (!Array.isArray(sources) || sources.length === 0) {
    return null;
  }

  const section = createElement("section", "detail-section");
  section.appendChild(createElement("h3", null, "Recent Observations"));

  const list = createElement("div", "source-list");
  for (const source of sources.slice(0, 5)) {
    const item = createElement("article", "source-item");
    const header = createElement("div", "source-item-head");
    const headerCopy = createElement("div");
    headerCopy.appendChild(createElement("p", "mini-label", source.job_kind || "job"));
    headerCopy.appendChild(
      createElement("p", "source-meta", `Observed ${formatDate(source.discovered_at)}`)
    );
    header.appendChild(headerCopy);
    header.appendChild(statusBadge(source.promising ? "promising" : "watchlist"));
    item.appendChild(header);

    const metaParts = [];
    if (source.tool) {
      metaParts.push(source.tool);
    }
    if (Number.isFinite(Number(source.score))) {
      metaParts.push(`score ${formatScore(source.score)}`);
    }
    if (source.job_id) {
      metaParts.push(source.job_id.slice(0, 8));
    }
    if (metaParts.length > 0) {
      item.appendChild(createElement("p", "source-meta", metaParts.join(" · ")));
    }
    if (source.objective) {
      item.appendChild(createElement("p", "source-copy", truncate(source.objective, 140)));
    }
    list.appendChild(item);
  }

  section.appendChild(list);
  return section;
}

function renderDrugDetail(drug) {
  clearNode(drugDetail);

  if (!drug) {
    drugDetail.appendChild(
      createElement(
        "div",
        "empty-state",
        "Select a therapeutic to inspect its evidence, source jobs, and key metrics."
      )
    );
    return;
  }

  const hero = createElement("section", "detail-hero");
  const heroCopy = createElement("div");
  heroCopy.appendChild(createElement("p", "eyebrow", drug.target || "Therapeutic candidate"));
  heroCopy.appendChild(createElement("h2", null, drug.name || drug.drug_id));

  const subtitleParts = [];
  if (drug.tool) {
    subtitleParts.push(`Primary tool: ${drug.tool}`);
  }
  subtitleParts.push(`Best score: ${formatScore(drug.score)}`);
  subtitleParts.push(`Latest seen: ${formatDate(drug.latest_seen_at)}`);
  heroCopy.appendChild(createElement("p", "panel-copy", subtitleParts.join(" · ")));

  hero.appendChild(heroCopy);
  hero.appendChild(statusBadge(drugStatus(drug)));
  drugDetail.appendChild(hero);

  const chipRow = createElement("div", "chip-row");
  chipRow.appendChild(metricChip(pluralize(drug.seen_count || 0, "observation")));
  chipRow.appendChild(metricChip(pluralize(drug.source_jobs_count || 0, "job"), "is-accent"));
  chipRow.appendChild(
    metricChip(
      `${drug.promising_runs || 0} promising run${Number(drug.promising_runs || 0) === 1 ? "" : "s"}`,
      drug.promising ? "is-success" : ""
    )
  );
  if (Array.isArray(drug.tools)) {
    for (const tool of drug.tools.slice(0, 3)) {
      chipRow.appendChild(metricChip(tool));
    }
  }
  drugDetail.appendChild(chipRow);

  if (drug.assessment) {
    drugDetail.appendChild(createElement("p", "detail-copy", drug.assessment));
  }

  const metaGrid = createElement("div", "detail-grid");
  appendDetailRow(metaGrid, "Drug ID", drug.drug_id, { mono: true });
  appendDetailRow(metaGrid, "Target", drug.target);
  appendDetailRow(metaGrid, "SMILES", drug.smiles, { mono: true });
  appendDetailRow(metaGrid, "First Seen", formatDate(drug.first_seen_at));
  appendDetailRow(metaGrid, "Latest Seen", formatDate(drug.latest_seen_at));
  appendDetailRow(metaGrid, "Primary Tool", drug.tool);
  drugDetail.appendChild(metaGrid);

  const metricSection = renderMetricSection("Key Metrics", drug.metrics);
  if (metricSection) {
    drugDetail.appendChild(metricSection);
  }

  const admetPayload = typeof drug.admet === "object" && drug.admet ? drug.admet : {};
  const admetKeyMetrics =
    typeof admetPayload.key_metrics === "object" && admetPayload.key_metrics
      ? admetPayload.key_metrics
      : {};
  const admetProperties =
    typeof admetPayload.properties === "object" && admetPayload.properties
      ? admetPayload.properties
      : {};

  if (admetPayload.status) {
    const admetStatus = createElement("div", "chip-row");
    admetStatus.appendChild(metricChip(`ADMET ${admetPayload.status}`, "is-accent"));
    drugDetail.appendChild(admetStatus);
  }

  const admetMetricsSection = renderMetricSection("ADMET Highlights", admetKeyMetrics);
  if (admetMetricsSection) {
    drugDetail.appendChild(admetMetricsSection);
  }

  const admetPropertiesSection = renderMetricSection("ADMET Properties", admetProperties, {
    limit: 6,
  });
  if (admetPropertiesSection) {
    drugDetail.appendChild(admetPropertiesSection);
  }

  const sourceSection = renderSourceList(drug.sources);
  if (sourceSection) {
    drugDetail.appendChild(sourceSection);
  }
}

function renderDrugCards(drugs) {
  clearNode(drugCards);

  if (!Array.isArray(drugs) || drugs.length === 0) {
    drugCards.appendChild(
      createElement(
        "div",
        "empty-state",
        "No therapeutics match the current filters."
      )
    );
    return;
  }

  for (const drug of drugs) {
    const button = createElement("button", "drug-card");
    button.type = "button";
    button.setAttribute("aria-pressed", String(drug.drug_id === state.selectedDrugId));
    if (drug.drug_id === state.selectedDrugId) {
      button.classList.add("is-selected");
    }

    const header = createElement("div", "drug-card-top");
    const headerCopy = createElement("div");
    headerCopy.appendChild(
      createElement("p", "mini-label", drug.target || drug.tool || "Therapeutic candidate")
    );
    headerCopy.appendChild(createElement("h3", "drug-card-title", drug.name || drug.drug_id));
    header.appendChild(headerCopy);
    header.appendChild(statusBadge(drugStatus(drug)));
    button.appendChild(header);

    button.appendChild(createElement("p", "drug-card-score", `Score ${formatScore(drug.score)}`));

    const metaParts = [];
    if (drug.tool) {
      metaParts.push(drug.tool);
    }
    metaParts.push(pluralize(drug.seen_count || 0, "observation"));
    if (drug.latest_seen_at) {
      metaParts.push(formatDate(drug.latest_seen_at));
    }
    button.appendChild(createElement("p", "drug-card-meta", metaParts.join(" · ")));

    const assessment = drug.assessment || "No qualitative assessment captured yet.";
    button.appendChild(createElement("p", "drug-card-assessment", truncate(assessment, 160)));

    const chips = createElement("div", "chip-row");
    chips.appendChild(metricChip(`${drug.source_jobs_count || 0} jobs`));
    if (drug.metrics?.binding_probability !== null && drug.metrics?.binding_probability !== undefined) {
      chips.appendChild(
        metricChip(
          `bind ${formatMetricValue("binding_probability", drug.metrics.binding_probability)}`,
          "is-accent"
        )
      );
    }
    if (drug.metrics?.admet_score !== null && drug.metrics?.admet_score !== undefined) {
      chips.appendChild(
        metricChip(
          `admet ${formatMetricValue("admet_score", drug.metrics.admet_score)}`,
          drug.promising ? "is-success" : ""
        )
      );
    }
    button.appendChild(chips);

    button.addEventListener("click", () => {
      state.selectedDrugId = drug.drug_id;
      renderPromisingDrugs();
    });

    drugCards.appendChild(button);
  }
}

function renderPromisingDrugs() {
  const drugs = filteredPromisingDrugs();
  if (!drugs.some((drug) => drug.drug_id === state.selectedDrugId)) {
    state.selectedDrugId = drugs[0]?.drug_id || null;
  }

  renderPromisingDrugsSummary(drugs.length);
  renderDrugCards(drugs);
  renderDrugDetail(drugs.find((drug) => drug.drug_id === state.selectedDrugId) || null);
}

async function refreshPromisingDrugs() {
  const payload = await api("/api/promising-drugs?limit=300", { method: "GET" });
  state.promisingDrugs = Array.isArray(payload.drugs) ? payload.drugs : [];
  state.promisingSummary =
    payload.summary || {
      total_drugs: 0,
      promising_count: 0,
      watchlist_count: 0,
      source_jobs_count: 0,
    };
  state.promisingFacets = payload.facets || { targets: [], tools: [] };

  setFacetOptions(drugTargetFilter, state.promisingFacets.targets || [], "All targets");
  setFacetOptions(drugToolFilter, state.promisingFacets.tools || [], "All tools");
  renderPromisingDrugs();
}

function resetDrugFilters() {
  drugSearchInput.value = "";
  drugPromisingFilter.value = "";
  drugTargetFilter.value = "";
  drugToolFilter.value = "";
  renderPromisingDrugs();
}

async function wrapAction(fn) {
  try {
    await fn();
  } catch (err) {
    showOutput("Error", { message: err.message });
  }
}

function bindKeyboardShortcuts() {
  document.addEventListener("keydown", (event) => {
    if (!event.metaKey && !event.ctrlKey) {
      return;
    }
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    if (event.shiftKey) {
      wrapAction(() => doRun({ autonomous: true }));
      return;
    }
    wrapAction(() => doRun({ autonomous: false }));
  });
}

function bindActions() {
  document.getElementById("loadObjectiveTemplateButton").addEventListener("click", () =>
    wrapAction(loadObjectiveTemplate)
  );
  document.getElementById("loadClawCuresObjectiveButton").addEventListener("click", () =>
    wrapAction(loadClawCuresObjective)
  );
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
  document.getElementById("refreshJobsButton").addEventListener("click", () =>
    wrapAction(refreshJobs)
  );
  document.getElementById("cancelJobButton").addEventListener("click", () =>
    wrapAction(doCancelSelectedJob)
  );
  document.getElementById("clearFinishedJobsButton").addEventListener("click", () =>
    wrapAction(doClearFinishedJobs)
  );
  document.getElementById("clearOutputButton").addEventListener("click", () => {
    resultOutput.textContent = "No actions yet.";
  });
  document.getElementById("refreshPromisingDrugsButton").addEventListener("click", () =>
    wrapAction(refreshPromisingDrugs)
  );
  document.getElementById("clearDrugFiltersButton").addEventListener("click", () => {
    resetDrugFilters();
  });

  for (const button of viewTabs) {
    button.addEventListener("click", () => {
      setActiveView(button.dataset.viewTarget || "campaign");
    });
  }

  jobStatusFilter.addEventListener("change", () => {
    wrapAction(refreshJobs);
  });

  drugSearchInput.addEventListener("input", renderPromisingDrugs);
  drugPromisingFilter.addEventListener("change", renderPromisingDrugs);
  drugTargetFilter.addEventListener("change", renderPromisingDrugs);
  drugToolFilter.addEventListener("change", renderPromisingDrugs);
}

function seedFallbackDefaults() {
  if (!objectiveInput.value.trim()) {
    objectiveInput.value = DEFAULT_CAMPAIGN_OBJECTIVE;
  }
  if (!systemPromptInput.value.trim()) {
    systemPromptInput.value = "";
  }
  if (!planInput.value.trim()) {
    planInput.value = "";
  }
}

async function init() {
  seedFallbackDefaults();
  bindActions();
  bindKeyboardShortcuts();
  setActiveView("campaign");

  await Promise.allSettled([
    refreshExamples(),
    refreshEcosystem(),
    refreshHealth(),
    refreshJobs(),
    refreshPromisingDrugs(),
  ]);

  if (state.pollTimer) {
    clearInterval(state.pollTimer);
  }
  state.pollTimer = setInterval(() => {
    refreshHealth().catch(() => {});
    refreshJobs().catch(() => {});
    refreshPromisingDrugs().catch(() => {});
  }, 5000);
}

window.addEventListener("DOMContentLoaded", init);
