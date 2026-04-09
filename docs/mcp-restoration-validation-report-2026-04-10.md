# MCP 恢复验证报告（2026-04-10）

本报告记录与 legacy MCP / 流程执行恢复相关的**验证矩阵**与**推荐命令**。状态摘要见 `docs/mcp-implementation-status.md`（含关键字 `legacy_gameplayflow_tool_surface`、`stepwise_chat_three_phase`、`fix_loop_rounds_contract`）。

## 验证矩阵

| 区域 | 目的 | 命令 | 说明 |
| --- | --- | --- | --- |
| MCP 传输协议 | stdio / 工具调用契约 | `python -m unittest tests.test_mcp_transport_protocol -v` | 协议层正负路径 |
| 流程执行运行时 | 运行时门闸与执行路径 | `python -m unittest tests.test_flow_execution_runtime -v` | 与 `run_game_basic_test_flow` 等路径相关 |
| MCP 缺口审计 | 新旧工具面对照 | `tests.test_mcp_gap_audit` | 依赖 `scripts/mcp_gap_audit.py` 与可选旧仓库路径 |
| Legacy 工具面 | 快照与表面一致性 | `tests.test_legacy_tool_surface` | 与 `legacy_gameplayflow_tool_surface` 跟踪项对应 |
| Legacy 流水线 |  runner / 解析 | `tests.test_legacy_runner_pipeline` | 端到端管线契约 |
| Flow 资源契约 | JSON flow 资产 | `tests.test_flow_assets_contract` | 流程文件结构 |
| Stepwise + fix-loop | 三阶段 / 轮次契约 | `tests.test_legacy_stepwise_fixloop_live` | 与 `stepwise_chat_three_phase`、`fix_loop_rounds_contract` 相关 |
| Godot 测试编排插件 | 插件打包 | `tests.test_godot_test_orchestrator_packaging` | `addons/test_orchestrator` |
| CI legacy 覆盖 | 覆盖率门禁 | `tests.test_ci_legacy_coverage` | CI 与 legacy 相关断言 |
| 状态文档 | 关键词存在性 | `tests.test_restoration_status_document` | 防止恢复项从状态文档中丢失 |

## 一键批量命令（与 Task 8 要求一致）

在仓库根目录 `D:/AI/pointer_gpf`：

```bash
python -m unittest tests.test_mcp_transport_protocol -v
python -m unittest tests.test_flow_execution_runtime -v
python -m unittest tests.test_mcp_gap_audit tests.test_legacy_tool_surface tests.test_legacy_runner_pipeline tests.test_flow_assets_contract tests.test_legacy_stepwise_fixloop_live tests.test_godot_test_orchestrator_packaging tests.test_ci_legacy_coverage tests.test_restoration_status_document -v
```

## 执行结果（2026-04-10，仓库根 `D:/AI/pointer_gpf`）

| 命令 | 结果 |
| --- | --- |
| `python -m unittest tests.test_mcp_transport_protocol -v` | 通过（2 tests） |
| `python -m unittest tests.test_flow_execution_runtime -v` | 通过（16 tests） |
| `python -m unittest tests.test_mcp_gap_audit tests.test_legacy_tool_surface tests.test_legacy_runner_pipeline tests.test_flow_assets_contract tests.test_legacy_stepwise_fixloop_live tests.test_godot_test_orchestrator_packaging tests.test_ci_legacy_coverage tests.test_restoration_status_document -v` | 通过（21 tests） |

### 失败与阻塞

无（本次运行未出现失败）。
