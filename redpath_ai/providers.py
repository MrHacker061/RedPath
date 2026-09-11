"""LLM provider interfaces and recommendation-only implementations."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .prompts import SYSTEM_PROMPT, explanation_prompt, recommendation_prompt
from .schemas import (
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
OLLAMA_MODEL = "qwen2.5:7b-instruct-q4_K_M"


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
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 20.0,
        invalid_output_retries: int = 1,
        fallback: LLMProvider | None = None,
        transport: Transport | None = None,
    ) -> None:
        if not 0.1 <= timeout_seconds <= 60:
            raise ValueError("timeout_seconds must be between 0.1 and 60")
        if invalid_output_retries not in (0, 1):
            raise ValueError("invalid_output_retries must be 0 or 1")
        if base_url.rstrip("/") != "http://127.0.0.1:11434":
            raise ValueError("Ollama must use the local loopback endpoint")
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
            payload = self._transport(f"{self.base_url}/api/tags", None, self.timeout_seconds)
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
                payload = self._chat(
                    recommendation_prompt(context),
                    ProposedStep.model_json_schema(),
                )
                proposal = ProposedStep.model_validate_json(self._content(payload))
                proposal.validate_against(context)
                self._record_metrics(payload, started, attempt)
                self.last_code = ProviderCode.OLLAMA_SUCCESS
                return proposal
            except (ProviderUnavailableError, OSError):
                if attempt == attempts:
                    self.last_metrics = ProviderMetrics(
                        model=self.model,
                        latency_ms=int((time.monotonic() - started) * 1000),
                        attempts=attempt,
                    )
                    self.last_code = ProviderCode.OLLAMA_UNAVAILABLE_FALLBACK
                    return self.fallback.recommend_next_step(context)
            except (ProviderError, ValidationError, ValueError, TypeError, KeyError):
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
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
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
