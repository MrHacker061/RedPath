import test from "node:test";
import assert from "node:assert/strict";
import { ApiError, RedPathApi, normalizeHealth } from "../api.js";

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

test("API client reads the shared health endpoint", async () => {
  let requestedUrl;
  const api = new RedPathApi({ baseUrl: "/api/", fetchImpl: async (url) => {
    requestedUrl = url;
    return jsonResponse({ fastapi: "healthy" });
  }});
  assert.deepEqual(await api.getHealth(), { fastapi: "healthy" });
  assert.equal(requestedUrl, "/api/health");
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

test("API client returns a clear timeout error", async () => {
  const api = new RedPathApi({ timeoutMs: 5, fetchImpl: (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
  }) });
  await assert.rejects(api.getHealth(), { code: "TIMEOUT" });
});

test("health normalization supports detailed and compact service states", () => {
  assert.deepEqual(normalizeHealth({ services: {
    fastapi: { status: "healthy", detail: "API ready" },
    ollama: "offline",
    kali: "running",
  }}), {
    fastapi: { state: "healthy", detail: "API ready" },
    ollama: { state: "offline", detail: "Service is not running." },
    kali: { state: "healthy", detail: "Service is available." },
  });
});

test("missing health values fail closed as unavailable", () => {
  const health = normalizeHealth({ fastapi: "healthy" });
  assert.equal(health.fastapi.state, "healthy");
  assert.equal(health.ollama.state, "error");
  assert.equal(health.kali.state, "error");
});
