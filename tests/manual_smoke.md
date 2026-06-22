# Manual Smoke Test — Sectest Phase 1

This document provides step-by-step instructions for running a full
end-to-end smoke test with a real LLM (via LiteLLM Proxy) and a real
Kali Linux Docker sandbox.

**Purpose:** Verify that the complete Phase 1 pipeline works correctly
with real infrastructure before the phase is marked complete.

**Estimated duration:** 20-30 minutes (depends on image pull speed)

---

## Prerequisites

- Docker Engine 24+ installed and running
- Kali sandbox image built (see Step 2)
- LiteLLM Proxy configured and running (see Step 1)
- Valid LLM API keys configured (OpenAI, Anthropic, or both)
- Python 3.12+ with `uv` installed
- All project dependencies installed: `uv sync`

**Verify prerequisites:**

```bash
docker version          # Docker daemon running
uv --version            # uv installed
uv run python -c "from sectest.llm.config import LLMConfig; print('OK')"  # imports work
```

---

## Step 1: Start LiteLLM Proxy

The LiteLLM Proxy handles multi-provider routing and fallback.

```bash
# From the project root
docker compose up litellm -d
```

Wait a few seconds, then verify it is healthy:

```bash
curl -s http://localhost:4000/health
# Expected: {"status":"healthy"} or similar OK response
```

**Troubleshooting:**
- If the proxy fails to start, check `docker compose logs litellm`
- Ensure `LITELLM_MASTER_KEY` is set in `.env` (default: `sk-lite`)
- Verify `.env` has valid provider API keys (`OPENAI_API_KEY`, etc.)

---

## Step 2: Build Kali Sandbox Image

The Kali sandbox image must be available locally.

```bash
# From the project root
bash docker/build.sh
```

This builds `sectest/kali-sandbox:latest`. Verify:

```bash
docker images sectest/kali-sandbox:latest
# Expected: shows the image with REPOSITORY, TAG, IMAGE ID, SIZE
```

**Troubleshooting:**
- If the build fails due to network issues, ensure internet access is available
- The first build may take 10-15 minutes (large image download)
- If `build.sh` is missing, check `docker/Dockerfile.kali` exists and build manually:
  ```bash
  docker build -t sectest/kali-sandbox:latest -f docker/Dockerfile.kali docker/
  ```

---

## Step 3: Run a Scan

Set the required environment variable and execute a scan against a safe
target (localhost or a test service you control).

```bash
# Set the LiteLLM master key
export LITELLM_API_KEY="sk-lite"

# Run a scan against localhost
uv run python -m sectest.main --target localhost --progress-format json
```

**If running against a code repository path (SAST test):**

```bash
uv run python -m sectest.main --target /path/to/some/code --progress-format json
```

**Expected behavior:**
1. Progress lines appear as JSON on stdout (one per line)
2. Phases: `PULL_IMAGE`, `CREATE_SANDBOX`, `TOOL_EXEC`, `PARSE_RESULTS`, `DONE`
3. Each phase transitions: `running` -> `done`
4. The scan may take 1-5 minutes depending on LLM latency

---

## Step 4: Verify JSON Output

Inspect the output. Each line is a standalone JSON object.

Expected progress line structure:

```json
{"phase": "PULL_IMAGE", "status": "running", "message": "Pre-pulling Kali sandbox image...", "timestamp": "2026-06-18T..."}
```

The final result line (from PARSE_RESULTS phase) is also a single JSON line:

```json
{"target": "localhost", "tool_results": [...], "summary": "..."}
```

**Checklist:**
- [ ] At least one `PULL_IMAGE` line with status `running` and one with `done`
- [ ] `CREATE_SANDBOX` with status `running` then `done`
- [ ] `TOOL_EXEC` with status `running` then `done`
- [ ] `PARSE_RESULTS` with status `running` then `done`
- [ ] `DONE` with status `done`
- [ ] Final result line contains keys: `target`, `tool_results`, `summary`
- [ ] `tool_results` is a list with at least one entry
- [ ] Each tool_result has keys: `tool`, `command`, `exit_code`, `findings`, `raw_output_summary`
- [ ] `summary` is a non-empty string

**Extract result to inspect:**

```bash
# Capture output and extract the final result line
uv run python -m sectest.main --target localhost --progress-format json 2>/dev/null | \
  grep '"target"' | python -m json.tool
```

---

## Step 5: Verify Container Cleanup

After the scan completes (success or error), the sandbox container
should be destroyed after a 15-minute retention window.

**Immediately after scan:**

```bash
# Check for any running sectest containers
docker ps --filter "ancestor=sectest/kali-sandbox:latest"
# Expected: shows the container (within first 15 minutes)
```

**After 15 minutes:**

```bash
# The container should be gone
docker ps -a --filter "ancestor=sectest/kali-sandbox:latest"
# Expected: no containers (or only exited containers from prior runs)
```

**Checklist:**
- [ ] Container exists during the retention window
- [ ] Container is destroyed after 15 minutes (D-04 compliance)
- [ ] No zombie containers left behind

---

## Step 6: Test Error Recovery

Simulate a failure condition and verify the platform handles it cleanly.

### 6a: LiteLLM Proxy Down

```bash
# Stop the proxy
docker compose stop litellm

# Run scan (should fail gracefully)
export LITELLM_API_KEY="sk-lite"
uv run python -m sectest.main --target localhost --progress-format json 2>&1

# Restart proxy after test
docker compose start litellm
```

**Expected:** The scan should emit an error phase (`"status": "error"`) with
a descriptive error message instead of crashing silently.

### 6b: Missing API Key

```bash
# Unset the API key
unset LITELLM_API_KEY

# Run scan
uv run python -m sectest.main --target localhost --progress-format json
```

**Expected:** Exit code 1. Error JSON line emitted: `{"phase": "PULL_IMAGE", "status": "error", ...}`. Clean exit, no traceback dump.

### 6c: Docker Down

If Docker daemon is stopped:
- The scan should fail during `CREATE_SANDBOX` or `PULL_IMAGE`
- Error phase JSON emitted
- No unhandled exceptions

**Checklist:**
- [ ] LiteLLM proxy down -> graceful error emission
- [ ] Missing API key -> clean exit code 1
- [ ] Docker unavailable -> graceful error emission

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `{"status":"error","message":"LITELLM_API_KEY..."}` | API key not set | `export LITELLM_API_KEY="sk-lite"` |
| `Connection refused` during scan | LiteLLM proxy not running | `docker compose up litellm -d` |
| `Image not found: sectest/kali-sandbox:latest` | Kali image not built | Run `bash docker/build.sh` |
| LLM returns 429 rate limit | LiteLLM fallback not configured | Check LiteLLM proxy config for fallback chain |
| Container not cleaned up after 15 min | asyncio task lost | Check for crashed/stopped event loop |
| `pytest` skip tests with reason "Docker" | Docker not running | Start Docker daemon |
| `uv run` fails with import error | Dependencies not installed | Run `uv sync` |

---

## Completion Sign-off

After completing all 6 steps successfully, sign off below:

- [ ] Step 1: LiteLLM Proxy running and healthy
- [ ] Step 2: Kali sandbox image built
- [ ] Step 3: Scan executed successfully
- [ ] Step 4: JSON output valid with all required fields
- [ ] Step 5: Container cleanup verified
- [ ] Step 6: Error recovery tested

**Tester:** __________________

**Date:** __________________

**Notes:** __________________
