# Phase 2: Engine — Multi-Agent Pipeline + Capability Registry - Context

**Gathered:** 2026-06-18
**Status:** Ready for planning

## Phase Boundary

本阶段交付：平台编排完整的 Recon→Analysis→Verification→Report Agent 管线（结构化握手机制），实现四层能力注册中心（Skill/Tool/Plugin/MCP Client），支持运行时注册与发现，以及 Phase Agent 动态生成子 Agent 的深度探索能力。

本阶段不交付：CLI 接口（Phase 4）、SAST/DAST 工具集成（Phase 4/5）、资产管理（Phase 3）、Web 面板（Phase 6）。

**覆盖需求：** CORE-02（多 Agent 协作框架）、CORE-04（四层能力注册中心）

## Implementation Decisions

### Agent 管线与握手机制

- **D-01: 仅结构化摘要握手** — 每个 Phase Agent 的 `final_output` 为结构化 JSON，作为唯一握手数据传递给下游 Agent。各 Agent 不共享 conversation history。Planner（gsd-planner）设计每个 Agent 的输入/输出 JSON schema。
- **D-02: 阶段顺序约定** — Recon→Analysis→Verification→Report 为固定顺序。每个阶段 Agent 只做该阶段的事，不要跨阶段工作。
- **D-03: 上下文隔离** — 各 Agent 拥有独立 Runner.run() 调用。每个 Agent 创建时为全新 Agent 实例，不含上游 conversation history。只有 final_output 被传递。

### 能力注册中心

- **D-04: 文件系统注册** — Skill（.md 文件）、Tool（.py function_tool）、Plugin（.py Plugin 类）通过目录结构自动发现。启动时扫描 `src/sectest/skills/`、`src/sectest/tools/`、`src/sectest/plugins/` 目录。新增能力只需新增文件，无需修改注册代码。
- **D-05: 四层分类** — Skill（Markdown 知识文档）→ Tool（沙箱可执行命令）→ Plugin（Skill+Tool 组合的漏洞检查）→ MCP Client（外部 MCP Server 接入）。TypeScript 定义各层接口，Python 实现。
- **D-06: Plugin 组合模式** — Plugin 同时引用一个 Skill（知识）和一个 Tool（执行），形成可复用的漏洞检查策略。例如 "SQL Injection Scanner" Plugin 组合 SQL injection 知识 Skill + SQLMap Tool。

### 子 Agent 机制

- **D-07: 独立沙箱隔离** — Phase Agent 生成子 Agent 时，子 Agent 获得独立的 SandboxSession（通过 SandboxManager.create_session()）。Phase 1 的 SandboxManager 已经完整支持多 session 并行。
- **D-08: spawn 语义** — 父 Agent 生成子 Agent（独立的 Agent + Runner），子 Agent 独立执行探索路径、回报结果（结构化 JSON）后销毁。父 Agent 在 `final_output` 中聚合子 Agent 发现。

### Claude's Discretion

以下领域由下游 Agent（researcher、planner）自行决定：
- 各 Phase Agent 的具体 JSON schema 设计
- Skill/Tool/Plugin 目录扫描的实现细节
- 能力注册中心的数据结构（dict / registry class）
- 子 Agent 的生命周期管理（timeout、重试、错误处理）
- MCP Client 的具体集成方式（Phase 2 仅留接口，实际 MCP 集成交付 Phase 5）

## Canonical References

**下游 Agent 在规划和实施前必须阅读。**

### 项目核心
- `.planning/ROADMAP.md` — 7 阶段路线图，Phase 2 目标、成功标准、依赖关系
- `.planning/PROJECT.md` — 项目定义、核心价值、关键决策记录
- `.planning/REQUIREMENTS.md` — CORE-02（多 Agent 协作）、CORE-04（能力注册中心）

### 架构与调研
- `.planning/research/ARCHITECTURE.md` — 六层架构设计，Agent Orchestration Layer + Capability Registry 层
- `.planning/research/STACK.md` — openai-agents SDK 0.17.5 技术栈
- `.planning/research/SUMMARY.md` — 多 Agent 编排设计、Pipeline with Handoffs 模式

### Phase 1 代码（已实现）
- `src/sectest/agents/recon.py` — Phase 1 ReconAgent 基准实现（function_tool 模式、SandboxSession 用法）
- `src/sectest/sandbox/manager.py` — SandboxManager（多 session 并行已就绪）
- `src/sectest/llm/provider.py` — LiteLLMModelProvider（所有 Agent 共用）
- `tests/test_recon_agent.py` — Agent 测试模式参考
- `tests/test_e2e_smoke.py` — E2E 测试模式参考

## Existing Code Insights

### 可复用资产
- **SandboxManager.create_session()** — 已支持并发多 session。子 Agent 独立沙箱直接复用。
- **LiteLLMModelProvider** — 所有 Agent 共用同一 provider，无需新代码。
- **function_tool 模式** — Phase 1 ReconAgent 确立了 `@function_tool` 装饰 `session.exec()` 的模式。所有 Phase Agent 遵循此模式。

### 已确立的模式
- **L-01 合规** — 只有 `sandbox/manager.py` 导入 `agents.sandbox`。所有 Agent 使用 `SandboxSession.exec()` 和 `function_tool`。
- **结构化输出解析** — Agent final_output 通过 json 解析为 dict。`_parse_output()` 处理 JSON + markdown fence + raw text 三种情况。
- **流式进度** — ProgressEmitter JSON 行输出（Phase 1）。Phase 2 可扩展 phase 类型（新增 ANALYSIS、VERIFICATION、REPORT 等阶段）。

### 集成点
- **Agent pipeline** → 新 Agent（AnalysisAgent、VerificationAgent、ReportAgent）复用 `ReconAgent` 的 function_tool + SandboxSession 模式
- **Capability registry** → 新 `src/sectest/skills/`、`src/sectest/tools/`、`src/sectest/plugins/` 目录

## Specific Ideas

无特定用户偏好——按标准方式实现。

## Deferred Ideas

None — 讨论过程未超出阶段范围。

---

*Phase: 2-Engine*
*Context gathered: 2026-06-18*
