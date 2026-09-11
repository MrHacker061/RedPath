const ACTION_ARGUMENTS = Object.freeze({
  inspect_http_headers: { required: ["target_id", "port"], optional: [] },
  inspect_tls_certificate: { required: ["target_id", "port"], optional: [] },
  check_tcp_connection: { required: ["target_id", "port"], optional: ["timeout_seconds"] },
});
const ACTION_PARSERS = Object.freeze({
  check_tcp_connection: "tcp_connection_v1",
  inspect_http_headers: "http_headers_v1",
  inspect_tls_certificate: "tls_certificate_v1",
});

function unavailable() {
  throw new TypeError("The recommendation is unavailable because its response was invalid.");
}

function boundedText(value, maxLength) {
  if (typeof value !== "string" || !value.trim() || value.length > maxLength) unavailable();
  return value;
}

function normalizeArguments(actionName, value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) unavailable();
  if (!Object.hasOwn(ACTION_ARGUMENTS, actionName)) unavailable();
  const schema = ACTION_ARGUMENTS[actionName];
  const allowed = [...schema.required, ...schema.optional];
  const supplied = Object.keys(value);
  if (supplied.some((name) => !allowed.includes(name)) || schema.required.some((name) => !Object.hasOwn(value, name))) unavailable();
  const result = {};
  for (const name of allowed) {
    if (!Object.hasOwn(value, name)) continue;
    const argument = value[name];
    if (name === "target_id") result[name] = boundedText(argument, 128);
    else if (!Number.isInteger(argument) || argument < 1 || argument > (name === "port" ? 65535 : 10)) unavailable();
    else result[name] = argument;
  }
  return result;
}

export function normalizeRecommendation(payload, expectedSessionId = null) {
  const proposal = payload?.proposal;
  const policy = payload?.policy_decision;
  if (!proposal || !policy || proposal.requires_approval !== true || typeof policy.allowed !== "boolean") unavailable();
  const id = boundedText(proposal.id, 128);
  const sessionId = boundedText(proposal.session_id, 128);
  if (expectedSessionId !== null && sessionId !== expectedSessionId) unavailable();
  const actionName = boundedText(proposal.action_name, 100);
  if (policy.proposal_id !== id) unavailable();
  if (!Array.isArray(proposal.finding_ids) || !proposal.finding_ids.length || proposal.finding_ids.length > 100) unavailable();

  return {
    proposal: {
      id,
      sessionId,
      findingIds: proposal.finding_ids.map((findingId) => boundedText(findingId, 128)),
      actionName,
      arguments: normalizeArguments(actionName, proposal.arguments),
      reason: boundedText(proposal.reason, 1000),
      learningGoal: boundedText(proposal.learning_goal, 1000),
      requiresApproval: true,
    },
    policyDecision: {
      id: boundedText(policy.id, 128),
      proposalId: id,
      allowed: policy.allowed,
      code: boundedText(policy.code, 80),
      explanation: boundedText(policy.explanation, 1000),
    },
  };
}

export function renderRecommendation(elements, recommendation, documentImpl = document) {
  const { proposal, policyDecision } = recommendation;
  elements.findingIds.replaceChildren(...proposal.findingIds.map((findingId) => {
    const item = documentImpl.createElement("li");
    item.textContent = findingId;
    return item;
  }));
  elements.reason.textContent = proposal.reason;
  elements.learningGoal.textContent = proposal.learningGoal;
  elements.action.textContent = proposal.actionName;
  const argumentNodes = [];
  for (const [name, value] of Object.entries(proposal.arguments)) {
    const term = documentImpl.createElement("dt");
    term.textContent = name.replaceAll("_", " ");
    const detail = documentImpl.createElement("dd");
    detail.textContent = String(value);
    argumentNodes.push(term, detail);
  }
  elements.arguments.replaceChildren(...argumentNodes);
  elements.policyResult.textContent = policyDecision.allowed ? "Allowed pending approval" : "Rejected";
  elements.policyCode.textContent = policyDecision.code;
  elements.policyExplanation.textContent = policyDecision.explanation;
  elements.content.hidden = false;
  elements.heading.focus();
}

export function renderProposalState(elements, state, emergencyStopClear = false) {
  const canDecide = state.status === "pending" && !state.busy;
  elements.controls.hidden = state.status !== "pending";
  elements.approve.disabled = !canDecide || state.emergencyStopActive !== false;
  elements.reject.disabled = !canDecide;
  elements.message.dataset.state = state.status;
  elements.message.textContent = state.message;
  if (elements.run) elements.run.disabled = !(state.status === "approved" && !state.busy && state.executionAvailable === true && emergencyStopClear === true);
}

function pendingProposalMessage(emergencyStopActive) {
  return emergencyStopActive
    ? "Emergency stop is active. Approval is disabled; you can still reject this proposal."
    : "Policy allowed this exact proposal. Approve or reject it below.";
}

function normalizeDecisionReceipt(payload, expectedProposalId) {
  if (!payload || payload.proposal_id !== expectedProposalId || !["approved", "rejected"].includes(payload.status)) unavailable();
  if (payload.status === "rejected") {
    return { proposalId: expectedProposalId, status: "rejected", approvalId: null, expiresAt: null };
  }
  const expiresAt = boundedText(payload.expires_at, 64);
  if (!Number.isFinite(Date.parse(expiresAt))) unavailable();
  return {
    proposalId: expectedProposalId,
    status: "approved",
    approvalId: boundedText(payload.approval_id, 128),
    expiresAt,
  };
}

export function normalizeExecutionResult(payload, actionName) {
  if (!Object.hasOwn(ACTION_PARSERS, actionName) || !payload || !["completed", "failed", "timed_out"].includes(payload.status)) unavailable();
  if (payload.parser !== ACTION_PARSERS[actionName] || !Array.isArray(payload.evidence) || payload.evidence.length > 100) unavailable();
  if (!(payload.exit_code === null || Number.isInteger(payload.exit_code))) unavailable();
  const evidence = payload.evidence.map((item) => {
    if (!item || item.action_name !== actionName || !["succeeded", "failed", "timed_out"].includes(item.outcome) || !Number.isInteger(item.port) || item.port < 1 || item.port > 65535 || typeof item.output_truncated !== "boolean") unavailable();
    if (!(item.http_status === null || (Number.isInteger(item.http_status) && item.http_status >= 100 && item.http_status <= 599)) || !(item.failure_category === null || typeof item.failure_category === "string")) unavailable();
    return {
      kind: boundedText(item.kind, 80), targetId: boundedText(item.target_id, 128), targetAddress: boundedText(item.target_address, 128), port: item.port,
      outcome: item.outcome, outputTruncated: item.output_truncated, httpStatus: item.http_status,
      failureCategory: item.failure_category === null ? null : boundedText(item.failure_category, 80),
    };
  });
  return { actionId: boundedText(payload.action_id, 128), status: payload.status, exitCode: payload.exit_code, parser: payload.parser, evidence, cleanupStatus: boundedText(payload.cleanup_status, 80) };
}

export class ProposalWorkflow {
  constructor({ api, now = () => Date.now(), onChange = () => {}, confirmRun = globalThis.confirm }) {
    this.api = api;
    this.now = now;
    this.onChange = onChange;
    this.confirmRun = confirmRun;
    this.state = { status: "idle", busy: false, message: "No recommendation requested.", executionAvailable: false, emergencyStopActive: true };
  }

  load(recommendation) {
    const status = recommendation.policyDecision.allowed ? "pending" : "rejected";
    const emergencyStopActive = this.state.emergencyStopActive !== false;
    this.state = {
      status,
      busy: false,
      message: status === "pending"
        ? pendingProposalMessage(emergencyStopActive)
        : "Policy rejected this proposal. It cannot be approved or executed.",
      executionAvailable: false,
      emergencyStopActive,
      recommendation,
      receipt: null,
    };
    this.emit();
  }

  async decide(choice) {
    if (this.state.status !== "pending" || this.state.busy || !["approve", "reject"].includes(choice)) return false;
    if (choice === "approve" && this.state.emergencyStopActive !== false) return false;
    this.state = { ...this.state, busy: true, message: `${choice === "approve" ? "Approving" : "Rejecting"} the exact proposal…` };
    this.emit();
    const { proposal } = this.state.recommendation;
    try {
      const payload = choice === "approve"
        ? await this.api.approveProposal(proposal.sessionId, proposal.id)
        : await this.api.rejectProposal(proposal.sessionId, proposal.id);
      const receipt = normalizeDecisionReceipt(payload, proposal.id);
      const expired = receipt.status === "approved" && Date.parse(receipt.expiresAt) <= this.now();
      const status = expired ? "expired" : receipt.status;
      this.state = {
        ...this.state,
        status,
        busy: false,
        receipt,
        executionAvailable: status === "approved" && this.state.emergencyStopActive === false,
        message: status === "approved"
          ? "Approved for this exact action and arguments. Confirm before running it."
          : status === "expired"
            ? "The approval has expired. It cannot be executed."
            : "Proposal rejected. It cannot be approved or executed.",
      };
    } catch {
      this.state = {
        ...this.state,
        status: "error",
        busy: false,
        executionAvailable: false,
        message: "The proposal decision could not be saved. Request a fresh recommendation before trying again.",
      };
    }
    this.emit();
    return true;
  }

  refreshExpiration() {
    if (this.state.status === "approved" && Date.parse(this.state.receipt?.expiresAt) <= this.now()) {
      this.state = { ...this.state, status: "expired", executionAvailable: false, message: "The approval has expired. It cannot be executed." };
      this.emit();
    }
  }

  async run() {
    const { receipt, recommendation } = this.state;
    if (this.state.status !== "approved" || this.state.busy || this.state.emergencyStopActive !== false || !this.state.executionAvailable || !receipt || Date.parse(receipt.expiresAt) <= this.now()) return false;
    if (typeof this.confirmRun !== "function" || this.confirmRun("Run this exact approved learning action? RedPath will not run any other action or target.") !== true) return false;
    const proposal = recommendation.proposal;
    this.state = { ...this.state, busy: true, executionAvailable: false, message: "Running the exact approved action…" };
    this.emit();
    try {
      const result = normalizeExecutionResult(await this.api.runProposal(proposal.sessionId, proposal.id), proposal.actionName);
      this.state = { ...this.state, status: result.status, busy: false, executionAvailable: false, result, message: `Action ${result.status}. Review bounded results below.` };
    } catch {
      this.state = { ...this.state, status: "error", busy: false, executionAvailable: false, message: "The approved action could not be completed. Review the report and audit history." };
    }
    this.emit();
    return true;
  }

  setEmergencyStop(active) {
    const emergencyStopActive = active !== false;
    const approvedAndCurrent = this.state.status === "approved" && Date.parse(this.state.receipt?.expiresAt) > this.now();
    this.state = {
      ...this.state,
      emergencyStopActive,
      executionAvailable: approvedAndCurrent && !emergencyStopActive,
      message: this.state.status === "pending" ? pendingProposalMessage(emergencyStopActive) : this.state.message,
    };
    this.emit();
  }

  emit() {
    this.onChange(this.state);
  }
}
