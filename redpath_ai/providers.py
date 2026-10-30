"""LLM provider interfaces and recommendation-only implementations."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import selected_model
from .prompts import SYSTEM_PROMPT, explanation_prompt, recommendation_prompt
from .schemas import (
    ActionArgumentConstraint,
    ArgumentKind,
    Explanation,
    ProposalKind,
    ProposedStep,
    ProviderHealth,
    ProviderCode,
    RecommendationContext,
)


class ProviderError(RuntimeError):
    """A provider failed without exposing untrusted response content."""


class ProviderUnavailableError(ProviderError):
    """The local provider could not be reached within its bounded request."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Reject redirects so Ollama requests cannot leave the validated endpoint."""

    def redirect_request(
        self, req: urllib.request.Request, fp: Any, code: int,
        msg: str, headers: Any, newurl: str,
    ) -> None:
        return None


class LLMProvider(ABC):
    """Recommendation and explanation contract; deliberately cannot execute actions."""

    @abstractmethod
    def health(self) -> ProviderHealth:
        raise NotImplementedError

    @abstractmethod
    def recommend_next_step(self, context: RecommendationContext) -> ProposedStep:
        raise NotImplementedError

    @abstractmethod
    def explain_result(self, result: str) -> Explanation:
        raise NotImplementedError


class RuleBasedProvider(LLMProvider):
    """Deterministic safe fallback for unavailable or invalid model output."""

    _SERVICE_ACTIONS = {
        "http": "inspect_http_headers",
        "https": "inspect_tls_certificate",
        "ssl": "inspect_tls_certificate",
        "ssh": "check_tcp_connection",
    }

    def __init__(self) -> None:
        self.last_code = ProviderCode.RULE_BASED_SUCCESS

    def health(self) -> ProviderHealth:
        return ProviderHealth(available=True, provider="rule_based", detail="local fallback")

    def recommend_next_step(self, context: RecommendationContext) -> ProposedStep:
        actions = {action.name: action for action in context.allowed_actions}
        for finding in sorted(context.findings, key=lambda item: item.id):
            service = (finding.service_hint or "").lower()
            action_name = self._SERVICE_ACTIONS.get(service)
            if action_name not in actions:
                continue
            definition = actions[action_name]
            arguments: dict[str, Any] = {}
            for constraint in definition.argument_constraints:
                known_values = {
                    ArgumentKind.TARGET_ID: context.target_id,
                    ArgumentKind.PORT: finding.port,
                    ArgumentKind.PROTOCOL: finding.protocol,
                    ArgumentKind.FINDING_ID: finding.id,
                }
                value = known_values.get(constraint.kind)
                if value is None and constraint.required:
                    break
                if value is not None:
                    arguments[constraint.name] = value
            else:
                return ProposedStep(
                    kind=ProposalKind.ACTION,
                    finding_ids=[finding.id],
                    action_name=action_name,
                    arguments=arguments,
                    reason=(f"The {service} service is {finding.state.value} evidence and "
                            "has a matching fixed learning action."),
                    learning_goal=f"Learn what a limited {service} check can and cannot show.",
                    requires_approval=True,
                ).validate_against(context)
        return ProposedStep(
            kind=ProposalKind.MORE_EVIDENCE,
            finding_ids=[],
            reason="No supplied finding has a matching fixed action with complete arguments.",
            learning_goal="Collect enough normalized evidence to choose a safe next step.",
            requires_approval=True,
            evidence_needed="Import a normalized scan result or enable a matching registered action.",
        )

    def explain_result(self, result: str) -> Explanation:
        return Explanation(
            summary="The action returned a result that should be reviewed with its supporting evidence.",
            what_it_proves="It proves only what the specific fixed check directly observed.",
            limitations="It does not prove the whole target is secure or that every service was tested.",
            terms={},
            study_next=["evidence states", "service enumeration", "authorization boundaries"],
        )


Transport = Callable[[str, dict[str, Any] | None, float], dict[str, Any]]
# Default model tag and time limit; the app passes the REDPATH_MODEL choice
# explicitly (see models.py).
OLLAMA_MODEL = selected_model().tag
OLLAMA_TIMEOUT_SECONDS = selected_model().timeout_seconds
# Health checks only ask Ollama for its list of installed models, which answers
# almost instantly. They get their own short limit so the setup screen and
# status cards never wait the full answer time limit (up to 60 s) if Ollama hangs.
HEALTH_TIMEOUT_SECONDS = 5.0

# The only two addresses RedPath will ever send AI requests to.
# Ollama on this computer, reached through loopback. Used by the native app.
LOOPBACK_OLLAMA_URL = "http://127.0.0.1:11434"
# Docker's name for the host computer, used when RedPath runs in a container
# (docker-compose.yml sets REDPATH_OLLAMA_URL to this). Only safe inside a
# container: on Windows itself, Docker Desktop maps this name to the computer's
# network address, so the native app must never use it.
DOCKER_HOST_OLLAMA_URL = "http://host.docker.internal:11434"

# Files that Docker (/.dockerenv) and Podman (/run/.containerenv) create inside
# every container. Their presence is how RedPath knows it is in a container.
# Shared by two checks: the Docker launcher (redpath/container.py) and the
# Ollama address rule below, so both agree on what "in a container" means.
CONTAINER_MARKERS = (Path("/.dockerenv"), Path("/run/.containerenv"))


def in_container() -> bool:
    """Return True when a container marker file exists."""
    return any(marker.exists() for marker in CONTAINER_MARKERS)


def recommendation_schema(context: RecommendationContext) -> dict[str, Any]:
    """Build the answer format sent to Ollama for one recommendation request.

    Ollama forces the model's answer to match this format, so it is built fresh
    from each session's own scan and lists only answers RedPath would accept:

    - one answer shape per offered action, where ``action_name`` is that action
      and ``arguments`` holds exactly its arguments: ``target_id`` can only be
      this session's target, and ``port`` or ``protocol`` only a value from the
      scan's findings (a closed port, such as 80 in the sample scan, is not a
      finding, so it is not offered)
    - ``finding_ids`` can only contain this session's finding IDs
    - one "more evidence" shape with no action and empty arguments

    Every field is required, because Ollama lets the model skip any field the
    format does not list as required (models used to skip finding_ids, so every
    action answer was rejected). The rules mirror ``_validate_argument`` in
    schemas.py. Those strict checks still run on every answer, since a format
    cannot tie a port to the specific finding the model cites.

    Explanations keep their normal format: their extras (terms, study_next) are
    optional, and forcing them makes answers slower.
    """
    fields = ProposedStep.model_json_schema()["properties"]
    finding_ids = [finding.id for finding in context.findings]
    # The only values RedPath accepts for these argument kinds in this session.
    known_values: dict[ArgumentKind, list[Any]] = {
        ArgumentKind.TARGET_ID: [context.target_id],
        ArgumentKind.FINDING_ID: finding_ids,
        ArgumentKind.PORT: sorted({finding.port for finding in context.findings}),
        ArgumentKind.PROTOCOL: sorted({finding.protocol for finding in context.findings}),
    }

    # Builds the rule for one action argument, so the model can only write a
    # value RedPath would accept (for example only ports from the scan's
    # findings). Without these rules, models wrote ports that were not among
    # the findings and left out required arguments such as target_id.
    def argument_rule(constraint: ActionArgumentConstraint) -> dict[str, Any] | None:
        """The format for one argument, or None when no value would be accepted."""
        def allowed(value: Any) -> bool:
            if isinstance(value, int):
                if constraint.minimum is not None and value < constraint.minimum:
                    return False
                if constraint.maximum is not None and value > constraint.maximum:
                    return False
            return not constraint.choices or value in constraint.choices

        if constraint.kind in known_values:
            values = [value for value in known_values[constraint.kind] if allowed(value)]
            return {"enum": values} if values else None
        if constraint.choices:
            return {"enum": list(constraint.choices)}
        if constraint.kind == ArgumentKind.STRING:
            return {"type": "string", "minLength": 1, "maxLength": 256}
        bounds = {"minimum": constraint.minimum, "maximum": constraint.maximum}
        return {"type": "integer", **{key: value for key, value in bounds.items() if value is not None}}

    # Builds one allowed answer shape: the exact fields and values an answer
    # must have so RedPath can use it. The model's answer must match one shape.
    def answer_shape(kind: ProposalKind, cited: dict[str, Any], action_name: dict[str, Any],
                     arguments: dict[str, Any], evidence_needed: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": list(fields),
            "properties": {
                "kind": {"const": kind.value},
                "finding_ids": cited,
                "action_name": action_name,
                "arguments": arguments,
                "reason": fields["reason"],
                "learning_goal": fields["learning_goal"],
                "requires_approval": {"const": True},
                "evidence_needed": evidence_needed,
            },
        }

    shapes = []
    # Actions must cite at least one finding, so they are only offered when the
    # scan has findings. An action is left out when one of its required
    # arguments has no acceptable value (for example no port in the scan).
    if finding_ids:
        for action in context.allowed_actions:
            properties: dict[str, Any] = {}
            required: list[str] = []
            for constraint in action.argument_constraints:
                rule = argument_rule(constraint)
                if rule is None:
                    if constraint.required:
                        break
                    continue
                properties[constraint.name] = rule
                if constraint.required:
                    required.append(constraint.name)
            else:
                shapes.append(answer_shape(
                    ProposalKind.ACTION,
                    {"type": "array", "items": {"enum": finding_ids}, "minItems": 1, "maxItems": 50},
                    {"const": action.name},
                    {"type": "object", "additionalProperties": False,
                     "required": required, "properties": properties},
                    {"type": "null"},
                ))
    # Asking for more evidence is always possible, even with an empty scan.
    shapes.append(answer_shape(
        ProposalKind.MORE_EVIDENCE,
        {"type": "array", "items": {"enum": finding_ids}, "maxItems": 50} if finding_ids
        else {"type": "array", "maxItems": 0},
        {"type": "null"},
        {"type": "object", "additionalProperties": False, "properties": {}},
        {"type": "string", "minLength": 1, "maxLength": 500},
    ))
    return {"anyOf": shapes}


@dataclass(frozen=True)
class ProviderMetrics:
    model: str
    latency_ms: int
    attempts: int
    prompt_eval_count: int | None = None
    eval_count: int | None = None


class OllamaProvider(LLMProvider):
    """Local Ollama client with bounded timeouts and strict output validation."""

    def __init__(
        self,
        model: str = OLLAMA_MODEL,
        base_url: str = LOOPBACK_OLLAMA_URL,
        timeout_seconds: float = OLLAMA_TIMEOUT_SECONDS,
        # How many extra tries a rejected (invalid) answer gets. The default is
        # 0: a retry sends the exact same question, and with "temperature": 0
        # (see _chat) the model repeats the exact same answer, so a retry only
        # made the user wait longer (5 to 30 s). Setting it to 1 resends the
        # same question; it is kept for a future retry that tells the model
        # what was wrong.
        invalid_output_retries: int = 0,
        fallback: LLMProvider | None = None,
        transport: Transport | None = None,
    ) -> None:
        if not 0.1 <= timeout_seconds <= 60:
            raise ValueError("timeout_seconds must be between 0.1 and 60")
        if invalid_output_retries not in (0, 1):
            raise ValueError("invalid_output_retries must be 0 or 1")
        # Loopback is always allowed. The Docker host address is allowed only
        # when a container marker exists (see CONTAINER_MARKERS above), so the
        # native app can never send AI requests over the network. Exact matches
        # only: lookalike hosts, other ports, and https are all rejected.
        url = base_url.rstrip("/")
        if url != LOOPBACK_OLLAMA_URL and not (url == DOCKER_HOST_OLLAMA_URL and in_container()):
            raise ValueError(
                "Ollama must use the local loopback endpoint "
                "(or Docker's host endpoint inside a container)"
            )
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.invalid_output_retries = invalid_output_retries
        self.fallback = fallback or RuleBasedProvider()
        self._transport = transport or self._http_transport
        self.last_metrics: ProviderMetrics | None = None
        self.last_code: ProviderCode | None = None

    def health(self) -> ProviderHealth:
        try:
            payload = self._transport(
                f"{self.base_url}/api/tags", None, min(HEALTH_TIMEOUT_SECONDS, self.timeout_seconds)
            )
            names = {item.get("name") for item in payload.get("models", []) if isinstance(item, dict)}
            available = self.model in names
            return ProviderHealth(
                available=available,
                provider="ollama",
                model=self.model,
                detail=None if available else "configured model is not installed",
            )
        except (ProviderError, OSError, ValueError, TypeError):
            return ProviderHealth(
                available=False,
                provider="ollama",
                model=self.model,
                detail="local Ollama endpoint is unavailable",
            )

    def recommend_next_step(self, context: RecommendationContext) -> ProposedStep:
        started = time.monotonic()
        attempts = self.invalid_output_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                payload = self._chat(recommendation_prompt(context), recommendation_schema(context))
                proposal = ProposedStep.model_validate_json(self._content(payload))
                proposal.validate_against(context)
                self._record_metrics(payload, started, attempt)
                self.last_code = ProviderCode.OLLAMA_SUCCESS
                return proposal
            except (ProviderUnavailableError, OSError):
                # Timed out or could not connect: use the safe answer right away,
                # even when invalid_output_retries is 1. Retrying a timeout made
                # the user wait the full time limit twice (up to 2 minutes), and
                # a model that was too slow once, or an Ollama that is not
                # running, rarely succeeds a moment later.
                self.last_metrics = ProviderMetrics(
                    model=self.model,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    attempts=attempt,
                )
                self.last_code = ProviderCode.OLLAMA_UNAVAILABLE_FALLBACK
                return self.fallback.recommend_next_step(context)
            except (ProviderError, ValidationError, ValueError, TypeError, KeyError):
                # The answer arrived but failed the checks. With the default of
                # no retries this is the only attempt, so the safe rule-based
                # answer is used right away.
                if attempt == attempts:
                    self.last_metrics = ProviderMetrics(
                        model=self.model,
                        latency_ms=int((time.monotonic() - started) * 1000),
                        attempts=attempt,
                    )
                    self.last_code = ProviderCode.OLLAMA_INVALID_OUTPUT_FALLBACK
                    return self.fallback.recommend_next_step(context)
        raise AssertionError("unreachable")

    def explain_result(self, result: str) -> Explanation:
        try:
            payload = self._chat(explanation_prompt(result), Explanation.model_json_schema())
            return Explanation.model_validate_json(self._content(payload))
        except (ProviderError, ValidationError, ValueError, TypeError, KeyError, OSError):
            self.last_code = ProviderCode.EXPLANATION_FALLBACK
            return self.fallback.explain_result(result)

    def _chat(self, user_prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        body = {
            "model": self.model,
            "stream": False,
            # Some models "think" out loud before answering, which slows them
            # down and can break the strict JSON answer. Neither current model
            # has a thinking mode, so both accept and ignore this setting; it
            # stays so a thinking model added later is handled too.
            "think": False,
            "format": schema,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "options": {"temperature": 0},
        }
        return self._transport(f"{self.base_url}/api/chat", body, self.timeout_seconds)

    @staticmethod
    def _content(payload: dict[str, Any]) -> str:
        content = payload.get("message", {}).get("content")
        if not isinstance(content, str) or len(content) > 100_000:
            raise ProviderError("Ollama returned missing or oversized structured content")
        return content

    def _record_metrics(self, payload: dict[str, Any], started: float, attempts: int) -> None:
        self.last_metrics = ProviderMetrics(
            model=self.model,
            latency_ms=int((time.monotonic() - started) * 1000),
            attempts=attempts,
            prompt_eval_count=payload.get("prompt_eval_count"),
            eval_count=payload.get("eval_count"),
        )

    @staticmethod
    def _http_transport(url: str, body: dict[str, Any] | None, timeout: float) -> dict[str, Any]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="GET" if body is None else "POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        try:
            with opener.open(request, timeout=timeout) as response:
                raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    raise ProviderError("Ollama response exceeded size limit")
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ProviderError("Ollama response was not an object")
                return payload
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ProviderUnavailableError("local Ollama request failed") from exc
        except json.JSONDecodeError as exc:
            raise ProviderError("local Ollama returned invalid JSON") from exc
