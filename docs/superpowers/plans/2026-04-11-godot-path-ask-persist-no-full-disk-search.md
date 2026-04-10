# Godot 路径 AskQuestion + 持久化（禁止全盘搜索）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 当 GPF（MCP）无法解析到可用的 Godot 编辑器可执行文件时，**根因上**应通过 MCP 返回清晰、可操作的失败信息，引导 **AskQuestion + 写入项目内 `godot_executable.json`** 完成持久化；**仓库内若曾存在**对整盘或等价大范围文件系统的 Godot 搜索逻辑，须**调查后彻底删除**。装载 GPF 的 IDE 代理**不得**用「再叠一条禁止搜索的规则」代替「删掉错误代码、修好流程」。

**Architecture:** **第一优先级（代码）**：Task 0 全仓审计与删除/收敛任何「全盘 / 多盘根递归 / `where /R` 式」Godot 发现逻辑；MCP 在 gate 失败时注入 `godot_executable_resolution`（仅事实字段：`status`、`persist_*`、`example_object`），让正确流程不依赖禁令字符串。**第二优先级（文档与 IDE）**：`docs/gpf-godot-executable-ask-and-persist.md` 写清用户路径与 JSON；`.cursor/rules/gpf-godot-executable-discovery.mdc` **仅**作为对代理行为的说明与验收清单，**不**视为对错误代码的掩盖。**可选**：`configure_godot_executable` 工具减少手写 JSON 出错。

**Tech Stack:** Python 3.11+、`pathlib`、`json`、`unittest`、Cursor AskQuestion、现有 `tools/game-test-runner/core/godot_executable_config.py`。

---

## 永久工程原则（此类问题的统一处理方式）

以下原则适用于 **本计划及以后所有「流程明显不合理」的排障/方案**，写入本计划并应在实施时同步到 **`AGENTS.md`** 或 **`docs/design/99-tools/`** 下独立一页（实现 Task 0 末尾勾选其一即可），避免只在本文件口头约定：

1. **功能或流程错了，优先判定为代码或契约写错了**，而不是「用户环境不对」「代理不够聪明」。
2. **修复顺序**：**定位根因（哪段代码、哪份契约）→ 改代码或契约使默认路径正确 → 删除或停用错误分支 → 全局检索受影响调用点并一并修正/清理**；禁止把「新增一条禁止某某命令的规则」当作首选手段去**掩盖**仍未删除的错误逻辑。
3. **规则类产物（`.cursor/rules`、文档中的「禁止」列表）的定位**：仅用于**记录正确流程、供人类与代理对照验收**；若在审计中发现**仓库代码已无不合理搜索**，则规则中应明确写「根因已在代码层消除」，避免规则与代码双重真值冲突。
4. **若禁令式规则已存在、但错误代码仍在**：应先删/改代码，再**收紧或删除**仅为压制症状而加的规则条目，避免「越禁越多」。

---

## 背景事实与根因假设（须由 Task 0 证实或推翻）

- **`mcp/server.py`** 的 `_discover_godot_executable_candidates` **当前实现**仅组合：项目内 `tools/game-test-runner/config/godot_executable.json`、工具参数、环境变量 `GODOT_*`；**不包含**对 `C:\` / `D:\` 根目录的递归枚举。
- **`tools/game-test-runner/mcp/server_common.py`** 中 `common_windows_godot_candidates()` 仅在 `ProgramFiles`、`LOCALAPPDATA\Programs` 等**有限根目录**下做 `glob`，属于「固定安装前缀枚举」，**不等价**于对整盘 `Get-ChildItem -Path D:\ -Recurse`；若产品决策认为连该枚举也不允许，应在 Task 0 中**单独立项**删除或收紧并更新文档，而非用代理全盘搜索替代。
- 用户截图中的「浅层递归搜索 C/D 盘」**高度疑似**为 **Cursor 代理在收到「未找到 Godot」后的即兴 Shell 策略**，而非 `pointer_gpf` 已提交 Python 入口；Task 0 必须用 `rg`/代码搜索**证实**仓库内**不存在**被 CI 或 MCP 调用的同类脚本；若**发现**则**整段删除**并补充回归测试。
- **Task 0 结论（2026-04-11）**：仓库内 **未发现** MCP 主路径对 `C:\`/`D:\` 根递归搜索 Godot 的实现；审计表见 `docs/superpowers/notes/2026-04-11-task0-godot-discovery-audit.md`。`common_windows_godot_candidates` 为有限前缀 `glob`，本计划周期内**保留**（未删）。扫盘行为归类为 IDE 代理即兴 Shell，由文档与规则约束。

---

## 文件结构（创建或修改）

| 文件 | 职责 |
|------|------|
| `AGENTS.md` 或 `docs/design/99-tools/XX-root-cause-before-forbid-rules.md`（二选一新建/扩写） | 固化「永久工程原则」为仓库级契约，供检索与评审 |
| `docs/gpf-godot-executable-ask-and-persist.md` | 用户/代理：何时提问、写哪一文件、JSON 形状、**正确**排障步骤（不以「禁止标签」为主） |
| `.cursor/rules/gpf-godot-executable-discovery.mdc` | **补充性**：AskQuestion + 写配置；写明「若 MCP 已返回 `godot_executable_resolution`，按字段执行，禁止自行发明搜索脚本」 |
| `mcp/server.py` | gate 失败时 `godot_executable_resolution`；**删除**经 Task 0 认定的有害发现逻辑（若有） |
| `tools/game-test-runner/mcp/server_common.py` 等 | Task 0 审计命中时删除或替换 `common_windows_godot_candidates` 等争议逻辑 |
| `tests/test_flow_execution_runtime.py` | 断言 `godot_executable_resolution`（`no_executable_candidates` 等缺失场景） |
| `docs/gpf-ai-agent-integration.md` | 增加指向 `docs/gpf-godot-executable-ask-and-persist.md` 的链接（不重复时） |

---

### Task 0: 根因调查 —— 为何会全盘搜索？仓库内是否仍有实现？彻底删除

**Files:**
- 全仓检索（只读）：`rg -i "recurse|Get-ChildItem|where\\.exe\\s+/R|glob\\(.*Godot"` 等，范围 `d:\\AI\\pointer_gpf`（含 `mcp/`、`tools/`、`scripts/`、`.cursor/`、`docs/`）
- Modify：经命中且确认为「Godot 可执行文件发现」用途的 **Python / PowerShell / 文档中的可复制命令模板** —— **删除**该逻辑或改为「仅读配置/参数/环境变量」；**不得**改为「再写一条规则禁止」而不删代码

- [ ] **Step 1: 记录调查表（写入计划附录或 `docs/superpowers/notes/` 单页，≤40 行）**

列：`路径`、`函数或脚本名`、`行为摘要（是否整盘/多盘根）`、`结论（删 / 留 / 收紧）`、`删除 PR 链接或 commit`。

- [ ] **Step 2: 若 `mcp/server.py` 与截图行为无关，在结论中明确写出一句**，避免后续贡献者误以为 MCP 调用了全盘搜索。

- [ ] **Step 3: 执行删除或收敛后** `python -m unittest tests.test_flow_execution_runtime tests.test_godot_bootstrap_session_gate -q`（或当前仓库约定的最小回归集），**全部通过**再进入 Task 1。

- [ ] **Step 4: 提交**

```bash
git add -A
git commit -m "fix: remove unsafe godot discovery; document Task0 audit"
```

（`git add -A` 仅当确有多文件删除；否则显式列出路径。）

---

### Task 1: 人类与代理共用的说明文档

**Files:**
- Create: `docs/gpf-godot-executable-ask-and-persist.md`

- [ ] **Step 1: 写入下列完整正文（可按需微调标题层级，不得删字段语义）**

```markdown
# Godot 可执行文件：询问用户并持久化

## 何时必须询问用户

当 `run_game_basic_test_flow` / `run_game_basic_test_flow_by_current_state` 返回失败，且 `error.details.engine_bootstrap.launch_error` 为 **`no_executable_candidates`**，或 `error.details.godot_executable_resolution.status` 为 **`missing`** 时，代理**必须先**用 AskQuestion 向用户索取 **Godot 4.x 编辑器** 的 **`Godot*.exe` 绝对路径**（Windows 示例：`D:\Godot\Godot_v4.2.2-stable_win64.exe`）。**不要**自行编写对 `C:\`/`D:\` 根目录递归、`where.exe /R` 等「扫盘式」Shell 来「找 Godot」——那是错误流程；若仓库内仍有脚本这么做，应在代码层删除（见本仓库 `docs/superpowers/plans/2026-04-11-godot-path-ask-persist-no-full-disk-search.md` 的 Task 0）。

## 持久化路径（按 project_root）

- 相对路径：`tools/game-test-runner/config/godot_executable.json`
- 绝对路径：`{project_root}/tools/game-test-runner/config/godot_executable.json`
- 目录不存在时：`mkdir -p` 等价创建 `tools/game-test-runner/config`。

## JSON 文件内容（UTF-8）

```json
{
  "godot_executable": "D:/Godot/Godot_v4.2.2-stable_win64.exe"
}
```

键名允许使用 **`godot_executable`**（推荐）、`godot_bin` 或 `GODOT_BIN` 之一；与 `tools/game-test-runner/core/godot_executable_config.py` 一致。

## 用户已在消息中给出路径时

若用户在同一条消息中已给出可验证的绝对路径且以 `.exe` 结尾（Windows），可跳过 AskQuestion，但仍须在写入 JSON 后**复述**已采用的路径与文件位置。

## 写入后

重新执行同一 `project_root` 下的 `run_game_basic_test_flow*`（可在 `--args` 中继续传 `failure_handling` 等字段）。

## 正确排障顺序（与仓库原则一致）

1. 读 MCP 返回的 `godot_executable_resolution.persist_abs` 与 `example_object`。  
2. AskQuestion → 用户确认路径 → 写入该 JSON。  
3. 重跑同一 `project_root` 的流程。  
4. 若仍失败：查 `engine_bootstrap` 其它字段，**不要**扩大搜索范围到整盘。
```

- [ ] **Step 2: 提交**

```bash
git add docs/gpf-godot-executable-ask-and-persist.md
git commit -m "docs: godot path ask persist and forbid full drive search"
```

---

### Task 2: Cursor 规则（**补充**：正确代理行为；**不**替代 Task 0 的代码删除）

**Files:**
- Create: `.cursor/rules/gpf-godot-executable-discovery.mdc`

- [ ] **Step 1: 写入 frontmatter + 正文**

```yaml
---
description: Godot 未配置时：按 MCP 返回字段 AskQuestion 并写入 godot_executable.json；不自行扫盘。本规则不替代仓库内错误代码的删除（见 AGENTS / 设计文档中的根因优先原则）。
alwaysApply: false
---
```

正文要点（完整写入文件）：

1. **前置声明（必须出现在正文首段）**：若 `pointer_gpf` 仓库代码经 Task 0 审计已不包含全盘搜索，代理**不得**「发明」扫盘命令；本规则与 **`godot_executable_resolution`** 字段共同约束**代理侧**行为。
2. 触发条件：`RUNTIME_GATE_FAILED` 且（`engine_bootstrap.launch_error == "no_executable_candidates"` **或** `details.godot_executable_resolution.status == "missing"`）。
3. **不要**：在 PowerShell 中对 `C:\`、`D:\`（或任意整盘根）使用 `-Recurse` 搜索 `Godot*.exe`；不要使用 `where.exe /R` 作为主要策略——**与「永久工程原则」一致：若曾依赖此类脚本排障，应删除脚本并改用本流程**。
4. **必须**：使用 **AskQuestion**，`question id`：`godot_editor_executable_path`，`prompt` 使用 `docs/gpf-godot-executable-ask-and-persist.md` 中「何时必须询问用户」段落的语义（中文），选项可为「用户将下一条消息粘贴路径」的单选占位 + 「取消」——若 Cursor AskQuestion 仅支持固定选项，则采用：**选项 A**：「我将在下一条消息发送 Godot 的 `.exe` 绝对路径」；**选项 B**：「取消本次流程」。用户选 A 后，代理在下一条用户消息中读取路径。
5. **必须**：将路径写入 `{project_root}/tools/game-test-runner/config/godot_executable.json`，格式见该文档 JSON 示例。
6. 若用户拒绝或未提供有效路径：`blocking_point` 已在 MCP 中说明，代理复述 `next_actions` 中的第一条即可。

- [ ] **Step 2: 提交**

```bash
git add .cursor/rules/gpf-godot-executable-discovery.mdc
git commit -m "chore(cursor): document godot path ask+persist (supplement to code fix)"
```

---

### Task 3: MCP 在 gate 失败时注入 `godot_executable_resolution`

**Files:**
- Modify: `mcp/server.py`（`_tool_run_game_basic_test_flow_execute` 内构建 `_rgf_details` 的分支，`runtime_gate_passed` 为 false 时）

- [ ] **Step 1: 在 `mcp/server.py` 顶部工具区附近新增小函数**

```python
def _godot_executable_resolution_for_gate_failure(
    project_root: Path, engine_bootstrap: dict[str, Any]
) -> dict[str, Any] | None:
    launch_err = str(engine_bootstrap.get("launch_error", "")).strip()
    if launch_err == "no_executable_candidates":
        return _build_godot_resolution_missing(project_root)
    if launch_err.startswith("executable_not_found:"):
        return _build_godot_resolution_missing(project_root)
    return None


def _build_godot_resolution_missing(project_root: Path) -> dict[str, Any]:
    cfg_abs = (project_root / "tools" / "game-test-runner" / "config" / "godot_executable.json").resolve()
    return {
        "status": "missing",
        "persist_abs": str(cfg_abs),
        "persist_rel": "tools/game-test-runner/config/godot_executable.json",
        "example_object": {"godot_executable": "D:/Godot/Godot_v4.2.2-stable_win64.exe"},
    }
```

（**不**在 JSON 中堆叠「禁止标签」代替产品语义；若需禁止扫盘，用文档与 Task 0 删代码表达。）

（若希望合并「候选皆不存在」：`launch_attempted` 为 true 且 `launch_succeeded` 为 false 且每条错误均为 `executable_not_found:` 前缀——可在实现时用一个 5 行内的辅助判断，计划不展开分支爆炸。）

- [ ] **Step 2: 在 `_rgf_details` 字典构建处合并**

在 `"engine_bootstrap": engine_bootstrap` 之后插入：

```python
        _gres = _godot_executable_resolution_for_gate_failure(project_root, engine_bootstrap)
        if _gres is not None:
            _rgf_details["godot_executable_resolution"] = _gres
```

- [ ] **Step 3: 在 `next_actions` 列表首条或新增一条（中文）**

```python
                "若尚未配置：用 AskQuestion 取得用户 Godot 编辑器 .exe 绝对路径，并写入 godot_executable_resolution.persist_abs 所指 JSON（见 docs/gpf-godot-executable-ask-and-persist.md）；勿使用整盘递归 Shell 自行发现 Godot（错误流程，见仓库根因优先原则）。",
```

（保留原有 `next_actions` 条目，仅追加，避免破坏依赖「列表非空」的测试。）

- [ ] **Step 4: 提交**

```bash
git add mcp/server.py
git commit -m "feat(mcp): godot_executable_resolution on gate failure"
```

---

### Task 4: 单元测试

**Files:**
- Modify: `tests/test_flow_execution_runtime.py`

- [ ] **Step 1: 在 `test_run_flow_gate_failure_includes_engine_bootstrap_evidence` 末尾追加断言**

```python
        gres = details.get("godot_executable_resolution") or {}
        self.assertEqual(gres.get("status"), "missing")
        self.assertIn("persist_abs", gres)
        self.assertEqual(
            gres.get("persist_rel"),
            "tools/game-test-runner/config/godot_executable.json",
        )
```

- [ ] **Step 2: 运行**

```bash
cd D:\AI\pointer_gpf
python -m unittest tests.test_flow_execution_runtime.FlowExecutionRuntimeTests.test_run_flow_gate_failure_includes_engine_bootstrap_evidence -v
```

期望：`ok`。

- [ ] **Step 3: 提交**

```bash
git add tests/test_flow_execution_runtime.py
git commit -m "test(mcp): godot_executable_resolution on missing exe"
```

---

### Task 5（可选）：MCP 工具 `configure_godot_executable`

**Files:**
- Modify: `mcp/server.py`（`_build_tool_map`、schema、`main` CLI 分支）
- Create: `tests/test_configure_godot_executable_tool.py`

- [ ] **Step 1: 实现 `_tool_configure_godot_executable(ctx, arguments)`**

```python
def _tool_configure_godot_executable(ctx: ServerCtx, arguments: dict[str, Any]) -> dict[str, Any]:
    project_root = _resolve_project_root(arguments)
    raw = str(arguments.get("godot_executable", "")).strip()
    if not raw:
        raise AppError("INVALID_ARGUMENT", "godot_executable is required", {})
    p = Path(raw).expanduser()
    if not p.is_file():
        raise AppError("INVALID_ARGUMENT", f"godot_executable not a file: {p}", {"path": str(p)})
    cfg_dir = (project_root / "tools" / "game-test-runner" / "config").resolve()
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / "godot_executable.json"
    payload = {"godot_executable": str(p)}
    cfg_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "written", "path": str(cfg_path), "godot_executable": str(p)}
```

- [ ] **Step 2: 注册工具名 `configure_godot_executable`，inputSchema `required: ["project_root","godot_executable"]`**

- [ ] **Step 3: 单测**（临时目录 + CLI `--tool configure_godot_executable`）

```python
def test_configure_godot_executable_writes_json(self) -> None:
    # 创建假 exe 空文件 + project_root + 调用 _run_tool_cli_raw
    ...
```

- [ ] **Step 4: 提交**

```bash
git add mcp/server.py tests/test_configure_godot_executable_tool.py
git commit -m "feat(mcp): configure_godot_executable tool"
```

---

## Self-Review

1. **Spec coverage:** Task 0 根因删除 + Task 1 文档 + Task 2 补充规则 + Task 3 MCP 事实字段 + Task 4 测试 + 可选 Task 5；**永久工程原则**有独立章节并要求落入 `AGENTS.md` 或 `docs/design/99-tools/`。
2. **Placeholder scan:** 无 TBD。
3. **Type一致性:** `persist_rel` 与 `godot_executable_config.py` 中 `tools/game-test-runner/config/godot_executable.json` 一致。
4. **原则自检:** 未把「新增禁止命令/标签」列为首选修复；MCP payload 已去掉 `forbidden_agent_patterns` 示例。

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-11-godot-path-ask-persist-no-full-disk-search.md`. Two execution options:**

**1. Subagent-Driven（推荐）** — 每个 Task 派生子代理，任务间复核，迭代快。

**2. Inline Execution** — 本会话内用 executing-plans 批量执行并设检查点。

**Which approach?**
