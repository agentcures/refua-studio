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

const productGrid = document.getElementById("productGrid");
const ecosystemWarnings = document.getElementById("ecosystemWarnings");
const defaultObjectiveText = document.getElementById("defaultObjectiveText");
const defaultPromptPreview = document.getElementById("defaultPromptPreview");

const state = {
  selectedJobId: null,
  jobs: [],
  examples: {
    objectives: [],
  },
  ecosystem: null,
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

function renderWarnings(warnings) {
  if (!Array.isArray(warnings) || warnings.length === 0) {
    ecosystemWarnings.hidden = true;
    ecosystemWarnings.textContent = "";
    return;
  }
  ecosystemWarnings.hidden = false;
  ecosystemWarnings.textContent = warnings.join("\n");
}

function statusBadge(status) {
  const normalized = String(status || "unknown");
  const badge = createElement("span", `status-pill is-${normalized}`, normalized);
  return badge;
}

function renderProductGrid(products) {
  clearNode(productGrid);

  if (!Array.isArray(products) || products.length === 0) {
    productGrid.appendChild(createElement("div", "empty-state", "No stack metadata available."));
    return;
  }

  for (const product of products) {
    const health = String(product.health || "unknown");
    const card = createElement("article", `product-card is-${health}`);

    const header = createElement("div", "product-card-header");
    const titleBlock = createElement("div");
    titleBlock.appendChild(createElement("p", "mini-label", "Service"));
    titleBlock.appendChild(
      createElement("h3", "product-name", product.name || product.id || "unknown")
    );
    header.appendChild(titleBlock);
    header.appendChild(statusBadge(health));

    card.appendChild(header);
    card.appendChild(createElement("p", "product-role", product.role || "No role provided."));
    card.appendChild(createElement("p", "product-meta", `ID: ${product.id || "n/a"}`));
    card.appendChild(createElement("p", "product-meta", `Repo: ${product.repo || "n/a"}`));
    productGrid.appendChild(card);
  }
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

  if (result.job_id) {
    state.selectedJobId = result.job_id;
  }

  showOutput(autonomous ? "Autonomous Run Submitted" : "Run Submitted", result);
  await refreshJobs();
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
  if (result.job_id) {
    state.selectedJobId = result.job_id;
  }
  advancedOptions.open = true;
  showOutput("Plan Execution", result);
  await refreshJobs();
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
  await refreshJobs();
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
  document.getElementById("refreshEcosystemButton").addEventListener("click", () =>
    wrapAction(async () => {
      await refreshEcosystem();
      await refreshHealth();
    })
  );
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
  jobStatusFilter.addEventListener("change", () => {
    wrapAction(refreshJobs);
  });
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
    planInput.value = "";
  }
}

async function init() {
  seedFallbackDefaults();
  bindActions();
  bindKeyboardShortcuts();

  await Promise.allSettled([
    refreshExamples(),
    refreshEcosystem(),
    refreshHealth(),
    refreshJobs(),
  ]);

  if (state.pollTimer) {
    clearInterval(state.pollTimer);
  }
  state.pollTimer = setInterval(() => {
    refreshHealth().catch(() => {});
    refreshJobs().catch(() => {});
  }, 5000);
}

window.addEventListener("DOMContentLoaded", init);
