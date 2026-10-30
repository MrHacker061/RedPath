"""Tests for the REDPATH_MODEL toggle in redpath_ai/models.py."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from redpath.app import create_app
from redpath.config import Settings
from redpath_ai import OllamaProvider
from redpath_ai.models import DEFAULT_MODEL, MODELS, selected_model


def test_qwen3_is_the_default_model():
    assert DEFAULT_MODEL == "qwen3"
    assert selected_model().tag == "hf.co/IamLucif3r/Qwen3-4B-Instruct-2507-Abliterated:Q4_K_M"
    assert OllamaProvider().model == "hf.co/IamLucif3r/Qwen3-4B-Instruct-2507-Abliterated:Q4_K_M"


def test_toggle_selects_each_model():
    assert selected_model("qwen3").tag == "hf.co/IamLucif3r/Qwen3-4B-Instruct-2507-Abliterated:Q4_K_M"
    assert selected_model("qwen2.5-coder").tag == "hf.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF:Q3_K_M"
    assert set(MODELS) == {"qwen3", "qwen2.5-coder"}


def test_unknown_model_is_rejected_with_the_valid_choices():
    with pytest.raises(ValueError, match="qwen3, qwen2.5-coder"):
        selected_model("gemma2")
    # The old names were renamed, so they are rejected too.
    with pytest.raises(ValueError):
        selected_model("qwen3.5")
    with pytest.raises(ValidationError, match="REDPATH_MODEL"):
        Settings(model="gemma2")


def test_toggle_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("REDPATH_MODEL", "qwen2.5-coder")
    assert Settings().model == "qwen2.5-coder"


def test_app_uses_the_selected_model_everywhere(tmp_path, security_config, client_options):
    app = create_app(
        Settings(database_url=f"sqlite:///{tmp_path / 'models.db'}", model="qwen2.5-coder"),
        security=security_config,
    )
    qwen_2_5 = selected_model("qwen2.5-coder")
    # The AI provider and the setup screen's check/download share one model.
    assert app.state.llm_provider.model == qwen_2_5.tag
    assert app.state.ollama_setup.provider is app.state.llm_provider

    with TestClient(app, **client_options) as client:
        card = client.get("/api/v1/setup").json()["components"]["model"]
    assert (card["version"], card["download_size_bytes"]) == (qwen_2_5.tag, qwen_2_5.download_bytes)


def test_chat_requests_turn_thinking_off():
    requests = []

    def transport(url, body, timeout):
        requests.append(body)
        return {"message": {"content": "{}"}}

    OllamaProvider(transport=transport).explain_result("result")
    assert requests[0]["model"] == "hf.co/IamLucif3r/Qwen3-4B-Instruct-2507-Abliterated:Q4_K_M"
    assert requests[0]["think"] is False
