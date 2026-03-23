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
const openTopDrugReportButton = document.getElementById("openTopDrugReportButton");
const drugReportPage = document.getElementById("drugReportPage");
const drugReportEmpty = document.getElementById("drugReportEmpty");

const DEFAULT_CAMPAIGN_OBJECTIVE =
  "Find cures for all diseases by prioritizing the highest-burden conditions and researching the best drug design strategies for each.";

const VIEW_TAB_TARGETS = {
  campaign: "campaign",
  "promising-drugs": "promising-drugs",
  "drug-report": "promising-drugs",
};

const MOLSTAR_JS_CDN =
  "https://cdn.jsdelivr.net/npm/molstar@4.18.0/build/viewer/molstar.min.js";
const MOLSTAR_CSS_CDN =
  "https://cdn.jsdelivr.net/npm/molstar@4.18.0/build/viewer/molstar.min.css";

let molstarScriptPromise = null;

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

function createSvgElement(tagName, attributes = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tagName);
  for (const [key, value] of Object.entries(attributes)) {
    if (value === null || value === undefined) {
      continue;
    }
    node.setAttribute(key, String(value));
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

function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), maximum);
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function asObject(value) {
  return typeof value === "object" && value ? value : {};
}

function asText(value) {
  const normalized = typeof value === "string" ? value.trim() : "";
  return normalized || null;
}

function collectChainIds(value) {
  const tokens = [];

  function collect(item) {
    if (item === null || item === undefined) {
      return;
    }
    if (Array.isArray(item)) {
      for (const nested of item) {
        collect(nested);
      }
      return;
    }
    if (typeof item === "string") {
      for (const piece of item.split(/[\s,;]+/)) {
        if (piece) {
          tokens.push(piece);
        }
      }
      return;
    }
    tokens.push(String(item));
  }

  collect(value);
  return Array.from(new Set(tokens.map((token) => token.trim()).filter(Boolean)));
}

function inferMolstarFormat(pathValue, formatValue) {
  const explicit = String(formatValue || "").trim().toLowerCase();
  if (explicit === "bcif") {
    return "bcif";
  }
  if (explicit === "pdb") {
    return "pdb";
  }
  if (explicit === "cif" || explicit === "mmcif") {
    return "mmcif";
  }

  const pathText = String(pathValue || "").trim().toLowerCase();
  if (pathText.endsWith(".bcif")) {
    return "bcif";
  }
  if (pathText.endsWith(".pdb")) {
    return "pdb";
  }
  if (pathText.endsWith(".cif") || pathText.endsWith(".mmcif")) {
    return "mmcif";
  }
  return null;
}

function buildStructureUrl(pathValue) {
  const pathText = asText(pathValue);
  if (!pathText) {
    return null;
  }
  return `/structures/file?path=${encodeURIComponent(pathText)}`;
}

function ensureMolstarCss() {
  if (document.querySelector('link[data-refua-molstar-css="1"]')) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = MOLSTAR_CSS_CDN;
  link.setAttribute("data-refua-molstar-css", "1");
  document.head.appendChild(link);
}

function ensureMolstarAssets() {
  ensureMolstarCss();
  if (typeof window.molstar !== "undefined") {
    return Promise.resolve(window.molstar);
  }
  if (molstarScriptPromise) {
    return molstarScriptPromise;
  }

  molstarScriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = MOLSTAR_JS_CDN;
    script.async = true;
    script.setAttribute("data-refua-molstar-js", "1");
    script.onload = () => resolve(window.molstar);
    script.onerror = () => reject(new Error("Failed to load Mol* viewer assets"));
    document.head.appendChild(script);
  });
  return molstarScriptPromise;
}

function normalizeChainGroups(rawGroups) {
  if (!Array.isArray(rawGroups)) {
    return [];
  }

  const seen = new Set();
  const groups = [];
  for (const rawGroup of rawGroups) {
    if (!Array.isArray(rawGroup)) {
      continue;
    }
    const group = [];
    for (const token of rawGroup) {
      const normalized = String(token || "").trim();
      if (!normalized || seen.has(normalized)) {
        continue;
      }
      seen.add(normalized);
      group.push(normalized);
    }
    if (group.length > 0) {
      groups.push(group);
    }
  }
  return groups;
}

function buildMolstarColorPlan(report) {
  return {
    protein_chain_groups: report.proteins.map((item) => item.chainIds || []),
    ligand_chain_groups: report.ligands.map((item) => item.chainIds || []),
    other_chain_groups: report.otherEntities.map((item) => item.chainIds || []),
    nucleic_chain_groups: [],
    ion_chain_groups: [],
  };
}

function makeChainSelector(chainIds) {
  if (!Array.isArray(chainIds) || chainIds.length === 0) {
    return null;
  }
  const selectors = [];
  const seen = new Set();
  for (const chainId of chainIds) {
    const normalized = String(chainId || "").trim();
    if (!normalized) {
      continue;
    }
    const labelKey = `label:${normalized}`;
    if (!seen.has(labelKey)) {
      seen.add(labelKey);
      selectors.push({ label_asym_id: normalized });
    }
    const authKey = `auth:${normalized}`;
    if (!seen.has(authKey)) {
      seen.add(authKey);
      selectors.push({ auth_asym_id: normalized });
    }
  }
  if (selectors.length === 0) {
    return null;
  }
  return selectors.length === 1 ? selectors[0] : selectors;
}

function addChainRepresentation(structure, chainIds, type, color, opacity) {
  const selector = makeChainSelector(chainIds);
  if (!selector) {
    return null;
  }
  const component = structure.component({ selector });
  const colorProps = { color };
  if (typeof opacity === "number") {
    colorProps.opacity = opacity;
  }
  component.representation({ type }).color(colorProps);
  return component;
}

function applyMolstarColorPlan(structure, colorPlan, ligandName) {
  const proteinPalette = ["#2563eb", "#0891b2", "#7c3aed", "#0f766e"];
  const ligandPalette = ["#db2777", "#c026d3", "#e11d48", "#ec4899"];

  const proteinGroups = normalizeChainGroups(colorPlan?.protein_chain_groups);
  const ligandGroups = normalizeChainGroups(colorPlan?.ligand_chain_groups);
  const otherGroups = normalizeChainGroups(colorPlan?.other_chain_groups);

  if (proteinGroups.length > 0) {
    for (const [index, group] of proteinGroups.entries()) {
      addChainRepresentation(
        structure,
        group,
        "cartoon",
        proteinPalette[index % proteinPalette.length],
        1
      );
    }
  } else {
    structure
      .component({ selector: "protein" })
      .representation({ type: "cartoon" })
      .color({ color: "#2563eb" });
  }

  if (ligandGroups.length > 0) {
    for (const [index, group] of ligandGroups.entries()) {
      const ligandComponent = addChainRepresentation(
        structure,
        group,
        "ball_and_stick",
        ligandPalette[index % ligandPalette.length],
        1
      );
      if (ligandName && index === 0 && ligandComponent) {
        ligandComponent.label({ text: ligandName });
      }
    }
  } else {
    const ligandComponent = structure.component({ selector: "ligand" });
    if (ligandName) {
      ligandComponent.label({ text: ligandName });
    }
    ligandComponent
      .representation({ type: "ball_and_stick" })
      .color({ color: "#db2777" });
  }

  for (const group of otherGroups) {
    addChainRepresentation(structure, group, "ball_and_stick", "#64748b", 1);
  }
}

async function initMolstarStage(stageNode) {
  if (!stageNode || stageNode.dataset.refuaInitialized === "1") {
    return;
  }
  stageNode.dataset.refuaInitialized = "1";

  const viewerNode = stageNode.querySelector("[data-refua-molstar-viewer='1']");
  const loadingNode = stageNode.querySelector("[data-refua-molstar-loading='1']");
  const structureUrl = stageNode.dataset.url || "";
  const formatType = stageNode.dataset.format || "mmcif";
  const ligandName = stageNode.dataset.ligand || null;
  const colorPlan = JSON.parse(stageNode.dataset.colorPlan || "{}");

  try {
    const molstar = await ensureMolstarAssets();
    if (!document.body.contains(stageNode) || !viewerNode) {
      return;
    }

    function loadWithMvs(viewer) {
      try {
        const mvs = molstar?.PluginExtensions?.mvs;
        if (!mvs?.MVSData || typeof mvs.loadMVS !== "function") {
          return Promise.resolve(false);
        }

        const builder = mvs.MVSData.createBuilder();
        const structure = builder
          .download({ url: structureUrl })
          .parse({ format: formatType })
          .modelStructure({});
        applyMolstarColorPlan(structure, colorPlan, ligandName);

        return mvs
          .loadMVS(viewer.plugin, builder.getState(), {
            sourceUrl: null,
            sanityChecks: true,
            replaceExisting: false,
          })
          .then(() => {
            stageNode.dataset.refuaLoadedPath = "mvs";
            stageNode.dataset.refuaLoadedFormat = formatType;
            return true;
          })
          .catch(() => false);
      } catch (_err) {
        return Promise.resolve(false);
      }
    }

    function loadDirectly(viewer) {
      const isBinary = formatType === "bcif";
      return viewer
        .loadStructureFromUrl(structureUrl, formatType, isBinary, {
          representationParams: {
            theme: { globalName: "entity-id" },
          },
        })
        .then(() => {
          stageNode.dataset.refuaLoadedPath = "direct";
          stageNode.dataset.refuaLoadedFormat = formatType;
        });
    }

    const viewer = await molstar.Viewer.create(viewerNode.id, {
      layoutIsExpanded: false,
      layoutShowControls: false,
      layoutShowRemoteState: false,
      layoutShowSequence: true,
      layoutShowLog: false,
      layoutShowLeftPanel: false,
      viewportShowExpand: false,
      viewportShowSelectionMode: false,
      viewportShowAnimation: false,
      viewportShowTrajectoryControls: false,
      disabledExtensions: ["volumes-and-segmentations"],
    });

    const loadedWithMvs = await loadWithMvs(viewer);
    if (!loadedWithMvs) {
      await loadDirectly(viewer);
    }
    if (loadingNode) {
      loadingNode.style.display = "none";
    }
    viewer.plugin.managers.camera.reset();
  } catch (err) {
    console.error("Failed to initialize Mol* viewer", err);
    if (loadingNode) {
      loadingNode.textContent = "Failed to load structure";
      loadingNode.style.display = "flex";
    }
  }
}

function activateStructureViewers(root = document) {
  for (const node of root.querySelectorAll("[data-refua-molstar-stage='1']")) {
    initMolstarStage(node);
  }
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
  const activeTabTarget = VIEW_TAB_TARGETS[viewName] || viewName;

  for (const button of viewTabs) {
    const isActive = button.dataset.viewTarget === activeTabTarget;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  }

  for (const panel of viewPanels) {
    const isActive = panel.dataset.viewPanel === viewName;
    panel.classList.toggle("is-active", isActive);
    panel.hidden = !isActive;
  }
}

function buildHashForRoute(viewName, drugId = null) {
  if (viewName === "drug-report" && drugId) {
    return `#promising-drugs/${encodeURIComponent(drugId)}`;
  }
  if (viewName === "promising-drugs") {
    return "#promising-drugs";
  }
  return "#campaign";
}

function parseRouteFromHash() {
  const rawHash = window.location.hash.replace(/^#/, "").trim();
  if (!rawHash || rawHash === "campaign") {
    return { view: "campaign", drugId: null };
  }
  if (rawHash === "promising-drugs") {
    return { view: "promising-drugs", drugId: null };
  }
  if (rawHash.startsWith("promising-drugs/")) {
    const rawDrugId = rawHash.slice("promising-drugs/".length);
    return {
      view: "drug-report",
      drugId: rawDrugId ? decodeURIComponent(rawDrugId) : null,
    };
  }
  return { view: "campaign", drugId: null };
}

function navigateToView(viewName, { drugId = null, replace = false } = {}) {
  const nextHash = buildHashForRoute(viewName, drugId);
  if (replace) {
    const nextUrl = new URL(window.location.href);
    nextUrl.hash = nextHash;
    window.history.replaceState(null, "", nextUrl);
    syncRouteWithLocation();
    return;
  }
  if (window.location.hash === nextHash) {
    syncRouteWithLocation();
    return;
  }
  window.location.hash = nextHash;
}

function syncRouteWithLocation() {
  const route = parseRouteFromHash();
  if (route.view === "drug-report" && route.drugId) {
    state.selectedDrugId = route.drugId;
  }
  setActiveView(route.view);
  renderPromisingDrugs();
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

function renderPromisingDrugsSummary(visibleCount, drugs = []) {
  const summary = state.promisingSummary || {};
  const topDrug = drugs[0] || null;
  const parts = [
    `${visibleCount} shown`,
    `${summary.total_drugs || 0} tracked`,
    `${summary.promising_count || 0} promising`,
    `${summary.watchlist_count || 0} watchlist`,
    `${summary.source_jobs_count || 0} source jobs`,
  ];
  promisingDrugsSummary.textContent = parts.join(" | ");

  openTopDrugReportButton.disabled = !topDrug;
  openTopDrugReportButton.textContent = topDrug
    ? `Open Top Report${topDrug.name ? ` · ${topDrug.name}` : ""}`
    : "Open Top Report";
}

function findDrugById(drugId) {
  if (!drugId) {
    return null;
  }
  return state.promisingDrugs.find((drug) => drug.drug_id === drugId) || null;
}

function inferStructureFormat(pathValue, formatValue) {
  const explicit = asText(formatValue);
  if (explicit) {
    return explicit.toUpperCase();
  }
  const pathText = asText(pathValue);
  if (!pathText || !pathText.includes(".")) {
    return null;
  }
  return pathText.split(".").pop().toUpperCase();
}

function percentageOrNull(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return null;
  }
  return clamp(numeric > 1 ? numeric / 100 : numeric, 0, 1);
}

function shortLabel(value, limit = 22) {
  const text = asText(value) || "Unknown";
  return truncate(text, limit);
}

function buildDrugReportModel(drug) {
  const toolArgs = asObject(drug.tool_args);
  const admet = asObject(drug.admet);
  const admetKeyMetrics = asObject(admet.key_metrics);
  const admetProperties = asObject(admet.properties);

  const rawEntities = asArray(toolArgs.entities).filter((item) => typeof item === "object" && item);
  const proteins = rawEntities
    .filter((entity) => String(entity.type || "").toLowerCase() === "protein")
    .map((entity, index) => ({
      id: asText(entity.id) || `protein-${index + 1}`,
      name: asText(entity.name) || asText(entity.id) || drug.target || `Protein ${index + 1}`,
      sequenceLength: asText(entity.sequence)?.length || 0,
      chainIds: collectChainIds(
        entity.chain_ids ?? entity.chain_id ?? entity.label_asym_id ?? entity.auth_asym_id ?? entity.ids
      ),
      inferred: false,
    }));
  const ligands = rawEntities
    .filter((entity) => String(entity.type || "").toLowerCase() === "ligand")
    .map((entity, index) => ({
      id: asText(entity.id) || `ligand-${index + 1}`,
      name:
        asText(entity.name) ||
        (index === 0 ? drug.name || drug.drug_id : `Ligand ${index + 1}`),
      smiles: asText(entity.smiles) || drug.smiles,
      chainIds: collectChainIds(
        entity.chain_ids ?? entity.chain_id ?? entity.label_asym_id ?? entity.auth_asym_id ?? entity.ids
      ),
      inferred: false,
    }));
  const otherEntities = rawEntities
    .filter((entity) => {
      const normalized = String(entity.type || "").toLowerCase();
      return normalized !== "protein" && normalized !== "ligand";
    })
    .map((entity, index) => ({
      id: asText(entity.id) || `component-${index + 1}`,
      type: asText(entity.type) || "component",
      name: asText(entity.name) || asText(entity.id) || `Component ${index + 1}`,
      chainIds: collectChainIds(
        entity.chain_ids ?? entity.chain_id ?? entity.label_asym_id ?? entity.auth_asym_id ?? entity.ids
      ),
    }));

  if (proteins.length === 0 && drug.target) {
    proteins.push({
      id: "target",
      name: drug.target,
      sequenceLength: 0,
      chainIds: [],
      inferred: true,
    });
  }
  if (ligands.length === 0 && (drug.name || drug.smiles || drug.drug_id)) {
    ligands.push({
      id: "candidate",
      name: drug.name || drug.drug_id,
      smiles: drug.smiles || null,
      chainIds: [],
      inferred: true,
    });
  }

  const structurePath = asText(toolArgs.structure_output_path);
  const structureFormat = inferStructureFormat(structurePath, toolArgs.structure_output_format);
  const structureUrl = buildStructureUrl(structurePath);
  const viewerFormat = inferMolstarFormat(structurePath, toolArgs.structure_output_format);
  const bindingProbability = percentageOrNull(asObject(drug.metrics).binding_probability);
  const admetScore = percentageOrNull(
    asObject(drug.metrics).admet_score ?? admetKeyMetrics.admet_score
  );
  const hasStructureArtifact = Boolean(structurePath);
  const complexConfidence = clamp(
    (bindingProbability ?? 0.42) * 0.62 +
      (admetScore ?? 0.36) * 0.18 +
      (drug.promising ? 0.2 : 0.08),
    0,
    1
  );
  const hasComplexSignal =
    hasStructureArtifact || drug.promising || (bindingProbability !== null && bindingProbability >= 0.55);
  const complexStateLabel = hasStructureArtifact
    ? "Structure-backed complex"
    : hasComplexSignal
      ? "Predicted bound complex"
      : "Interaction hypothesis";

  return {
    proteins,
    ligands,
    otherEntities,
    bindingProbability,
    admetScore,
    admet,
    admetKeyMetrics,
    admetProperties,
    structurePath,
    structureFormat,
    structureUrl,
    viewerFormat,
    hasStructureArtifact,
    hasComplexSignal,
    complexConfidence,
    complexStateLabel,
  };
}

function appendFactRow(container, label, value, { mono = false } = {}) {
  if (value === null || value === undefined || value === "") {
    return;
  }
  const row = createElement("div", "report-fact");
  row.appendChild(createElement("span", "mini-label", label));
  row.appendChild(createElement("span", mono ? "report-fact-value detail-mono" : "report-fact-value", value));
  container.appendChild(row);
}

function createReportStat(label, value, tone = "") {
  const item = createElement("div", `report-stat ${tone}`.trim());
  item.appendChild(createElement("span", "mini-label", label));
  item.appendChild(createElement("strong", "report-stat-value", value));
  return item;
}

function renderMetricSection(title, metrics, { limit = null, className = "" } = {}) {
  const entries = Object.entries(metrics || {}).filter(([, value]) => {
    return value !== null && value !== undefined && String(value).trim() !== "";
  });
  if (entries.length === 0) {
    return null;
  }

  const section = createElement("section", `report-card detail-section ${className}`.trim());
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

function renderSourceList(sources, { title = "Evidence Timeline" } = {}) {
  if (!Array.isArray(sources) || sources.length === 0) {
    return null;
  }

  const section = createElement("section", "report-card detail-section");
  section.appendChild(createElement("h3", null, title));

  const list = createElement("div", "source-list");
  for (const source of sources.slice(0, 6)) {
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
      item.appendChild(createElement("p", "source-copy", truncate(source.objective, 150)));
    }
    list.appendChild(item);
  }

  section.appendChild(list);
  return section;
}

function renderEvidencePaths(evidencePaths) {
  const entries = Object.entries(asObject(evidencePaths));
  if (entries.length === 0) {
    return null;
  }

  const section = createElement("section", "report-card detail-section");
  section.appendChild(createElement("h3", null, "Evidence Provenance"));

  const list = createElement("div", "report-evidence-list");
  for (const [key, value] of entries.slice(0, 8)) {
    const item = createElement("div", "report-evidence-item");
    item.appendChild(createElement("span", "mini-label", metricLabel(key)));
    item.appendChild(createElement("code", "report-evidence-path", String(value)));
    list.appendChild(item);
  }
  section.appendChild(list);
  return section;
}

function renderEntityCards(report) {
  const grid = createElement("div", "report-entity-grid");
  for (const protein of report.proteins) {
    const card = createElement("article", "report-entity-card is-protein");
    card.appendChild(createElement("span", "mini-label", protein.inferred ? "Protein · inferred" : "Protein"));
    card.appendChild(createElement("h3", null, protein.name));
    if (protein.sequenceLength) {
      card.appendChild(createElement("p", "panel-copy", `${protein.sequenceLength} aa sequence`));
    }
    grid.appendChild(card);
  }
  for (const ligand of report.ligands) {
    const card = createElement("article", "report-entity-card is-ligand");
    card.appendChild(createElement("span", "mini-label", ligand.inferred ? "Ligand · inferred" : "Ligand"));
    card.appendChild(createElement("h3", null, ligand.name));
    if (ligand.smiles) {
      card.appendChild(createElement("p", "panel-copy detail-mono", truncate(ligand.smiles, 54)));
    }
    grid.appendChild(card);
  }
  for (const entity of report.otherEntities) {
    const card = createElement("article", "report-entity-card");
    card.appendChild(createElement("span", "mini-label", entity.type));
    card.appendChild(createElement("h3", null, entity.name));
    grid.appendChild(card);
  }
  return grid;
}

function renderMolstarStructureStage(drug, report) {
  const wrapper = createElement("figure", "molstar-stage-figure");
  const meta = createElement("div", "complex-meta");
  meta.appendChild(
    createElement(
      "span",
      "complex-name",
      report.structurePath ? `${drug.name || drug.drug_id} · ${report.structureFormat || "structure"}` : (drug.name || drug.drug_id)
    )
  );
  meta.appendChild(
    createElement(
      "span",
      `complex-status ${report.hasStructureArtifact ? "ready" : "pending"}`,
      report.hasStructureArtifact ? "3D Ready" : "Pending"
    )
  );
  wrapper.appendChild(meta);

  const stage = createElement("div", "molstar-stage");
  stage.setAttribute("data-refua-molstar-stage", "1");
  stage.dataset.url = report.structureUrl || "";
  stage.dataset.format = report.viewerFormat || "mmcif";
  stage.dataset.ligand = drug.name || drug.drug_id || "";
  stage.dataset.colorPlan = JSON.stringify(buildMolstarColorPlan(report));

  const viewerId = `molstar-stage-${String(drug.drug_id || "candidate").replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  const viewerNode = createElement("div", "molstar-stage-viewer");
  viewerNode.id = viewerId;
  viewerNode.setAttribute("data-refua-molstar-viewer", "1");
  stage.appendChild(viewerNode);

  const loadingNode = createElement("div", "molstar-loading", "Loading structure...");
  loadingNode.setAttribute("data-refua-molstar-loading", "1");
  stage.appendChild(loadingNode);

  wrapper.appendChild(stage);
  wrapper.appendChild(
    createElement(
      "figcaption",
      "panel-copy complex-figure-caption",
      `Mol* is rendering ${report.structureFormat || "structure"} data directly from the stored artifact path for ${drug.name || drug.drug_id}.`
    )
  );
  return wrapper;
}

function renderComplexVisualization(drug, report) {
  if (report.structureUrl && report.viewerFormat) {
    return renderMolstarStructureStage(drug, report);
  }

  const figure = createElement("figure", "complex-figure");
  const svg = createSvgElement("svg", {
    viewBox: "0 0 860 380",
    class: "complex-figure-svg",
    role: "img",
    "aria-label": `Complex visualization for ${drug.name || drug.drug_id}`,
  });

  const defs = createSvgElement("defs");
  const coreGradient = createSvgElement("linearGradient", {
    id: "complex-core-gradient",
    x1: "0%",
    y1: "0%",
    x2: "100%",
    y2: "100%",
  });
  coreGradient.appendChild(createSvgElement("stop", { offset: "0%", "stop-color": "#0e7490" }));
  coreGradient.appendChild(createSvgElement("stop", { offset: "100%", "stop-color": "#17233a" }));
  defs.appendChild(coreGradient);
  svg.appendChild(defs);

  svg.appendChild(
    createSvgElement("rect", {
      x: 8,
      y: 8,
      width: 844,
      height: 364,
      rx: 34,
      fill: "#fffdf8",
      opacity: 0.94,
      stroke: "#d7cebf",
    })
  );

  if (report.hasStructureArtifact) {
    svg.appendChild(
      createSvgElement("circle", {
        cx: 430,
        cy: 188,
        r: 112,
        fill: "rgba(14, 116, 144, 0.08)",
        stroke: "rgba(14, 116, 144, 0.28)",
        "stroke-width": 3,
      })
    );
  }

  const bridgeWidth = 2 + Math.round((report.bindingProbability ?? 0.38) * 8);
  for (const [index, protein] of report.proteins.slice(0, 3).entries()) {
    const y = 122 + index * 72;
    svg.appendChild(
      createSvgElement("path", {
        d: `M 268 ${y + 18} C 324 ${y + 8}, 356 165, 392 188`,
        fill: "none",
        stroke: "rgba(23, 35, 58, 0.28)",
        "stroke-width": bridgeWidth,
        "stroke-linecap": "round",
      })
    );
    svg.appendChild(
      createSvgElement("rect", {
        x: 92,
        y,
        width: 178,
        height: 42,
        rx: 21,
        fill: "#17233a",
      })
    );
    const label = createSvgElement("text", {
      x: 181,
      y: y + 26,
      "text-anchor": "middle",
      fill: "#f5f9ff",
      "font-family": "Space Grotesk, sans-serif",
      "font-size": 16,
      "font-weight": 600,
    });
    label.textContent = shortLabel(protein.name, 18);
    svg.appendChild(label);
  }

  for (const [index, ligand] of report.ligands.slice(0, 3).entries()) {
    const y = 122 + index * 72;
    svg.appendChild(
      createSvgElement("path", {
        d: `M 592 188 C 632 168, 644 ${y + 10}, 684 ${y + 18}`,
        fill: "none",
        stroke: "rgba(14, 116, 144, 0.34)",
        "stroke-width": bridgeWidth + 1,
        "stroke-linecap": "round",
      })
    );
    svg.appendChild(
      createSvgElement("rect", {
        x: 590,
        y,
        width: 178,
        height: 42,
        rx: 21,
        fill: "#0e7490",
      })
    );
    const label = createSvgElement("text", {
      x: 679,
      y: y + 26,
      "text-anchor": "middle",
      fill: "#f5f9ff",
      "font-family": "Space Grotesk, sans-serif",
      "font-size": 16,
      "font-weight": 600,
    });
    label.textContent = shortLabel(ligand.name, 18);
    svg.appendChild(label);
  }

  svg.appendChild(
    createSvgElement("ellipse", {
      cx: 430,
      cy: 188,
      rx: 116,
      ry: 78,
      fill: "url(#complex-core-gradient)",
    })
  );

  const centerLabel = createSvgElement("text", {
    x: 430,
    y: 178,
    "text-anchor": "middle",
    fill: "#f5f9ff",
    "font-family": "IBM Plex Mono, monospace",
    "font-size": 12,
    "letter-spacing": 1.8,
  });
  centerLabel.textContent = "COMPLEX STATE";
  svg.appendChild(centerLabel);

  const centerState = createSvgElement("text", {
    x: 430,
    y: 208,
    "text-anchor": "middle",
    fill: "#f5f9ff",
    "font-family": "Space Grotesk, sans-serif",
    "font-size": 26,
    "font-weight": 700,
  });
  centerState.textContent = report.complexStateLabel;
  svg.appendChild(centerState);

  const centerConfidence = createSvgElement("text", {
    x: 430,
    y: 234,
    "text-anchor": "middle",
    fill: "rgba(245, 249, 255, 0.82)",
    "font-family": "Space Grotesk, sans-serif",
    "font-size": 14,
  });
  centerConfidence.textContent = `confidence ${Math.round(report.complexConfidence * 100)}%`;
  svg.appendChild(centerConfidence);

  const topPill = createSvgElement("rect", {
    x: 347,
    y: 44,
    width: 166,
    height: 34,
    rx: 17,
    fill: "rgba(20, 122, 76, 0.12)",
    stroke: "rgba(20, 122, 76, 0.22)",
  });
  svg.appendChild(topPill);
  const topText = createSvgElement("text", {
    x: 430,
    y: 65,
    "text-anchor": "middle",
    fill: "#147a4c",
    "font-family": "IBM Plex Mono, monospace",
    "font-size": 12,
    "letter-spacing": 1.2,
  });
  topText.textContent = report.hasStructureArtifact
    ? `artifact ${report.structureFormat || "ready"}`
    : `best score ${formatScore(drug.score)}`;
  svg.appendChild(topText);

  const bottomText = createSvgElement("text", {
    x: 430,
    y: 332,
    "text-anchor": "middle",
    fill: "#60708a",
    "font-family": "Space Grotesk, sans-serif",
    "font-size": 15,
  });
  bottomText.textContent = `${pluralize(report.proteins.length, "protein")} · ${pluralize(report.ligands.length, "ligand")} · ${pluralize(drug.source_jobs_count || 0, "source job")}`;
  svg.appendChild(bottomText);

  figure.appendChild(svg);
  figure.appendChild(
    createElement(
      "figcaption",
      "panel-copy complex-figure-caption",
      report.hasStructureArtifact
        ? "A stored structure artifact is attached to this candidate. The diagram centers the inferred binding core and all captured entities."
        : "No structure artifact was stored for this candidate, so the report renders an interaction map from the best available target, ligand, and scoring evidence."
    )
  );
  return figure;
}

function renderDrugReportPage(drug) {
  clearNode(drugReportPage);

  if (!drug) {
    drugReportPage.hidden = true;
    drugReportEmpty.hidden = false;
    return;
  }

  drugReportPage.hidden = false;
  drugReportEmpty.hidden = true;

  const report = buildDrugReportModel(drug);
  const admetStatus = asText(report.admet.status);
  const shell = createElement("div", "report-shell");

  const backRow = createElement("div", "report-topbar");
  const backButton = createElement("button", "btn btn-secondary", "Back to Library");
  backButton.id = "backToPromisingDrugsButton";
  backButton.type = "button";
  backButton.addEventListener("click", () => {
    navigateToView("promising-drugs");
  });
  backRow.appendChild(backButton);
  backRow.appendChild(statusBadge(drugStatus(drug)));
  shell.appendChild(backRow);

  const hero = createElement("section", "report-hero");
  const heroCopy = createElement("div", "report-hero-copy");
  heroCopy.appendChild(
    createElement(
      "p",
      "eyebrow",
      report.hasStructureArtifact ? "Structure-Backed Therapeutic Report" : "Therapeutic Evidence Report"
    )
  );
  heroCopy.appendChild(createElement("h2", "report-title", drug.name || drug.drug_id));
  heroCopy.appendChild(
    createElement(
      "p",
      "report-lead",
      drug.assessment ||
        `${drug.name || drug.drug_id} is currently ${drug.promising ? "ranked as promising" : "tracked as a watchlist candidate"} for ${drug.target || "its selected target"}.`
    )
  );

  const heroMeta = createElement("div", "chip-row");
  heroMeta.appendChild(metricChip(drug.target || "Target unspecified", "is-accent"));
  heroMeta.appendChild(metricChip(`Primary tool ${drug.tool || "unknown"}`));
  heroMeta.appendChild(metricChip(`Latest ${formatDate(drug.latest_seen_at)}`));
  if (admetStatus) {
    heroMeta.appendChild(metricChip(`ADMET ${admetStatus}`, admetStatus === "favorable" ? "is-success" : "is-accent"));
  }
  heroCopy.appendChild(heroMeta);
  hero.appendChild(heroCopy);

  const stats = createElement("div", "report-stat-grid");
  stats.appendChild(createReportStat("Best Score", formatScore(drug.score), "is-dark"));
  stats.appendChild(
    createReportStat(
      "Binding",
      report.bindingProbability !== null
        ? formatMetricValue("binding_probability", report.bindingProbability)
        : "Pending",
      "is-accent"
    )
  );
  stats.appendChild(
    createReportStat(
      "ADMET",
      report.admetScore !== null ? formatMetricValue("admet_score", report.admetScore) : "Pending",
      report.admetScore !== null && report.admetScore >= 0.65 ? "is-success" : ""
    )
  );
  stats.appendChild(
    createReportStat(
      "Signals",
      `${drug.promising_runs || 0}/${drug.seen_count || 0}`,
      drug.promising ? "is-success" : ""
    )
  );
  hero.appendChild(stats);
  shell.appendChild(hero);

  const mainGrid = createElement("div", "report-main-grid");

  const visualCard = createElement("section", "report-card report-visual-card");
  visualCard.appendChild(createElement("h3", null, "Complex Formation"));
  visualCard.appendChild(
    createElement(
      "p",
      "panel-copy",
      report.hasStructureArtifact
        ? "This candidate includes a stored structure artifact, and the report now uses Mol* to render the captured CIF or BCIF complex directly."
        : "This page synthesizes the captured target, ligand, and scoring data into a direct interaction visualization."
    )
  );
  visualCard.appendChild(renderComplexVisualization(drug, report));

  const visualFacts = createElement("div", "report-facts-grid");
  appendFactRow(visualFacts, "Drug ID", drug.drug_id, { mono: true });
  appendFactRow(visualFacts, "Target", drug.target);
  appendFactRow(visualFacts, "Structure Artifact", report.structurePath, { mono: true });
  appendFactRow(visualFacts, "Artifact Format", report.structureFormat);
  appendFactRow(visualFacts, "SMILES", drug.smiles, { mono: true });
  visualCard.appendChild(visualFacts);
  visualCard.appendChild(renderEntityCards(report));
  mainGrid.appendChild(visualCard);

  const summaryCard = createElement("section", "report-card report-summary-card");
  summaryCard.appendChild(createElement("h3", null, "Executive Readout"));
  summaryCard.appendChild(
    createElement(
      "p",
      "report-paragraph",
      `${drug.name || drug.drug_id} has been observed across ${pluralize(drug.source_jobs_count || 0, "source job")} and ${pluralize(drug.seen_count || 0, "captured observation")}. The current report is anchored to the strongest run by score and status, then merged with the latest supporting evidence.`
    )
  );
  summaryCard.appendChild(
    createElement(
      "p",
      "report-paragraph",
      report.hasStructureArtifact
        ? `A ${report.structureFormat || "structure"} artifact is available, which upgrades this candidate from a simple scorecard to a structure-backed report page.`
        : `No structure artifact path was retained in the candidate payload, so the visualization remains evidence-derived rather than atomistic.`
    )
  );
  summaryCard.appendChild(
    createElement(
      "p",
      "report-paragraph",
      report.bindingProbability !== null
        ? `Predicted binding probability sits at ${formatMetricValue("binding_probability", report.bindingProbability)}, while the ADMET profile reads ${report.admetScore !== null ? formatMetricValue("admet_score", report.admetScore) : "pending"}.`
        : `The current report is being carried primarily by qualitative assessment and source provenance because no binding probability was captured in the strongest observation.`
    )
  );

  const summaryChips = createElement("div", "chip-row");
  summaryChips.appendChild(metricChip(report.complexStateLabel, report.hasComplexSignal ? "is-success" : "is-accent"));
  for (const toolName of asArray(drug.tools).slice(0, 4)) {
    summaryChips.appendChild(metricChip(toolName));
  }
  summaryCard.appendChild(summaryChips);
  mainGrid.appendChild(summaryCard);

  shell.appendChild(mainGrid);

  const metricsRow = createElement("div", "report-secondary-grid");
  const metricsSection = renderMetricSection("Key Metrics", asObject(drug.metrics));
  if (metricsSection) {
    metricsRow.appendChild(metricsSection);
  }
  const admetMetricsSection = renderMetricSection("ADMET Highlights", report.admetKeyMetrics);
  if (admetMetricsSection) {
    metricsRow.appendChild(admetMetricsSection);
  }
  const admetPropertiesSection = renderMetricSection("ADMET Properties", report.admetProperties, {
    limit: 6,
  });
  if (admetPropertiesSection) {
    metricsRow.appendChild(admetPropertiesSection);
  }
  shell.appendChild(metricsRow);

  const bottomGrid = createElement("div", "report-secondary-grid");
  const sourceSection = renderSourceList(drug.sources, { title: "Source Runs" });
  if (sourceSection) {
    bottomGrid.appendChild(sourceSection);
  }
  const evidenceSection = renderEvidencePaths(drug.evidence_paths);
  if (evidenceSection) {
    bottomGrid.appendChild(evidenceSection);
  }
  shell.appendChild(bottomGrid);

  drugReportPage.appendChild(shell);
  activateStructureViewers(drugReportPage);
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
    button.setAttribute("aria-label", `Open report for ${drug.name || drug.drug_id}`);
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

    button.appendChild(
      createElement(
        "p",
        "drug-card-launch",
        reportLaunchLabel(drug)
      )
    );

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
      navigateToView("drug-report", { drugId: drug.drug_id });
    });

    drugCards.appendChild(button);
  }
}

function reportLaunchLabel(drug) {
  const toolArgs = asObject(drug.tool_args);
  return toolArgs.structure_output_path ? "Open structure-backed report" : "Open full report";
}

function renderPromisingDrugs() {
  const drugs = filteredPromisingDrugs();
  const selectedDrug = findDrugById(state.selectedDrugId);
  const selectedVisible = drugs.some((drug) => drug.drug_id === state.selectedDrugId);
  const route = parseRouteFromHash();

  if (!selectedDrug && state.activeView === "drug-report") {
    if (state.promisingDrugs.length === 0) {
      renderPromisingDrugsSummary(drugs.length, drugs);
      renderDrugCards(drugs);
      renderDrugReportPage(null);
      return;
    }
    navigateToView("promising-drugs", { replace: true });
    return;
  }

  if (!selectedVisible && state.activeView !== "drug-report") {
    state.selectedDrugId = drugs[0]?.drug_id || null;
  }

  renderPromisingDrugsSummary(drugs.length, drugs);
  renderDrugCards(drugs);
  renderDrugReportPage(route.view === "drug-report" ? selectedDrug : null);
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
  openTopDrugReportButton.addEventListener("click", () => {
    const topDrug = filteredPromisingDrugs()[0] || state.promisingDrugs[0] || null;
    if (!topDrug) {
      return;
    }
    state.selectedDrugId = topDrug.drug_id;
    navigateToView("drug-report", { drugId: topDrug.drug_id });
  });
  document.getElementById("clearDrugFiltersButton").addEventListener("click", () => {
    resetDrugFilters();
  });

  for (const button of viewTabs) {
    button.addEventListener("click", () => {
      navigateToView(button.dataset.viewTarget || "campaign");
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
  openTopDrugReportButton.disabled = true;
  window.addEventListener("hashchange", syncRouteWithLocation);
  syncRouteWithLocation();

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
