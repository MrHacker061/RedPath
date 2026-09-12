const COMPONENTS = ["ollama", "model", "wsl", "kali"];
const STATUSES = new Set(["ready", "needs_attention", "in_progress", "failed"]);

function unavailable() { throw new TypeError("Setup data is unavailable because its response was invalid."); }
function text(value, maximum = 240) {
  if (typeof value !== "string" || !value.trim() || value.length > maximum) unavailable();
  return value;
}
function componentStatus(value) {
  if (!value || !STATUSES.has(value.status)) unavailable();
  return { status: value.status, code: text(value.code, 80), detail: text(value.detail) };
}
function fixedComponent(component) {
  if (!COMPONENTS.includes(component)) unavailable();
  return component;
}

export function normalizeSetup(payload) {
  if (!payload || !payload.components || typeof payload.components !== "object" || Array.isArray(payload.components)) unavailable();
  const names = Object.keys(payload.components);
  if (names.length !== COMPONENTS.length || names.some((name) => !COMPONENTS.includes(name))) unavailable();
  return { components: Object.fromEntries(COMPONENTS.map((name) => [name, componentStatus(payload.components[name])])) };
}

export function normalizeDiagnostics(payload) {
  if (!payload || !Array.isArray(payload.codes) || !payload.components || typeof payload.components !== "object") unavailable();
  const components = normalizeSetup({ components: Object.fromEntries(COMPONENTS.map((name) => [name, {
    status: payload.components[name]?.status, code: payload.components[name]?.code, detail: payload.components[name]?.code,
  }])) }).components;
  return { version: text(payload.version, 64), dataPath: text(payload.data_path, 400), codes: payload.codes.map((code) => text(code, 80)).slice(0, COMPONENTS.length), components };
}

function initialComponents() {
  return Object.fromEntries(COMPONENTS.map((name) => [name, { status: "needs_attention", code: "CHECKING", detail: "Checking setup status." }]));
}

export class SetupController {
  constructor({ api, onChange = () => {} }) {
    this.api = api;
    this.onChange = onChange;
    this.state = { status: "checking", busy: null, components: initialComponents(), message: "Checking guided setup." };
  }
  async refresh() {
    if (this.state.busy) return false;
    this.update({ ...this.state, status: "checking", message: "Checking guided setup." });
    try {
      const setup = normalizeSetup(await this.api.getSetup());
      this.update({ status: "ready", busy: null, components: setup.components, message: "Setup status refreshed." });
    } catch {
      this.update({ ...this.state, status: "error", busy: null, message: "Setup status is unavailable. Retry when the local service is ready." });
    }
    return true;
  }
  async repair(component) {
    fixedComponent(component);
    if (this.state.busy) return false;
    this.update({ ...this.state, status: "repairing", busy: component, message: `Repairing ${component}.` });
    try {
      const stage = componentStatus(await this.api.repairSetup(component));
      this.update({ ...this.state, status: "ready", busy: null, components: { ...this.state.components, [component]: stage }, message: `${component} repair finished.` });
      return true;
    } catch {
      this.update({ ...this.state, status: "error", busy: null, message: `${component} repair could not be confirmed.` });
      return false;
    }
  }
  async cancel(component) {
    fixedComponent(component);
    const activeComponent = this.state.busy || component;
    const selectionMismatch = Boolean(this.state.busy && this.state.busy !== component);
    try {
      const stage = componentStatus(await this.api.cancelSetup(activeComponent));
      this.update({ ...this.state, status: "ready", busy: null, components: { ...this.state.components, [activeComponent]: stage }, message: selectionMismatch ? `${component} was not active. Cancellation request sent to ${activeComponent}.` : `${activeComponent} cancellation request sent.` });
      return true;
    } catch {
      this.update({ ...this.state, status: "error", busy: null, message: `${activeComponent} cancellation could not be confirmed.` });
      return false;
    }
  }
  update(state) { this.state = state; this.onChange(state); }
}
