# 调试游戏窗口（DEBUG）收尾闭环 — 根因分析与可交付修复方案

> **给代理执行者：** REQUIRED SUB-SKILL: 使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans，按 Task 勾选推进。

**Goal:** 保证任意一次 GPF 自动测试流程结束后（成功/失败/超时/门禁失败），**Godot 从工程启动的「游戏测试会话」**（用户截图中标题为 `PointerGPF Minimal (DEBUG)`、带运行时调试工具条的那类窗口）**必须结束**；**Godot 编辑器工程**（任务管理器中 `main_scene_example.tscn - PointerGPF Minimal - Godot Engine` 所代表的 IDE 侧进程/窗口组）**默认保持**，以便人类继续在引擎里排查。与 Cursor/VS Code 等**外层 IDE** 无关。

**Architecture:** 收尾仍由 MCP 发 `closeProject` → `runtime_bridge.gd` 写 `auto_stop_play_mode.flag` → `plugin.gd` 调用 **`EditorInterface.stop_playing_scene()`**（及加固路径）。本计划把「为何长期未在用户侧闭环」拆成 **交付链、命名、验证口径、引擎运行形态** 四类根因，并给出 **可测、可回归** 的修复任务（含示例工程与模板同源、失败可观测、契约用语）。

**Tech Stack:** Godot 4.x GDScript（`godot_plugin_template/addons/pointer_gpf/`）、Python（`mcp/server.py`）、仓库 `.gitignore`、契约文档（`docs/godot-adapter-contract-v1.md`、`mcp/adapter_contract_v1.json`）、单测（`tests/test_runtime_gate_marker_plugin.py`、`tests/test_flow_execution_runtime.py`）。

**用户提供的验收截图（工作区内副本，便于评审对照）：**

- Godot 编辑器进程（任务管理器）：`assets/c__Users_baine_AppData_Roaming_Cursor_User_workspaceStorage_f34fc5c2bf80e30ce9245f2a1939c914_images_image-edfee36f-6fd7-4090-9242-5115d4a400a6.png`
- `(DEBUG)` 游戏测试窗口：`assets/c__Users_baine_AppData_Roaming_Cursor_User_workspaceStorage_f34fc5c2bf80e30ce9245f2a1939c914_images_image-427cae30-47e6-4552-ba59-a9a4f7b0ef19.png`

---

## 1. 用户侧「三件套」与必须关闭的对象（验收锚点）

| 对象 | 典型表现 | 流程结束后默认 |
|------|----------|----------------|
| 外层 IDE（Cursor / VS Code） | 跑 MCP / Agent | **不关**（不在本仓库 Godot 插件控制范围内） |
| Godot **编辑器**（打开 `examples/godot_minimal` 的工程） | 任务管理器里 `… Godot Engine`、主编辑器 UI | **保持** |
| **游戏测试会话**（从该 Godot 工程按「运行项目」启动） | 窗口标题常含 **`(DEBUG)`**、截图 2 顶部调试条 | **必须结束**（与人在编辑器里点「停止运行」同一产品语义） |

**注意：** 在多数 Godot 配置下，调试游戏窗口与编辑器可能**同属一个 `Godot*.exe` 进程**（独立窗口而非第二进程）；用户关心的是 **DEBUG 窗口消失**，不是「再杀一个 exe」。

---

## 2. 「一直以来没修好」的根因分析（用语 / 误解 / 代码与交付）

### 2.1 用语与心智模型漂移

| 现象 | 后果 |
|------|------|
| 动作名叫 **`closeProject`** | 被理解成「关 Godot 工程 / 关编辑器」，而不是「结束当前这次运行的调试游戏」；Agent 与用户对话长期在 **B（关编辑器进程）** 上绕圈，偏离 **关 DEBUG 窗口**。 |
| 文档写 **「停止 Play 运行态」** | 对不写 Godot 的读者抽象；未与截图 2 的 **`(DEBUG)` 窗口** 建立一一对应，验收不可目视对齐。 |
| **`execution_report.runtime_mode` 仍为 `play_mode`** | 与 `project_close.play_running_by_runtime_gate=false` 同时出现时，读者以为「工具说停了但还在跑」；实际是 **报告快照与收尾后 gate 不同步**（已部分用 `stale_execution_report_*` 缓解，但未解决「窗口仍可见」类报告）。 |

### 2.2 交付链断裂（高概率「代码对了但用户工程仍旧」）

`.gitignore` 当前包含：

```18:21:d:\AI\pointer_gpf\.gitignore
examples/godot_minimal/addons/pointer_gpf/
examples/godot_minimal/pointer_gpf/
examples/godot_minimal/gameplayflow/
examples/godot_minimal/artifacts/
```

**后果：** `godot_plugin_template/addons/pointer_gpf/` 的修复（每帧消费 stop、`call_deferred` 二次 `stop_playing_scene` 等）**不会**随仓库提交进入用户常用的 `examples/godot_minimal` 工作副本，除非人工复制。  
→ **同一问题在模板已修、在示例仍旧**，表现为「一直没修好」。

### 2.3 代码与引擎语义（中等概率）

| 风险点 | 说明 |
|--------|------|
| **`EditorInterface.stop_playing_scene()` 与「独立 DEBUG 窗口」** | Godot 官方 API 意图与编辑器「停止运行」一致；若某版本/设置下仍存在窗口残留，需在**真实 4.6** 上复现并查 Editor 设置（如「在独立窗口运行」等）是否引入额外子进程；计划内预留 **Task 5 引擎侧验证**。 |
| **`issued_at_unix` 时间窗** | `plugin.gd` 丢弃「过旧/时钟偏差过大」的 flag 时，等价于 **未执行 stop**；MCP 仍可能收到 bridge 的 `closeProject acknowledged`（若 bridge 先写 ack 再写 flag顺序反了需核对 `runtime_bridge.gd` 中 `closeproject` 分支顺序）。 |
| **编辑器失焦 / 节流** | 若 `EditorPlugin` `_process` 在极端情况下不推进（少见），stop 延迟；可用 **`call_deferred` + 多帧重试** 或 **`EditorInterface` 主线程队列** 加固（Task 4）。 |

### 2.4 验证口径不足（工具「说停了」与用户「仍看见 DEBUG」）

| 缺口 | 后果 |
|------|------|
| MCP 只读 **`runtime_gate.json`** | 反映 `EditorInterface.is_playing_scene()` 的代理量；**不直接证明** OS 上 DEBUG 顶层窗已销毁（通常一致，极端不同步时用户不信）。 |
| **无「收尾失败」结构化文件** | 插件若执行了 `stop_playing_scene` 但下一帧仍为 playing，没有 **写入 `pointer_gpf/tmp/` 的可读证据** 供 MCP 在 `details` 中返回。 |

---

## 3. 文件职责地图（修复时会动到的路径）

| 路径 | 职责 |
|------|------|
| `godot_plugin_template/addons/pointer_gpf/plugin.gd` | 消费 stop 标志、调用 `EditorInterface.stop_playing_scene()`、加固重试、（计划）写入 teardown 失败证据 |
| `godot_plugin_template/addons/pointer_gpf/runtime_bridge.gd` | 处理 `closeProject`、写 flag、写 `response.json` |
| `mcp/server.py` | `_maybe_request_project_close`、可选：读插件写入的 teardown 证据并入 `project_close` |
| `.gitignore` | 是否继续忽略 `examples/godot_minimal/addons/pointer_gpf/`（交付策略核心） |
| `scripts/`（新建） | 将模板插件 **同步** 到 `examples/godot_minimal`（或由 MCP 在 bootstrap 调用） |
| `docs/godot-adapter-contract-v1.md`、`docs/design/99-tools/14-mcp-core-invariants.md`、`README.md` | 三进程模型、**「必须关闭的是 DEBUG 游戏会话窗口」**、与 `closeProject` 的对应关系 |
| `mcp/adapter_contract_v1.json` | 可选：增加 `stopGameTestSession` 作为 `closeProject` 的文档别名（JSON schema 描述层，未必改 action 字符串以兼容旧流） |
| `tests/test_runtime_gate_marker_plugin.py` | 静态断言插件关键符号 |
| `tests/test_flow_execution_runtime.py` 或新建 `tests/test_teardown_debug_window_contract.py` | MCP 侧对 `project_close` 新字段的契约测试 |

---

## 4. 任务分解（带完整步骤与命令）

### Task 1: 交付策略 — 示例工程与模板「同源可验证」

**Files:**

- Modify: `.gitignore`（**二选一**，在计划中选定一种并在 PR 写清理由）
  - **方案 A（推荐）：** 删除对 `examples/godot_minimal/addons/pointer_gpf/` 的忽略，**改为跟踪**与 `godot_plugin_template/addons/pointer_gpf/` 同步的副本（CI 中增加 `diff` 检查或与模板同步脚本）。
  - **方案 B：** 保留 ignore，新增 `scripts/sync_pointer_gpf_addon_from_template.py`（或 `.ps1`），在 **`run_game_basic_test_flow*` 若 `project_root` 为本仓库 `examples/godot_minimal`** 时由 MCP **在 bootstrap 前自动执行**（与「不扫盘找 Godot」规则不冲突：仅仓库内路径拷贝）。

- Create: `scripts/sync_pointer_gpf_addon_from_template.py`（若选方案 B）
- Modify: `mcp/server.py`（若选方案 B：在 `_ensure_runtime_play_mode` 或 `init` 路径前调用同步，需 `allow_temp_project` 类门闩避免误伤临时目录）

- [ ] **Step 1:** 在 PR 描述中写明选定方案 A 或 B（须与团队对「是否提交 addons 到 examples」一致）。

- [ ] **Step 2（方案 A）：** 从模板 **完整复制** `godot_plugin_template/addons/pointer_gpf/` → `examples/godot_minimal/addons/pointer_gpf/`，`git add -f` 若曾被 ignore；提交后 `git status` 无未跟踪的核心插件文件。

- [ ] **Step 2（方案 B）：** 实现同步脚本（用 `shutil.copytree`，覆盖 `plugin.gd`、`runtime_bridge.gd`、`plugin.cfg` 等），在 MCP 内对 `examples/godot_minimal` 调用；单测用 `tempfile` 模拟 `project_root` 验证拷贝结果。

```python
# scripts/sync_pointer_gpf_addon_from_template.py 核心逻辑示意（方案 B）
from pathlib import Path
import shutil

def sync(repo_root: Path, example_root: Path) -> None:
    src = repo_root / "godot_plugin_template" / "addons" / "pointer_gpf"
    dst = example_root / "addons" / "pointer_gpf"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)
```

- [ ] **Step 3:** 运行 `python -m unittest tests.test_runtime_gate_marker_plugin tests.test_godot_test_orchestrator_packaging -v`（若 packaging 与 `project.godot` 冲突，按当前仓库状态调整断言或修复 `project.godot` 测试数据）。

- [ ] **Step 4:** `git commit -m "chore: ship pointer_gpf addon with examples (or auto-sync before flow)"`

---

### Task 2: 契约与产品用语 — 锁定「三进程 + DEBUG 窗口」叙述

**Files:**

- Modify: `docs/godot-adapter-contract-v1.md` — 在 Teardown 节首段增加 **ASCII 或表格**：外层 IDE / Godot 编辑器 / `(DEBUG)` 游戏测试会话；明确 **`closeProject` = 结束第三项**。
- Modify: `docs/design/99-tools/14-mcp-core-invariants.md` — 同上，与 invariant 对齐。
- Modify: `README.md` 与 `README.zh-CN.md` — 各加一句「示例工程内插件须与模板一致（见 Task 1）」。

- [ ] **Step 1:** 提交文档-only commit；`python -m unittest tests.test_adapter_contract_remediation -v`（若仍绑定契约版本）。

---

### Task 3: 桥接层 — 确认 `closeProject` 应答与 flag 写入顺序

**Files:**

- Modify: `godot_plugin_template/addons/pointer_gpf/runtime_bridge.gd`（`closeproject` 分支）

- [ ] **Step 1:** 阅读 `closeproject` 分支：确保 **`issued_at_unix` 写入 flag 文件成功** 之后才写 `response.json` 的 `ok: true`；若当前顺序相反，改为「先持久化 stop 请求，再 ack」，避免 MCP 读到 ack 而编辑器尚未看到 flag。

- [ ] **Step 2:** 若调整顺序，在 `docs/godot-adapter-contract-v1.md` 增加一句「closeProject 应答不得早于 stop 标志落盘」。

- [ ] **Step 3:** `git commit -m "fix(bridge): order closeProject flag before ack"`

---

### Task 4: 插件层 — 收尾失败可观测 + 多帧 stop 兜底

**Files:**

- Modify: `godot_plugin_template/addons/pointer_gpf/plugin.gd`

- [ ] **Step 1:** 在 `_handle_auto_stop_play_request` 成功调用 `EditorInterface.stop_playing_scene()` 后，增加 **最多 5 帧** 的 `call_deferred` 链或计数循环：若 `EditorInterface.is_playing_scene()` 仍为 `true`，重复 `stop_playing_scene()`；若仍真，写入：

```json
{
  "schema": "pointer_gpf.teardown_debug_game.v1",
  "ok": false,
  "reason": "is_playing_scene_still_true_after_stop_retries",
  "stopped_at_unix": 1710000000
}
```

到 `pointer_gpf/tmp/teardown_debug_game_last.json`（路径写进契约）。

- [ ] **Step 2:** `mcp/server.py` 的 `_enrich_project_close_with_runtime_gate_evidence` 或 `_maybe_request_project_close` 返回前 **尝试读取**该文件；若存在且 `ok:false`，在 `project_close` 增加 `debug_game_teardown_ok: false` 与 `debug_game_teardown_detail`。

- [ ] **Step 3:** 单测：Python 侧 mock 文件存在性（不写 Godot 运行时），断言 MCP 把字段透传到 `details.project_close`。

- [ ] **Step 4:** `python -m unittest tests.test_mcp_hard_teardown tests.test_runtime_gate_marker_plugin -v`

- [ ] **Step 5:** `git commit -m "feat(teardown): observable debug-game stop failures"`

---

### Task 5: 真机/版本矩阵 — Godot 4.6 独立 DEBUG 窗口

**Files:**

- Create: `docs/superpowers/notes/2026-04-11-godot-4.6-debug-window-teardown-manual-matrix.md`（手测清单，非代码）

- [ ] **Step 1:** 在装有 **Godot 4.6.1**（与用户一致）的机器上：打开 `examples/godot_minimal`，运行项目至 `(DEBUG)` 窗口出现，触发 MCP `closeProject`（或完整 `run_game_basic_test_flow`），目检窗口是否在 **2 秒内**关闭；记录 Editor 设置里与「独立窗口 / 嵌入」相关项。

- [ ] **Step 2:** 若 **仅** 在某种 Editor 设置下无法关闭，把复现步骤写入上述 note，并在 Task 4 中增加 **针对该设置的专用 API**（从 Godot 文档查 `EditorRunBar` / `EditorDebuggerPlugin` 等，**禁止扫盘**，仅官方 API）。

---

### Task 6: （可选）动作别名 — 降低 `closeProject` 歧义

**Files:**

- Modify: `godot_plugin_template/addons/pointer_gpf/runtime_bridge.gd` — `_resolve_action` 或 `match action`：接受 **`stopGameTestSession`**（新）与 **`closeProject`**（旧）同义。

- Modify: `mcp/adapter_contract_v1.json`、`docs/godot-adapter-contract-v1.md` — 标注 deprecate 语义：推荐新名，旧名保留兼容。

- [ ] **Step 1:** 单测：字符串层测试 `action` 映射（Python 或 GDScript 静态片段由仓库惯例决定）。

- [ ] **Step 2:** `git commit -m "feat(bridge): alias stopGameTestSession to closeProject"`

---

## 5. 自检（writing-plans）

**5.1 需求覆盖**

| 用户要求 | Task |
|----------|------|
| DEBUG 游戏测试窗口必须关 | 1 交付、3 顺序、4 兜底与证据、5 真机 |
| Godot 编辑器工程保持 | 契约 Task 2、不变更 `quit` 默认 |
| 多 IDE / 自动拉起 Godot | Task 2 文档写清边界；MCP 已有 bootstrap，不在此计划重复实现 |

**5.2 占位扫描**  
无 TBD；Task 5 手测文件为明确路径的清单文档。

**5.3 命名一致**  
`teardown_debug_game_last.json`、`debug_game_teardown_ok` 在 Task 4 的 MCP 与契约中保持一致。

---

## 6. 执行交接

**计划已保存到：** `docs/superpowers/plans/2026-04-11-debug-game-window-teardown-closure.md`

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每 Task 派生子代理，Task 间核对；实现时 **必须** 使用 superpowers:subagent-driven-development。  
2. **Inline Execution** — 本会话内用 executing-plans 带检查点连续执行。

**你更倾向哪一种？**
