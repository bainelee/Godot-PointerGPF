# MCP 真实运行与非侵入输入设计文档

## 1. 问题定义

当前基础测试流程虽然可以完成步骤执行与三段播报，但默认路径是“已运行编辑器 + 文件桥接”，没有把“启动后按 F5 进入真实游戏态”作为强制前置条件，也没有把“输入模拟不影响系统真实鼠标键盘”固化为显式契约字段与验收项。

本设计文档用于恢复并固定以下核心要求：基础测试流程必须运行在真实游戏态，且输入注入必须是游戏内虚拟输入，不干扰用户操作系统层面的鼠标键盘。

## 2. 约定来源（历史规则回溯）

以下内容来自旧规则与旧实现，作为本次设计的依据：

- `./.tmp_old_archives/chat-first-stepwise-core.mdc`
  - 主观测渠道为 shell，逐步输出。
  - 每步固定 `started -> result -> verify`，失败即停。
- `./.tmp_old_archives/06-chat-first-status-and-requirements.md`
  - 要求聊天播报与游戏内动作时序一致。
  - 要求可审计（聊天时间戳与游戏时间戳可对照）。
  - 在思考间隙允许暂停游戏时间，避免状态偷跑。
- 旧实现 `bainelee/old_archives_sp/scripts/test/test_driver_actions.gd`
  - 输入执行通过 `Input.parse_input_event(...)` 注入到游戏进程内。
  - 点击/移动/滚轮/拖拽均在游戏内部处理，不需要接管 OS 全局鼠标键盘。

## 3. 核心规则（必须满足）

### 3.1 真实运行规则

1. 运行基础测试流程时，必须确保目标项目进入“真实游戏运行态”（Play 模式，F5 等价语义）。
2. 禁止把“仅编辑器空闲态 + 最终 JSON 返回”视为满足要求。
3. 执行报告必须记录运行态来源：
   - `runtime_mode`: `play_mode` | `editor_bridge`
   - `runtime_entry`: `f5_equivalent` | `already_running_play_session` | `unknown`

### 3.2 输入隔离规则

1. 所有自动化输入必须走“游戏内虚拟输入注入”路径。
2. 禁止依赖会占用 OS 全局输入焦点的自动化方案（例如系统级鼠标键盘抢占）。
3. 执行报告必须记录输入模式：
   - `input_mode`: `in_engine_virtual_input`
   - `os_input_interference`: `false`（布尔）

### 3.3 播报与门控规则

1. 每步对外可见事件必须是 `started -> result -> verify`。
2. 任一步 `verify` 失败立即停止。
3. shell 播报保留两行结构：
   - 时间戳行
   - 中文语义行
4. 播报模板只定义句式，步骤文案必须来自 flow 功能语义。

### 3.4 虚拟鼠标可视化规则

1. 自动化输入执行时，必须在游戏画面中实时显示“虚拟鼠标位置”。
2. 可视化标记采用红色方形（与旧版一致），用于让人类观察输入落点与移动轨迹。
3. 标记属于游戏内覆盖层，不得影响玩家真实系统鼠标光标与键盘输入。
4. 对 `click`、`drag`、`moveMouse` 等输入动作，标记位置必须与实际注入坐标一致。

## 4. 目标架构

### 4.1 执行前置检查层（Runtime Gate）

- 新增运行前检查：
  - 目标 Godot 项目是否已进入 Play 态。
  - 若未进入，自动触发“F5 等价启动”流程。
- 启动失败直接返回结构化错误，不进入 step 执行。

### 4.2 输入执行层（Input Virtual Layer）

- 输入动作统一映射到“游戏内注入接口”（点击、移动、滚轮、拖拽、按键）。
- 在适配器契约里声明输入来源与隔离能力。
- 对无法确认隔离性的输入路径直接阻断。
- 增加“虚拟鼠标可视化层”：
  - 每次输入步骤在画面上刷新红色方形到当前注入坐标；
  - 支持最小显示时长（便于观察）；
  - 在步骤结束或超时后自动回收，不残留无效标记。

### 4.3 审计层（Evidence Layer）

- `execution_report` 新增字段：
  - `runtime_mode`
  - `runtime_entry`
  - `input_mode`
  - `os_input_interference`
  - `runtime_gate_passed`
- `step_broadcast_summary` 保持现有结构，同时增加：
  - `protocol_mode`: `three_phase`
  - `fail_fast_on_verify`: `true`

## 5. 与现有文档的关系

本文件与以下文档共同组成约束集合：

- `docs/stepwise-shell-broadcast-standard.md`：播报格式与文案来源规则。
- `docs/godot-adapter-contract-v1.md`：适配器动作与字段契约。
- `docs/mcp-testing-spec.md`：测试方法与验收流程。

若文档冲突，以本文件中的“真实运行规则”和“输入隔离规则”为高优先级要求。

## 6. 验收标准

必须同时通过以下验收项：

1. 执行基础测试流程时，报告明确显示 `runtime_mode=play_mode`。
2. 报告明确显示 `input_mode=in_engine_virtual_input` 且 `os_input_interference=false`。
3. shell 中每一步均有 `started/result/verify` 三阶段播报。
4. 人工在本机移动鼠标/键盘时，不出现被测试脚本抢占或控制的现象。
5. 任一步校验失败后流程立即停止，且报告给出失败步骤与原因。
6. 执行 `click/drag/moveMouse` 时，游戏画面可见红色方形实时跟随到注入位置，且落点与动作一致。

## 7. 分阶段落地计划

### Phase A：契约补齐（文档 + 字段）

- 扩展 `godot-adapter-contract-v1.md` 与运行产物字段定义。
- 扩展 `execution_report` 数据结构与断言脚本。

### Phase B：运行态门控

- 在 `run_game_basic_test_flow*` 入口增加 Play 态检查与 F5 等价启动。
- 失败路径标准化输出。

### Phase C：输入隔离校验

- 对输入动作执行链统一收口到游戏内注入接口。
- 增加 `os_input_interference=false` 的运行时证据采集与测试断言。

### Phase D：回归验证

- 在 `examples/godot_minimal` 与至少一个非示例项目跑完整回归。
- 输出完整执行产物与播报审计结果。

## 8. 当前实现映射（2026-04）

- 契约字段：
  - `mcp/adapter_contract_v1.json` 已补充 `runtime_requirements`，并新增错误码 `NOT_IN_PLAY_MODE`、`INPUT_PATH_BLOCKED`。
- 运行态门控：
  - `mcp/server.py` 的 `run_game_basic_test_flow*` 已支持 `require_play_mode`，门控失败返回 `RUNTIME_GATE_FAILED`。
- 审计字段：
  - `mcp/flow_execution.py` 的 `execution_report` 已输出 `runtime_mode/runtime_entry/input_mode/os_input_interference/runtime_gate_passed` 与 `step_broadcast_summary`。
- 输入与可视化：
  - `godot_plugin_template/addons/pointer_gpf/runtime_bridge.gd` 已实现引擎内虚拟输入分发（`click`/`moveMouse`/`drag`）与红色方形虚拟鼠标覆盖层。
- CI 断言：
  - `scripts/assert-mcp-artifacts.ps1` 与 `mcp-smoke/mcp-integration` 已加入执行层 runtime/input 字段断言。
