import { RedPathApi, normalizeHealth } from "./api.js";

const api = new RedPathApi();
const refreshButton = document.querySelector("#refresh-health");
const message = document.querySelector("#health-message");

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
refreshHealth();
