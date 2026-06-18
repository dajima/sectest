"""ReconAgent — single-agent reconnaissance using Kali sandbox tools.

Phase 1 agent that executes Nmap/Semgrep/Bandit inside a sandbox container
and returns structured findings (T6 — to be fully implemented).
"""

from __future__ import annotations

from sectest.sandbox.manager import SandboxManager, SandboxSession


class ReconAgent:
    """Phase 1: Single-agent reconnaissance using Kali sandbox tools.

    Uses ``SandboxSession`` — never imports from ``agents.sandbox`` directly
    (L-01 compliant).
    """

    def __init__(self, sandbox_manager: SandboxManager, model: str = "gpt-4o") -> None:
        self._sandbox = sandbox_manager
        self._model = model

    async def run_scan(self, target: str, session: SandboxSession) -> dict:
        """Execute a reconnaissance scan against a target."""
        raise NotImplementedError("ReconAgent.run_scan() — implement in T6")
