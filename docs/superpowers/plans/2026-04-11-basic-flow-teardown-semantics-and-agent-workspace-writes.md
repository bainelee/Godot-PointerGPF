# 基础测试流程收尾语义与代理侧文件写入说明（分析 + 可选改造计划）

> **给代理执行者：** 若下文「可选改造」要落地，优先使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans，按 Task 勾选推进。

**Goal:** 说清「跑完 `run_game_basic_test_flow` 后仍觉得游戏/运行态没关掉」的**代码与规则层面原因**；说明用户观察到「代理在跑流程时改代码」对应**哪些真实文件写入**；给出与「通过 Godot 与插件的稳定接口结束游戏运行」一致的改造与排障任务。**不再**把用户口述的「关闭进程」偷换成「强杀 OS 进程」或「退出编辑器二选一」——那是先前计划表述错误，已在此纠正。

**Architecture:** 收尾主路径是：MCP `close_project_on_finish` → 桥接 `closeProject` → `runtime_bridge.gd` 写 `auto_stop_play_mode.flag` → **编辑器插件** `plugin.gd` 在 `_process` 中轮询消费该标志并调用 **`EditorInterface.stop_playing_scene()`**（与编辑器 UI「停止运行」同源能力）。GPF 插件常驻编辑器进程内，**具备**操作引擎运行态的条件；若用户仍看到「没关掉」，工程上应查 **标志是否被消费、时间窗、ack 与实际 stop 的时序、或运行形态（编辑器 Play vs 独立进程）**，而不是把问题降维成「只能靠强杀或关整个编辑器」。

**Tech Stack:** Python（`mcp/server.py`）、Godot 4.x GDScript（`godot_plugin_template/addons/pointer_gpf/plugin.gd`、`runtime_bridge.gd`）、仓库 Cursor 规则（`.cursor/rules/gpf-runtime-test-mandatory-play-mode.mdc`）。

---

## 0. 措辞纠正（相对旧版计划）

| 错误表述 | 纠正 |
|----------|------|
| 把「关闭进程」等同于「强杀 / 退出编辑器二选一」 | 需求方从未要求「强制关闭进程」；「关闭进程」在此仓库语境应对齐为 **结束当前游戏运行实例**（编辑器内即 **停止运行**），由 **Godot 已暴露的编辑器 API**（如 `EditorInterface.stop_playing_scene()`）完成，与 UI 按钮同源。 |
| 暗示「没有插件能走的稳定关游戏路径」 | 插件 **已经** 在消费 stop 标志后调用 `EditorInterface.stop_playing_scene()`；问题应落在 **链路是否可靠、语义是否对用户可见、或 MCP 注释/命名是否让人误解**，而不是扩写成 OS 层极端手段。 |
| `force_terminate_godot_on_flow_failure` 与用户目标并列 | 该字段是 MCP 在 **桥接 close 长期无确认** 等少数情况下的 **运维兜底**，**不是**满足「关闭游戏运行」的主路径，**不得**在计划里与用户表述对立成「二选一」。 |

---

## 1. 文件与职责（与本次问题直接相关）

| 路径 | 职责 |
|------|------|
| `mcp/server.py` | `_request_project_close_once`：写 `closeProject` 并等 ack；`_hard_teardown_for_flow_failure`：失败时结构化证据（含可选 OS 层兜底，见第 2.4 节脚注） |
| `godot_plugin_template/addons/pointer_gpf/runtime_bridge.gd` | 解析 `closeProject`：写 `auto_stop_play_mode.flag` |
| `godot_plugin_template/addons/pointer_gpf/plugin.gd` | 轮询消费 stop 标志，调用 **`EditorInterface.stop_playing_scene()`** |
| `.cursor/rules/gpf-runtime-test-mandatory-play-mode.mdc` | 约定收尾为「停止 Play 运行态」；其中「默认保留编辑器进程」指 **编辑器应用进程可保留**，不等于「允许游戏一直处于 Play 运行态不结束」 |
| `tests/test_mcp_hard_teardown.py` | `hard_teardown` / `force_terminate` 分支单测（兜底路径） |
| `examples/godot_minimal/addons/pointer_gpf/` | 与模板同步的插件副本 |

---

## 2. 分析：为什么仍可能出现「游戏没关掉」的感受

### 2.1 命名误导：`closeProject` 实际只做「请求停止运行」

桥接里 `closeProject` **并不**关闭操作系统上的 Godot 应用；它只触发「写停止 Play 标志」：

```197:210:godot_plugin_template/addons/pointer_gpf/runtime_bridge.gd
        "closeproject":
            if not _request_stop_play_mode():
                return _error_payload(
                    "STOP_FLAG_WRITE_FAILED",
                    "could not write auto_stop_play_mode.flag",
                    seq,
                    run_id
                )
            return {
                "ok": true,
                "seq": seq,
                "run_id": run_id,
                "message": "closeProject acknowledged",
            }
```

MCP 侧注释「stop Play, keep editor」中的 **keep editor** 指：**不退出 Godot 编辑器应用**；**不是**说可以永远不调 `stop_playing_scene()`。

```651:652:mcp/server.py
def _request_project_close_once(project_root: Path, *, timeout_ms: int) -> dict[str, Any]:
    """Write one closeProject command and wait up to timeout_ms for matching response (stop Play, keep editor)."""
```

### 2.2 真正结束「游戏运行」的稳定接口（已存在）

`plugin.gd` 在 `_process` 中约每 200ms 调用 `_handle_auto_stop_play_request()`；在标志时间窗合法且当前仍在 Play 时，调用 **`EditorInterface.stop_playing_scene()`** —— 与用户在编辑器里点「停止运行」属于同一类引擎能力，**不是**强杀进程。

```83:109:godot_plugin_template/addons/pointer_gpf/plugin.gd
func _handle_auto_stop_play_request() -> void:
    var request_path := ProjectSettings.globalize_path(_AUTO_STOP_PLAY_MODE_FLAG_REL)
    if not FileAccess.file_exists(request_path):
        return
    # ... 校验 issued_at_unix 与最大年龄窗 ...
    var _cleanup_err := DirAccess.remove_absolute(request_path)
    if not bool(EditorInterface.is_playing_scene()):
        return
    EditorInterface.stop_playing_scene()
```

因此：**「游戏在跑之后一定有稳定接口关」** 在工程上已由 Godot + 插件承接；若验收仍失败，应排查例如：

- **时序**：MCP 是否在 `stop_playing_scene()` 实际执行**之前**就把 `closeProject` 标成已 ack，导致自动化侧以为已收尾、用户侧仍短暂看到运行态；
- **标志窗**：`_STOP_FLAG_MAX_AGE_SEC`（45s）等逻辑是否导致标志被丢弃而未触发 stop；
- **运行形态**：若未来存在「无 `EditorInterface` 的纯导出进程」跑同一套桥接，则需另定「退出应用」路径——那是 **运行形态分支**，仍应优先 **引擎内 `SceneTree.quit` 等正常 API**，而不是先把 OS 强杀写进需求选项。

### 2.3 用户说的「关闭进程」应如何对齐验收

- 在 **编辑器 + Play** 形态下，验收建议对齐为：**Play 运行态结束**（`EditorInterface.is_playing_scene()` 变为 false，或等价门禁），与 UI 停止运行一致。
- **Godot 编辑器进程（`Godot*.exe`）是否退出** 是另一档产品选择（是否每次流程后关 IDE）；**不应**与用户说的「关游戏」默认混为一谈，也**不应**用「强杀」去冒充「关游戏」。

### 2.4 脚注：`hard_teardown` 与 `force_terminate_godot`（兜底，非主路径）

`_hard_teardown_for_flow_failure` 中，当 `closeProject` **已确认**时，`force_terminate_godot` 结果为 `skipped_close_acknowledged`，**不**调用 `_force_terminate_godot_processes_holding_project`。仅当 **close 长期无确认** 且调用方显式传入 `force_terminate_godot_on_flow_failure: true` 时，才会走 OS 侧枚举杀进程。**这属于桥接失联时的运维兜底**，计划正文不将其与用户「关闭游戏运行」需求并列。

---

## 3. 解释：为什么跑流程过程中你会看到「代理在改代码」

以下对应 **上一轮本会话中已发生的、会出现在 Git / IDE 变更里的操作**（不是「流程引擎在跑步骤时自动改 GDScript」）：

1. **写入 `pointer_gpf/tmp/_run_basic_flow_args.json`**  
   用途：在 Windows PowerShell 下把 `--args` JSON **稳定传给** `python mcp/server.py`，避免引号被 shell 吃掉导致 `json.loads` 失败。  
   性质：**仓库内临时参数文件**，不是游戏逻辑；部分环境会把它显示为「代理编辑了文件」。

2. **调用 `configure_godot_executable` 写入**  
   `examples/godot_minimal/tools/game-test-runner/config/godot_executable.json`  
   用途：在 `RUNTIME_GATE_FAILED` / `no_executable_candidates` 之后持久化 Godot 路径，使后续能拉起编辑器。  
   性质：**测试运行器配置**，不是 `.gd` 游戏代码，但同样是工作区内的可跟踪变更。

**未做事项：** 上一轮未修改 `examples/godot_minimal/scripts/**/*.gd` 等游戏脚本；若你看到的是上述 JSON 或 `godot_executable.json`，属于 **集成/排障所需的配置文件写入**，与「基础流程步骤执行中改玩法代码」不是同一类事件。

---

## 4. 自检（writing-plans 要求）

**4.1 需求覆盖**

| 你的问题 | 上文对应 |
|----------|-----------|
| 为何仍觉得没关 | 第 2 节：区分「停 Play」与「关编辑器 exe」；主路径为 `EditorInterface.stop_playing_scene()`；列出时序/标志窗/运行形态等排查方向 |
| 为何看到改代码 | 第 3 节：临时 args JSON + `godot_executable.json` |

**4.2 占位扫描**

- 无 `TBD` / 「适当处理」类占位；可选改造见第 5 节。

**4.3 类型与命名**

- `force_terminate_godot_on_flow_failure`、`close_project_on_finish` 与 `mcp/server.py` 工具 schema 一致；前者在文档中明确为 **兜底**，不与「关游戏运行」混谈。

---

## 5. 可选改造（对齐「稳定关闭游戏运行」的工程闭环）

下列任务**不**引入「强杀 vs 退出编辑器二选一」式产品拆分；聚焦 **命名、时序、可观测性、与引擎 API 对齐**。

### Task 3: 契约与文档用语对齐

**Files:**

- Modify: `docs/godot-adapter-contract-v1.md`（或 teardown 小节）：写明 `closeProject` 的**实际语义**为「请求停止 Play / 等价 UI 停止运行」，并指向 `EditorInterface.stop_playing_scene()` 消费链。
- Modify: `mcp/server.py` 中 `_request_project_close_once` 的 docstring（若需）：避免读者把「keep editor」理解成「可以不结束 Play」。

- [x] **Step 1:** 在契约中增加「收尾完成」的推荐判据（例如：Play 已结束 + 桥接 ack 时序定义），与当前 `runtime_gate` 字段对齐。
- [x] **Step 2:** `git add` + `git commit`（见会话内提交说明）

### Task 4: 插件与桥接 — 加固「关游戏运行」可靠性（非 OS 强杀）

**Files:**

- Modify: `godot_plugin_template/addons/pointer_gpf/plugin.gd`：评估是否在收到有效 stop 标志后 **立即**（同帧或 `call_deferred`）调用 `EditorInterface.stop_playing_scene()`，减少对 `_process` 200ms 轮询的依赖；保留现有时间窗防误触逻辑。
- Modify: `godot_plugin_template/addons/pointer_gpf/runtime_bridge.gd`（若需）：是否由 `closeproject` 分支在 **editor 插件可调用上下文** 内直接触发 stop（需 Godot 4.x 线程/上下文约束查证）。
- Modify: `examples/godot_minimal/addons/pointer_gpf/`：与模板同步。
- Test: 新增或扩展单测（若 CI 无头 Godot，可用 mock/契约测试覆盖「命令 → 标志 → 调用 stop API」的静态约束）。

- [x] **Step 1:** 写失败用例或场景说明（当前：仅 ack、Play 仍可能最多延迟 200ms 等）。
- [x] **Step 2:** 实现最小改动并跑 `python -m unittest` 相关子集。
- [x] **Step 3:** `git commit`（与 Task 3/5 一并说明）

### Task 5: MCP 返回体与规则 — 减少「已关 / 未关」误解

**Files:**

- Modify: `mcp/server.py`（成功/失败返回体中 `project_close` / 可选新字段）：在语义上区分 **「桥接已 ack」** 与 **「Play 已确认结束」**（若可通过读 `runtime_gate.json` 或二次探测实现）。
- Modify: `.cursor/rules/gpf-runtime-test-mandatory-play-mode.mdc`：明确「停止 Play」= 结束游戏运行态；「保留编辑器」= 不退出 Godot IDE 应用，**不**与「保持 Play」混淆。

- [x] **Step 1:** 规则与 MCP 默认行为一致后提交。

---

## 6. 执行交接（writing-plans 固定话术）

**计划已保存到：** `docs/superpowers/plans/2026-04-11-basic-flow-teardown-semantics-and-agent-workspace-writes.md`

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 派生子代理，Task 间人工核对，迭代快。实现改造时 **必须** 使用 superpowers:subagent-driven-development。
2. **Inline Execution** — 本会话内用 executing-plans 批量执行并设检查点。

**你更倾向哪一种？** 若当前仅需「分析结论」、不立刻改代码，可回复「暂不实施 Task 3+」，本文件第 2–3 节即可作为验收依据。
