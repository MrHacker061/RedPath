import test from "node:test";
import assert from "node:assert/strict";
import { SetupController, normalizeDiagnostics, normalizeSetup } from "../setup.js";

const setup = {
  components: {
    ollama: { status: "ready", code: "OLLAMA_READY", detail: "Ready." },
    model: { status: "needs_attention", code: "MODEL_MISSING", detail: "Download required." },
    wsl: { status: "ready", code: "WSL_READY", detail: "Ready." },
    kali: { status: "failed", code: "KALI_NOT_INSTALLED", detail: "Install required." },
  },
};

test("setup exposes only fixed repair components", async () => {
  const repairs = [];
  const controller = new SetupController({ api: {
    getSetup: async () => setup,
    repairSetup: async (component) => { repairs.push(component); return setup.components[component]; },
    cancelSetup: async () => ({ status: "in_progress", code: "CANCEL_REQUESTED", detail: "Cancellation was requested." }),
  } });
  await assert.rejects(controller.repair("shell"), /unavailable/i);
  await controller.repair("kali");
  assert.deepEqual(repairs, ["kali"]);
});

test("setup normalization rejects missing components and never keeps backend markup", () => {
  assert.throws(() => normalizeSetup({ components: { ...setup.components, shell: {} } }), /unavailable/i);
  const normalized = normalizeSetup({
    components: { ...setup.components, ollama: { status: "ready", code: "OLLAMA_READY", detail: "<img src=x onerror=alert(1)>" } },
  });
  assert.equal(normalized.components.ollama.detail, "<img src=x onerror=alert(1)>");
  assert.throws(() => normalizeDiagnostics({ version: "1", components: {}, data_path: "x", codes: [] }), /unavailable/i);
});

test("setup refresh fails closed and cancellation stays component scoped", async () => {
  const updates = [];
  const controller = new SetupController({
    api: {
      getSetup: async () => { throw new Error("secret traceback"); },
      cancelSetup: async (component) => ({ status: "in_progress", code: "CANCEL_REQUESTED", detail: `Stopping ${component}.` }),
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
        return { status: "in_progress", code: "CANCEL_REQUESTED", detail: `Stopping ${component}.` };
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
