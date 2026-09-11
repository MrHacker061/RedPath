const DEFAULT_TIMEOUT_MS = 5000;
const SETUP_COMPONENTS = new Set(["ollama", "model", "wsl", "kali"]);

function setupComponent(component) {
  if (!SETUP_COMPONENTS.has(component)) throw new TypeError("Setup component is unavailable.");
  return component;
}

export class ApiError extends Error {
  constructor(message, { status = null, code = "REQUEST_FAILED" } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export class RedPathApi {
  constructor({ baseUrl = "/api/v1", fetchImpl = globalThis.fetch, timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
    if (typeof fetchImpl !== "function") throw new TypeError("A fetch implementation is required.");
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.fetchImpl = fetchImpl;
    this.timeoutMs = timeoutMs;
  }

  async getHealth() {
    return this.request("/health");
  }

  getSetup() { return this.request("/setup"); }
  repairSetup(component) {
    return this.request(`/setup/${encodeURIComponent(setupComponent(component))}/repair`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ consent: true }) });
  }
  cancelSetup(component) { return this.request(`/setup/${encodeURIComponent(setupComponent(component))}/cancel`, { method: "POST" }); }
  getDiagnostics() { return this.request("/diagnostics"); }

  async createSession(session) {
    return this.request("/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(session) });
  }

  async addLessonSource(sessionId, lesson) {
    return this.request(`/sessions/${encodeURIComponent(sessionId)}/lesson-source`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(lesson) });
  }

  async addTarget(sessionId, target) {
    return this.request(`/sessions/${encodeURIComponent(sessionId)}/target`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(target) });
  }

  async importScan(sessionId, scan) {
    return this.request(`/sessions/${encodeURIComponent(sessionId)}/scan-import`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(scan) });
  }

  async getExplanation(sessionId) {
    return this.request(`/sessions/${encodeURIComponent(sessionId)}/explanation`);
  }

  async requestRecommendation(sessionId) {
    return this.request(`/sessions/${encodeURIComponent(sessionId)}/recommendation`, { method: "POST" });
  }

  async approveProposal(sessionId, proposalId) {
    return this.request(`/sessions/${encodeURIComponent(sessionId)}/proposals/${encodeURIComponent(proposalId)}/approve`, { method: "POST" });
  }

  async rejectProposal(sessionId, proposalId) {
    return this.request(`/sessions/${encodeURIComponent(sessionId)}/proposals/${encodeURIComponent(proposalId)}/reject`, { method: "POST" });
  }

  runProposal(sessionId, proposalId) {
    return this.request(`/sessions/${encodeURIComponent(sessionId)}/proposals/${encodeURIComponent(proposalId)}/run`, { method: "POST" });
  }

  async getEmergencyStop() {
    return this.request("/emergency-stop");
  }

  async activateEmergencyStop() {
    return this.request("/emergency-stop", { method: "POST" });
  }

  async clearEmergencyStop() {
    return this.request("/emergency-stop/clear", { method: "POST" });
  }

  async getAuditHistory(sessionId) {
    return this.request(`/sessions/${encodeURIComponent(sessionId)}/audit-history?limit=100`);
  }

  async getLearningReport(sessionId) {
    return this.request(`/sessions/${encodeURIComponent(sessionId)}/report`);
  }

  async request(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        ...options,
        headers: { Accept: "application/json", ...options.headers },
        signal: controller.signal,
        credentials: "same-origin",
      });
      if (!response.ok) {
        throw new ApiError(`RedPath API returned ${response.status}.`, { status: response.status });
      }
      const contentType = response.headers.get("content-type") || "";
      if (!contentType.includes("application/json")) {
        throw new ApiError("RedPath API returned an unexpected response.", { code: "INVALID_RESPONSE" });
      }
      try {
        return await response.json();
      } catch {
        throw new ApiError("RedPath API returned invalid JSON.", { code: "INVALID_RESPONSE" });
      }
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (error?.name === "AbortError") {
        throw new ApiError("RedPath API did not respond in time.", { code: "TIMEOUT" });
      }
      throw new ApiError("RedPath API is unavailable.", { code: "NETWORK_ERROR" });
    } finally {
      clearTimeout(timeout);
    }
  }
}

export function normalizeFinding(finding) {
  const state = ["observed", "inferred", "verified"].includes(finding?.state) ? finding.state : "unknown";
  const port = Number.isInteger(finding?.port) && finding.port >= 1 && finding.port <= 65535 ? finding.port : null;
  return {
    id: typeof finding?.id === "string" && finding.id.length <= 128 ? finding.id : "unidentified-finding",
    state,
    protocol: ["tcp", "udp"].includes(finding?.protocol) ? finding.protocol : "unknown",
    port,
    service: typeof finding?.service_hint === "string" && finding.service_hint.length <= 80 ? finding.service_hint : "unknown service",
    source: typeof finding?.evidence_source === "string" && finding.evidence_source.length <= 100 ? finding.evidence_source : "unknown source",
  };
}

function boundedResponseText(value, maximum = 1000) {
  if (typeof value !== "string" || !value.trim() || value.length > maximum) throw new TypeError("Learning data is unavailable because its response was invalid.");
  return value;
}

export function normalizeExplanation(payload) {
  if (!payload || payload.execution_authorized !== false || !Array.isArray(payload.explanations) || !Array.isArray(payload.missing_evidence) || payload.explanations.length > 100 || payload.missing_evidence.length > 100) {
    throw new TypeError("Learning data is unavailable because its response was invalid.");
  }
  return {
    explanations: payload.explanations.map((item) => ({
      summary: boundedResponseText(item?.summary),
      whatItMeans: boundedResponseText(item?.what_it_means),
      whatItDoesNotProve: boundedResponseText(item?.what_it_does_not_prove),
    })),
    missingEvidence: payload.missing_evidence.map((item) => boundedResponseText(item, 240)),
  };
}

export function normalizeHealth(payload) {
  const isObject = payload !== null && typeof payload === "object" && !Array.isArray(payload);
  const isAggregate = isObject && payload.services !== null && typeof payload.services === "object" && !Array.isArray(payload.services);
  const source = isAggregate ? payload.services : {};

  // Worker 1's Milestone 1 response reports the API and database only. Keep
  // this adapter until the backend publishes aggregate service health.
  if (!isAggregate && payload?.service === "redpath-api") {
    source.fastapi = payload.status === "ok" && payload.database === "ok" ? "healthy" : "degraded";
  }

  return ["fastapi", "ollama", "kali"].reduce((result, name) => {
    const value = source[name];
    const rawState = typeof value === "string" ? value : value?.status;
    const state = ["healthy", "online", "ready", "running", "ok"].includes(rawState) ? "healthy"
      : name === "kali" && ["poweroff", "not_created", "stopped"].includes(rawState) ? "standby"
      : ["stopped", "offline", "unavailable"].includes(rawState) ? "offline"
      : rawState === undefined ? "unknown"
      : "error";

    // Never render backend-provided detail. Tool output and error details are
    // untrusted; these bounded messages are owned by the frontend.
    const detail = state === "healthy" ? "Service is available."
      : state === "standby" ? "Available on demand for an approved action."
      : state === "offline" ? "Service is currently offline."
      : state === "unknown" ? "Status is not reported by the current API."
      : "Service reported a problem.";
    result[name] = { state, detail };
    return result;
  }, {});
}
