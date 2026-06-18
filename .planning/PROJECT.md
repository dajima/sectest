# Strix — Unified AI Security Testing Platform

## What This Is

Strix 是一个面向安全渗透测试人员的 AI 驱动安全审计平台，统一融合 SAST（静态代码审计）和 DAST（动态渗透测试）能力。平台基于多 Agent 协作架构，在 Kali Linux Docker 沙箱中运行完整的安全工具链，通过顺序流水线（侦察→分析→验证→报告）驱动主体流程，同时支持动态 Agent 编排查进行开放式深度探索。

目标用户是安全渗透测试工程师——平台提供 CLI 和 Web 双界面，支持本地单机快速扫描和远程多用户团队部署。

## Core Value

AI agent 能够自主完成从代码审计到动态渗透的端到端安全评估，在 Kali 沙箱中运行真实安全工具，通过 PoC 严格验证每个发现的漏洞，输出可操作的安全报告。

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] SAST 静态代码审计 — 源码导入、RAG 语义索引、多 agent 深度审计
- [ ] DAST 动态渗透测试 — 实时 Web 应用/API 攻击、代理截获、浏览器自动化
- [ ] Docker Kali 沙箱 — 统一工具集、隔离执行、SandboxAgent 绑定
- [ ] 多 Agent 编排 — 顺序流水线（侦察→分析→验证→报告）+ 动态 spawn 深度探索
- [ ] 能力注册系统 — Skill/Tool/Plugin/MCP Client 四层分类管理，可快速扩展
- [ ] PoC 自动生成与验证 — Fuzzing Harness、沙箱执行、自修复重试
- [ ] Web 管理面板 — React 前端，实时监控、报告查看、项目管理
- [ ] CLI 本地工具 — 命令行扫描，本地单机快速使用
- [ ] 观测与调试 — Agent 执行链路追踪、Token 消耗监控、扫描可回放
- [ ] 混合部署 — 本地单机 + 远程服务器多用户并发

### Out of Scope

- 生产环境安全监控 (WAF/RASP) — 聚焦审计和测试，不涉及运行时防护
- 非 Kali 的沙箱镜像 — Kali 统一所有工具，避免维护多镜像
- 移动端 App 渗透测试 — v1 聚焦 Web 应用和代码仓库

## Context

**现有参考项目：**

- **Strix (usestrix/strix)**: Apache 2.0 许可，openai-agents SDK 架构的 AI 渗透测试工具。核心优势：动态多 agent 协作用图、Docker 沙箱运行时、完整黑客工具包（HTTP 代理、浏览器自动化、终端、Python 运行时）、CLI/TUI 界面。22.8k GitHub stars。
- **DeepAudit (lintsinghua/DeepAudit)**: AGPL 3.0 许可，LangChain+LangGraph 架构的 AI 代码安全审计平台。核心优势：4-agent 顺序流水线（Orchestrator→Recon→Analysis→Verification）、RAG 向量语义索引（ChromaDB）、SAST 工具集成（Semgrep/Bandit/Gitleaks）、沙箱 PoC 验证、React Web 面板。6.4k GitHub stars，49 个 CVE 发现记录。

**两者互补关系：**
- Strix 擅长运行时动态测试（IDOR、权限绕过、CSRF、业务逻辑）但对代码级语义分析较弱
- DeepAudit 擅长代码级静态审计（注入、硬编码密钥、弱加密、路径穿越）但不支持实时目标测试
- 新平台取两者之长，统一为单一架构

**技术环境（继承自两个参考项目）：**
- Python 3.12+ + uv 包管理器
- openai-agents SDK（Agent 编排核心）
- FastAPI（Web API 后端）
- React 18 + TypeScript + Vite（Web 前端）
- Docker Engine API（沙箱生命周期）
- LiteLLM（多 LLM 提供商路由）
- ChromaDB（RAG 向量检索）
- PostgreSQL（持久化存储）
- Redis（缓存/队列）

**已知约束：**
- openai-agents SDK 必须保留——它是 Python only，决定了后端语言
- Kali 镜像体积大（~3GB+），首次 pull 需要时间
- AGPL 3.0 的 DeepAudit 代码不能直接复制——需要重新设计等效能力

## Constraints

- **Runtime:** Docker 强依赖（Kali 沙箱），Python 3.12+
- **Agent SDK:** openai-agents SDK，Python only
- **Platform:** Windows / Linux / macOS 宿主机
- **Deployment:** 单机 CLI 模式 + Docker Compose 多服务模式
- **License:** 待定（需避开 AGPL 3.0 代码直接复制）
- **Security:** LLM API key 通过环境变量或加密存储，不硬编码

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| openai-agents SDK 作为 Agent 框架 | 成熟的 SandboxAgent 抽象、streaming 执行循环、function_tool 注册模式、RunHooks 生命周期——这些设计经过验证且可扩展 | — Pending |
| Kali Linux 作为统一沙箱镜像 | 一个镜像包含所有 SAST+DAST 工具，上游维护更新，避免自定义工具镜像的维护负担 | — Pending |
| 全新架构设计 | 两边代码许可不兼容（Apache 2.0 vs AGPL 3.0），且直接移植会带入历史设计债 | — Pending |
| 顺序流水线 + 动态探索双模式 | 审计任务需要可控的阶段流程，但安全测试也需要开放式探索才能发现非预期漏洞 | — Pending |
| Skill/Tool/Plugin/MCP Client 四层分类 | 知识（Skill）和执行（Tool）解耦，Plugin 组合两者形成漏洞测试策略，MCP 接入外部生态 | — Pending |
| 混合部署模型 | 安全工程师需要本地快速扫描（CLI），也需要团队协作平台（Web 远程部署） | — Pending |
| 前后端分离 | Python 后端 + React 前端是 AI 安全工具的主流模式，各自独立开发和部署 | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-18 after initialization*
