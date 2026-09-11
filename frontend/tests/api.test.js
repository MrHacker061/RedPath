import test from "node:test";
import assert from "node:assert/strict";
import { ApiError, RedPathApi, normalizeFinding, normalizeHealth } from "../api.js";

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

test("API client reads Worker 1's versioned health endpoint", async () => {
  let requestedUrl;
  const api = new RedPathApi({ fetchImpl: async (url) => {
    requestedUrl = url;
    return jsonResponse({ fastapi: "healthy" });
  }});
  assert.deepEqual(await api.getHealth(), { fastapi: "healthy" });
  assert.equal(requestedUrl, "/api/v1/health");
});

test("API client reports HTTP failures without exposing response bodies", async () => {
  const api = new RedPathApi({ fetchImpl: async () => jsonResponse({ secret: "do-not-show" }, 503) });
  await assert.rejects(api.getHealth(), (error) => {
    assert(error instanceof ApiError);
    assert.equal(error.status, 503);
    assert.doesNotMatch(error.message, /do-not-show/);
    return true;
  });
});

test("API client rejects non-JSON responses", async () => {
  const api = new RedPathApi({ fetchImpl: async () => new Response("debug output", { status: 200 }) });
  await assert.rejects(api.getHealth(), { code: "INVALID_RESPONSE" });
});

test("API client classifies malformed JSON as an invalid response", async () => {
  const api = new RedPathApi({ fetchImpl: async () => new Response("{broken", {
    status: 200,
    headers: { "content-type": "application/json" },
  }) });
  await assert.rejects(api.getHealth(), { code: "INVALID_RESPONSE" });
});

test("API client returns a clear timeout error", async () => {
  const api = new RedPathApi({ timeoutMs: 5, fetchImpl: (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
  }) });
  await assert.rejects(api.getHealth(), { code: "TIMEOUT" });
});

test("health normalization ignores arbitrary backend detail", () => {
  assert.deepEqual(normalizeHealth({ services: {
    fastapi: { status: "healthy", detail: "<script>untrusted</script>" },
    ollama: "offline",
    kali: "running",
  }}), {
    fastapi: { state: "healthy", detail: "Service is available." },
    ollama: { state: "offline", detail: "Service is currently offline." },
    kali: { state: "healthy", detail: "Service is available." },
  });
});

test("Worker 1 foundation health response maps API and leaves unreported services unknown", () => {
  const health = normalizeHealth({ status: "ok", service: "redpath-api", version: "0.1.0", database: "ok" });
  assert.equal(health.fastapi.state, "healthy");
  assert.equal(health.ollama.state, "unknown");
  assert.equal(health.kali.state, "unknown");
});

test("degraded Worker 1 health response reports an API problem", () => {
  const health = normalizeHealth({ status: "degraded", service: "redpath-api", version: "0.1.0", database: "unavailable" });
  assert.equal(health.fastapi.state, "error");
});

test("powered-off and not-created Kali states are safe on-demand states", () => {
  for (const status of ["poweroff", "not_created", "stopped"]) {
    const health = normalizeHealth({ services: { fastapi: "healthy", ollama: "healthy", kali: status } });
    assert.deepEqual(health.kali, {
      state: "standby",
      detail: "Available on demand for an approved action.",
    });
  }
});

test("session creation keeps lesson and target separate", async () => {
  const requests = [];
  const api = new RedPathApi({ fetchImpl: async (url, options) => { requests.push({ url, body: JSON.parse(options.body) }); return jsonResponse({ id: "session-1" }); } });
  await api.createSession({ authorization_confirmed: true, expires_at: "2030-01-01T00:00:00Z" });
  await api.addLessonSource("session-1", { url: "https://example.test/lesson" });
  await api.addTarget("session-1", { address: "192.168.56.20", authorization_source: "user_confirmation", expires_at: "2030-01-01T00:00:00Z" });
  assert.deepEqual(requests.map(({ url }) => url), ["/api/v1/sessions", "/api/v1/sessions/session-1/lesson-source", "/api/v1/sessions/session-1/target"]);
  assert.equal(requests[1].body.url, "https://example.test/lesson");
  assert.equal(requests[2].body.address, "192.168.56.20");
});

test("scan import encodes session identifier", async () => {
  let url;
  const api = new RedPathApi({ fetchImpl: async (value) => { url = value; return jsonResponse({ findings: [] }); } });
  await api.importScan("session /1", { filename: "scan.xml", xml_text: "<nmaprun/>" });
  assert.equal(url, "/api/v1/sessions/session%20%2F1/scan-import");
});

test("explanation request remains scoped to the session", async () => {
  let url;
  const api = new RedPathApi({ fetchImpl: async (value) => { url = value; return jsonResponse({ explanations: [], notes: [], missing_evidence: [], execution_authorized: false }); } });
  const response = await api.getExplanation("session /1");
  assert.equal(url, "/api/v1/sessions/session%20%2F1/explanation");
  assert.equal(response.execution_authorized, false);
});

test("recommendation request posts to the encoded session endpoint", async () => {
  let request;
  const api = new RedPathApi({ fetchImpl: async (url, options) => {
    request = { url, options };
    return jsonResponse({ proposal: {}, policy_decision: {} });
  } });
  await api.requestRecommendation("session /1");
  assert.equal(request.url, "/api/v1/sessions/session%20%2F1/recommendation");
  assert.equal(request.options.method, "POST");
  assert.equal(request.options.body, undefined);
});

test("proposal decisions post the exact encoded proposal path", async () => {
  const requests = [];
  const api = new RedPathApi({ fetchImpl: async (url, options) => {
    requests.push({ url, method: options.method });
    return jsonResponse({ proposal_id: "proposal /1", status: "approved", approval_id: "approval-1", expires_at: "2030-01-01T00:00:00Z" });
  } });
  await api.approveProposal("session /1", "proposal /1");
  await api.rejectProposal("session /1", "proposal /1");
  assert.deepEqual(requests, [
    { url: "/api/v1/sessions/session%20%2F1/proposals/proposal%20%2F1/approve", method: "POST" },
    { url: "/api/v1/sessions/session%20%2F1/proposals/proposal%20%2F1/reject", method: "POST" },
  ]);
});

test("emergency-stop client uses separate read, activate, and clear endpoints", async () => {
  const requests = [];
  const api = new RedPathApi({ fetchImpl: async (url, options) => {
    requests.push({ url, method: options.method || "GET" });
    return jsonResponse({ active: options.method === "POST" && !url.endsWith("/clear"), activated_at: null, cleared_at: null });
  } });
  await api.getEmergencyStop();
  await api.activateEmergencyStop();
  await api.clearEmergencyStop();
  assert.deepEqual(requests, [
    { url: "/api/v1/emergency-stop", method: "GET" },
    { url: "/api/v1/emergency-stop", method: "POST" },
    { url: "/api/v1/emergency-stop/clear", method: "POST" },
  ]);
});

test("audit history and learning report reads remain session scoped", async () => {
  const requests = [];
  const api = new RedPathApi({ fetchImpl: async (url, options) => {
    requests.push({ url, method: options.method || "GET" });
    return jsonResponse({});
  } });
  await api.getAuditHistory("session /1");
  await api.getLearningReport("session /1");
  assert.deepEqual(requests, [
    { url: "/api/v1/sessions/session%20%2F1/audit-history?limit=100", method: "GET" },
    { url: "/api/v1/sessions/session%20%2F1/report", method: "GET" },
  ]);
});

test("finding normalization keeps bounded evidence fields", () => {
  assert.deepEqual(normalizeFinding({ id: "finding-1", state: "observed", protocol: "tcp", port: 80, service_hint: "http", evidence_source: "scan-1" }), {
    id: "finding-1", state: "observed", protocol: "tcp", port: 80, service: "http", source: "scan-1",
  });
});
