"""Explicit desktop security configuration for in-process API fixtures."""

import pytest

from redpath.local_security import LocalSecurityConfig


@pytest.fixture
def security_config():
    return LocalSecurityConfig(port=43210, csrf_token="a" * 43)


@pytest.fixture
def client_options(security_config):
    return {"base_url": security_config.origin, "headers": {
        "Origin": security_config.origin, "X-RedPath-Session": security_config.csrf_token,
    }}
