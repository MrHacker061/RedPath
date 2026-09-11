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
const ACTION_KINDS = Object.freeze({
  check_tcp_connection: "tcp_connection",
  inspect_http_headers: "http_headers",
  inspect_tls_certificate: "tls_certificate",
});
const CLEANUP_STATUSES = new Set(["not_required", "completed", "failed"]);

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

function currentApproval(state, now = Date.now()) {
  const receipt = state.receipt;
  const proposal = state.recommendation?.proposal;
  return state.status === "approved" && state.busy === false && state.emergencyStopActive === false
    && receipt?.proposalId === proposal?.id && Number.isFinite(Date.parse(receipt?.expiresAt))
    && Date.parse(receipt.expiresAt) > now;
}

export function recommendationRequestDisabled(recommendationReady, state) {
  return !recommendationReady || state?.busy === true;
}

export function renderProposalState(elements, state, emergencyStopClear = false, now = Date.now()) {
  const canDecide = state.status === "pending" && !state.busy;
  const hideDecisionControls = state.status !== "pending";
  const wasDecisionControlsVisible = !elements.controls.hidden;
  const wasRunControlsVisible = Boolean(elements.runControls && !elements.runControls.hidden);
  const canRun = currentApproval(state, now) && state.executionAvailable === true && emergencyStopClear === true;
  elements.controls.hidden = hideDecisionControls;
  elements.approve.disabled = !canDecide || state.emergencyStopActive !== false;
  elements.reject.disabled = !canDecide;
  elements.message.dataset.state = state.status;
  elements.message.textContent = state.message;
  if (elements.runControls) elements.runControls.hidden = !canRun;
  if (elements.run) elements.run.disabled = !canRun;
  if ((hideDecisionControls && wasDecisionControlsVisible) || (wasRunControlsVisible && !canRun)) (canRun ? elements.run : elements.message)?.focus?.();
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

export function normalizeExecutionResult(payload, proposal) {
  const actionName = proposal?.actionName;
  const expectedOutcome = { completed: "succeeded", failed: "failed", timed_out: "timed_out" };
  if (!Object.hasOwn(ACTION_PARSERS, actionName) || !payload || !Object.hasOwn(expectedOutcome, payload.status)) unavailable();
  if (payload.parser !== ACTION_PARSERS[actionName] || !Array.isArray(payload.evidence) || payload.evidence.length !== 1 || !CLEANUP_STATUSES.has(payload.cleanup_status)) unavailable();
  if (!(payload.exit_code === null || Number.isInteger(payload.exit_code))) unavailable();
  const item = payload.evidence[0];
  if (!item || item.kind !== ACTION_KINDS[actionName] || item.action_name !== actionName || item.target_id !== proposal.arguments.target_id || item.port !== proposal.arguments.port || item.outcome !== expectedOutcome[payload.status] || typeof item.output_truncated !== "boolean") unavailable();
  const failureCategory = payload.status === "completed" ? null : payload.status === "timed_out" ? "timed_out" : "fixed_action_failed";
  if (item.failure_category !== failureCategory) unavailable();
  const evidence = {
    kind: ACTION_KINDS[actionName], targetId: boundedText(item.target_id, 128), targetAddress: boundedText(item.target_address, 128), port: item.port,
    outcome: item.outcome, outputTruncated: item.output_truncated, failureCategory,
  };
  if (actionName === "check_tcp_connection") {
    if (typeof item.reachable !== "boolean") unavailable();
    evidence.reachable = item.reachable;
  } else if (actionName === "inspect_http_headers") {
    if (!(item.http_status === null || (Number.isInteger(item.http_status) && item.http_status >= 100 && item.http_status <= 599))) unavailable();
    evidence.httpStatus = item.http_status;
  } else {
    if (!(item.protocol === null || ["TLSv1", "TLSv1.1", "TLSv1.2", "TLSv1.3"].includes(item.protocol)) || !(item.cipher_suite === null || /^[A-Z0-9_-]{1,64}$/.test(item.cipher_suite)) || !["verified", "failed", "unknown"].includes(item.verification)) unavailable();
    evidence.protocol = item.protocol;
    evidence.cipherSuite = item.cipher_suite;
    evidence.verification = item.verification;
  }
  return { actionId: boundedText(payload.action_id, 128), status: payload.status, exitCode: payload.exit_code, parser: payload.parser, evidence: [evidence], cleanupStatus: payload.cleanup_status };
}

export class ProposalWorkflow {
  constructor({ api, now = () => Date.now(), onChange = () => {}, confirmRun = globalThis.confirm }) {
    this.api = api;
    this.now = now;
    this.onChange = onChange;
    this.confirmRun = confirmRun;
    this.state = { status: "idle", busy: false, generation: 0, message: "No recommendation requested.", executionAvailable: false, emergencyStopActive: true };
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
      generation: this.state.generation + 1,
    };
    this.emit();
  }

  async decide(choice) {
    if (this.state.status !== "pending" || this.state.busy || !["approve", "reject"].includes(choice)) return false;
    if (choice === "approve" && this.state.emergencyStopActive !== false) return false;
    const { proposal } = this.state.recommendation;
    const generation = this.state.generation;
    this.state = { ...this.state, busy: true, message: `${choice === "approve" ? "Approving" : "Rejecting"} the exact proposal…` };
    this.emit();
    try {
      const payload = choice === "approve"
        ? await this.api.approveProposal(proposal.sessionId, proposal.id)
        : await this.api.rejectProposal(proposal.sessionId, proposal.id);
      const receipt = normalizeDecisionReceipt(payload, proposal.id);
      if (this.state.generation !== generation || this.state.recommendation?.proposal.id !== proposal.id) return false;
      const expired = receipt.status === "approved" && Date.parse(receipt.expiresAt) <= this.now();
      const status = expired ? "expired" : receipt.status;
      this.state = {
        ...this.state,
        status,
        busy: false,
        receipt,
        executionAvailable: currentApproval({ ...this.state, status, busy: false, receipt }, this.now()),
        message: status === "approved"
          ? "Approved for this exact action and arguments. Confirm before running it."
          : status === "expired"
            ? "The approval has expired. It cannot be executed."
            : "Proposal rejected. It cannot be approved or executed.",
      };
    } catch {
      if (this.state.generation !== generation || this.state.recommendation?.proposal.id !== proposal.id) return false;
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
    if (!currentApproval(this.state, this.now()) || !this.state.executionAvailable || !receipt || receipt.proposalId !== recommendation?.proposal.id) return false;
    if (typeof this.confirmRun !== "function" || this.confirmRun("Run this exact approved learning action? RedPath will not run any other action or target.") !== true) return false;
    const proposal = recommendation.proposal;
    this.state = { ...this.state, busy: true, executionAvailable: false, message: "Running the exact approved action…" };
    this.emit();
    try {
      const result = normalizeExecutionResult(await this.api.runProposal(proposal.sessionId, proposal.id), proposal);
      this.state = { ...this.state, status: result.status, busy: false, executionAvailable: false, result, message: `Action ${result.status}. Review bounded results below.` };
    } catch {
      this.state = { ...this.state, status: "error", busy: false, executionAvailable: false, message: "The approved action could not be completed. Review the report and audit history." };
    }
    this.emit();
    return true;
  }

  setEmergencyStop(active) {
    const emergencyStopActive = active !== false;
    const approvedAndCurrent = currentApproval({ ...this.state, emergencyStopActive }, this.now());
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
