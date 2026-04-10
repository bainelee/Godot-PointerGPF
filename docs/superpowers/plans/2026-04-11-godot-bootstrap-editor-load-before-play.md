# Godot 工程未启动时自动拉起与「加载完成」门闩 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 跑 `run_game_basic_test_flow` / `run_game_basic_test_flow_by_current_state` 时，若目标 Godot 工程尚未在可协作的编辑器实例中就绪，GPF（MCP + 插件）须先**启动工程**（已有雏形），并在进入 `auto_enter_play_mode` / Play 门闩前**显式等待「工程 + PointerGPF 编辑器插件已加载并可写门闩文件」**；装载 GPF 的 IDE（如 Cursor）仅负责不阻断子进程启动、在无法发现 `godot` 可执行文件时由代理传入 `godot_executable`，不把「用户手动开编辑器」当作默认前置条件。

**Architecture:** 在 `mcp/server.py` 的 `_ensure_runtime_play_mode` 中把引导拆成有序阶段：**(S0)** 写入 MCP 侧 bootstrap 会话文件；**(S1)** 若未检测到带 `--path`+`project_root` 的 Godot 编辑器进程则 `Popen` 拉起；**(S2)** 轮询 `pointer_gpf/tmp/runtime_gate.json` 直至插件回显同一会话 id（表示**该**工程上插件 `_process` 已运行、可写磁盘门闩）；**(S3)** 再写 `auto_enter_play_mode.flag` 并轮询现有 `runtime_gate_passed`（Play 态）。`godot_plugin_template/addons/pointer_gpf/plugin.gd` 在每次 `_write_runtime_gate_marker` 时合并读取 `pointer_gpf/tmp/mcp_bootstrap_session.json` 中的 `session_id` 到字段 `bootstrap_session_ack`（仅当文件存在且 JSON 合法）。契约与字段写入 `docs/godot-adapter-contract-v1.md` 与 `mcp/adapter_contract_v1.json` 的说明区（不破坏现有必填 action 列表）。

**Tech Stack:** Python 3.11+（仓库 MCP）、Godot 4.x GDScript（`@tool` EditorPlugin）、`unittest`（仓库现有测试风格）、Windows / POSIX 子进程。

---

## 文件结构（创建或修改）

| 文件 | 职责 |
|------|------|
| `mcp/server.py` | 新增 `_write_mcp_bootstrap_session` / `_await_bootstrap_session_ack`；调整 `_ensure_runtime_play_mode` 在 `launch` 与 `_request_auto_enter_play_mode` 之间插入 S2 等待；`engine_bootstrap` 增加 `bootstrap_session_id`、`editor_plugin_ack_elapsed_ms` 等 |
| `godot_plugin_template/addons/pointer_gpf/plugin.gd` | 读取 bootstrap 会话文件并把 `session_id` 写入 `runtime_gate.json`；与示例工程 `examples/godot_minimal/addons/pointer_gpf/plugin.gd` 同步（若示例内存在同路径副本） |
| `docs/godot-adapter-contract-v1.md` | 新增「编辑器启动与工程加载门闩」小节：文件路径、字段语义、失败时 `blocking_point` 建议文案 |
| `mcp/adapter_contract_v1.json` | 在文档型字段或 `x-pointer-gpf-notes` 类扩展中描述 `runtime_gate.json` 可选键（若仓库约定 JSON 注释则用并列 `description` 字段所在结构） |
| `tests/test_godot_bootstrap_session_gate.py`（新建） | 纯文件系统 + monkeypatch 时间，验证 `_await_bootstrap_session_ack` 在写入 ack 后返回 |

---

### Task 1: 契约与对外说明（先锁语义）

**Files:**
- Modify: `docs/godot-adapter-contract-v1.md`（在 `## Runtime Bridge` 后插入新小节）
- Modify: `mcp/adapter_contract_v1.json`（补充与 gate 相关的说明字符串，不删除现有键）

- [ ] **Step 1: 在 `docs/godot-adapter-contract-v1.md` 追加小节全文**

在 `docs/godot-adapter-contract-v1.md` 的 `## Runtime Bridge` 小节末尾、`### TIMEOUT semantics` 小节之前插入：

```markdown
### 编辑器未启动时的引导顺序（MCP + EditorPlugin）

1. **MCP** 在尝试进入 Play 门闩前，写入 `pointer_gpf/tmp/mcp_bootstrap_session.json`（UTF-8 JSON 对象），至少包含：
   - `session_id`（字符串，UUID）
   - `issued_at_unix`（数字，秒级 Unix 时间，由 MCP 写入）
2. 若未检测到已打开的 Godot 编辑器进程持有该 `project_root`（现有 `_is_godot_editor_running_for_project`），MCP 使用已配置的 Godot 可执行文件路径执行 `Godot --editor --path <project_root>`（现有 `_launch_godot_editor`）。
3. **EditorPlugin** 在编辑器已打开该工程且插件启用后，于常规门闩刷新路径中读取上述文件；若存在且 `session_id` 非空，则在写入 `pointer_gpf/tmp/runtime_gate.json` 时附带字段 **`bootstrap_session_ack`**，其值**等于**当前文件中的 `session_id`。
4. **MCP** 轮询 `runtime_gate.json`，直到 `bootstrap_session_ack == session_id` 或超时；该条件成立表示「该工程实例上的 PointerGPF 编辑器插件已加载并具备写门闩能力」，即本计划所称的**工程加载完成（GPF 视角）**。
5. 随后 MCP 写入 `auto_enter_play_mode.flag` 并继续等待 `runtime_gate_passed == true`（现有 Play 门闩），再执行流程步骤。

**装载 GPF 的 IDE义务（非 Godot 内代码）：** 允许 MCP 进程以分离子进程方式启动 Godot；在无法通过 `tools/game-test-runner/config/godot_executable.json`、工具参数或 `GODOT_*` 环境变量解析到可执行文件时，由集成方在调用 `run_game_basic_test_flow*` 时传入 `godot_executable`（或等价别名字段），而不是要求终端用户手动点击启动编辑器。
```

- [ ] **Step 2: 在 `mcp/adapter_contract_v1.json` 顶层或 `transport_modes` 旁增加可读说明**

若顶层已有 `"description"`，追加一句英文（与中文文档互链）：

`"PointerGPF bootstrap: MCP may write pointer_gpf/tmp/mcp_bootstrap_session.json; editor plugin echoes session_id as bootstrap_session_ack inside pointer_gpf/tmp/runtime_gate.json before play-mode auto-enter."`

（具体插入位置以当前 JSON 结构为准：不得破坏 JSON 合法性。）

- [ ] **Step 3: 提交**

```bash
git add docs/godot-adapter-contract-v1.md mcp/adapter_contract_v1.json
git commit -m "docs: bootstrap session gate for editor load"
```

---

### Task 2: 插件回显 `bootstrap_session_ack`

**Files:**
- Modify: `godot_plugin_template/addons/pointer_gpf/plugin.gd`
- Modify: `examples/godot_minimal/addons/pointer_gpf/plugin.gd`（若存在；若示例通过安装工具同步，则 Task 末尾运行一次 `install_godot_plugin` 等效复制并再提交）

- [ ] **Step 1: 在 `plugin.gd` 顶部增加常量**

```gdscript
const _MCP_BOOTSTRAP_SESSION_REL := "res://pointer_gpf/tmp/mcp_bootstrap_session.json"
```

- [ ] **Step 2: 新增读取函数**

```gdscript
func _read_bootstrap_session_id() -> String:
    var p := ProjectSettings.globalize_path(_MCP_BOOTSTRAP_SESSION_REL)
    if not FileAccess.file_exists(p):
        return ""
    var f := FileAccess.open(p, FileAccess.READ)
    if f == null:
        return ""
    var txt := f.get_as_text()
    f.close()
    var data: Variant = JSON.parse_string(txt)
    if typeof(data) != TYPE_DICTIONARY:
        return ""
    var d: Dictionary = data
    return str(d.get("session_id", "")).strip_edges()
```

- [ ] **Step 3: 修改 `_write_runtime_gate_marker` 合并 ack**

在 `func _write_runtime_gate_marker(payload: Dictionary) -> void:` 内，`FileAccess.open` 之前插入：

```gdscript
    var ack := _read_bootstrap_session_id()
    if ack != "":
        payload = payload.duplicate()
        payload["bootstrap_session_ack"] = ack
```

（`duplicate()` 避免改动调用方传入的共享字典引用。）

- [ ] **Step 4: 本地 Godot 打开 `examples/godot_minimal` 验证无脚本错误（可选）**

- [ ] **Step 5: 提交**

```bash
git add godot_plugin_template/addons/pointer_gpf/plugin.gd examples/godot_minimal/addons/pointer_gpf/plugin.gd
git commit -m "feat(editor-plugin): echo mcp bootstrap session in runtime_gate"
```

---

### Task 3: MCP 写入会话、等待 ack、串进 `_ensure_runtime_play_mode`

**Files:**
- Modify: `mcp/server.py`

- [ ] **Step 1: 在 `import` 区域确认已有 `import uuid`（若无则增加）**

- [ ] **Step 2: 在 `_await_runtime_gate` 上方新增两个函数**

```python
def _write_mcp_bootstrap_session(project_root: Path) -> tuple[str, float]:
    bridge_dir = (project_root / "pointer_gpf" / "tmp").resolve()
    bridge_dir.mkdir(parents=True, exist_ok=True)
    session_id = uuid.uuid4().hex
    issued = time.time()
    path = bridge_dir / "mcp_bootstrap_session.json"
    path.write_text(
        json.dumps({"session_id": session_id, "issued_at_unix": issued}, ensure_ascii=False),
        encoding="utf-8",
    )
    return session_id, issued


def _await_bootstrap_session_ack(
    project_root: Path, session_id: str, *, timeout_ms: int, poll_ms: int = 120
) -> tuple[bool, dict[str, Any], float]:
    """Return (ack_seen, last_gate_payload, elapsed_ms)."""
    timeout_ms = max(1, int(timeout_ms))
    poll_ms = max(10, int(poll_ms))
    start = time.monotonic()
    deadline = start + timeout_ms / 1000.0
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = _probe_runtime_gate(project_root)
        if str(last.get("bootstrap_session_ack", "")).strip() == session_id:
            elapsed_ms = int((time.monotonic() - start) * 1000.0)
            return True, last, float(elapsed_ms)
        time.sleep(poll_ms / 1000.0)
    elapsed_ms = int((time.monotonic() - start) * 1000.0)
    return False, last, float(elapsed_ms)
```

- [ ] **Step 3: 扩展 `_probe_runtime_gate` 的 default 与解析分支**

在 `default = {` 字典中增加：

```python
        "bootstrap_session_ack": "",
```

在成功 `json.loads` 后的返回 dict 中增加：

```python
        "bootstrap_session_ack": str(payload.get("bootstrap_session_ack", "")).strip(),
```

- [ ] **Step 4: 修改 `_ensure_runtime_play_mode` 分支逻辑**

在**已有**早退之后写入会话 id（若已在 Play 则不得改写 bootstrap 会话文件以免干扰并行任务）：

```python
    runtime_meta = _probe_runtime_gate(project_root)
    if bool(runtime_meta.get("runtime_gate_passed", False)):
        return runtime_meta, bootstrap
    session_id, _issued = _write_mcp_bootstrap_session(project_root)
    bootstrap["bootstrap_session_id"] = session_id
```

在 `bootstrap["editor_running_before_launch"] = ...` 与可能的 `_launch_godot_editor` 循环**之后**、`_request_auto_enter_play_mode(project_root)` **之前**插入：

```python
    ack_timeout_ms = int(max(5_000, min(120_000, int(arguments.get("editor_plugin_ack_timeout_ms", 60_000)))))
    ack_ok, gate_after_ack, ack_elapsed_ms = _await_bootstrap_session_ack(
        project_root, session_id, timeout_ms=ack_timeout_ms, poll_ms=120
    )
    bootstrap["bootstrap_session_ack_seen"] = ack_ok
    bootstrap["bootstrap_session_ack_elapsed_ms"] = ack_elapsed_ms
    runtime_meta = gate_after_ack
```

若 `not ack_ok`，应直接返回当前 `runtime_meta` 与 `bootstrap`（上层 `RUNTIME_GATE_FAILED` 路径会带上 `engine_bootstrap`）；并在 `next_actions` 中增加一条：`确认 addons/pointer_gpf 已在该项目启用且未被 Godot 禁用`。同时**不要**在无 ack 时反复写 `auto_enter_play_mode.flag` 造成误触（保持现有「仅当将继续等待 play」逻辑，但若 ack 失败则提前失败）。

- [ ] **Step 5: 为工具 schema 增加可选参数 `editor_plugin_ack_timeout_ms`**

在 `run_game_basic_test_flow` / `run_game_basic_test_flow_by_current_state` 的 JSON Schema 片段（`server.py` 内 `_build_tool_map` 相关描述字典）增加：

```python
"editor_plugin_ack_timeout_ms": {"type": "integer", "description": "Max wait ms for editor plugin to echo bootstrap_session_ack in runtime_gate.json after launch (default 60000)."},
```

- [ ] **Step 6: 提交**

```bash
git add mcp/server.py
git commit -m "feat(mcp): wait for editor plugin bootstrap ack before play gate"
```

---

### Task 4: 单元测试 `_await_bootstrap_session_ack`

**Files:**
- Create: `tests/test_godot_bootstrap_session_gate.py`

- [ ] **Step 1: 新建测试文件**

```python
import json
import tempfile
import time
import unittest
from pathlib import Path


class GodotBootstrapSessionGateTests(unittest.TestCase):
    def test_await_bootstrap_session_ack_succeeds_when_gate_updated(self) -> None:
        import mcp.server as srv

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
            bridge = root / "pointer_gpf" / "tmp"
            bridge.mkdir(parents=True)
            sid = "test-session-abc"

            def delayed_write() -> None:
                time.sleep(0.05)
                marker = bridge / "runtime_gate.json"
                marker.write_text(
                    json.dumps(
                        {
                            "runtime_mode": "editor_bridge",
                            "runtime_entry": "unknown",
                            "runtime_gate_passed": False,
                            "bootstrap_session_ack": sid,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )

            import threading

            threading.Thread(target=delayed_write, daemon=True).start()
            ok, last, elapsed = srv._await_bootstrap_session_ack(
                root, sid, timeout_ms=3_000, poll_ms=20
            )
            self.assertTrue(ok, msg=str(last))
            self.assertGreaterEqual(elapsed, 0.0)

    def test_await_bootstrap_session_ack_times_out(self) -> None:
        import mcp.server as srv

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
            (root / "pointer_gpf" / "tmp").mkdir(parents=True)
            ok, _last, elapsed = srv._await_bootstrap_session_ack(
                root, "never-comes", timeout_ms=80, poll_ms=10
            )
            self.assertFalse(ok)
            self.assertLessEqual(elapsed, 500.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试**

```bash
cd D:\AI\pointer_gpf
python -m unittest tests.test_godot_bootstrap_session_gate -v
```

期望：两行均为 `ok`。

- [ ] **Step 3: 提交**

```bash
git add tests/test_godot_bootstrap_session_gate.py
git commit -m "test(mcp): bootstrap session ack polling"
```

---

### Task 5: 端到端验收（真实 Godot，可选但推荐）

**Files:**
- 证据：`examples/godot_minimal/pointer_gpf/tmp/runtime_gate.json`、`mcp_bootstrap_session.json`

- [ ] **Step 1: 关闭所有持有 `examples/godot_minimal` 的 Godot 实例**

- [ ] **Step 2: 运行（PowerShell 下 JSON 用 Python 子进程传入，避免转义错误）**

```bash
cd D:\AI\pointer_gpf
python -c "import subprocess,sys,json; a=json.dumps({'failure_handling':'run_only','godot_executable':r'C:\\Path\\To\\Godot.exe'}); subprocess.check_call([sys.executable,'mcp/server.py','--tool','run_game_basic_test_flow_by_current_state','--project-root',r'D:/AI/pointer_gpf/examples/godot_minimal','--args',a])"
```

将 `C:\\Path\\To\\Godot.exe` 替换为本机 Godot 4 编辑器真实路径。

- [ ] **Step 3: 期望**

- `engine_bootstrap` 中出现 `bootstrap_session_ack_seen: true`（冷启动成功路径）。
- 若 Godot 未安装或路径错误：`launch_succeeded: false` 且 `blocking_point` 可定位到可执行文件或 ack 超时。

- [ ] **Step 4: 提交（仅当有配置/文档微调时）**

---

## Self-Review

1. **Spec coverage:** 「未启动则启动」对应已有 `_launch_godot_editor` + 本计划 Task 3 顺序强化；「启动后等待加载完成」对应 Task 2+3 的 `bootstrap_session_ack`；「IDE 义务」对应 Task 1 文档小节。
2. **Placeholder scan:** 无 TBD；Godot 路径在 Task 5 用显式占位路径并要求替换，属验收步骤可接受说明。
3. **Type consistency:** `_probe_runtime_gate` 与 `_await_bootstrap_session_ack` 共用 `bootstrap_session_ack` 字符串字段名；插件写入与 MCP 读取一致。

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-11-godot-bootstrap-editor-load-before-play.md`. Two execution options:**

**1. Subagent-Driven（推荐）** — 每个 Task 派生子代理，任务间复核，迭代快。

**2. Inline Execution** — 本会话内用 executing-plans 批量执行并设检查点。

**Which approach?**
