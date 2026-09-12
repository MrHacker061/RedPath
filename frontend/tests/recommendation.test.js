import test from "node:test";
import assert from "node:assert/strict";
import * as workflow from "../recommendation.js";

const response = {
  proposal: {
    id: "proposal-1",
    session_id: "session-1",
    finding_ids: ["finding-1", "finding-2"],
    action_name: "check_tcp_connection",
    arguments: { target_id: "target-1", port: 22, timeout_seconds: 5 },
    reason: "Confirm whether the observed TCP service responds.",
    learning_goal: "Learn how a TCP handshake confirms reachability.",
    requires_approval: true,
  },
  policy_decision: {
    id: "decision-1",
    proposal_id: "proposal-1",
    allowed: true,
    code: "ALLOWED",
    explanation: "The fixed action matches the authorized target.",
    raw_detail: "do-not-show",
  },
  debug: "do-not-show",
};

function executionResult(overrides = {}) {
  return {
    action_id: "action-1", status: "completed", exit_code: 0, parser: "tcp_connection_v1", cleanup_status: "completed",
    evidence: [{ kind: "tcp_connection", action_name: "check_tcp_connection", target_id: "target-1", target_address: "192.168.56.20", port: 22, outcome: "succeeded", output_truncated: false, reachable: true, failure_category: null }],
    ...overrides,
  };
}

class FakeNode {
  constructor(tagName = "div") {
    this.tagName = tagName;
    this.children = [];
    this.dataset = {};
    this.disabled = false;
    this.hidden = false;
    this.focused = false;
    this._text = "";
  }

  set textContent(value) {
    this._text = String(value);
    this.children = [];
  }

  get textContent() {
    return this._text || this.children.map((child) => child.textContent).join("");
  }

  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; this._text = ""; }
  focus() { this.focused = true; }
}

function recommendationElements() {
  return {
    content: new FakeNode(),
    heading: new FakeNode("h3"),
    findingIds: new FakeNode("ul"),
    reason: new FakeNode(),
    learningGoal: new FakeNode(),
    action: new FakeNode("code"),
    arguments: new FakeNode("dl"),
    policyResult: new FakeNode(),
    policyCode: new FakeNode("code"),
    policyExplanation: new FakeNode(),
  };
}

const fakeDocument = { createElement: (tagName) => new FakeNode(tagName) };

test("recommendation normalization keeps only registered strict action fields", () => {
  assert.equal(typeof workflow.normalizeRecommendation, "function");
  const normalized = workflow.normalizeRecommendation(response);
  assert.deepEqual(normalized.proposal.arguments, {
    target_id: "target-1",
    port: 22,
    timeout_seconds: 5,
  });
  assert.deepEqual(normalized.proposal.findingIds, ["finding-1", "finding-2"]);
  assert.equal(normalized.proposal.actionName, "check_tcp_connection");
  assert.equal(JSON.stringify(normalized).includes("do-not-show"), false);
});

test("TCP recommendation accepts its optional timeout when omitted", () => {
  const withoutTimeout = structuredClone(response);
  withoutTimeout.proposal.arguments = { target_id: "target-1", port: 22 };
  assert.deepEqual(workflow.normalizeRecommendation(withoutTimeout).proposal.arguments, {
    target_id: "target-1",
    port: 22,
  });
});

test("recommendation normalization rejects unknown actions and mismatched decisions", () => {
  assert.throws(
    () => workflow.normalizeRecommendation({ ...response, proposal: { ...response.proposal, action_name: "run_shell" } }),
    /unavailable/i,
  );
  assert.throws(
    () => workflow.normalizeRecommendation({ ...response, proposal: { ...response.proposal, action_name: "__proto__" } }),
    /unavailable/i,
  );
  assert.throws(
    () => workflow.normalizeRecommendation({ ...response, policy_decision: { ...response.policy_decision, proposal_id: "other" } }),
    /unavailable/i,
  );
  assert.throws(() => workflow.normalizeRecommendation(response, "other-session"), /unavailable/i);
  assert.throws(() => workflow.normalizeRecommendation({
    ...response,
    proposal: { ...response.proposal, arguments: { ...response.proposal.arguments, secret: "do-not-show" } },
  }), /unavailable/i);
});

test("workflow prevents a duplicate approval request and becomes approved", async () => {
  let calls = 0;
  let resolveApproval;
  const api = { approveProposal: async () => {
    calls += 1;
    return new Promise((resolve) => { resolveApproval = resolve; });
  } };
  const controller = new workflow.ProposalWorkflow({ api, now: () => Date.parse("2029-01-01T00:00:00Z") });
  controller.setEmergencyStop(false, true);
  controller.load(workflow.normalizeRecommendation(response));
  const first = controller.decide("approve");
  const duplicate = await controller.decide("approve");
  assert.equal(duplicate, false);
  assert.equal(calls, 1);
  resolveApproval({ proposal_id: "proposal-1", status: "approved", approval_id: "approval-1", expires_at: "2030-01-01T00:00:00Z" });
  assert.equal(await first, true);
  assert.equal(controller.state.status, "approved");
  assert.equal(controller.state.executionAvailable, true);
});

test("workflow blocks decisions for a policy-rejected proposal", async () => {
  let calls = 0;
  const api = { rejectProposal: async () => { calls += 1; } };
  const controller = new workflow.ProposalWorkflow({ api });
  controller.load(workflow.normalizeRecommendation({
    ...response,
    policy_decision: { ...response.policy_decision, allowed: false, code: "TARGET_BLOCKED" },
  }));
  assert.equal(controller.state.status, "rejected");
  assert.equal(await controller.decide("reject"), false);
  assert.equal(calls, 0);
});

test("workflow marks an expired approval as non-executable", async () => {
  const api = { approveProposal: async () => ({
    proposal_id: "proposal-1",
    status: "approved",
    approval_id: "approval-1",
    expires_at: "2028-01-01T00:00:00Z",
  }) };
  const controller = new workflow.ProposalWorkflow({ api, now: () => Date.parse("2029-01-01T00:00:00Z") });
  controller.setEmergencyStop(false, true);
  controller.load(workflow.normalizeRecommendation(response));
  await controller.decide("approve");
  assert.equal(controller.state.status, "expired");
});

test("refreshing an expired approval clears the execution gate", async () => {
  let currentTime = Date.parse("2027-01-01T00:00:00Z");
  const api = { approveProposal: async () => ({
    proposal_id: "proposal-1",
    status: "approved",
    approval_id: "approval-1",
    expires_at: "2028-01-01T00:00:00Z",
  }) };
  const controller = new workflow.ProposalWorkflow({ api, now: () => currentTime });
  controller.setEmergencyStop(false, true);
  controller.load(workflow.normalizeRecommendation(response));
  await controller.decide("approve");
  assert.equal(controller.state.executionAvailable, true);

  currentTime = Date.parse("2029-01-01T00:00:00Z");
  controller.refreshExpiration();

  assert.equal(controller.state.status, "expired");
  assert.equal(controller.state.executionAvailable, false);
});

test("workflow records rejection and does not expose an execution action", async () => {
  const api = { rejectProposal: async () => ({ proposal_id: "proposal-1", status: "rejected", approval_id: null, expires_at: null }) };
  const controller = new workflow.ProposalWorkflow({ api });
  controller.load(workflow.normalizeRecommendation(response));
  await controller.decide("reject");
  assert.equal(controller.state.status, "rejected");
});

test("workflow replaces backend errors with a bounded frontend message", async () => {
  const api = { approveProposal: async () => { throw new Error("secret backend traceback"); } };
  const controller = new workflow.ProposalWorkflow({ api });
  controller.setEmergencyStop(false, true);
  controller.load(workflow.normalizeRecommendation(response));
  await controller.decide("approve");
  assert.equal(controller.state.status, "error");
  assert.doesNotMatch(controller.state.message, /secret|traceback/i);
});

test("recommendation renderer inserts contract fields as literal text", () => {
  assert.equal(typeof workflow.renderRecommendation, "function");
  const elements = recommendationElements();
  const malicious = structuredClone(response);
  malicious.proposal.reason = "<img src=x onerror=alert(1)>";
  malicious.policy_decision.explanation = "<script>not markup</script>";
  workflow.renderRecommendation(elements, workflow.normalizeRecommendation(malicious), fakeDocument);
  assert.equal(elements.content.hidden, false);
  assert.equal(elements.reason.textContent, "<img src=x onerror=alert(1)>");
  assert.equal(elements.policyExplanation.textContent, "<script>not markup</script>");
  assert.deepEqual(elements.findingIds.children.map((item) => item.textContent), ["finding-1", "finding-2"]);
  assert.deepEqual(elements.arguments.children.map((item) => item.textContent), ["target id", "target-1", "port", "22", "timeout seconds", "5"]);
  assert.equal(elements.heading.focused, true);
});

test("proposal state renderer enables controls only while a decision is pending", () => {
  assert.equal(typeof workflow.renderProposalState, "function");
  const elements = {
    controls: new FakeNode(),
    approve: new FakeNode("button"),
    reject: new FakeNode("button"),
    message: new FakeNode(),
  };
  workflow.renderProposalState(elements, { status: "pending", busy: false, emergencyStopActive: false, message: "Review it." });
  assert.equal(elements.controls.hidden, false);
  assert.equal(elements.approve.disabled, false);
  assert.equal(elements.reject.disabled, false);
  assert.equal(elements.message.dataset.state, "pending");

  workflow.renderProposalState(elements, { status: "approved", busy: false, message: "Approved." });
  assert.equal(elements.controls.hidden, true);
  assert.equal(elements.approve.disabled, true);
  assert.equal(elements.reject.disabled, true);
  assert.equal(elements.message.dataset.state, "approved");
});

test("emergency stop defaults safe and blocks approval locally while preserving rejection", async () => {
  let approvals = 0;
  let rejections = 0;
  const api = {
    approveProposal: async () => { approvals += 1; },
    rejectProposal: async () => {
      rejections += 1;
      return { proposal_id: "proposal-1", status: "rejected", approval_id: null, expires_at: null };
    },
  };
  const controller = new workflow.ProposalWorkflow({ api });
  controller.load(workflow.normalizeRecommendation(response));
  assert.equal(controller.state.emergencyStopActive, true);
  assert.match(controller.state.message, /emergency stop is active/i);
  assert.equal(await controller.decide("approve"), false);
  assert.equal(approvals, 0);
  assert.equal(await controller.decide("reject"), true);
  assert.equal(rejections, 1);
});

test("clearing emergency stop restores the pending proposal guidance", () => {
  const controller = new workflow.ProposalWorkflow({ api: {} });
  controller.load(workflow.normalizeRecommendation(response));
  controller.setEmergencyStop(false, true);
  assert.equal(controller.state.emergencyStopActive, false);
  assert.match(controller.state.message, /approve or reject/i);
  assert.doesNotMatch(controller.state.message, /emergency stop is active/i);
});

test("proposal renderer disables only approval when emergency stop is active", () => {
  const elements = {
    controls: new FakeNode(),
    approve: new FakeNode("button"),
    reject: new FakeNode("button"),
    message: new FakeNode(),
  };
  workflow.renderProposalState(elements, {
    status: "pending",
    busy: false,
    emergencyStopActive: true,
    message: "Emergency stop is active.",
  });
  assert.equal(elements.controls.hidden, false);
  assert.equal(elements.approve.disabled, true);
  assert.equal(elements.reject.disabled, false);
});

test("run controls hide and move focus when a proposal is pending, denied, expired, or stop-blocked", () => {
  const elements = {
    controls: new FakeNode(), runControls: new FakeNode(), approve: new FakeNode("button"), reject: new FakeNode("button"),
    run: new FakeNode("button"), message: new FakeNode(),
  };
  workflow.renderProposalState(elements, { status: "pending", busy: false, emergencyStopActive: false, executionAvailable: false, message: "Review." }, true);
  assert.equal(elements.controls.hidden, false);
  assert.equal(elements.runControls.hidden, true);
  assert.equal(elements.run.disabled, true);
  workflow.renderProposalState(elements, { status: "rejected", busy: false, emergencyStopActive: false, executionAvailable: false, message: "Denied." }, true);
  assert.equal(elements.controls.hidden, true);
  assert.equal(elements.runControls.hidden, true);
  assert.equal(elements.run.disabled, true);
  assert.equal(elements.message.focused, true);
});

test("a pending approval blocks a conflicting recommendation request", () => {
  assert.equal(workflow.recommendationRequestDisabled(true, { busy: true }), true);
  assert.equal(workflow.recommendationRequestDisabled(true, { busy: false }), false);
  assert.equal(workflow.recommendationRequestDisabled(false, { busy: false }), true);
});

test("run stays disabled until current approval and a confirmed clear stop", () => {
  const elements = {
    controls: new FakeNode(), approve: new FakeNode("button"), reject: new FakeNode("button"),
    runControls: new FakeNode(), run: new FakeNode("button"), message: new FakeNode(),
  };
  const approved = { status: "approved", busy: false, emergencyStopActive: false, emergencyStopConfirmedClear: true, executionAvailable: true, message: "Approved.", receipt: { proposalId: "proposal-1", expiresAt: "2030-01-01T00:00:00Z" }, recommendation: workflow.normalizeRecommendation(response) };
  workflow.renderProposalState(elements, approved, false);
  assert.equal(elements.run.disabled, true);
  assert.equal(elements.runControls.hidden, true);
  workflow.renderProposalState(elements, approved, true);
  assert.equal(elements.run.disabled, false);
  assert.equal(elements.runControls.hidden, false);
  elements.run.focus();
  workflow.renderProposalState(elements, { ...approved, receipt: { ...approved.receipt, expiresAt: "2028-01-01T00:00:00Z" } }, true, Date.parse("2029-01-01T00:00:00Z"));
  assert.equal(elements.run.disabled, true);
  assert.equal(elements.runControls.hidden, true);
  assert.equal(elements.message.focused, true);
});

test("run requires native confirmation and sends only the stored exact proposal", async () => {
  const calls = [];
  const controller = new workflow.ProposalWorkflow({
    api: { approveProposal: async () => ({ proposal_id: "proposal-1", status: "approved", approval_id: "approval-1", expires_at: "2030-01-01T00:00:00Z" }), runProposal: async (...args) => { calls.push(args); return executionResult(); } },
    now: () => Date.parse("2029-01-01T00:00:00Z"),
    confirmRun: () => false,
  });
  controller.setEmergencyStop(false, true);
  controller.load(workflow.normalizeRecommendation(response));
  await controller.decide("approve");
  assert.equal(controller.state.executionAvailable, true);
  assert.equal(await controller.run(), false);
  assert.deepEqual(calls, []);
  controller.confirmRun = () => true;
  assert.equal(await controller.run(), true);
  assert.deepEqual(calls, [["session-1", "proposal-1"]]);
  assert.equal(controller.state.status, "completed");
});

test("approval completion cannot overwrite a newer proposal generation", async () => {
  let resolveApproval;
  const controller = new workflow.ProposalWorkflow({ api: { approveProposal: () => new Promise((resolve) => { resolveApproval = resolve; }) }, now: () => Date.parse("2029-01-01T00:00:00Z") });
  controller.setEmergencyStop(false, true);
  controller.load(workflow.normalizeRecommendation(response));
  const pending = controller.decide("approve");
  const replacement = structuredClone(response);
  replacement.proposal.id = "proposal-2";
  replacement.policy_decision.proposal_id = "proposal-2";
  controller.load(workflow.normalizeRecommendation(replacement));
  resolveApproval({ proposal_id: "proposal-1", status: "approved", approval_id: "approval-1", expires_at: "2030-01-01T00:00:00Z" });
  assert.equal(await pending, false);
  assert.equal(controller.state.recommendation.proposal.id, "proposal-2");
  assert.equal(controller.state.status, "pending");
  assert.equal(controller.state.executionAvailable, false);
});

test("run revalidates the exact approval after native confirmation before dispatch", async () => {
  const approvedReceipt = { proposal_id: "proposal-1", status: "approved", approval_id: "approval-1", expires_at: "2030-01-01T00:00:00Z" };
  for (const invalidateDuringConfirm of [
    (_controller, advance) => { advance(); },
    (controller) => { controller.setEmergencyStop(true, false); },
  ]) {
    let now = Date.parse("2029-01-01T00:00:00Z");
    let calls = 0;
    const controller = new workflow.ProposalWorkflow({
      api: {
        approveProposal: async () => approvedReceipt,
        runProposal: async () => { calls += 1; return executionResult(); },
      },
      now: () => now,
      confirmRun: () => {
        invalidateDuringConfirm(controller, () => { now = Date.parse("2031-01-01T00:00:00Z"); });
        return true;
      },
    });
    controller.setEmergencyStop(false, true);
    controller.load(workflow.normalizeRecommendation(response));
    await controller.decide("approve");
    assert.equal(await controller.run(), false);
    assert.equal(calls, 0);
  }
});

test("execution result normalization requires the exact fixed result union and approved scope", () => {
  const proposal = workflow.normalizeRecommendation(response).proposal;
  const result = workflow.normalizeExecutionResult(executionResult(), proposal);
  assert.equal(result.evidence[0].targetAddress, "192.168.56.20");
  for (const payload of [
    executionResult({ evidence: [{ ...executionResult().evidence[0], kind: "arbitrary" }] }),
    executionResult({ cleanup_status: "arbitrary" }),
    executionResult({ evidence: [executionResult().evidence[0], executionResult().evidence[0]] }),
    executionResult({ evidence: [{ ...executionResult().evidence[0], target_id: "other-target" }] }),
    executionResult({ evidence: [{ ...executionResult().evidence[0], port: 4444 }] }),
  ]) assert.throws(() => workflow.normalizeExecutionResult(payload, proposal), /unavailable/i);
});

test("execution result normalization handles only the HTTP and TLS union variants", () => {
  const http = structuredClone(response);
  http.proposal.action_name = "inspect_http_headers";
  http.proposal.arguments = { target_id: "target-1", port: 80 };
  const tls = structuredClone(response);
  tls.proposal.action_name = "inspect_tls_certificate";
  tls.proposal.arguments = { target_id: "target-1", port: 443 };
  const httpProposal = workflow.normalizeRecommendation(http).proposal;
  const tlsProposal = workflow.normalizeRecommendation(tls).proposal;
  assert.equal(workflow.normalizeExecutionResult({ action_id: "http-1", status: "completed", exit_code: 0, parser: "http_headers_v1", cleanup_status: "completed", evidence: [{ kind: "http_headers", action_name: "inspect_http_headers", target_id: "target-1", target_address: "192.168.56.20", port: 80, outcome: "succeeded", output_truncated: false, http_status: 200, failure_category: null }] }, httpProposal).evidence[0].httpStatus, 200);
  assert.equal(workflow.normalizeExecutionResult({ action_id: "tls-1", status: "completed", exit_code: 0, parser: "tls_certificate_v1", cleanup_status: "completed", evidence: [{ kind: "tls_certificate", action_name: "inspect_tls_certificate", target_id: "target-1", target_address: "192.168.56.20", port: 443, outcome: "succeeded", output_truncated: false, protocol: "TLSv1.3", cipher_suite: "TLS_AES_256_GCM_SHA384", verification: "verified", failure_category: null }] }, tlsProposal).evidence[0].verification, "verified");
});
