# Feature Landscape

**Domain:** AI-powered security audit platform (SAST + DAST)
**Researched:** 2026-06-18

## Table Stakes

Features users expect. Missing = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Source code import (Git clone, zip upload, local path) | Users need to point at code to audit | Low | GitPython + file handling; mostly wiring |
| Multi-language SAST scanning (Python, JS/TS, Java, Go) | Security tools must cover common stacks | Medium | Semgrep handles multi-language; Bandit for Python depth |
| Dynamic target scanning (URL, API endpoint, IP range) | DAST requires live targets | Medium | Nmap, Nuclei, FFuf via Kali sandbox |
| Docker Kali sandbox execution | All dangerous tools run isolated | High | openai-agents SandboxAgent + Docker client. ~3GB image pull is slow. |
| Vulnerability report generation (PDF, JSON, SARIF) | Audit deliverables | Low | Jinja2 templates; SARIF is industry standard |
| LLM provider configuration (OpenAI, Anthropic, local) | Operators need model choice | Low | LiteLLM proxy handles this |
| Authentication (JWT + RBAC) | Multi-user web deployment requires it | Low | python-jose + passlib[bcrypt] |
| CLI interface for local scanning | Security engineers work in terminals | Medium | Textual TUI framework; wraps same API as web |
| Real-time scan progress streaming | Scans take minutes to hours | Medium | SSE from FastAPI; TanStack Query for reconnection |

## Differentiators

Features that set product apart. Not expected, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Unified SAST+DAST in single pipeline | No other tool combines code audit + live penetration testing with AI agents | High | Core innovation. Recon -> Analysis -> Verification agent pipeline with handoffs. |
| PoC auto-generation and sandbox verification | Near-zero false positives. Each finding has executable proof. | High | Fuzzing Harness technique from DeepAudit. Self-healing retry on PoC failure. |
| Skill/Tool/Plugin/MCP Client four-layer capability registry | Highly extensible. New vulnerability checks are declarative. | Medium | Skill=knowledge (prompt templates), Tool=execution (docker exec wrappers), Plugin=Skill+Tool composition, MCP Client=external ecosystem. |
| RAG-based code semantic indexing | Understands code context beyond pattern matching. Finds vulnerabilities that span multiple functions/files. | High | Tree-sitter AST chunking, ChromaDB HNSW indexing, multi-provider embeddings. |
| Agent collaboration graph visualization | Users see which agent found what, how they cooperated | Medium | Langfuse trace visualization, OpenInference span tree rendering. |
| Hybrid deployment (CLI single-machine + Web team server) | Same engine, two interfaces. No feature disparity. | Medium | Shared backend; CLI vs browser frontend choice is deployment config. |
| Scan replay and diff analysis | Re-run the same scan with the same agent state. See what changed. | High | Langfuse trace replay. Git diff-based incremental re-scanning. |

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Runtime WAF/RASP deployment | Out of scope per PROJECT.md. Focus is audit and testing, not production defense. | n/a |
| Mobile app penetration testing | Out of scope. v1 focuses on web apps and code repos. | Add in v2 if needed. |
| GUI-based security tool integration (Burp Suite, ZAP GUI) | Kali Docker containers run headless. GUI tools require X11 forwarding and are hard to automate. | Use CLI/API versions of tools (ZAP API, Burp REST API if available). Stick to Nmap/Nuclei/FFuf/SQLMap for DAST. |
| Custom LLM training/fine-tuning | Adds infrastructure complexity (GPU, training pipelines) without clear value for security auditing. Prompt engineering + RAG achieve the needed domain adaptation. | Invest in prompt engineering, RAG retrieval quality, and few-shot examples. |
| Real-time attack surface monitoring | Different product category (continuous monitoring vs point-in-time audits). | n/a |

## Feature Dependencies

```
Code Import -> RAG Semantic Indexing -> SAST Agent Analysis -> PoC Verification -> Report
Target Config -> Kali Sandbox Provision -> DAST Recon -> DAST Analysis -> PoC Verification -> Report
Auth -> RBAC -> Project/Scan Management -> All Agent Features
LiteLLM Config -> All Agent Features
MCP Server Registration -> Tool Discovery -> Agent Tool Use
Langfuse Setup -> All Tracing Features
```

## MVP Recommendation

Prioritize:
1. Code import (Git + local) + Target URL config
2. Kali Docker sandbox lifecycle (gold image build, ephemeral container creation/destruction)
3. Single-agent pipeline: Recon -> Analysis -> Report (simplest end-to-end flow)
4. LiteLLM integration with at least OpenAI + Anthropic
5. JSON vulnerability report output
6. CLI interface (`sectest scan --target ./app`)

Defer:
- Multi-agent collaboration graph: v2 after single-agent pipeline is stable
- PoC auto-generation: v2 after basic detection works reliably
- RAG semantic indexing: v2 after pattern-based detection proves the pipeline
- Web dashboard: v2 after CLI validates the core engine
- MCP integration: v2 after built-in tools are stable
- Team/multi-user: v2 after single-user flow works
