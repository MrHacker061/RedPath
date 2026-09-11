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
  controller.setEmergencyStop(false);
  controller.load(workflow.normalizeRecommendation(response));
  const first = controller.decide("approve");
  const duplicate = await controller.decide("approve");
  assert.equal(duplicate, false);
  assert.equal(calls, 1);
  resolveApproval({ proposal_id: "proposal-1", status: "approved", approval_id: "approval-1", expires_at: "2030-01-01T00:00:00Z" });
  assert.equal(await first, true);
  assert.equal(controller.state.status, "approved");
  assert.equal(controller.state.executionAvailable, false);
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
  assert.equal(controller.state.executionAvailable, false);
});

test("workflow marks an expired approval as non-executable", async () => {
  const api = { approveProposal: async () => ({
    proposal_id: "proposal-1",
    status: "approved",
    approval_id: "approval-1",
    expires_at: "2028-01-01T00:00:00Z",
  }) };
  const controller = new workflow.ProposalWorkflow({ api, now: () => Date.parse("2029-01-01T00:00:00Z") });
  controller.setEmergencyStop(false);
  controller.load(workflow.normalizeRecommendation(response));
  await controller.decide("approve");
  assert.equal(controller.state.status, "expired");
  assert.equal(controller.state.executionAvailable, false);
});

test("workflow records rejection and does not expose an execution action", async () => {
  const api = { rejectProposal: async () => ({ proposal_id: "proposal-1", status: "rejected", approval_id: null, expires_at: null }) };
  const controller = new workflow.ProposalWorkflow({ api });
  controller.load(workflow.normalizeRecommendation(response));
  await controller.decide("reject");
  assert.equal(controller.state.status, "rejected");
  assert.equal(controller.state.executionAvailable, false);
});

test("workflow replaces backend errors with a bounded frontend message", async () => {
  const api = { approveProposal: async () => { throw new Error("secret backend traceback"); } };
  const controller = new workflow.ProposalWorkflow({ api });
  controller.setEmergencyStop(false);
  controller.load(workflow.normalizeRecommendation(response));
  await controller.decide("approve");
  assert.equal(controller.state.status, "error");
  assert.doesNotMatch(controller.state.message, /secret|traceback/i);
  assert.equal(controller.state.executionAvailable, false);
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
  controller.setEmergencyStop(false);
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
