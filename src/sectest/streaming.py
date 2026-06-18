"""ProgressEmitter — structured JSON-line progress output (T7).

Provides a lightweight emitter that writes one JSON object per line to
stdout at each scan phase transition.  Supports a context-manager protocol
so callers can bracket a phase and get automatic ``done``/``error``
emission without manual calls.

Usage::

    from sectest.streaming import ProgressEmitter

    emitter = ProgressEmitter()

    # Manual emission
    emitter.emit("PULL_IMAGE", "running", "Pulling Kali image...")

    # Context-manager protocol (auto done/error)
    with emitter.phase("PULL_IMAGE", "Pulling Kali image..."):
        await manager.pre_pull_image()

Each output line is a JSON object::

    {"phase": "PULL_IMAGE", "status": "running", "message": "...",
     "timestamp": "2026-06-18T00:00:00+00:00"}
"""

from __future__ import annotations

import json
import sys
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Literal types for type-safe phase / status values
# ---------------------------------------------------------------------------

ScanPhase = Literal[
    "PULL_IMAGE",
    "CREATE_SANDBOX",
    "TOOL_EXEC",
    "PARSE_RESULTS",
    "DONE",
]

Status = Literal["running", "done", "error"]


# ---------------------------------------------------------------------------
# ProgressEmitter
# ---------------------------------------------------------------------------


class ProgressEmitter:
    """Write structured JSON-line progress updates to stdout.

    Each call to :meth:`emit` writes a single JSON object line containing
    ``phase``, ``status``, ``message``, ``timestamp``, and any extra keyword
    arguments.  :meth:`phase` provides a context manager that automatically
    emits ``"done"`` on success or ``"error"`` on exception.
    """

    def emit(
        self,
        phase: ScanPhase,
        status: Status,
        message: str = "",
        **extra: Any,
    ) -> None:
        """Write a single progress JSON line to stdout.

        Parameters:
            phase: The scan phase identifier (e.g. ``"PULL_IMAGE"``).
            status: One of ``"running"``, ``"done"``, or ``"error"``.
            message: Human-readable description of the current state.
            **extra: Additional key-value pairs merged into the JSON object.
        """
        payload: dict[str, Any] = {
            "phase": phase,
            "status": status,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        payload.update(extra)

        line = json.dumps(payload)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    @contextmanager
    def phase(self, phase: ScanPhase, message: str = ""):
        """Context manager that brackets a phase with running/done/error.

        Emits ``{"phase": ..., "status": "running"}`` on entry, then
        ``{"phase": ..., "status": "done"}`` on normal exit, or
        ``{"phase": ..., "status": "error"}`` if an exception occurs
        (the exception is re-raised after emission).

        Parameters:
            phase: The scan phase identifier.
            message: Human-readable description of the phase.
        """
        self.emit(phase, "running", message)
        try:
            yield
            self.emit(phase, "done", message)
        except Exception as exc:
            self.emit(
                phase,
                "error",
                message if message else str(exc),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise
