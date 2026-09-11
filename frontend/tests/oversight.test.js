import test from "node:test";
import assert from "node:assert/strict";

const oversight = await import("../oversight.js").catch(() => ({}));

const stopClear = { active: false, activated_at: null, cleared_at: "2030-01-01T00:00:00Z" };
const stopActive = { active: true, activated_at: "2030-01-01T00:01:00Z", cleared_at: null };

class FakeNode {
  constructor() {
    this.children = [];
    this.dataset = {};
    this.disabled = false;
    this.hidden = true;
    this.textContent = "";
  }

  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
}

const fakeDocument = { createElement: () => new FakeNode() };

test("emergency-stop workflow defaults safe when status is unknown", async () => {
  assert.equal(typeof oversight.EmergencyStopWorkflow, "function");
  const controller = new oversight.EmergencyStopWorkflow({
    api: { getEmergencyStop: async () => { throw new Error("secret backend traceback"); } },
  });
  assert.equal(controller.state.active, true);
  await controller.refresh();
  assert.equal(controller.state.active, true);
  assert.equal(controller.state.status, "error");
  assert.doesNotMatch(controller.state.message, /secret|traceback/i);
});

test("activation locks locally before the backend responds", async () => {
  let resolveActivation;
  const api = {
    getEmergencyStop: async () => stopClear,
    activateEmergencyStop: async () => new Promise((resolve) => { resolveActivation = resolve; }),
  };
  const controller = new oversight.EmergencyStopWorkflow({ api });
  await controller.refresh();
  assert.equal(controller.state.active, false);
  const pending = controller.activate();
  assert.equal(controller.state.active, true);
  assert.equal(controller.state.status, "activating");
  resolveActivation(stopActive);
  assert.equal(await pending, true);
  assert.equal(controller.state.status, "active");
});

test("clearing emergency stop requires a separate explicit call", async () => {
  let clears = 0;
  const api = {
    getEmergencyStop: async () => stopActive,
    clearEmergencyStop: async () => { clears += 1; return stopClear; },
  };
  const controller = new oversight.EmergencyStopWorkflow({ api });
  await controller.refresh();
  assert.equal(clears, 0);
  assert.equal(controller.state.active, true);
  assert.equal(await controller.clear(), true);
  assert.equal(clears, 1);
  assert.equal(controller.state.active, false);
  assert.equal(controller.state.status, "clear");
});

test("audit and report normalization omit raw and unknown backend fields", () => {
  assert.equal(typeof oversight.normalizeAuditHistory, "function");
  const history = oversight.normalizeAuditHistory({
    events: [{
      id: "event-1",
      session_id: "session-1",
      event_type: "approval.approved",
      details: { proposal_id: "proposal-1", code: "OK", password: "do-not-show" },
      created_at: "2030-01-01T00:00:00Z",
      raw_output: "do-not-show",
    }],
    truncated: false,
  }, "session-1");
  const report = oversight.normalizeLearningReport({
    report_id: "report-1",
    session_id: "session-1",
    session_state: "completed",
    generated_at: "2030-01-01T00:02:00Z",
    target: { target_id: "target-1", expires_at: "2030-01-01T01:00:00Z", locked: true },
    evidence: { total: 2, observed: 1, inferred: 1, verified: 0 },
    proposals: [{ proposal_id: "proposal-1", action_name: "check_tcp_connection", policy_allowed: true, policy_code: "ALLOWED" }],
    approvals: [{ proposal_id: "proposal-1", status: "approved", expires_at: "2030-01-01T00:15:00Z", used: false }],
    proposals_truncated: false,
    approvals_truncated: false,
    audit_event_count: 5,
    execution_authorized: false,
    raw_output: "do-not-show",
  }, "session-1");
  assert.deepEqual(history.events[0].details, { proposal_id: "proposal-1", code: "OK" });
  assert.equal(report.executionAuthorized, false);
  assert.equal(JSON.stringify({ history, report }).includes("do-not-show"), false);
});

test("report normalization rejects cross-session or execution-authorizing responses", () => {
  const base = {
    report_id: "report-1", session_id: "session-1", session_state: "ready", generated_at: "2030-01-01T00:00:00Z",
    target: null, evidence: { total: 0, observed: 0, inferred: 0, verified: 0 }, proposals: [], approvals: [],
    proposals_truncated: false, approvals_truncated: false, audit_event_count: 0, execution_authorized: false,
  };
  assert.throws(() => oversight.normalizeLearningReport(base, "other-session"), /unavailable/i);
  assert.throws(() => oversight.normalizeLearningReport({ ...base, execution_authorized: true }, "session-1"), /unavailable/i);
});

test("emergency-stop renderer enables only the safe explicit action", () => {
  assert.equal(typeof oversight.renderEmergencyStop, "function");
  const elements = { activate: new FakeNode(), clear: new FakeNode(), refresh: new FakeNode(), message: new FakeNode() };
  oversight.renderEmergencyStop(elements, { active: true, busy: false, status: "checking", message: "Checking." });
  assert.equal(elements.activate.disabled, true);
  assert.equal(elements.clear.disabled, true);
  oversight.renderEmergencyStop(elements, { active: false, busy: false, status: "clear", message: "Clear." });
  assert.equal(elements.activate.disabled, false);
  assert.equal(elements.clear.disabled, true);
  oversight.renderEmergencyStop(elements, { active: true, busy: false, status: "active", message: "Active." });
  assert.equal(elements.activate.disabled, true);
  assert.equal(elements.clear.disabled, false);
});

test("oversight renderer displays only normalized report and audit fields", () => {
  assert.equal(typeof oversight.renderSessionOversight, "function");
  const elements = {
    summary: new FakeNode(), overview: new FakeNode(), proposals: new FakeNode(),
    approvals: new FakeNode(), audit: new FakeNode(), events: new FakeNode(),
  };
  const report = {
    reportId: "report-1", sessionId: "session-1", sessionState: "completed",
    generatedAt: "2030-01-01T00:02:00.000Z", target: null,
    evidence: { total: 2, observed: 1, inferred: 1, verified: 0 },
    proposals: [{ proposalId: "proposal-1", actionName: "check_tcp_connection", policyAllowed: true, policyCode: "ALLOWED" }],
    approvals: [{ proposalId: "proposal-1", status: "approved", expiresAt: "2030-01-01T00:15:00.000Z", used: false }],
    proposalsTruncated: false, approvalsTruncated: false, auditEventCount: 1, executionAuthorized: false,
  };
  const history = {
    events: [{ id: "event-1", sessionId: "session-1", eventType: "approval.approved", details: { proposal_id: "proposal-1" }, createdAt: "2030-01-01T00:00:00.000Z" }],
    truncated: false,
  };
  oversight.renderSessionOversight(elements, report, history, fakeDocument);
  assert.equal(elements.summary.hidden, false);
  assert.equal(elements.audit.hidden, false);
  assert.match(elements.overview.textContent, /Execution authorized: No/i);
  assert.match(elements.proposals.children[0].textContent, /check_tcp_connection.*ALLOWED/i);
  assert.match(elements.approvals.children[0].textContent, /approved.*unused/i);
  assert.match(elements.events.children[0].textContent, /approval\.approved.*proposal-1/i);
});
