"""Shared test fixtures for the Sectest platform.

Provides common fixtures used across all test modules:
    - Mock Docker client
    - Mock LLM runner
    - Temporary configuration
    - Mock SandboxSession
"""

import pytest


@pytest.fixture
def sandbox_config():
    """Return a default SandboxConfig for testing."""
    from sectest.sandbox.manager import SandboxConfig

    return SandboxConfig()


@pytest.fixture
def mock_docker_client(mocker):
    """Return a mocked Docker SDK client."""
    return mocker.MagicMock(name="docker_client")
