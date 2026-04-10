# MCP 真实运行与非侵入输入设计文档

## 1. 问题定义

当前基础测试流程虽然可以完成步骤执行与三段播报，但默认路径是“已运行编辑器 + 文件桥接”，没有把“启动后按 F5 进入真实游戏态”作为强制前置条件，也没有把“输入模拟不影响系统真实鼠标键盘”固化为显式契约字段与验收项。

本设计文档用于恢复并固定以下核心要求：基础测试流程必须运行在真实游戏态，且输入注入必须是游戏内虚拟输入，不干扰用户操作系统层面的鼠标键盘。

## 2. 约定来源（历史规则回溯）

以下内容来自历史规则与历史实现，作为本次设计的依据：

- `./historical/chat-first-stepwise-core.mdc`（历史样例）
  - 主观测渠道为 shell，逐步输出。
  - 每步固定 `started -> result -> verify`，失败即停。
- `./historical/06-chat-first-status-and-requirements.md`（历史样例）
  - 要求聊天播报与游戏内动作时序一致。
  - 要求可审计（聊天时间戳与游戏时间戳可对照）。
  - 在思考间隙允许暂停游戏时间，避免状态偷跑。
- 历史实现样例 `scripts/test/test_driver_actions.gd`
  - 输入执行通过 `Input.parse_input_event(...)` 注入到游戏进程内。
  - 点击/移动/滚轮/拖拽均在游戏内部处理，不需要接管 OS 全局鼠标键盘。

## 3. 核心规则（必须满足）

### 3.1 真实运行规则

1. 运行基础测试流程时，必须确保目标项目进入“真实游戏运行态”（Play 模式，F5 等价语义）。
2. 禁止把“仅编辑器空闲态 + 最终 JSON 返回”视为满足要求。
3. 执行报告必须记录运行态来源：
   - `runtime_mode`: `play_mode` | `editor_bridge`
   - `runtime_entry`: `f5_equivalent` | `already_running_play_session` | `unknown`
4. 若检测到引擎未打开，系统必须自动执行“打开引擎 + 进入 Play 态”尝试；不得把该前置操作转嫁给用户。
5. 仅当系统自动启动与自动进入 Play 态均失败时，才允许失败返回；失败详情必须包含：已执行动作、当前阻塞点、下一步可直接执行动作。

### 3.2 输入隔离规则

1. 所有自动化输入必须走“游戏内虚拟输入注入”路径。
2. 禁止依赖会占用 OS 全局输入焦点的自动化方案（例如系统级鼠标键盘抢占）。
3. 执行报告必须记录输入模式：
   - `input_mode`: `in_engine_virtual_input`
   - `os_input_interference`: `false`（布尔）

### 3.3 播报与门控规则

1. 每步对外可见事件必须是 `started -> result -> verify`。
2. 任一步 `verify` 失败立即停止。
3. shell 播报保留两行结构（按阶段输出）：
   - 时间戳行：`[GPF-FLOW-TS] YYYY-MM-DD T HH:MM:SS`（本地系统时间）。
   - 中文语义行：只保留用户可读语义，不展示技术字段。

4. 播报模板只定义句式，步骤文案必须来自 flow 功能语义。
5. 中文语义句式固定为：
   - `开始执行:...`
   - `执行结果:...(通过/失败)`
   - `验证结论:通过/失败-目标:...`
6. 播报中禁止输出技术字段行（如 `run=`、`phase=`、`id=`、`action=`、`bridge_ok=`、`verified=`）。
7. 一次测试流程结束后（通过/失败/超时/门禁失败），必须发起关闭动作；关闭语义为“停止 Play 运行态并回到编辑器空闲态”。
8. 默认行为下应保留编辑器进程，不得把“停止 Play”错误实现为“退出整个编辑器”。

### 3.4 运行态诊断与失败衔接

1. 在等待文件桥响应期间，实现应轮询 `pointer_gpf/tmp/runtime_diagnostics.json`（契约见 `mcp/adapter_contract_v1.json` 与 `docs/design/99-tools/16-pointer-gpf-runtime-diagnostics-bridge.md`）。
2. 当诊断为 `error`/`fatal` 时，应返回 `ENGINE_RUNTIME_STALLED`（或等价结构化错误），并在 `details` 中附带 `suggested_next_tool: auto_fix_game_bug` 与可复制的 `issue` 草稿，避免代理在引擎已报错时仍表现为「长时间无反馈等待」。

### 3.5 虚拟鼠标可视化规则

1. 自动化输入执行时，必须在游戏画面中实时显示“虚拟鼠标位置”。
2. 可视化标记采用红色方形（与旧版一致），用于让人类观察输入落点与移动轨迹。
3. 标记属于游戏内覆盖层，不得影响玩家真实系统鼠标光标与键盘输入。
4. 对 `click`、`drag`、`moveMouse` 等输入动作，标记位置必须与实际注入坐标一致。

## 4. 目标架构

### 4.1 执行前置检查层（Runtime Gate）

- 新增运行前检查：
  - 目标 Godot 项目是否已进入 Play 态。
  - 若未进入，先自动拉起引擎（若未打开），再自动触发“F5 等价启动”流程。
- 启动失败直接返回结构化错误，不进入 step 执行。
- Godot 可执行路径来源优先级固定为：
  1. 项目内配置 `tools/game-test-runner/config/godot_executable.json`
  2. 调用参数（`godot_executable` / `godot_editor_executable` / `godot_path`）
  3. 环境变量（`GODOT_EXE` / `GODOT_EDITOR_PATH` / `GODOT_PATH`）
- 禁止使用硬编码本地路径作为自动发现兜底，避免误开错误项目。

### 4.2 输入执行层（Input Virtual Layer）

- 输入动作统一映射到“游戏内注入接口”（点击、移动、滚轮、拖拽、按键）。
- 在适配器契约里声明输入来源与隔离能力。
- 对无法确认隔离性的输入路径直接阻断。
- 对“点击后立即断言”的状态判断，必须支持短窗口轮询（`wait + until.hint`）以覆盖单帧时序差异，避免同帧检查误判。
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
- `RUNTIME_GATE_FAILED.details` 必须包含：
  - `engine_bootstrap.target_project_root`
  - `engine_bootstrap.selected_executable`
  - `engine_bootstrap.launch_process_id`
  - `blocking_point`
  - `next_actions[]`
- 执行结束返回中的 `project_close` 必须包含：
  - `requested`（是否发起关闭）
  - `acknowledged`（桥接是否确认）
  - `timeout_ms`
  - `reason` 或 `message`

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
4. 每个阶段播报符合两行结构：本地时间戳行 + 中文语义行。
5. shell 输出中不包含 `run=`、`phase=`、`id=`、`action=`、`bridge_ok=`、`verified=` 技术字段。
6. 中文语义播报包含三类句式：`开始执行`、`执行结果`、`验证结论`。
7. 人工在本机移动鼠标/键盘时，不出现被测试脚本抢占或控制的现象。
8. 任一步校验失败后流程立即停止，且报告给出失败步骤与原因。
9. 执行 `click/drag/moveMouse` 时，游戏画面可见红色方形实时跟随到注入位置，且落点与动作一致。
10. 流程结束结果中包含项目关闭证据（例如 `project_close.requested=true`）。
11. 流程结束后 `runtime_gate.json` 应回到 `runtime_mode=editor_bridge`（表示 Play 运行态已停止）。

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
- 收尾语义：
  - `closeProject` 已固定为“停止 Play 运行态，不退出编辑器”。
- **停止 Play 的标志文件（与契约对齐）**：
  - 路径（相对项目根）：`pointer_gpf/tmp/auto_stop_play_mode.flag`（与 `mcp/adapter_contract_v1.json` 的 `runtime_bridge.auto_stop_play_mode_flag_rel` 一致）。
  - 由 `runtime_bridge.gd` 在处理 `closeProject` 时写入；载荷需含 `issued_at_unix`（Unix 秒）供编辑器插件判断新鲜度；**写文件失败**时须返回 `ok=false`、`error.code=STOP_FLAG_WRITE_FAILED`，不得冒充成功。
  - `plugin.gd` 轮询消费该文件并调用 `EditorInterface.stop_playing_scene()`；须忽略过期/畸形/无时间戳的残留文件，并在插件加载时清除残留标志，避免用户手动 F5 后被误停（详见模板与 `examples/godot_minimal` 中实现）。
- 运行桥接挂载：
  - `godot_plugin_template/addons/pointer_gpf/plugin.gd` 使用 autoload 方式挂载 `runtime_bridge.gd`，避免编辑器树挂载导致的运行态失真。
- **`runtime_diagnostics.json` 当前覆盖范围（2026-04）**：
  - **桥接步骤结果**：`runtime_bridge.gd` 在分发命令后调用 `note_bridge_dispatch`；失败应答会将快照 `severity` 提升为 `error`。
  - **引擎 `_log_error` 路径（Godot 4.5+）**：参考实现通过 `OS.add_logger` 注册 `Logger` 子类 `runtime_diagnostics_logger.gd`，在 `_log_error` 中把 `rationale`、文件、行号与 `ScriptBacktrace` 文本入队，由 `runtime_diagnostics_writer.gd` 在主线程 `tick_flush` 中合并写入；**不**经过 `_log_message` 的 `push_error`/`push_warning` 仍以引擎文档为准（见官方 Logging 教程中 `_log_message` 与 `_log_error` 的差异说明）。
  - **仍可能缺失的情况**：主线程死锁、磁盘写入失败、或未走 `_log_error` 的仅 stdout 输出等；MCP 侧仍须把 `step_timeout` 与 `TIMEOUT` 视为合法失败路径。
- **失败收尾与可选硬杀进程**：
  - 运行失败时 MCP 会在错误详情中附带 **`hard_teardown`**（关闭请求是否发出、是否得到应答、是否建议人工检查引擎进程）。
  - **`force_terminate_godot_on_flow_failure`**（默认 `false`）：仅在「已请求 `closeProject` 但未收到应答」时，尝试结束命令行中包含 `project_root` 的 Godot 进程；有误杀同一工程编辑器实例的风险，须由调用方显式开启。
- **跑流程默认自动修与 L2（2026-04-10 起）**：
  - `run_game_basic_test_flow` / `run_game_basic_test_flow_by_current_state` 默认 **`auto_repair: true`**（可用参数或 **`GPF_AUTO_REPAIR_DEFAULT=0`** 关闭）；失败时在 `max_repair_rounds` / `auto_fix_max_cycles` 上限内调用 `auto_fix_game_bug` 并复测。
  - **`GPF_REPAIR_BACKEND_CMD`**：可选 L2 子进程，在 `bug_fix_strategies` 未应用补丁后执行；约定见 `docs/mcp-basic-test-flow-reference-usage.md` 与 `mcp/repair_backend.py`。

## 9. 新项目基础流程自动生成契约（真实化版本）

### 9.1 目标

当用户在一个新 Godot 项目上调用 `design_game_basic_test_flow` 时，系统必须生成“可执行 + 可验证”的最小基础流程；若证据不足，必须返回结构化阻塞信息，不得生成模板占位流程。

### 9.2 输入契约（生成前证据）

- 上下文来源：`pointer_gpf/project_context/index.json`
- 最小证据字段：
  - `flow_candidates.action_candidates`（候选动作）
  - `flow_candidates.assertion_candidates`（候选断言）
  - `scene_signals.button_nodes`（可交互节点来源）
  - `scene_signals.control_nodes`（可验证 UI 状态来源）
- 候选动作过滤规则：
  - 仅允许 `click` / `wait`
  - `click` 必须携带可解析目标提示（如 `target_hint`）
  - `wait` 必须携带可解析条件提示（如 `until_hint`）
- 存读档步骤启用规则：
  - 仅当“脚本能力证据 + UI 入口证据”同时成立时才允许注入 `save_game_smoke/load_game_smoke`
  - 仅关键词命中不构成启用条件

### 9.3 输出契约（生成结果）

- 成功生成（`status=generated`）时，返回必须包含：
  - `flow_file`
  - `step_count`
  - `generation_evidence`
- `generation_evidence` 最小字段：
  - `candidate_counts`（原始/过滤后数量）
  - `save_load`（启用判定与证据摘要）
  - `selected_steps`（每个关键步骤对应的候选 id 与证据）
  - `blocked_reasons`（若无阻塞可为空数组）
- 阻塞返回（`status=blocked`）时，返回必须包含：
  - `reasons`（例如 `no_executable_action_candidates`）
  - `generation_evidence`
  - `flow_file` 为空字符串

### 9.4 最小真实流程约束

- 生成流程必须至少包含：
  1. `launch_game`
  2. 至少 1 个有证据的交互步骤（通常映射为 `enter_game`）
  3. 至少 1 个验证步骤（`check`）
  4. `snapshot_end`
- 若无法满足第 2 或第 3 项，必须返回 `blocked`，禁止写入“看起来完整但不可执行”的流程。

### 9.5 执行前后联动约束

- `run_game_basic_test_flow_by_current_state` 在收到 `status=blocked` 的生成结果时，必须立即返回结构化错误（`FLOW_GENERATION_BLOCKED`），不得继续执行。
- 执行结果中的 `gameplay_runnability` 必须绑定真实性字段（`runtime_mode`、`runtime_gate_passed`、`input_mode`、`os_input_interference`），避免“协议通过但非真实运行”被误判为通过。
