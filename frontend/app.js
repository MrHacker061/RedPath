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
    const session = await api.createSession({
      lesson_url: data.get("lesson_url"), target: data.get("target"), objective: data.get("objective"),
      expires_in_minutes: Number(data.get("expires_in_minutes")), authorization_confirmed: data.get("authorization_confirmed") === "on",
    });
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
  } catch (error) { evidenceMessage.textContent = error.message; }
  finally { submit.disabled = false; }
});

refreshHealth();
