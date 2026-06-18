# Phase 1: Foundation — Kali Sandbox + LLM Gateway - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-18
**Phase:** 1-Foundation-Kali-Sandbox-LLM-Gateway
**Areas discussed:** 容器生命周期

---

## 容器生命周期

| Option | Description | Selected |
|--------|-------------|----------|
| 每次扫描一个容器（per-scan） | 整个扫描周期使用 1 个容器，proxy/tool server 启动一次，所有工具共用文件系统和网络状态。简单、快，但工具间存在交叉污染风险。 | ✓ |
| 每次工具调用一个容器（per-tool） | 每次调用 Nmap/Semgrep/PoC 等启动独立容器，执行完立即销毁。强隔离，但每次需要重新 apt install 工具。 | |
| 混合策略（per-scan + PoC 子容器） | 核心容器 per-scan 运行 proxy 和 tool server，PoC 验证时 spawn 独立子容器。兼顾共享便利性和高风险操作隔离。 | |

**User's choice:** 每次扫描一个容器（per-scan）
**Notes:** 用户选择了最简单的 per-scan 模型。后续 Phase（Phase 4 DAST PoC 验证阶段）如需更高隔离性，可以引入子容器策略——此决策不锁定未来扩展。

---

### 容器创建时机

| Option | Description | Selected |
|--------|-------------|----------|
| 扫描开始时创建（lazy init） | 扫描启动时同步创建容器。简单直接。首次扫描可能因镜像拉取有延迟。 | ✓ |
| 平台启动时预创建（eager init） | 平台启动时预拉取镜像并预热容器池。首次扫描无等待，但增加平台启动时间和空闲资源占用。 | |

**User's choice:** 扫描开始时创建（lazy init）
**Notes:** 这是 CLI-first 策略的自然配套。镜像仍然在平台启动时预拉取（已锁定决策 L-06），但容器实例在扫描启动时才创建。

---

### 容器销毁时机

| Option | Description | Selected |
|--------|-------------|----------|
| 扫描结束后立即销毁 | 正常结束后马上销毁容器。资源干净，但无法事后调试。 | |
| 延迟销毁（保留 N 分钟用于调试） | 扫描结束后保留容器一段窗口期，允许 docker exec 查看现场。超时后自动清理。 | ✓ |

**User's choice:** 延迟销毁

---

### 延迟销毁保留时长

| Option | Description | Selected |
|--------|-------------|----------|
| 5 分钟 | 够快速检查，几乎不占用资源。 | |
| 15 分钟 | 适合较长的调试会话，平衡了调试需求和资源占用。 | ✓ |
| 30 分钟 | 充足的调试时间，但容器占用资源较久。 | |

**User's choice:** 15 分钟
**Notes:** 15 分钟给用户合理的调试窗口。实现建议：扫描结束后启动一个 15 分钟倒计时定时器，超时自动调用 SandboxManager.destroy()。

---

## Claude's Discretion

以下领域由下游 Agent 自行决定：
- 容器资源限制的具体数值（CPU/memory 配额）
- Docker volume 挂载策略的细节
- 容器日志收集和持久化方式
- 镜像拉取进度展示的具体 UI/CLI 实现

## Deferred Ideas

None — 讨论过程未超出阶段范围。
