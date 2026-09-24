"""Planned integration points must remain visibly unavailable until implemented."""

from importlib import import_module
from typing import get_type_hints

import pytest

from redpath.action_registry import ValidatedProposal


@pytest.mark.parametrize(
    ("module_name", "function_name", "args", "kwargs"),
    [
        ("redpath_desktop.launcher", "check_prerequisites", (), {}),
        ("redpath_desktop.launcher", "start_stack", (), {}),
        ("redpath_desktop.launcher", "stop_stack", (), {}),
        ("redpath_desktop.launcher", "service_health", (), {}),
        ("redpath_kali.terminal", "open_terminal", ("session-1",), {}),
        ("redpath_kali.terminal", "resize_terminal", ("terminal-1", 80, 24), {}),
        ("redpath_kali.terminal", "close_terminal", ("terminal-1",), {}),
        ("redpath_ai.compose", "connect_ollama", (), {}),
        (
            "redpath.checks",
            "run_approved_check",
            (ValidatedProposal.model_construct(),),
            {"approved_protected_hash": "not-an-approval"},
        ),
    ],
)
def test_unimplemented_seam_fails_closed(module_name, function_name, args, kwargs):
    function = getattr(import_module(module_name), function_name)
    assert "return" in get_type_hints(function)
    with pytest.raises(NotImplementedError):
        function(*args, **kwargs)


def test_selected_model_source_is_explicit():
    from redpath_ai.compose import MODEL_SOURCE

    assert MODEL_SOURCE == "hf.co/IamLucif3r/Qwen3-4B-Instruct-2507-Abliterated:Q4_K_M"
