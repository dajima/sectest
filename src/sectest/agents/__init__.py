"""Security testing agents.

Phase 1 provides a single :class:`ReconAgent` that executes security
tools (Nmap, Semgrep, Bandit) inside Kali Linux sandbox containers and
returns structured findings.

All agents consume :class:`~sectest.sandbox.manager.SandboxSession` and
never import from ``agents.sandbox`` directly (L-01).
"""

from sectest.agents.recon import ReconAgent

__all__ = [
    "ReconAgent",
]
