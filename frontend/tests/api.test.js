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
  let request;
  const api = new RedPathApi({ fetchImpl: async (url, options) => { request = { url, body: JSON.parse(options.body) }; return jsonResponse({ id: "session-1" }); } });
  await api.createSession({ lesson_url: "https://example.test/lesson", target: "192.168.56.20" });
  assert.equal(request.url, "/api/v1/sessions");
  assert.equal(request.body.lesson_url, "https://example.test/lesson");
  assert.equal(request.body.target, "192.168.56.20");
});

test("scan import encodes session identifier", async () => {
  let url;
  const api = new RedPathApi({ fetchImpl: async (value) => { url = value; return jsonResponse({ findings: [] }); } });
  await api.importScan("session /1", { filename: "scan.xml", xml_text: "<nmaprun/>" });
  assert.equal(url, "/api/v1/sessions/session%20%2F1/scan-import");
});

test("finding normalization keeps bounded evidence fields", () => {
  assert.deepEqual(normalizeFinding({ id: "finding-1", state: "observed", protocol: "tcp", port: 80, service_hint: "http", evidence_source: "scan-1" }), {
    id: "finding-1", state: "observed", protocol: "tcp", port: 80, service: "http", source: "scan-1",
  });
});
