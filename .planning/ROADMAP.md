# Roadmap: Sectest — Unified AI Security Testing Platform

**Created:** 2026-06-18
**Updated:** 2026-06-18 (restructured: 6→7 phases, added Phase 3 Asset Management)
**Granularity:** Standard
**Mode:** MVP (each phase delivers usable end-to-end capability)
**Total Phases:** 7
**Requirements:** 23 v1 (100% mapped)

## Phases

- [ ] **Phase 1: Foundation — Kali Sandbox + LLM Gateway** — Docker sandbox lifecycle, LiteLLM proxy integration, single-agent tool execution loop, streaming progress
- [ ] **Phase 2: Engine — Multi-Agent Pipeline + Capability Registry** — Recon→Analysis→Verification→Report pipeline with handoffs, Skill/Tool/Plugin/MCP Client registry
- [ ] **Phase 3: Asset Management — Project/Asset/Scan Hierarchy** — CRUD asset management, multi-type asset registry (code repo + API + environment + secrets), credential vault, scan history
- [ ] **Phase 4: CLI + SAST — Code Audit with PoC Verification** — CLI tool, Semgrep/Bandit integration, PoC auto-generation with sandbox verification
- [ ] **Phase 5: DAST + Grey-Box — Dynamic Penetration Testing** — Nmap, Nuclei, FFuf, SQLMap, browser automation, HTTP proxy, SSH grey-box, MCP remote tools
- [ ] **Phase 6: Web UI + Reports + Deployment** — React dashboard, SSE real-time streaming, PDF/Markdown reports, Docker Compose single-machine + remote multi-user deployment
- [ ] **Phase 7: Advanced — Scan Replay + OWASP Coverage** — Scan replay and diff-based incremental scanning, OWASP Top 10 audit with CWE mapping

## Phase Details

### Phase 1: Foundation — Kali Sandbox + LLM Gateway
**Goal:** Platform can provision Kali Linux Docker containers and execute security tools via an LLM-backed agent, establishing the core agent-sandbox-tool execution loop with streaming progress feedback.
**Mode:** mvp
**Depends on:** Nothing (first phase)
**Requirements:** CORE-01, CORE-03
**Success Criteria** (what must be TRUE when this phase completes):
  1. Platform starts, pulls the Kali Linux Docker image, and creates an ephemeral sandbox container with least-privilege capabilities (NET_ADMIN, NET_RAW, SYS_PTRACE)
  2. A single ReconAgent can connect to LiteLLM Proxy, invoke a tool (e.g., Nmap or Semgrep) inside the Kali sandbox, and return structured output
  3. Scan progress is streamed to stdout in real-time structured JSON lines — each line reports current phase (PULL_IMAGE → CREATE_SANDBOX → TOOL_EXEC → PARSE_RESULTS → DONE) with timestamps and status
  4. Sandbox containers are automatically cleaned up after scan completion or on error
  5. LiteLLM Proxy routes LLM requests to at least two providers (e.g., OpenAI + Anthropic) with automatic fallback on rate limits
  6. SandboxManager abstraction layer isolates all sandbox API usage — no agent code imports from `agents.sandbox` directly
**Plans:** PLAN.md created (8 tasks); needs update for SC-3 streaming progress
**UI hint:** no

### Phase 2: Engine — Multi-Agent Pipeline + Capability Registry
**Goal:** Platform orchestrates the full Recon→Analysis→Verification→Report agent pipeline with structured handoffs, and manages all capabilities through a four-layer registry.
**Mode:** mvp
**Depends on:** Phase 1
**Requirements:** CORE-02, CORE-04
**Success Criteria** (what must be TRUE when this phase completes):
  1. A scan executes sequentially: ReconAgent gathers information, hands off summarized findings to AnalysisAgent, which hands off vulnerabilities to VerificationAgent, which hands off confirmed findings to ReportAgent
  2. Each agent handoff transfers structured summaries (not raw conversation history) to prevent context window exhaustion
  3. Any phase agent can dynamically spawn a child agent to investigate a specific vulnerability path, run independently, report results, and then be destroyed
  4. New Skills (Markdown knowledge documents) and Tools (sandbox-executable commands) can be registered at runtime and become immediately available to agents
  5. A Plugin can combine a Skill and a Tool into a reusable vulnerability check (e.g., "SQL Injection Scanner" plugin wraps the SQL injection knowledge skill + SQLMap tool)
**Plans:** TBD
**UI hint:** no

### Phase 3: Asset Management — Project/Asset/Scan Hierarchy
**Goal:** Platform provides persistent security asset management — users create Projects, register Assets (code repos, API endpoints, environments, credentials), and launch Scans that are permanently linked to their source assets. Scan history and findings accumulate per asset over time, enabling trend analysis and incremental re-scanning.
**Mode:** mvp
**Depends on:** Phase 2 (needs multi-agent pipeline + capability registry for scan execution)
**Requirements:** ASSET-01, ENTRY-01, ENTRY-02
**Success Criteria** (what must be TRUE when this phase completes):
  1. User can create a Project and register Assets of four types: code repository (Git URL/local path), API endpoint (URL + optional Swagger/OpenAPI spec), environment target (domain/IP range), and credential (SSH key, API token, Basic Auth — encrypted at rest)
  2. Asset registry is extensible — implementing a new `AssetProvider` subclass (e.g., `KubernetesClusterAsset`) and registering it makes the new asset type available in the UI/CLI with zero changes to scan orchestration
  3. User can tag assets with labels (code-repo/api/environment/secrets) and filter/search the asset inventory
  4. User launches a scan from the CLI: `sectest scan --asset <asset-id>` — the platform fetches the asset's target configuration, provisions a sandbox, and executes the pipeline
  5. Scan results are persisted and linked to the source asset — viewing an asset shows its complete scan history with findings trend (new/resolved/regressed counts over time)
  6. Credential assets are encrypted at rest (AES-256-GCM via platform master key) and decrypted only when injected into the sandbox for the scan session
**Plans:** TBD
**UI hint:** no (asset CRUD is API-only in this phase; UI comes in Phase 6)

### Phase 4: CLI + SAST — Code Audit with PoC Verification
**Goal:** Users can audit source code via CLI, importing repositories through the asset system. The platform runs Semgrep/Bandit SAST tools, generates PoC exploits, and verifies findings in the sandbox with automatic retry.
**Mode:** mvp
**Depends on:** Phase 3 (needs asset management for code repo targets)
**Requirements:** ENTRY-03, SAST-01, SAST-02, SAST-03
**Success Criteria** (what must be TRUE when this phase completes):
  1. User runs `sectest scan --asset <code-repo-asset-id>` from the CLI and the platform imports source code via Git clone, ZIP upload, or local path (all three methods)
  2. CLI displays real-time scan progress with phase transitions (Recon→Analysis→Verification→Report) using the streaming protocol established in Phase 1
  3. SAST scan detects vulnerabilities using Semgrep (multi-language rules) and Bandit (Python-specific checks), with structured output parsed before LLM consumption
  4. Semgrep rules include secret/key detection patterns (API keys, tokens, passwords, private keys) providing implicit sensitive information scanning coverage
  5. For each SAST finding, the platform generates a PoC script in the Kali sandbox, executes it, and retries with self-healing corrections up to 3 times on failure — verified findings are confirmed, unverifiable ones are flagged
**Plans:** TBD
**UI hint:** yes

### Phase 5: DAST + Grey-Box — Dynamic Penetration Testing
**Goal:** Users can run dynamic penetration tests against live targets, including reconnaissance, vulnerability scanning, browser-based testing, and HTTP traffic manipulation. Platform also supports SSH-based grey-box access into target systems and MCP-based remote tool execution.
**Mode:** mvp
**Depends on:** Phase 3 (needs asset management for API/environment/credential targets; can parallel with Phase 4)
**Requirements:** DAST-01, DAST-02, DAST-03, DAST-04, GBOX-01, GBOX-02
**Success Criteria** (what must be TRUE when this phase completes):
  1. DAST scan runs Nmap for port/service discovery, enumerates subdomains, and maps the target attack surface — all inside the Kali sandbox
  2. Platform executes Nuclei template-based vulnerability scans, FFuf web fuzzing, and SQLMap SQL injection tests against the target, with results parsed to structured format
  3. Platform drives a headless browser (Playwright) to test XSS, CSRF, and authentication flows, capturing DOM state and network traffic as evidence
  4. HTTP proxy (mitmproxy/Caido) intercepts and logs all scan traffic — agents can query captured requests/responses during analysis
  5. User provides SSH credentials and the platform connects from the Kali sandbox into the target system, performing file system enumeration, process/service discovery, configuration auditing, and lateral movement probing
  6. An external security tool exposed as an MCP Server (e.g., remote Nmap instance) is auto-discovered, its capabilities are registered in the capability registry, and agents invoke it through the MCP protocol
**Plans:** TBD
**UI hint:** no

### Phase 6: Web UI + Reports + Deployment
**Goal:** Platform provides a React web dashboard with real-time scan streaming, generates deliverable audit reports (PDF + Markdown), and supports Docker Compose single-machine deployment and remote multi-user server deployment.
**Mode:** mvp
**Depends on:** Phase 4, Phase 5
**Requirements:** ENTRY-04, RPT-01, RPT-02, RPT-03
**Success Criteria** (what must be TRUE when this phase completes):
  1. User opens the web dashboard, creates a new project, registers assets, starts a scan, and watches real-time progress via SSE streaming with phase transitions and agent activity updates
  2. Web dashboard supports project CRUD, asset CRUD with type-specific forms, scan history browsing, and viewing detailed findings with PoC evidence
  3. Asset inventory page displays all registered assets with tags, last scan date, and finding counts — filterable by type (code-repo/api/environment/credential)
  4. Platform generates a downloadable PDF security audit report containing vulnerability descriptions, severity levels, PoC summaries, CWE mappings, and actionable remediation guidance
  5. Platform generates a companion Markdown technical report with full tool output, raw PoC code, and agent reasoning traces for security engineers
  6. User runs `docker compose up` and gets a fully working platform (backend, frontend, PostgreSQL, Redis, LiteLLM Proxy, Kali sandbox) on a single machine
  7. Administrator deploys the platform to a remote server where multiple users can log in via the web panel, create independent projects, and run concurrent scans
**Plans:** TBD
**UI hint:** yes

### Phase 7: Advanced — Scan Replay + OWASP Coverage
**Goal:** Platform supports scan replay for audit reproducibility and incremental diff-based re-scanning. Vulnerability detection covers all OWASP Top 10 categories with CWE identifier mapping in reports.
**Mode:** mvp
**Depends on:** Phase 6
**Requirements:** ADV-01, ADV-02
**Success Criteria** (what must be TRUE when this phase completes):
  1. User can replay a historical scan — the platform restores the original Agent state and inputs, re-executes the same pipeline, and produces comparable results for audit trail purposes
  2. User can run an incremental scan on a Git repository asset — only files changed since the last scan (detected via git diff) are re-audited, reducing scan time while maintaining coverage of modified code
  3. Platform's combined SAST + DAST pipeline detects vulnerabilities across all OWASP Top 10 (2021) categories — a test suite with known-vulnerable targets produces findings for each category
  4. Every vulnerability in generated reports includes a CWE identifier, enabling security teams to map findings to industry-standard weakness classifications
**Plans:** TBD
**UI hint:** no

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 1/2 | In planning | — |
| 2. Engine | 0/2 | Not started | — |
| 3. Asset Management | 0/3 | Not started | — |
| 4. CLI + SAST | 0/5 | Not started | — |
| 5. DAST + Grey-Box | 0/6 | Not started | — |
| 6. Web UI + Reports + Deployment | 0/4 | Not started | — |
| 7. Advanced | 0/2 | Not started | — |

## Dependency Graph

```
Phase 1 (Foundation)
  └── Phase 2 (Engine)
        └── Phase 3 (Asset Management) ── NEW
              ├── Phase 4 (CLI + SAST) ─────────┐
              └── Phase 5 (DAST + Grey-Box) ────┤
                                                  ├── Phase 6 (Web UI + Reports + Deployment)
                                                  │     └── Phase 7 (Advanced)
                                                  └──────────────────────────────────────────┘
```

**Key changes from v1 roadmap (6 phases):**
- Phase 3 (Asset Management) inserted between Engine and scanning phases — all scan targets now flow through the asset registry
- Original Phase 3→6 renumbered to Phase 4→7
- Phase 4 (SAST) and Phase 5 (DAST) can still be developed in parallel after Phase 3 completes
- ASSET-01 requirement added (23 v1 requirements total, up from 22)
- Phase 1 now includes streaming progress (SC-3 added, 5→6 success criteria)

---

*Roadmap created: 2026-06-18*
*Roadmap updated: 2026-06-18 (restructured for asset management)*
*Next: `/gsd-plan-phase 1`*
