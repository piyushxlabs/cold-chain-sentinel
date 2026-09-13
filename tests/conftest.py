import os
import pytest


@pytest.fixture(autouse=True)
def ensure_mock_client_mode_in_tests(monkeypatch):
    """Ensure test suites execute deterministically in mock mode unless explicitly patched."""
    monkeypatch.setenv("CLIENT_MODE", "mock")
