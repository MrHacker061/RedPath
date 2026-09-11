const SAFE_AUDIT_KEYS = new Set([
  "approval_id", "authorization_confirmed", "code", "content_hash", "expires_at",
  "finding_count", "policy_code", "policy_decision_id", "proposal_id", "report_id",
  "source_ids", "status", "target_id", "used_fallback",
]);
const SESSION_STATES = new Set(["draft", "authorized", "ready", "running", "completed", "expired", "blocked"]);
const ACTIONS = new Set(["inspect_http_headers", "inspect_tls_certificate", "check_tcp_connection"]);

function unavailable() {
  throw new TypeError("Oversight data is unavailable because its response was invalid.");
}

function text(value, maxLength = 160) {
  if (typeof value !== "string" || !value.trim() || value.length > maxLength) unavailable();
  return value;
}

function timestamp(value, nullable = false) {
  if (nullable && value === null) return null;
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) unavailable();
  return new Date(value).toISOString();
}

function count(value) {
  if (!Number.isInteger(value) || value < 0 || value > 1_000_000_000) unavailable();
  return value;
}

export function normalizeEmergencyStop(payload) {
  if (!payload || typeof payload.active !== "boolean") unavailable();
  return {
    active: payload.active,
    activatedAt: timestamp(payload.activated_at, true),
    clearedAt: timestamp(payload.cleared_at, true),
  };
}

function auditValue(value) {
  if (value === null || typeof value === "boolean") return value;
  if (Number.isInteger(value)) return Math.max(-1_000_000_000, Math.min(value, 1_000_000_000));
  if (typeof value === "string") return value.slice(0, 160);
  if (Array.isArray(value)) return value.slice(0, 20).map((item) => String(item).slice(0, 160));
  return null;
}

export function normalizeAuditHistory(payload, sessionId) {
  if (!payload || !Array.isArray(payload.events) || payload.events.length > 100 || typeof payload.truncated !== "boolean") unavailable();
  return {
    events: payload.events.map((event) => {
      if (!event || (event.session_id !== null && event.session_id !== sessionId) || !event.details || typeof event.details !== "object" || Array.isArray(event.details)) unavailable();
      const details = {};
      for (const [key, value] of Object.entries(event.details)) {
        if (SAFE_AUDIT_KEYS.has(key)) details[key] = auditValue(value);
      }
      return {
        id: text(event.id, 128),
        sessionId: event.session_id,
        eventType: text(event.event_type, 100),
        details,
        createdAt: timestamp(event.created_at),
      };
    }),
    truncated: payload.truncated,
  };
}

function reportTarget(value) {
  if (value === null) return null;
  if (!value || typeof value.locked !== "boolean") unavailable();
  return { targetId: text(value.target_id, 128), expiresAt: timestamp(value.expires_at), locked: value.locked };
}

export function normalizeLearningReport(payload, sessionId) {
  if (!payload || payload.session_id !== sessionId || !SESSION_STATES.has(payload.session_state) || payload.execution_authorized !== false) unavailable();
  if (!payload.evidence || !Array.isArray(payload.proposals) || !Array.isArray(payload.approvals) || payload.proposals.length > 100 || payload.approvals.length > 100) unavailable();
  if (typeof payload.proposals_truncated !== "boolean" || typeof payload.approvals_truncated !== "boolean") unavailable();
  const evidence = {
    total: count(payload.evidence.total),
    observed: count(payload.evidence.observed),
    inferred: count(payload.evidence.inferred),
    verified: count(payload.evidence.verified),
  };
  const proposals = payload.proposals.map((proposal) => {
    if (!proposal || !ACTIONS.has(proposal.action_name) || typeof proposal.policy_allowed !== "boolean") unavailable();
    return {
      proposalId: text(proposal.proposal_id, 128),
      actionName: proposal.action_name,
      policyAllowed: proposal.policy_allowed,
      policyCode: text(proposal.policy_code, 80),
    };
  });
  const approvals = payload.approvals.map((approval) => {
    if (!approval || !["approved", "rejected"].includes(approval.status) || typeof approval.used !== "boolean") unavailable();
    return {
      proposalId: text(approval.proposal_id, 128),
      status: approval.status,
      expiresAt: timestamp(approval.expires_at, true),
      used: approval.used,
    };
  });
  return {
    reportId: text(payload.report_id, 128),
    sessionId,
    sessionState: payload.session_state,
    generatedAt: timestamp(payload.generated_at),
    target: reportTarget(payload.target),
    evidence,
    proposals,
    approvals,
    proposalsTruncated: payload.proposals_truncated,
    approvalsTruncated: payload.approvals_truncated,
    auditEventCount: count(payload.audit_event_count),
    executionAuthorized: false,
  };
}

export function renderEmergencyStop(elements, state) {
  elements.message.dataset.state = state.status === "clear" ? "healthy"
    : state.status === "error" ? "error"
    : "pending";
  elements.message.textContent = state.message;
  elements.activate.disabled = state.busy || state.active;
  elements.clear.disabled = state.busy || !state.active || state.status !== "active";
  elements.refresh.disabled = state.busy;
}

function listItem(documentRef, value) {
  const item = documentRef.createElement("li");
  item.textContent = value;
  return item;
}

function replaceList(element, values, emptyText, documentRef) {
  const items = values.length ? values : [emptyText];
  element.replaceChildren(...items.map((value) => listItem(documentRef, value)));
}

export function renderSessionOversight(elements, report, history, documentRef = document) {
  const evidence = report.evidence;
  elements.overview.textContent = `Session ${report.sessionState}. Evidence: ${evidence.total} total, ${evidence.observed} observed, ${evidence.inferred} inferred, ${evidence.verified} verified. Audit events: ${report.auditEventCount}. Execution authorized: No.`;
  replaceList(elements.proposals, report.proposals.map((proposal) =>
    `${proposal.actionName} — ${proposal.policyAllowed ? "allowed" : "blocked"} by policy (${proposal.policyCode}); proposal ${proposal.proposalId}.`
  ), "No proposals recorded.", documentRef);
  replaceList(elements.approvals, report.approvals.map((approval) =>
    `${approval.status} — ${approval.used ? "used" : "unused"}; proposal ${approval.proposalId}${approval.expiresAt ? `; expires ${approval.expiresAt}` : ""}.`
  ), "No approval decisions recorded.", documentRef);
  replaceList(elements.events, history.events.map((event) => {
    const details = Object.entries(event.details)
      .map(([key, value]) => `${key.replaceAll("_", " ")}: ${Array.isArray(value) ? value.join(", ") : String(value)}`)
      .join("; ");
    return `${event.eventType} at ${event.createdAt}${details ? ` — ${details}` : ""}.`;
  }), "No audit events recorded.", documentRef);
  elements.summary.hidden = false;
  elements.audit.hidden = false;
}

export class EmergencyStopWorkflow {
  constructor({ api, onChange = () => {} }) {
    this.api = api;
    this.onChange = onChange;
    this.state = { active: true, busy: false, status: "checking", message: "Checking emergency-stop status. Approval stays disabled until it is confirmed clear." };
  }

  async refresh() {
    if (this.state.busy) return false;
    this.update({ active: true, busy: true, status: "checking", message: "Checking emergency-stop status. Approval stays disabled until it is confirmed clear." });
    try {
      const stop = normalizeEmergencyStop(await this.api.getEmergencyStop());
      this.update({ ...stop, busy: false, status: stop.active ? "active" : "clear", message: stop.active ? "Emergency stop is active. New approvals are blocked." : "Emergency stop is clear. Exact proposals may be approved." });
    } catch {
      this.update({ active: true, busy: false, status: "error", message: "Emergency-stop status is unavailable. Approval remains disabled for safety." });
    }
    return true;
  }

  async activate() {
    if (this.state.busy || this.state.active) return false;
    this.update({ active: true, busy: true, status: "activating", message: "Activating emergency stop. New approvals are disabled locally." });
    try {
      const stop = normalizeEmergencyStop(await this.api.activateEmergencyStop());
      if (!stop.active) unavailable();
      this.update({ ...stop, busy: false, status: "active", message: "Emergency stop is active. New approvals are blocked." });
    } catch {
      this.update({ active: true, busy: false, status: "error", message: "Activation could not be confirmed. Approval remains disabled for safety." });
    }
    return true;
  }

  async clear() {
    if (this.state.busy || !this.state.active || this.state.status !== "active") return false;
    this.update({ ...this.state, busy: true, status: "clearing", message: "Clearing emergency stop. Approval remains disabled until the backend confirms it." });
    try {
      const stop = normalizeEmergencyStop(await this.api.clearEmergencyStop());
      if (stop.active) unavailable();
      this.update({ ...stop, busy: false, status: "clear", message: "Emergency stop is clear. Exact proposals may be approved." });
    } catch {
      this.update({ active: true, busy: false, status: "error", message: "Clear could not be confirmed. Approval remains disabled for safety." });
    }
    return true;
  }

  update(next) {
    this.state = next;
    this.onChange(this.state);
  }
}
