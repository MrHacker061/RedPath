import { RedPathApi, normalizeFinding, normalizeHealth } from "./api.js";

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
let activeSessionId = null;

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

refreshHealth();
