# 自动测试结束后「游戏测试窗口」必须关闭 — 根因合并与硬保证实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在任意一次 GPF 自动基础测试流程结束（成功 / 失败 / 超时 / 门禁失败）后，由该 Godot 工程通过「运行项目」启动的 **游戏测试会话**（与编辑器内 **停止运行** / `EditorInterface.stop_playing_scene()` 同语义）**在操作系统层面不再保持为可交互的独立调试游戏前台会话**；Godot **编辑器**进程默认保留。本计划针对「工具返回已收尾、用户仍看见 `(DEBUG)` 游戏窗口」类长期未闭环报告，给出 **可测、可交付、可回归** 的修复链。

**Architecture:** 保留「MCP → `command.json` → `runtime_bridge.gd` 写 `auto_stop_play_mode.flag` → `plugin.gd` 消费并 `stop_playing_scene()`」主路径；在 **契约层** 区分 **bridge ack** 与 **Play 真停**；在 **交付层** 保证示例工程与模板插件同源；在 **收尾层** 增加 **ack 后轮询 gate + teardown 证据** 与 **ack 但仍在跑时的分级补救**（二次 stop / 延长等待 / 可选进程级处置），避免 `hard_teardown` 在「已 ack」时无条件跳过一切强制路径。

**Tech Stack:** Python 3（`mcp/server.py`、`mcp/flow_execution.py`）、Godot 4.x GDScript（`godot_plugin_template/addons/pointer_gpf/`）、unittest、`.gitignore`、现有契约测试（`tests/test_mcp_hard_teardown.py`、`tests/test_flow_execution_runtime.py`、`tests/test_runtime_gate_marker_plugin.py`）。

---

## 1. 文件职责地图（本计划会创建或修改）

| 路径 | 职责 |
|------|------|
| `godot_plugin_template/addons/pointer_gpf/plugin.gd` | 消费 stop 标志、停 Play、写入 `teardown_debug_game_last.json`（失败 / **成功** 证据，见 Task 3） |
| `godot_plugin_template/addons/pointer_gpf/runtime_bridge.gd` | `closeProject` 写 flag；**不得**在仅写盘成功时暗示「窗口已关」（注释与 MCP 字段对齐） |
| `mcp/server.py` | `_request_project_close*`、`_enrich_project_close_with_runtime_gate_evidence`、`_hard_teardown_for_flow_failure`（**ack 后轮询仍 play 时的分支**） |
| `.gitignore` 与 `examples/godot_minimal/addons/pointer_gpf/` | 与既有计划一致：示例工程内插件 **纳入版本控制或与模板同步脚本**（见 Task 1） |
| `tests/test_mcp_hard_teardown.py` | 硬收尾：ack 且 gate 仍 play / teardown 失败时的行为 |
| `tests/test_flow_execution_runtime.py` 或新建 `tests/test_project_close_post_ack_poll.py` | MCP 对 `project_close` 扩展字段的契约 |
| `docs/design/99-tools/` 下与 `close_project_on_finish` 相关条目 | 用语：`closeProject` = **请求结束游戏测试会话**，不是「退出编辑器应用」 |

---

## 2. 「一直没修好」的根因分析（用语 / 误解 / 代码 / 交付）

### 2.1 契约语义：ack ≠ 窗口已消失

`runtime_bridge.gd` 在 `closeProject` 分支中，只要 **`_request_stop_play_mode()` 成功写入了 `auto_stop_play_mode.flag`** 就返回：

```197:210:d:\AI\pointer_gpf\godot_plugin_template\addons\pointer_gpf\runtime_bridge.gd
        "closeproject", "stopgametestsession":
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

**后果：** MCP 侧 `closeProject` 的 **`acknowledged: true`** 只保证「flag 已落盘 + bridge 已回包」，**不保证** `EditorPlugin` 已在下一帧消费、更不保证 OS 顶层 `(DEBUG)` 窗已销毁。交接记录里用户看到「已 ack + `play_running_by_runtime_gate`: false」仍抱怨窗口未关，说明还需 **「真停」的可观测证据** 与 **「ack 与 gate 矛盾」时的补救**，而不能停在「bridge 说 ok」。

### 2.2 硬收尾逻辑在「已 ack」时过早放弃

`_hard_teardown_for_flow_failure` 在 **`acknowledged`** 时直接返回 `skipped_close_acknowledged`，**不再**尝试任何 `force_terminate_godot` 路径：

```1012:1015:d:\AI\pointer_gpf\mcp\server.py
    if acknowledged:
        ft["outcome"] = "skipped_close_acknowledged"
        ft["detail"] = "closeProject was acknowledged; engine should be back in editor idle"
        return block
```

**后果：** 若出现 **「bridge ack 了但插件未停 / gate 与真实窗口不同步」** 的边角情况，工具链 **主动放弃** 用户唯一可选的 opt-in 强杀路径，Agent 与用户只能从字面上读到「引擎应已空闲」，与目视经验冲突，表现为「修了等于没修」。

### 2.3 观测证据不对称：只记录失败、不记录成功

`plugin.gd` 仅在多帧重试后 **`is_playing_scene()` 仍为真** 时写入 `teardown_debug_game_last.json`（`ok: false`）。**成功停 Play 时不写「ok: true」**。MCP `_attach_teardown_debug_game_artifact_to_close_meta` 只把 **`ok is False`** 并入 `project_close`。

**后果：** 集成方与用户 **无法区分**「未写文件 = 成功」与「未写文件 = 插件根本没跑到消费逻辑」。排障时只能猜。

### 2.4 交付链：示例工程插件与模板脱节

`.gitignore` 若仍忽略 `examples/godot_minimal/addons/pointer_gpf/`，则仓库内对 `godot_plugin_template/` 的修复 **不会** 出现在克隆后的 `examples/godot_minimal`，用户编辑器加载的仍是 **旧副本或手工拷贝**。这与 `docs/superpowers/plans/2026-04-11-debug-game-window-teardown-closure.md` 中 **Task 1（方案 A 已勾选）** 一致：**必须先解决同源交付**，否则任何 Python 侧增强都无法在用户工程生效。

### 2.5 用户心智与产品用语

| 误解来源 | 实际语义 |
|----------|----------|
| 动作名 **`closeProject`** | 应为 **结束当前 F5 游戏测试会话**；不是关闭 `.godot` 工程、不是退出 Godot 编辑器应用。 |
| **`保留编辑器进程`** | 指 **不退出 Godot IDE 进程**；**不得** 理解成允许 **调试游戏窗口 / Play 会话** 在流程结束后仍保持。 |
| **`runtime_gate.json` 的 `editor_bridge`** | 表示 `EditorInterface.is_playing_scene()` 为假；在极少数引擎版本或「独立进程运行」类设置下，**仍可能与用户看到的顶层窗不同步**（需在 Task 5 用真实 Godot 4.6.1 做目视 + 任务管理器对照）。 |
| **`failure_handling: run_only`** | 只关闭 **自动改工程** 的修复环；**不得** 被实现成跳过 **`close_project_on_finish`**（若代码中存在此类耦合，Task 4 用测试锁死默认行为）。 |

### 2.6 与本次交接记录（`pointer_gpf/tmp/handoff-prompt-basic-flow-run-2026-04-11.md`）的对照

- 流程在 **`enter_game`** 失败，`fail_fast` 后仍走到 **`_maybe_request_project_close`**（`mcp/server.py` 中 `FlowExecutionStepFailed` 分支），与「关窗绑定在后续步骤」类假设不符；**收尾在失败路径已触发**。
- `project_close` 显示 **`play_running_by_runtime_gate`: false**，说明 **gate 与插件侧认为 Play 已结束**。用户仍见窗口时，优先怀疑：**(A) 用户所指窗口不是本 Play 会话**、**(B) gate 与 OS 窗不同步**、**(C) 示例工程插件版本落后于模板**。本计划 Task 1–5 分别覆盖。

---

## 3. 任务分解（TDD、可执行命令、完整代码）

### Task 1: 示例工程 `addons/pointer_gpf` 与模板同源（交付硬前提）

**Files:**

- Modify: `.gitignore`（若仍存在对 `examples/godot_minimal/addons/pointer_gpf/` 的忽略行则删除该行）
- Create / Modify: `examples/godot_minimal/addons/pointer_gpf/**`（与 `godot_plugin_template/addons/pointer_gpf/` 目录树一致）
- Modify: `tests/test_godot_test_orchestrator_packaging.py`（或仓库内等价测试）：断言示例工程 **存在** `examples/godot_minimal/addons/pointer_gpf/plugin.gd`

- [ ] **Step 1: 写失败测试（若 addons 被忽略则仓库中无文件）**

```python
# tests/test_examples_minimal_pointer_gpf_addon_tracked.py
from pathlib import Path

def test_godot_minimal_has_tracked_pointer_gpf_addon() -> None:
    root = Path(__file__).resolve().parents[1]
    plugin = root / "examples" / "godot_minimal" / "addons" / "pointer_gpf" / "plugin.gd"
    assert plugin.is_file(), "examples/godot_minimal must ship addons/pointer_gpf for reproducible teardown"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_examples_minimal_pointer_gpf_addon_tracked -v`  
Expected: **FAIL**（`AssertionError` 或文件不存在）

- [ ] **Step 3: 从模板同步目录并解除 ignore**

在仓库根执行（PowerShell 可用 robocopy；此处用 Python 一次写入计划执行者可复制）：

```bash
git checkout -- examples/godot_minimal/addons/pointer_gpf 2>nul || true
# 然后手工或脚本: xcopy /E /I godot_plugin_template\addons\pointer_gpf examples\godot_minimal\addons\pointer_gpf
```

编辑 `.gitignore` 删除 `examples/godot_minimal/addons/pointer_gpf/` 行。

- [ ] **Step 4: 再跑测试**

Run: `python -m unittest tests.test_examples_minimal_pointer_gpf_addon_tracked -v`  
Expected: **PASS**

- [ ] **Step 5: Commit**

```bash
git add .gitignore examples/godot_minimal/addons/pointer_gpf tests/test_examples_minimal_pointer_gpf_addon_tracked.py
git commit -m "chore: track pointer_gpf addon in godot_minimal example for teardown parity"
```

---

### Task 2: MCP — `closeProject` ack 后轮询 `runtime_gate`，仍 play 则二次写命令

**Files:**

- Modify: `mcp/server.py`（`_request_project_close` 或 `_enrich_project_close_with_runtime_gate_evidence` 之后新增 `_stabilize_play_stop_after_close_ack`）

- [ ] **Step 1: 写失败测试（mock 文件系统 / gate 序列）**

在 `tests/test_mcp_hard_teardown.py` 末尾新增：

```python
import json
import unittest
from pathlib import Path
from unittest import mock

import mcp.server as mcp_server


class TestPostAckPlayStillRunning(unittest.TestCase):
    def test_second_close_when_gate_still_play_after_ack(self) -> None:
        calls = {"n": 0}

        def fake_once(root: Path, *, timeout_ms: int) -> dict:
            calls["n"] += 1
            return {"requested": True, "acknowledged": True, "timeout_ms": timeout_ms, "message": "ack"}

        gate_states = [
            {"runtime_mode": "play_mode", "runtime_gate_passed": True},
            {"runtime_mode": "play_mode", "runtime_gate_passed": True},
            {"runtime_mode": "editor_bridge", "runtime_gate_passed": False},
        ]
        idx = {"i": 0}

        def fake_read_gate(_root: Path) -> dict:
            g = gate_states[min(idx["i"], len(gate_states) - 1)]
            idx["i"] += 1
            return g

        root = Path("/tmp/pointer_gpf_fake_project")
        with mock.patch.object(mcp_server, "_request_project_close_once", side_effect=fake_once):
            with mock.patch.object(mcp_server, "_read_runtime_gate_marker", side_effect=fake_read_gate):
                # 假定新函数名为 _request_project_close_until_gate_quiescent
                out = mcp_server._request_project_close_until_gate_quiescent(root, timeout_ms_per_attempt=100, max_attempts=3)
        self.assertTrue(out.get("acknowledged"))
        self.assertGreaterEqual(calls["n"], 2, "should issue another close when gate still implies playing")
```

- [ ] **Step 2: 运行测试**

Run: `python -m unittest tests.test_mcp_hard_teardown.TestPostAckPlayStillRunning -v`  
Expected: **FAIL**（`AttributeError: _request_project_close_until_gate_quiescent`）

- [ ] **Step 3: 在 `mcp/server.py` 实现**

在 `_request_project_close` 成功 `acknowledged` 后：

1. 轮询 `_read_runtime_gate_marker` 最多约 **2s**（步进 80ms），若 `_runtime_gate_implies_playing(marker) is True`：
2. 再次调用 `_request_project_close_once`（最多 **2** 次额外尝试），并把摘要写入 `close_meta["post_ack_resync"]`：`{"extra_close_attempts": N, "final_play_running": bool}`。
3. 将原 `_request_project_close` 重命名或包装为 `_request_project_close_until_gate_quiescent`，保持对外 `_maybe_request_project_close` 仍返回 enrich 后的 dict。

伪代码（计划执行者需写成真实 Python）：

```python
def _request_project_close_until_gate_quiescent(project_root: Path, *, timeout_ms_per_attempt: int = 5_500, max_attempts: int = 3) -> dict[str, Any]:
    last = _request_project_close(project_root, timeout_ms_per_attempt=timeout_ms_per_attempt, max_attempts=max_attempts)
    if not last.get("acknowledged"):
        return last
    deadline = time.monotonic() + 2.0
    extra = 0
    while time.monotonic() < deadline:
        if _runtime_gate_implies_playing(_read_runtime_gate_marker(project_root)) is not True:
            break
        time.sleep(0.08)
    if _runtime_gate_implies_playing(_read_runtime_gate_marker(project_root)) is True and extra < 2:
        last["post_ack_gate_still_playing"] = True
        last2 = _request_project_close(project_root, timeout_ms_per_attempt=timeout_ms_per_attempt, max_attempts=max_attempts)
        last.update({f"resync_{extra}": last2})
        extra += 1
    last["post_ack_extra_close_rounds"] = extra
    return last
```

- [ ] **Step 4: 运行测试**

Expected: **PASS**

- [ ] **Step 5: Commit**

```bash
git add mcp/server.py tests/test_mcp_hard_teardown.py
git commit -m "fix(mcp): retry closeProject when runtime_gate still implies play after ack"
```

---

### Task 3: Godot — 成功停 Play 时写入 `teardown_debug_game_last.json`（`ok: true`）

**Files:**

- Modify: `godot_plugin_template/addons/pointer_gpf/plugin.gd`
- Modify: `examples/godot_minimal/addons/pointer_gpf/plugin.gd`（与模板同步后应一致）
- Modify: `mcp/server.py` 中 `_attach_teardown_debug_game_artifact_to_close_meta`：若 `ok is True`，写入 `close_meta["debug_game_teardown_ok"] = True`

- [ ] **Step 1: 更新静态测试 `tests/test_runtime_gate_marker_plugin.py`**

断言 `plugin.gd` 源码含字符串 `"\"ok\": true"` 或 `"ok\": true"`（按你实现的 `JSON.stringify` 字段名）。

- [ ] **Step 2: 运行测试**

Run: `python -m unittest tests.test_runtime_gate_marker_plugin -v`  
Expected: **FAIL**（直到实现完成）

- [ ] **Step 3: 修改 `plugin.gd`**

在 `_deferred_chain_stop_debug_game_session` 中当 `not EditorInterface.is_playing_scene()` 分支里，除 `_clear_teardown_debug_game_failure_file()` 外，调用新函数 `_write_teardown_debug_game_success_file()`，内容 schema 仍为 `pointer_gpf.teardown_debug_game.v1`，`"ok": true`。

- [ ] **Step 4: 更新 MCP**

```python
def _attach_teardown_debug_game_artifact_to_close_meta(project_root: Path, close_meta: dict[str, Any]) -> None:
    td = _read_teardown_debug_game_artifact(project_root)
    if not isinstance(td, dict):
        return
    if td.get("ok") is True:
        close_meta["debug_game_teardown_ok"] = True
        close_meta["debug_game_teardown_schema"] = str(td.get("schema", ""))
        return
    if td.get("ok") is False:
        close_meta["debug_game_teardown_ok"] = False
        close_meta["debug_game_teardown_reason"] = str(td.get("reason", ""))
        close_meta["debug_game_teardown_schema"] = str(td.get("schema", ""))
```

- [ ] **Step 5: 新增单测 `tests/test_mcp_hard_teardown.py`**

```python
def test_attach_teardown_success_artifact() -> None:
    # 在 tmp 写入 ok:true JSON，调用 _attach_teardown_debug_game_artifact_to_close_meta，断言 close_meta["debug_game_teardown_ok"] is True
```

Run: `python -m unittest tests.test_mcp_hard_teardown -v`  
Expected: **PASS**

- [ ] **Step 6: Commit**

```bash
git add godot_plugin_template/addons/pointer_gpf/plugin.gd examples/godot_minimal/addons/pointer_gpf/plugin.gd mcp/server.py tests/
git commit -m "feat(godot): record successful debug game teardown for MCP evidence"
```

---

### Task 4: 确认 `failure_handling: run_only` 从不跳过 `close_project_on_finish`

**Files:**

- Modify: `tests/test_flow_execution_runtime.py`（或新建 `tests/test_basic_flow_run_only_still_closes_play.py`）
- Modify: `mcp/server.py`（若发现 `run_only` 与 `close_project_on_finish` 耦合则删除该耦合）

- [ ] **Step 1: 写测试**

调用 `_tool_run_game_basic_test_flow_execute` 的依赖过重时，可只测 **参数归一化函数**（若存在 `_normalize_basic_flow_arguments`）；否则用 `unittest.mock` patch `FlowRunner.run` 抛 `FlowExecutionStepFailed`，断言传给 `_maybe_request_project_close` 的 `close_project_on_finish` 为 **True**（当用户未显式传 `close_project_on_finish: false`）。

- [ ] **Step 2: 若测试失败则修正实现**

确保 `failure_handling` 仅影响 bug-fix 环，不影响默认 `close_project_on_finish=True`。

- [ ] **Step 3: Commit**

```bash
git add mcp/server.py tests/test_basic_flow_run_only_still_closes_play.py
git commit -m "fix(mcp): run_only must not skip play session teardown"
```

---

### Task 5: 真机验收脚本（Windows + Godot 4.6.1）

**Files:**

- Create: `docs/superpowers/notes/2026-04-11-game-window-teardown-manual-acceptance.md`（仅含步骤清单，不含占位符）

验收步骤（执行者照抄）：

1. 打开 `examples/godot_minimal`，确认 **仅一个** Godot 编辑器实例加载该路径。
2. 不手动 F5；运行 Task 1 中的 PowerShell 内联 Python 命令（`failure_handling: run_only`）。
3. 流程故意失败后：确认 **`(DEBUG)` 独立窗口关闭**；编辑器仍存活。
4. 若仍见窗口：记录 `pointer_gpf/tmp/runtime_gate.json`、`teardown_debug_game_last.json`、任务管理器中 **所有** 含 `godot_minimal` 命令行的进程截图，并回写到上述 note。

- [ ] **Step 1: 按清单完成一次真机运行并粘贴证据路径**

- [ ] **Step 2: Commit note（若含截图则放 `assets/` 并引用）**

---

### Task 6: `hard_teardown` — ack 但 gate / teardown 表明仍在跑时允许 opt-in 强杀

**Files:**

- Modify: `mcp/server.py` 中 `_hard_teardown_for_flow_failure`
- Modify: `tests/test_mcp_hard_teardown.py`

逻辑变更：

```python
# 伪代码 — 执行者写入真实实现
playing = close_meta.get("play_running_by_runtime_gate")
teardown_ok = close_meta.get("debug_game_teardown_ok")
if acknowledged and playing is not True and teardown_ok is not False:
    ft["outcome"] = "skipped_close_acknowledged"
    return block
# 否则：若 force 为 true，则与未 ack 类似地调用 _force_terminate_godot_processes_holding_project
```

- [ ] **Step 1: 写单测** `acknowledged=True`, `play_running_by_runtime_gate=True`, `force=True` → `attempted=True`。

- [ ] **Step 2: 实现并跑全量相关测试**

Run: `python -m unittest tests.test_mcp_hard_teardown tests.test_flow_execution_runtime -v`

- [ ] **Step 3: Commit**

```bash
git add mcp/server.py tests/test_mcp_hard_teardown.py
git commit -m "fix(mcp): allow force teardown when close is acked but play evidence disagrees"
```

---

## 4. 计划自检（Self-Review）

**4.1 Spec 覆盖（对照用户叙述）**

| 用户要求 | 对应 Task |
|----------|-----------|
| 自动测试结束后必须关游戏测试窗口 | Task 2、3、6 + 既有插件 stop 链 |
| IDE（Cursor）不关 | 无改动（本计划不杀外层 IDE） |
| Godot 编辑器默认保留 | Task 6 强杀仍仅限 opt-in 且命令行含 `project_root`（与现实现一致） |
| `run_only` 不误伤收尾 | Task 4 |
| 长期未修 / 交付脱节 | Task 1 |

**4.2 Placeholder 扫描**

- 无 TBD；Task 5 为人工步骤但给出明确清单。

**4.3 类型与字段一致性**

- `teardown_debug_game_last.json` 沿用 schema `pointer_gpf.teardown_debug_game.v1`，新增成功分支 `ok: true`；MCP 字段 `debug_game_teardown_ok: bool`。

---

## 5. 执行交接

Plan complete and saved to `docs/superpowers/plans/2026-04-11-automated-test-game-window-teardown-hard-guarantee.md`. Two execution options:

**1. Subagent-Driven（推荐）** — 每个 Task 派生子代理，Task 之间做审查合并。

**2. Inline Execution** — 本会话用 executing-plans 批量执行并设检查点。

**Which approach?**

---

## 6. 全局验证命令（声称整计划完成前必跑）

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

（若仓库标准命令不同，以 `AGENTS.md` / CI 为准。）

本回合已按 **writing-plans** 要求产出：文件结构、根因表、无占位步骤、精确路径与可运行测试片段；完成实现后需再按 **verification-before-completion** 跑通上述 unittest 才可在对话中声称「已修复」。
