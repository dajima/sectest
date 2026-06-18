"""ReconAgent — single-agent reconnaissance using Kali sandbox tools (T6).

Phase 1 agent that creates an openai-agents SDK ``Agent`` with a custom
``function_tool`` shell wrapper bound to a ``SandboxSession``.  The agent
receives a target, runs Nmap/Semgrep/Bandit inside a sandbox container,
parses results to structured JSON, and returns findings.

All tool integration uses ``function_tool`` from ``agents`` — never
``from agents.sandbox`` (L-01 compliant).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agents import Agent, Runner, function_tool

from sectest.sandbox.manager import SandboxManager, SandboxSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ReconAgent
# ---------------------------------------------------------------------------


class ReconAgent:
    """Phase 1: Single-agent reconnaissance using Kali sandbox tools.

    Creates an openai-agents SDK ``Agent`` with a custom ``function_tool``
    shell wrapper bound to a :class:`SandboxSession`.  The agent executes
    security tools (Nmap, Semgrep, Bandit) inside the sandbox and returns
    structured findings.

    Uses :class:`SandboxSession` — never imports from ``agents.sandbox``
    directly (L-01 compliant).

    Parameters:
        sandbox_manager: The :class:`SandboxManager` used to create sessions
            when none is provided to :meth:`run_scan`.
        model: Optional model name override (e.g. ``"gpt-4o"``).  When
            *None*, the LiteLLM default model is used.
    """

    _INSTRUCTIONS_TEMPLATE = """\
You are a security reconnaissance agent operating inside a Kali Linux sandbox.
Your mission is to perform thorough reconnaissance against the specified target
using security tools available in the sandbox.

## Target
{target}

## Available Tools
- **shell**: Execute commands in the Kali sandbox. This is your primary tool.
  Use it to run nmap, semgrep, bandit, curl, dig, and any other CLI security
  tools available in Kali.

## Workflow
1. Run an nmap service/version scan against the target:
   `nmap -sV -oX /workspace/results/nmap_scan.xml {target}`
2. If the target is a code repository path, also run Semgrep:
   `semgrep --config auto --json --output /workspace/results/semgrep.json {target}`
3. Parse and summarize the tool outputs:
   - List all open ports and services discovered
   - List any SAST findings with severity
   - Provide an overall summary of what was found

## Output Format
You **must** respond with valid JSON only, using this exact structure:
{{
  "target": "the scan target",
  "tool_results": [
    {{
      "tool": "tool name (nmap/semgrep/bandit/etc.)",
      "command": "the exact command executed",
      "exit_code": 0,
      "findings": ["finding 1", "finding 2"],
      "raw_output_summary": "brief summary of raw tool output"
    }}
  ],
  "summary": "Executive summary of all findings"
}}

Do NOT include any text outside the JSON object.  Your entire response
must be parseable by `json.loads()`.  Do not wrap in markdown fences."""

    def __init__(
        self,
        sandbox_manager: SandboxManager,
        model: str | None = None,
    ) -> None:
        self._sandbox = sandbox_manager
        self._model = model

    # -- public API ----------------------------------------------------------

    async def run_scan(
        self,
        target: str,
        session: SandboxSession | None = None,
    ) -> dict[str, Any]:
        """Execute a reconnaissance scan against a target.

        Creates an openai-agents SDK ``Agent`` with a shell ``function_tool``
        bound to the sandbox session, then runs it via ``Runner.run()``.

        Args:
            target: IP address, hostname, URL, or repository path to scan.
            session: Optional pre-created sandbox session.  When *None*, a
                new session is created via :meth:`SandboxManager.create_session`.

        Returns:
            Structured dict with keys ``target``, ``tool_results``, and
            ``summary``.
        """
        # Resolve session — create if none provided
        _created_session = False
        if session is None:
            session = await self._sandbox.create_session()
            _created_session = True

        try:
            # Build the shell function_tool bound to this session
            shell_tool = self._create_shell_tool(session)

            # Build the openai-agents SDK Agent
            agent = Agent(
                name="ReconAgent",
                model=self._model,
                instructions=self._INSTRUCTIONS_TEMPLATE.format(target=target),
                tools=[shell_tool],
            )

            # Run the agent via Runner
            result = await Runner.run(
                agent,
                f"Perform reconnaissance against {target}",
            )

            # Parse the final output to structured dict
            return self._parse_output(result.final_output)

        finally:
            # If we created the session, schedule its cleanup
            if _created_session:
                self._sandbox.schedule_cleanup(session)

    # -- shell tool ----------------------------------------------------------

    def _create_shell_tool(self, session: SandboxSession):
        """Create a ``function_tool`` that wraps :meth:`SandboxSession.exec`.

        Uses the ``function_tool`` decorator from ``agents`` — **never**
        imports ``ShellTool`` from ``agents.sandbox`` (L-01 compliance).

        Args:
            session: The sandbox session to bind the tool to.

        Returns:
            A ``FunctionTool`` that the openai-agents SDK Agent can use.
        """

        @function_tool
        async def shell(command: str) -> str:
            """Execute a command in the Kali Linux sandbox.

            Args:
                command: Shell command to execute (e.g., 'nmap -sV target').
                    The command runs inside the Kali container with full access
                    to all installed security tools.

            Returns:
                Formatted string with exit code, stdout, and stderr.
            """
            result = await session.exec(command, timeout=300)
            return (
                f"EXIT_CODE: {result.exit_code}\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}\n"
                f"DURATION_MS: {result.duration_ms}"
            )

        return shell

    # -- output parsing ------------------------------------------------------

    def _parse_output(self, raw: str) -> dict[str, Any]:
        """Parse agent output to structured dict.

        Attempts ``json.loads()`` first.  On failure, returns a
        ``{"raw_output": ...}`` dict as a fallback so callers always
        receive a well-formed dict.

        Parameters:
            raw: The raw string output from the agent (``result.final_output``).

        Returns:
            A dict — either the parsed JSON or ``{"raw_output": raw}``.
        """
        # Strip whitespace before attempting parse
        text = raw.strip()

        # Try direct JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code fences
        if text.startswith("```"):
            lines = text.splitlines()
            # Remove opening fence, optional language tag, and closing fence
            content_lines: list[str] = []
            in_content = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("```"):
                    if in_content:
                        break  # closing fence
                    in_content = True  # opening fence
                    continue
                if in_content:
                    content_lines.append(line)
            if content_lines:
                try:
                    return json.loads("\n".join(content_lines))
                except json.JSONDecodeError:
                    pass

        # Fallback: return raw output
        logger.warning(
            "Failed to parse agent output as JSON. Returning raw_output."
        )
        return {"raw_output": text}
