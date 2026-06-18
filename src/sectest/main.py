"""Sectest platform entry point (T7).

Orchestrates the Phase 1 end-to-end scan pipeline:

1. Load configuration from environment variables
2. Initialize ``SandboxManager`` with ``sectest/kali-sandbox:latest``
3. Pre-pull Kali image with progress reporting (L-06)
4. Create ephemeral sandbox session (D-01, D-02)
5. Run ``ReconAgent`` scan
6. Stream real-time progress as structured JSON lines to stdout
7. Output final results
8. Schedule 15-minute delayed cleanup (D-03, D-04)
9. Ensure cleanup runs on error via try/finally (L-08)

Usage::

    uv run python -m sectest.main --target example.com
    uv run python -m sectest.main --target localhost --progress-format text
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import TYPE_CHECKING

from sectest.agents.recon import ReconAgent
from sectest.llm.config import LLMConfig
from sectest.sandbox.manager import SandboxConfig, SandboxManager
from sectest.streaming import ProgressEmitter, ScanPhase

if TYPE_CHECKING:
    from sectest.sandbox.manager import SandboxSession


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="sectest",
        description="AI-driven security reconnaissance platform.",
    )
    parser.add_argument(
        "--target",
        default="localhost",
        help="IP address, hostname, or URL to scan (default: localhost).",
    )
    parser.add_argument(
        "--progress-format",
        choices=["json", "text"],
        default="json",
        help="Progress output format.  'json' emits one JSON object per "
        "line; 'text' prints human-readable messages (default: json).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override the model name (e.g. deepseek-v4-flash).  Defaults to "
        "the LLM_MODEL or DEFAULT_MODEL environment variable.",
    )
    parser.add_argument(
        "--llm-only",
        action="store_true",
        help="Skip Docker sandbox entirely — only test LLM connectivity. "
        "Useful for verifying API keys and model access.",
    )
    return parser


# ---------------------------------------------------------------------------
# Phase helpers
# ---------------------------------------------------------------------------


async def _run_phase_pull_image(
    emitter: ProgressEmitter | None,
    manager: SandboxManager,
) -> bool:
    """Pre-pull Kali sandbox image. Returns True if image is ready."""
    if emitter is not None:
        with emitter.phase("PULL_IMAGE", "Pre-pulling Kali sandbox image..."):
            ok = await manager.pre_pull_image()
            if not ok:
                raise RuntimeError(
                    "Kali sandbox image not found. Build it first:\n"
                    "  bash docker/build.sh\n"
                    f"Expected image: {manager._config.image}"
                )
            return True
    else:
        print("Pre-pulling Kali sandbox image...")
        ok = await manager.pre_pull_image()
        if not ok:
            print(
                f"Error: Kali sandbox image '{manager._config.image}' not found.",
                file=sys.stderr,
            )
            print("Build it first: bash docker/build.sh", file=sys.stderr)
            sys.exit(1)
        return True


async def _run_phase_create_sandbox(
    emitter: ProgressEmitter | None,
    manager: SandboxManager,
) -> SandboxSession:
    """Create ephemeral sandbox container."""
    if emitter is not None:
        with emitter.phase("CREATE_SANDBOX", "Creating sandbox container..."):
            session = await manager.create_session()
    else:
        print("Creating sandbox container...")
        session = await manager.create_session()
    return session


async def _run_phase_tool_exec(
    emitter: ProgressEmitter | None,
    agent: ReconAgent,
    target: str,
    session: SandboxSession,
) -> dict:
    """Run the reconnaissance scan inside the sandbox."""
    if emitter is not None:
        with emitter.phase("TOOL_EXEC", f"Running scan against {target}..."):
            result = await agent.run_scan(target, session=session)
    else:
        print(f"Running scan against {target}...")
        result = await agent.run_scan(target, session=session)
    return result


def _output_results(
    emitter: ProgressEmitter | None,
    result: dict,
) -> None:
    """Output scan results to stdout as structured JSON.

    When an emitter is active the result is written as a single JSON line
    (no indentation) so every stdout line remains independently parseable.
    In text mode the result is pretty-printed for human readability.
    """
    if emitter is not None:
        with emitter.phase("PARSE_RESULTS", "Parsing scan results..."):
            # Single-line JSON -- preserves the "one JSON per line" contract
            sys.stdout.write(json.dumps(result, default=str) + "\n")
            sys.stdout.flush()
    else:
        json.dump(result, sys.stdout, indent=2, default=str)
        print()

    if emitter is not None:
        emitter.emit(
            "DONE",
            "done",
            "Scan completed successfully.",
            summary=result.get("summary", ""),
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def async_main() -> None:
    """Async entry point for the sectest platform.

    Orchestrates the full startup--scan--cleanup lifecycle with
    streaming progress output.
    """
    parser = _build_parser()
    args = parser.parse_args()

    # 1. Resolve progress emitter
    emitter = ProgressEmitter() if args.progress_format == "json" else None

    # 2. Load configuration (validates API keys are set)
    try:
        llm_config = LLMConfig()
    except ValueError as exc:
        if emitter is not None:
            emitter.emit("PULL_IMAGE", "error", str(exc))
        else:
            print(f"Configuration error: {exc}", file=sys.stderr)
            print(
                "\nTip: Use direct mode to skip LiteLLM Proxy:",
                "\n  $env:LLM_MODEL=\"deepseek/deepseek-v4-flash\"",
                "\n  $env:LLM_API_KEY=\"sk-...\"",
                "\n  $env:LLM_API_BASE=\"https://api.deepseek.com/v1\"",
                "\nOr set LITELLM_API_KEY and start the proxy:",
                "\n  docker compose up litellm -d",
                file=sys.stderr,
            )
        sys.exit(1)

    # 3. Initialize SandboxManager
    sandbox_config = SandboxConfig()
    manager = SandboxManager(sandbox_config)

    # 4. Initialize ReconAgent with configured model (--model overrides env)
    model = args.model or llm_config.model
    agent = ReconAgent(manager, model=model)

    session: SandboxSession | None = None

    try:
        # --llm-only: skip Docker entirely, test LLM connectivity only
        if args.llm_only:
            if emitter is not None:
                emitter.emit("TOOL_EXEC", "running", f"Testing LLM connectivity with model={model}...")

            from agents import Runner, Agent as SDKAgent, RunConfig
            from sectest.llm.provider import llm_provider

            test_agent = SDKAgent(
                name="connectivity-test",
                instructions="You are a security platform connectivity test. Reply with exactly: OK",
            )
            run_result = await Runner.run(
                test_agent,
                "Hello",
                run_config=RunConfig(
                    model_provider=llm_provider,
                    model=model,  # resolved via OUR provider, not SDK multi-provider
                ),
            )
            output = run_result.final_output

            if emitter is not None:
                emitter.emit("TOOL_EXEC", "done", "LLM test completed.")
                emitter.emit("DONE", "done", f"LLM response: {output}", model=model)

            if emitter is None:
                print(f"Model: {model}")
                print(f"Response: {output}")
            return

        # Phase: PULL_IMAGE
        await _run_phase_pull_image(emitter, manager)

        # Phase: CREATE_SANDBOX
        session = await _run_phase_create_sandbox(emitter, manager)

        # Phase: TOOL_EXEC
        result = await _run_phase_tool_exec(emitter, agent, args.target, session)

        # Output results
        _output_results(emitter, result)

    finally:
        # Ensure cleanup is scheduled regardless of success or error (L-08)
        if session is not None:
            manager.schedule_cleanup(session)


def main() -> None:
    """Synchronous wrapper around :func:`async_main`."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
