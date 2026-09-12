import { RedPathApi, normalizeFinding, normalizeHealth } from "./api.js";
import { normalizeRecommendation, ProposalWorkflow, renderProposalState, renderRecommendation } from "./recommendation.js";
import {
  EmergencyStopWorkflow,
  normalizeAuditHistory,
  normalizeLearningReport,
  renderEmergencyStop,
  renderSessionOversight,
} from "./oversight.js";

const api = new RedPathApi();
const refreshButton = document.querySelector("#refresh-health");
const message = document.querySelector("#health-message");
const sessionForm = document.querySelector("#session-form");
const sessionMessage = document.querySelector("#session-message");
const scanForm = document.querySelector("#scan-form");
const scanFile = document.querySelector("#scan-file");
const evidenceMessage = document.querySelector("#evidence-message");
const findingsBody = document.querySelector("#findings-body");
const reportMessage = document.querySelector("#report-message");
const explanations = document.querySelector("#explanations");
const recommendationButton = document.querySelector("#request-recommendation");
const recommendationMessage = document.querySelector("#recommendation-message");
const recommendationElements = {
  content: document.querySelector("#recommendation-content"),
  heading: document.querySelector("#ai-recommendation-title"),
  findingIds: document.querySelector("#recommendation-finding-ids"),
  reason: document.querySelector("#recommendation-reason"),
  learningGoal: document.querySelector("#recommendation-learning-goal"),
  action: document.querySelector("#recommendation-action"),
  arguments: document.querySelector("#recommendation-arguments"),
  policyResult: document.querySelector("#policy-result"),
  policyCode: document.querySelector("#policy-code"),
  policyExplanation: document.querySelector("#policy-explanation"),
};
const proposalElements = {
  controls: document.querySelector("#proposal-controls"),
  approve: document.querySelector("#approve-proposal"),
  reject: document.querySelector("#reject-proposal"),
  message: document.querySelector("#proposal-state"),
};
const emergencyElements = {
  activate: document.querySelector("#emergency-stop"),
  clear: document.querySelector("#clear-emergency-stop"),
  refresh: document.querySelector("#refresh-emergency-stop"),
  message: document.querySelector("#emergency-stop-state"),
};
const oversightButton = document.querySelector("#refresh-oversight");
const oversightMessage = document.querySelector("#oversight-message");
const oversightElements = {
  summary: document.querySelector("#report-summary"),
  overview: document.querySelector("#report-overview"),
  proposals: document.querySelector("#report-proposals"),
  approvals: document.querySelector("#report-approvals"),
  audit: document.querySelector("#audit-history"),
  events: document.querySelector("#audit-events"),
};
let activeSessionId = null;
let recommendationReady = false;
let recommendationPending = false;
let approvalTimer = null;

const proposalWorkflow = new ProposalWorkflow({
  api,
  onChange: (state) => {
    renderProposalState(proposalElements, state);
    clearTimeout(approvalTimer);
    if (state.status === "approved") {
      const delay = Math.max(0, Date.parse(state.receipt.expiresAt) - Date.now());
      approvalTimer = setTimeout(() => proposalWorkflow.refreshExpiration(), Math.min(delay + 25, 2_147_483_647));
    }
  },
});

const emergencyStopWorkflow = new EmergencyStopWorkflow({
  api,
  onChange: (state) => {
    proposalWorkflow.setEmergencyStop(state.active);
    renderEmergencyStop(emergencyElements, state);
  },
});

renderEmergencyStop(emergencyElements, emergencyStopWorkflow.state);

function resetRecommendation(text) {
  clearTimeout(approvalTimer);
  recommendationElements.content.hidden = true;
  recommendationButton.disabled = true;
  recommendationMessage.dataset.state = "";
  recommendationMessage.textContent = text;
  proposalElements.controls.hidden = true;
  proposalElements.approve.disabled = true;
  proposalElements.reject.disabled = true;
}

function setLoading(isLoading) {
  refreshButton.disabled = isLoading;
  refreshButton.textContent = isLoading ? "Checking…" : "Refresh status";
  refreshButton.setAttribute("aria-busy", String(isLoading));
}

function renderService(name, health) {
  const card = document.querySelector(`[data-service="${name}"]`);
  const badge = card.querySelector("[data-status]");
  badge.dataset.state = health.state;
  badge.textContent = health.state === "healthy" ? "Available"
    : health.state === "standby" ? "On demand"
    : health.state === "offline" ? "Offline"
    : health.state === "unknown" ? "Not reported"
    : "Problem";
  card.querySelector("[data-detail]").textContent = health.detail;
}

async function refreshHealth() {
  setLoading(true);
  message.dataset.state = "";
  message.textContent = "Checking RedPath services…";
  try {
    const health = normalizeHealth(await api.getHealth());
    Object.entries(health).forEach(([name, value]) => renderService(name, value));
    const states = Object.values(health).map(({ state }) => state);
    const allHealthy = states.every((state) => state === "healthy");
    const hasError = states.includes("error");
    message.dataset.state = hasError ? "error" : "healthy";
    message.textContent = allHealthy
      ? "All RedPath services are available."
      : hasError
        ? "Some services need attention. You can still review available learning material."
        : "RedPath is reachable. Other services may be offline, on demand, or not reported yet.";
  } catch (error) {
    ["fastapi", "ollama", "kali"].forEach((name) => renderService(name, {
      state: "error",
      detail: name === "fastapi" ? error.message : "Status unavailable while the API is offline.",
    }));
    message.dataset.state = "error";
    message.textContent = `${error.message} Check that the backend is running, then try again.`;
  } finally {
    setLoading(false);
  }
}

refreshButton.addEventListener("click", refreshHealth);
emergencyElements.activate.addEventListener("click", () => emergencyStopWorkflow.activate());
emergencyElements.clear.addEventListener("click", () => emergencyStopWorkflow.clear());
emergencyElements.refresh.addEventListener("click", () => emergencyStopWorkflow.refresh());

async function refreshOversight() {
  if (!activeSessionId || oversightButton.disabled) return;
  oversightButton.disabled = true;
  oversightButton.setAttribute("aria-busy", "true");
  oversightMessage.dataset.state = "pending";
  oversightMessage.textContent = "Loading the bounded learning report and audit history…";
  try {
    const sessionId = activeSessionId;
    const [reportPayload, historyPayload] = await Promise.all([
      api.getLearningReport(sessionId),
      api.getAuditHistory(sessionId),
    ]);
    if (sessionId !== activeSessionId) throw new TypeError("Session changed.");
    const report = normalizeLearningReport(reportPayload, sessionId);
    const history = normalizeAuditHistory(historyPayload, sessionId);
    renderSessionOversight(oversightElements, report, history);
    oversightMessage.dataset.state = "healthy";
    oversightMessage.textContent = "Latest bounded report and audit records loaded.";
  } catch {
    oversightElements.summary.hidden = true;
    oversightElements.audit.hidden = true;
    oversightMessage.dataset.state = "error";
    oversightMessage.textContent = "RedPath could not load valid oversight records for this session.";
  } finally {
    oversightButton.disabled = !activeSessionId;
    oversightButton.setAttribute("aria-busy", "false");
  }
}

oversightButton.addEventListener("click", refreshOversight);

sessionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = sessionForm.querySelector("button[type=submit]");
  const data = new FormData(sessionForm);
  submit.disabled = true;
  sessionMessage.textContent = "Creating the authorized session…";
  try {
    const expiresAt = new Date(Date.now() + Number(data.get("expires_in_minutes")) * 60_000).toISOString();
    const session = await api.createSession({ authorization_confirmed: data.get("authorization_confirmed") === "on", expires_at: expiresAt });
    await api.addLessonSource(session.id, { url: data.get("lesson_url"), title: data.get("objective") });
    await api.addTarget(session.id, { address: data.get("target"), authorization_source: "user_confirmation", expires_at: expiresAt });
    activeSessionId = session.id;
    oversightElements.summary.hidden = true;
    oversightElements.audit.hidden = true;
    oversightButton.disabled = false;
    oversightMessage.dataset.state = "";
    oversightMessage.textContent = "Session created. Load the latest bounded report and audit records when needed.";
    recommendationReady = false;
    resetRecommendation("Import evidence before requesting a recommendation.");
    scanFile.disabled = false;
    scanForm.querySelector("button[type=submit]").disabled = false;
    sessionMessage.textContent = "Session created. You can now import evidence for the authorized target.";
    evidenceMessage.textContent = "Choose an Nmap XML file produced for this session's target.";
  } catch (error) {
    sessionMessage.textContent = error.message;
  } finally { submit.disabled = false; }
});

scanForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!activeSessionId || !scanFile.files?.[0]) return;
  const submit = scanForm.querySelector("button[type=submit]");
  submit.disabled = true;
  recommendationReady = false;
  resetRecommendation("Importing new evidence before another recommendation can be requested.");
  evidenceMessage.textContent = "Importing and validating the scan…";
  try {
    const file = scanFile.files[0];
    if (file.size > 2_000_000) throw new Error("The XML file is larger than the 2 MB browser limit.");
    const result = await api.importScan(activeSessionId, { filename: file.name, xml_text: await file.text() });
    const findings = Array.isArray(result.findings) ? result.findings.map(normalizeFinding) : [];
    findingsBody.replaceChildren();
    if (!findings.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 4; cell.textContent = "No open-port findings were present."; row.append(cell); findingsBody.append(row);
    } else for (const finding of findings) {
      const row = document.createElement("tr");
      for (const value of [finding.state, finding.port ? `${finding.port}/${finding.protocol}` : "Unknown", finding.service, finding.source]) {
        const cell = document.createElement("td"); cell.textContent = String(value); row.append(cell);
      }
      findingsBody.append(row);
    }
    evidenceMessage.textContent = `${findings.length} observed finding${findings.length === 1 ? "" : "s"} imported.`;
    recommendationReady = findings.length > 0;
    recommendationButton.disabled = !recommendationReady;
    recommendationMessage.textContent = recommendationReady
      ? "Evidence is ready. Request one policy-checked learning recommendation."
      : "A recommendation needs at least one imported finding.";
    const learning = await api.getExplanation(activeSessionId);
    explanations.replaceChildren();
    for (const explanation of learning.explanations || []) {
      const article = document.createElement("article");
      const heading = document.createElement("h3");
      heading.textContent = explanation.summary;
      const meaning = document.createElement("p");
      meaning.textContent = explanation.what_it_means;
      const limit = document.createElement("p");
      limit.textContent = explanation.what_it_does_not_prove;
      article.append(heading, meaning, limit);
      explanations.append(article);
    }
    reportMessage.textContent = learning.explanations?.length
      ? "These explanations describe evidence only. They do not authorize execution."
      : (learning.missing_evidence?.[0] || "No explanation was available.");
  } catch (error) { evidenceMessage.textContent = error.message; }
  finally { submit.disabled = false; }
});

recommendationButton.addEventListener("click", async () => {
  if (!activeSessionId || !recommendationReady || recommendationPending) return;
  recommendationPending = true;
  recommendationButton.disabled = true;
  recommendationButton.setAttribute("aria-busy", "true");
  recommendationButton.textContent = "Requesting…";
  recommendationMessage.dataset.state = "pending";
  recommendationMessage.textContent = "Requesting an AI recommendation and an independent policy decision…";
  recommendationElements.content.hidden = true;
  try {
    const recommendation = normalizeRecommendation(await api.requestRecommendation(activeSessionId), activeSessionId);
    renderRecommendation(recommendationElements, recommendation);
    proposalWorkflow.load(recommendation);
    recommendationMessage.dataset.state = recommendation.policyDecision.allowed ? "approved" : "rejected";
    recommendationMessage.textContent = recommendation.policyDecision.allowed
      ? "Recommendation received. Review the exact proposal before deciding."
      : "Recommendation received, but policy rejected the proposal.";
  } catch {
    recommendationMessage.dataset.state = "error";
    recommendationMessage.textContent = "RedPath could not load a valid recommendation. Review the evidence and try again.";
  } finally {
    recommendationPending = false;
    recommendationButton.disabled = !recommendationReady;
    recommendationButton.setAttribute("aria-busy", "false");
    recommendationButton.textContent = "Request recommendation";
  }
});

proposalElements.approve.addEventListener("click", () => proposalWorkflow.decide("approve"));
proposalElements.reject.addEventListener("click", () => proposalWorkflow.decide("reject"));

refreshHealth();
emergencyStopWorkflow.refresh();
