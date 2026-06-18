# Roadmap: Strix — Unified AI Security Testing Platform

**Created:** 2026-06-18
**Granularity:** Standard
**Mode:** MVP (each phase delivers usable end-to-end capability)
**Total Phases:** 6
**Requirements:** 22 v1 (100% mapped)

## Phases

- [ ] **Phase 1: Foundation — Kali Sandbox + LLM Gateway** — Docker sandbox lifecycle, LiteLLM proxy integration, single-agent tool execution loop
- [ ] **Phase 2: Engine — Multi-Agent Pipeline + Capability Registry** — Recon→Analysis→Verification→Report pipeline with handoffs, Skill/Tool/Plugin/MCP Client registry
- [ ] **Phase 3: CLI + SAST — Code Audit with PoC Verification** — CLI tool, multi-target input, Semgrep/Bandit integration, PoC auto-generation with sandbox verification
- [ ] **Phase 4: DAST + Grey-Box — Dynamic Penetration Testing** — Nmap, Nuclei, FFuf, SQLMap, browser automation, HTTP proxy, SSH grey-box, MCP remote tools
- [ ] **Phase 5: Web UI + Reports + Deployment** — Vue 3 dashboard, SSE real-time streaming, PDF/Markdown reports, Docker Compose single-machine + remote multi-user deployment
- [ ] **Phase 6: Advanced — Scan Replay + OWASP Coverage** — Scan replay and diff-based incremental scanning, OWASP Top 10 audit with CWE mapping

## Phase Details

### Phase 1: Foundation — Kali Sandbox + LLM Gateway
**Goal:** Platform can provision Kali Linux Docker containers and execute security tools via an LLM-backed agent, establishing the core agent-sandbox-tool execution loop.
**Mode:** mvp
**Depends on:** Nothing (first phase)
**Requirements:** CORE-01, CORE-03
**Success Criteria** (what must be TRUE when this phase completes):
  1. Platform starts, pulls the Kali Linux Docker image, and creates an ephemeral sandbox container with least-privilege capabilities (NET_ADMIN, NET_RAW, SYS_PTRACE)
  2. A single ReconAgent can connect to LiteLLM Proxy, invoke a tool (e.g., Nmap or Semgrep) inside the Kali sandbox, and return structured output
  3. Sandbox containers are automatically cleaned up after scan completion or on error
  4. LiteLLM Proxy routes LLM requests to at least two providers (e.g., OpenAI + Anthropic) with automatic fallback on rate limits
  5. SandboxManager abstraction layer isolates all sandbox API usage — no agent code imports from `agents.sandbox` directly
**Plans:** TBD
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

### Phase 3: CLI + SAST — Code Audit with PoC Verification
**Goal:** Users can audit source code via CLI, importing repositories in multiple formats. The platform runs Semgrep/Bandit SAST tools, generates PoC exploits, and verifies findings in the sandbox with automatic retry.
**Mode:** mvp
**Depends on:** Phase 2
**Requirements:** ENTRY-01, ENTRY-02, ENTRY-03, SAST-01, SAST-02, SAST-03
**Success Criteria** (what must be TRUE when this phase completes):
  1. User runs `strix scan --target <git-url|zip-path|local-path>` from the CLI and the platform imports source code via all three methods
  2. User can pass multiple target types in a single scan command (e.g., a code repo + a live URL + an SSH credential) via an extensible TargetProvider architecture
  3. CLI displays real-time scan progress with phase transitions (Recon→Analysis→Verification→Report) and a summary report at completion
  4. SAST scan detects vulnerabilities using Semgrep (multi-language rules) and Bandit (Python-specific checks), with structured output parsed before LLM consumption
  5. For each SAST finding, the platform generates a PoC script in the Kali sandbox, executes it, and retries with self-healing corrections up to 3 times on failure — verified findings are confirmed, unverifiable ones are flagged
**Plans:** TBD
**UI hint:** yes

### Phase 4: DAST + Grey-Box — Dynamic Penetration Testing
**Goal:** Users can run dynamic penetration tests against live targets, including reconnaissance, vulnerability scanning, browser-based testing, and HTTP traffic manipulation. Platform also supports SSH-based grey-box access into target systems and MCP-based remote tool execution.
**Mode:** mvp
**Depends on:** Phase 2 (can parallel with Phase 3)
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

### Phase 5: Web UI + Reports + Deployment
**Goal:** Platform provides a Vue 3 web dashboard with real-time scan streaming, generates deliverable audit reports (PDF + Markdown), and supports Docker Compose single-machine deployment and remote multi-user server deployment.
**Mode:** mvp
**Depends on:** Phase 3, Phase 4
**Requirements:** ENTRY-04, RPT-01, RPT-02, RPT-03
**Success Criteria** (what must be TRUE when this phase completes):
  1. User opens the web dashboard, creates a new project, starts a scan, and watches real-time progress via SSE streaming with phase transitions and agent activity updates
  2. Web dashboard supports project CRUD, scan history browsing, and viewing detailed findings with PoC evidence
  3. Platform generates a downloadable PDF security audit report containing vulnerability descriptions, severity levels, PoC summaries, CWE mappings, and actionable remediation guidance
  4. Platform generates a companion Markdown technical report with full tool output, raw PoC code, and agent reasoning traces for security engineers
  5. User runs `docker compose up` and gets a fully working platform (backend, frontend, PostgreSQL, Redis, LiteLLM Proxy, Kali sandbox) on a single machine
  6. Administrator deploys the platform to a remote server where multiple users can log in via the web panel, create independent projects, and run concurrent scans
**Plans:** TBD
**UI hint:** yes

### Phase 6: Advanced — Scan Replay + OWASP Coverage
**Goal:** Platform supports scan replay for audit reproducibility and incremental diff-based re-scanning. Vulnerability detection covers all OWASP Top 10 categories with CWE identifier mapping in reports.
**Mode:** mvp
**Depends on:** Phase 5
**Requirements:** ADV-01, ADV-02
**Success Criteria** (what must be TRUE when this phase completes):
  1. User can replay a historical scan — the platform restores the original Agent state and inputs, re-executes the same pipeline, and produces comparable results for audit trail purposes
  2. User can run an incremental scan on a Git repository — only files changed since the last scan (detected via git diff) are re-audited, reducing scan time while maintaining coverage of modified code
  3. Platform's combined SAST + DAST pipeline detects vulnerabilities across all OWASP Top 10 (2021) categories — a test suite with known-vulnerable targets produces findings for each category
  4. Every vulnerability in generated reports includes a CWE identifier, enabling security teams to map findings to industry-standard weakness classifications
**Plans:** TBD
**UI hint:** no

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/2 | Not started | — |
| 2. Engine | 0/2 | Not started | — |
| 3. CLI + SAST | 0/6 | Not started | — |
| 4. DAST + Grey-Box | 0/6 | Not started | — |
| 5. Web UI + Reports + Deployment | 0/4 | Not started | — |
| 6. Advanced | 0/2 | Not started | — |

## Dependency Graph

```
Phase 1 (Foundation)
  └── Phase 2 (Engine)
        ├── Phase 3 (CLI + SAST) ──┐
        └── Phase 4 (DAST + Grey-Box) ──┤
                                        ├── Phase 5 (Web UI + Reports + Deployment)
                                        │     └── Phase 6 (Advanced)
                                        └──────────────────────────────────────────────┘
```

Phases 3 and 4 can be developed in parallel after Phase 2 completes.

---

*Roadmap created: 2026-06-18*
*Next: `/gsd-plan-phase 1`*
