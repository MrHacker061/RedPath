const ACTION_ARGUMENTS = Object.freeze({
  inspect_http_headers: { required: ["target_id", "port"], optional: [] },
  inspect_tls_certificate: { required: ["target_id", "port"], optional: [] },
  check_tcp_connection: { required: ["target_id", "port"], optional: ["timeout_seconds"] },
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

export function renderProposalState(elements, state) {
  const canDecide = state.status === "pending" && !state.busy;
  elements.controls.hidden = state.status !== "pending";
  elements.approve.disabled = !canDecide || state.emergencyStopActive !== false;
  elements.reject.disabled = !canDecide;
  elements.message.dataset.state = state.status;
  elements.message.textContent = state.message;
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

export class ProposalWorkflow {
  constructor({ api, now = () => Date.now(), onChange = () => {} }) {
    this.api = api;
    this.now = now;
    this.onChange = onChange;
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
        executionAvailable: false,
        message: status === "approved"
          ? "Approved for this exact action and arguments. Execution is not available in this frontend."
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

  setEmergencyStop(active) {
    const emergencyStopActive = active !== false;
    this.state = {
      ...this.state,
      emergencyStopActive,
      message: this.state.status === "pending" ? pendingProposalMessage(emergencyStopActive) : this.state.message,
    };
    this.emit();
  }

  emit() {
    this.onChange(this.state);
  }
}
