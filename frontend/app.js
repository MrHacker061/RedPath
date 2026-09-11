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
  badge.textContent = health.state === "healthy" ? "Available" : health.state === "offline" ? "Offline" : "Problem";
  card.querySelector("[data-detail]").textContent = health.detail;
}

async function refreshHealth() {
  setLoading(true);
  message.dataset.state = "";
  message.textContent = "Checking RedPath services…";
  try {
    const health = normalizeHealth(await api.getHealth());
    Object.entries(health).forEach(([name, value]) => renderService(name, value));
    const allHealthy = Object.values(health).every(({ state }) => state === "healthy");
    message.dataset.state = allHealthy ? "healthy" : "error";
    message.textContent = allHealthy
      ? "All RedPath services are available."
      : "Some services need attention. You can still review available learning material.";
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
