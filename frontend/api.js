const DEFAULT_TIMEOUT_MS = 5000;

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

  async createSession(session) {
    return this.request("/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(session) });
  }

  async importScan(sessionId, scan) {
    return this.request(`/sessions/${encodeURIComponent(sessionId)}/scan-import`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(scan) });
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
    id: typeof finding?.id === "string" ? finding.id : "unidentified-finding",
    state,
    protocol: ["tcp", "udp"].includes(finding?.protocol) ? finding.protocol : "unknown",
    port,
    service: typeof finding?.service_hint === "string" && finding.service_hint.length <= 80 ? finding.service_hint : "unknown service",
    source: typeof finding?.evidence_source === "string" && finding.evidence_source.length <= 100 ? finding.evidence_source : "unknown source",
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
