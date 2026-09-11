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
  constructor({ baseUrl = "/api", fetchImpl = globalThis.fetch, timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
    if (typeof fetchImpl !== "function") throw new TypeError("A fetch implementation is required.");
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.fetchImpl = fetchImpl;
    this.timeoutMs = timeoutMs;
  }

  async getHealth() {
    return this.request("/health");
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
      return await response.json();
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

export function normalizeHealth(payload) {
  const source = payload?.services ?? payload ?? {};
  return ["fastapi", "ollama", "kali"].reduce((result, name) => {
    const value = source[name];
    const rawState = typeof value === "string" ? value : value?.status;
    const state = ["healthy", "online", "ready", "running"].includes(rawState) ? "healthy"
      : ["stopped", "offline", "unavailable"].includes(rawState) ? "offline"
      : "error";
    const detail = typeof value === "object" && typeof value?.detail === "string"
      ? value.detail
      : state === "healthy" ? "Service is available."
      : state === "offline" ? "Service is not running."
      : "Health information is unavailable.";
    result[name] = { state, detail };
    return result;
  }, {});
}
