import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";
import * as setupModule from "../setup.js";
const { SetupController, normalizeDiagnostics, normalizeSetup } = setupModule;

const setup = {
  components: {
    ollama: { status: "ready", code: "OLLAMA_READY", detail: "Ready.", version: "0.34.0", download_size_bytes: 1_574_272_976 },
    model: { status: "needs_attention", code: "MODEL_MISSING", detail: "Download required.", version: "qwen2.5:7b-instruct-q4_K_M", download_size_bytes: 4_683_087_332 },
    wsl: { status: "ready", code: "WSL_READY", detail: "Ready.", version: null, download_size_bytes: null },
    kali: { status: "failed", code: "KALI_NOT_INSTALLED", detail: "Install required.", version: "2026.2", download_size_bytes: 247_857_686 },
  },
};

test("setup normalizes exact pinned download metadata and nulls", () => {
  const normalized = normalizeSetup(setup);
  assert.deepEqual(Object.fromEntries(Object.entries(normalized.components).map(([name, stage]) => [name, [stage.version, stage.downloadSizeBytes]])), {
    ollama: ["0.34.0", 1_574_272_976], model: ["qwen2.5:7b-instruct-q4_K_M", 4_683_087_332],
    wsl: [null, null], kali: ["2026.2", 247_857_686],
  });
});

test("setup rejects invalid versions and download sizes", () => {
  for (const version of [undefined, "", " ", "a".repeat(81), 1, false, {}]) {
    assert.throws(() => normalizeSetup({ components: { ...setup.components, ollama: { ...setup.components.ollama, version } } }), /unavailable/i);
  }
  for (const download_size_bytes of [undefined, 0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1, Infinity, NaN, "1574272976", true, {}]) {
    assert.throws(() => normalizeSetup({ components: { ...setup.components, ollama: { ...setup.components.ollama, download_size_bytes } } }), /unavailable/i);
  }
  const boundary = normalizeSetup({ components: { ...setup.components, ollama: { ...setup.components.ollama, version: "a".repeat(80), download_size_bytes: Number.MAX_SAFE_INTEGER } } });
  assert.equal(boundary.components.ollama.downloadSizeBytes, Number.MAX_SAFE_INTEGER);
});

test("download sizes use GiB at the boundary and MiB below it", () => {
  assert.equal(typeof setupModule.formatDownloadSize, "function");
  assert.equal(setupModule.formatDownloadSize(1_574_272_976), "1.47 GiB");
  assert.equal(setupModule.formatDownloadSize(4_683_087_332), "4.36 GiB");
  assert.equal(setupModule.formatDownloadSize(247_857_686), "236.38 MiB");
  assert.equal(setupModule.formatDownloadSize(1024 ** 3), "1.00 GiB");
  assert.equal(setupModule.formatDownloadSize(1024 ** 2), "1.00 MiB");
});

test("setup cards disclose metadata as visible literal text before repair", async () => {
  const html = await readFile(new URL("../index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../app.js", import.meta.url), "utf8");
  assert.match(html, /id="setup-components"[^>]*aria-live="polite"/);
  assert(html.indexOf('id="setup-components"') < html.indexOf('id="setup-repair"'));
  class FakeNode {
    constructor(tagName) { this.tagName = tagName; this.children = []; this.dataset = {}; this.hidden = false; this.textContent = ""; }
    set innerHTML(_value) { assert.fail("Setup metadata must render with literal text."); }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
  }
  const elements = Object.fromEntries(["message", "components", "refresh", "component", "repair", "cancel"].map((name) => [name, new FakeNode("div")]));
  const render = runInNewContext(app.slice(app.indexOf("function renderSetup(state)"), app.indexOf("function renderResults(result)")) + "\nrenderSetup", {
    setupElements: elements, document: { createElement: (tag) => new FakeNode(tag) }, formatDownloadSize: setupModule.formatDownloadSize,
  });
  const components = normalizeSetup(setup).components;
  components.ollama.version = "<img src=x onerror=alert(1)>";
  render({ status: "ready", busy: null, message: "Ready.", components });
  const metadata = elements.components.children[0].children.find((node) => node.textContent === "<img src=x onerror=alert(1)> · 1.47 GiB");
  assert(metadata, "Ollama card must expose its literal version and size.");
  assert.equal(metadata.tagName, "p");
  assert.equal(metadata.hidden, false);
  assert.equal(metadata.children.length, 0);
  assert.equal(elements.components.children[2].children.some((node) => /null|undefined/.test(node.textContent)), false);
  assert.equal(elements.repair.disabled, false);
  for (const status of ["checking", "error"]) {
    render({ status, busy: null, message: "Setup unavailable.", components });
    assert.equal(elements.repair.disabled, true, "Consent must wait for a successful setup response.");
  }
  render({ status: "ready", busy: null, message: "Cancellation requested.", components: { ...components, kali: { ...components.kali, code: "CHECKING", version: null, downloadSizeBytes: null } } });
  assert.equal(elements.repair.disabled, true, "An early cancellation response must not enable repair before setup loads.");
});

test("setup exposes only fixed repair components", async () => {
  const repairs = [];
  const controller = new SetupController({ api: {
    getSetup: async () => setup,
    repairSetup: async (component) => { repairs.push(component); return setup.components[component]; },
    cancelSetup: async () => ({ status: "in_progress", code: "CANCEL_REQUESTED", detail: "Cancellation was requested.", version: null, download_size_bytes: null }),
  } });
  await assert.rejects(controller.repair("shell"), /unavailable/i);
  await controller.repair("kali");
  assert.deepEqual(repairs, ["kali"]);
});

test("setup normalization rejects missing components and never keeps backend markup", () => {
  assert.throws(() => normalizeSetup({ components: { ...setup.components, shell: {} } }), /unavailable/i);
  const normalized = normalizeSetup({
    components: { ...setup.components, ollama: { ...setup.components.ollama, detail: "<img src=x onerror=alert(1)>" } },
  });
  assert.equal(normalized.components.ollama.detail, "<img src=x onerror=alert(1)>");
  assert.throws(() => normalizeDiagnostics({ version: "1", components: {}, data_path: "x", codes: [] }), /unavailable/i);
});

test("setup refresh fails closed and cancellation stays component scoped", async () => {
  const updates = [];
  const controller = new SetupController({
    api: {
      getSetup: async () => { throw new Error("secret traceback"); },
      cancelSetup: async (component) => ({ status: "in_progress", code: "CANCEL_REQUESTED", detail: `Stopping ${component}.`, version: null, download_size_bytes: null }),
    },
    onChange: (state) => updates.push(state),
  });
  await controller.refresh();
  assert.equal(controller.state.status, "error");
  assert.doesNotMatch(controller.state.message, /secret|traceback/i);
  await assert.rejects(controller.cancel("terminal"), /unavailable/i);
  assert.equal(await controller.cancel("model"), true);
  assert.equal(controller.state.components.model.code, "CANCEL_REQUESTED");
  assert(updates.length > 0);
});

test("setup cancellation follows the active repair when selection changes", async () => {
  let finishRepair;
  const cancellations = [];
  const controller = new SetupController({
    api: {
      repairSetup: async () => new Promise((resolve) => { finishRepair = resolve; }),
      cancelSetup: async (component) => {
        cancellations.push(component);
        return { status: "in_progress", code: "CANCEL_REQUESTED", detail: `Stopping ${component}.`, version: null, download_size_bytes: null };
      },
    },
  });
  const repair = controller.repair("kali");
  assert.equal(controller.state.busy, "kali");
  assert.equal(await controller.cancel("model"), true);
  assert.deepEqual(cancellations, ["kali"]);
  assert.match(controller.state.message, /model.*kali/i);
  finishRepair(setup.components.kali);
  await repair;
});
