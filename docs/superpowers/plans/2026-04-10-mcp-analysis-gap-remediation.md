# MCP 分析结论落地：验证基础与核心能力补强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 依据 GPT 5.4 仓库分析结论，在 **Windows 开发与 CI** 前提下先修好测试与门禁、统一版本事实源，再补强「玩法可运行性」判定、自然语言路由与自动修复策略，最后处理文档预期、stdio 协议与 `project_root` 边界。

**Architecture:** 以「单一版本来源 + 契约测试在 PR 上必跑」为底座；`mcp/basic_flow_contracts.py` 集中维护双结论推导（在现有 runtime/input 检查之上叠加步骤与播报证据）；`mcp/nl_intent_router.py` 用可测试的规则表扩展意图；`mcp/bug_fix_strategies.py` 用策略注册表增量扩展；`mcp/server.py` 的 `_resolve_project_root` 与 `_read_mcp_message` 做小步、可测的硬化。

**Tech Stack:** Python 3.11+、`unittest`、`subprocess`、`pathlib`、GitHub Actions (`windows-latest` + PowerShell)、现有 `mcp/server.py` CLI/`stdio` 双模式。

**支持范围（显式收窄）：** 本 MCP 工具链 **仅针对 Windows**（本地开发与 `windows-latest` CI）。本计划**不包含**其他操作系统的支持、验收或专用改造任务。

---

## 文件结构（将创建 / 修改的职责）

| 路径 | 职责 |
| --- | --- |
| `tests/test_*.py`（见各 Task） | 用 `sys.executable` 启动 `mcp/server.py`（与当前 venv/`py` 会话一致）；PowerShell 相关测试见 Task 2 |
| `tests/test_version_manifest_consistency.py`（新建） | 断言 manifest / 运行时 / 可选 README 片段版本一致 |
| `tests/test_nl_intent_router_expanded.py`（新建，或与现有测试合并） | ≥20 条中文表达 → 目标工具映射 |
| `tests/test_basic_flow_dual_conclusions.py`（新建，或与现有合并） | `gameplay_runnability` 正负例（弱证据失败 / 强证据通过） |
| `mcp/version_manifest.json` | **权威**产品版本（`current_version` / `channels.stable.version`） |
| `mcp/server.py` | 启动时读取 manifest 填充默认 `server_version`；`project_root` Godot 校验；stdio 错误计数/退出 |
| `gtr.config.json` | `server_version` 与 manifest 对齐（或由生成脚本同步） |
| `mcp/basic_flow_contracts.py` | 强化 `gameplay_runnability`（`step_broadcast_summary`、`step_count` 下限等） |
| `mcp/nl_intent_router.py` | 扩展意图规则（设计/跑流程/验证可玩性/自动修/UI 对比） |
| `mcp/bug_fix_strategies.py` / `mcp/bug_fix_loop.py` | 新增 3～5 个策略类并注册 |
| `.github/workflows/mcp-smoke.yml` | PR 上增加 Python 契约测试步骤（与文档「PR Required」对齐） |
| `.github/workflows/mcp-integration.yml` | 可选：`pull_request` 触发或内联脚本改用 `sys.executable` |
| `README.md` / `README.zh-CN.md` / `docs/quickstart.md` | 区分一次性人工准备 vs 准备后可自动执行 |
| `docs/mcp-testing-spec.md` | 若 CI 行为变更，同步「PR 必跑」描述 |
| `tests/test_mcp_transport_protocol.py` | `sys.executable` + stdio 坏输入新断言（与 Task 9 联动） |

---

### Task 1: 测试里用当前解释器替代硬编码 `python`

**动机：** 避免子进程固定调用 `python` 时与当前会话使用的解释器（venv、`py -3` 等）不一致导致偶发失败。

**Files:**
- Modify: `tests/test_flow_execution_runtime.py`（含 `grep` 命中行）
- Modify: `tests/test_natural_language_basic_flow_commands.py`（`_run_tool` 内 `cmd`）
- Modify: `tests/test_bug_auto_fix_loop.py`
- Modify: `tests/test_figma_ui_pipeline.py`
- Modify: `tests/test_legacy_runner_pipeline.py`
- Modify: `tests/test_mcp_gap_audit.py`
- Modify: `tests/test_mcp_transport_protocol.py`
- Modify: `tests/test_start_mcp_config.py`（见 Task 2）
- Test: 本地与 CI（`windows-latest`）运行 `python -m unittest discover -s tests -v`

- [ ] **Step 1: 在共用位置增加解释器解析（若尚无）**

在每个直接 `subprocess` 的文件顶部确保：

```python
import sys
```

将 `Popen`/`run` 的第一参数从 `"python"` 改为 `sys.executable`。

以 `tests/test_natural_language_basic_flow_commands.py` 的 `_run_tool` 为例，完整替换为：

```python
def _run_tool(repo_root: Path, tool: str, args: dict) -> dict:
    import json
    import subprocess
    import sys

    payload_args = dict(args)
    if "project_root" in payload_args and "allow_temp_project" not in payload_args:
        payload_args["allow_temp_project"] = True
    cmd = [
        sys.executable,
        str(repo_root / "mcp" / "server.py"),
        "--tool",
        tool,
        "--args",
        json.dumps(payload_args, ensure_ascii=False),
    ]
    proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise AssertionError(f"tool {tool} failed: {proc.stdout}\n{proc.stderr}")
    payload = json.loads(proc.stdout)
    if not payload.get("ok"):
        raise AssertionError(f"tool {tool} returned error: {json.dumps(payload, ensure_ascii=False)}")
    return payload["result"]
```

- [ ] **Step 2: 逐文件替换**

对 `tests/test_mcp_transport_protocol.py` 的 `setUp`：

```python
def setUp(self) -> None:
    self.repo_root = Path(__file__).resolve().parents[1]
    import sys
    self.python_exe = sys.executable
    self.server = str(self.repo_root / "mcp" / "server.py")
```

- [ ] **Step 3: 运行测试**

Run: `python -m unittest discover -s tests -v`

Expected: 子进程始终使用与当前测试进程相同的解释器，避免「PATH 上 `python` 与当前环境不一致」导致的偶发失败

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: use sys.executable instead of hardcoded python for MCP subprocess calls"
```

---

### Task 2: `start-mcp.ps1` 测试（仅 Windows）

**Files:**
- Modify: `tests/test_start_mcp_config.py`

**约定：** 官方开发与 PR CI 均在 Windows 上执行；本测试在非 Windows 上 **整类跳过**。

- [ ] **Step 1: 用 `skipUnless(sys.platform == "win32")` 包裹测试类，并在 Windows 上要求存在 pwsh/powershell**

```python
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


def _has_powershell() -> bool:
    return bool(shutil.which("pwsh") or shutil.which("powershell"))


@unittest.skipUnless(sys.platform == "win32", "MCP 安装脚本测试仅针对 Windows")
class StartMcpConfigTests(unittest.TestCase):
    def test_start_script_prints_stdio_safe_cursor_config(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / "install" / "start-mcp.ps1"
        self.assertTrue(script.exists(), f"missing script: {script}")
        pwsh = shutil.which("pwsh") or shutil.which("powershell")
        self.assertIsNotNone(pwsh, "Windows 环境应安装 PowerShell（pwsh 或 powershell）以运行安装脚本测试")
        proc = subprocess.run(
            [pwsh, "-ExecutionPolicy", "Bypass", "-File", str(script), "-PythonExe", sys.executable],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=f"{proc.stdout}\n{proc.stderr}")
        self.assertIn('"command": "', proc.stdout)
        low = proc.stdout.lower()
        self.assertTrue("python" in low or "py" in low or sys.executable.lower() in low)
        self.assertIn('"-u"', proc.stdout)
        self.assertIn('"--stdio"', proc.stdout)
```

- [ ] **Step 2: 运行**

Run: `python -m unittest tests.test_start_mcp_config -v`

Expected: 在 Windows + PowerShell 可用时 `ok`；非 Windows 上整类 `skipped`

- [ ] **Step 3: Commit**

```bash
git add tests/test_start_mcp_config.py
git commit -m "test: gate start-mcp.ps1 tests to Windows; pass sys.executable to -PythonExe"
```

---

### Task 3: PR 默认 CI 跑关键 Python 契约测试

**Files:**
- Modify: `.github/workflows/mcp-smoke.yml`
- Modify: `docs/mcp-testing-spec.md`（若需与「PR Required」段落一致）

**说明:** `mcp-integration.yml` 仅在 `schedule` 或 `scope==full` 时跑 `unittest`；分析要求与 `docs/mcp-testing-spec.md` 中 L0/L1「PR Required」叙述一致，因此在已在 PR 触发的 `mcp-smoke.yml` 中增加一步最稳妥。

- [ ] **Step 1: 在 `mcp-smoke.yml` 的 `jobs.smoke.steps` 中、`Runtime info smoke` 之后插入**

```yaml
      - name: Python contract tests (NL + flow + bugfix loop)
        shell: pwsh
        run: |
          python -m unittest tests.test_natural_language_basic_flow_commands tests.test_flow_execution_runtime tests.test_bug_auto_fix_loop -v
```

- [ ] **Step 2: 可选 — 内联脚本中的 `["python", ...]` 改为 `sys.executable`**

将 `__mcp_stdio_smoke.py`、`__mcp_exec_smoke.py`、`__mcp_figma_smoke.py` 里 `subprocess` 的 `python` 改为：

```python
import sys
# cmd = [sys.executable, str(repo_root / "mcp" / "server.py"), ...]
```

（与 Task 1 原则一致，避免未来 `windows-latest` 镜像行为变化。）

- [ ] **Step 3: 推送 PR 验证**

Expected: `mcp-smoke` job 绿色，且日志中出现三个 unittest 模块的 `ok`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/mcp-smoke.yml docs/mcp-testing-spec.md
git commit -m "ci: run core MCP unittest modules on every PR smoke workflow"
```

---

### Task 4: 统一版本事实源（manifest 为权威）

**Files:**
- Modify: `mcp/server.py`（`DEFAULT_SERVER_VERSION` 与 `_default_runtime_config` / `_tool_get_mcp_runtime_info` 数据来源）
- Modify: `gtr.config.json`（`server_version`）
- Create: `tests/test_version_manifest_consistency.py`
- Modify: `README.md` / `docs/configuration.md`（若文中硬编码版本号）

- [ ] **Step 1: 在 `mcp/server.py` 增加读取 manifest 的函数（放在 `DEFAULT_SERVER_VERSION` 附近）**

```python
def _read_mcp_version_from_manifest(repo_root: Path) -> str | None:
    manifest = repo_root / "mcp" / "version_manifest.json"
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict):
        v = str(data.get("current_version", "")).strip()
        if v:
            return v
        ch = data.get("channels")
        if isinstance(ch, dict):
            st = ch.get("stable")
            if isinstance(st, dict):
                sv = str(st.get("version", "")).strip()
                if sv:
                    return sv
    return None
```

在构建 `ServerCtx` 后首次需要版本时，用 `ctx.repo_root` 解析；`_default_runtime_config` 中：

```python
def _default_runtime_config(ctx: ServerCtx) -> RuntimeConfig:
    mv = _read_mcp_version_from_manifest(ctx.repo_root)
    ver = mv if mv else DEFAULT_SERVER_VERSION
    return RuntimeConfig(
        server_name=DEFAULT_SERVER_NAME,
        server_version=ver,
        ...
    )
```

保留 `DEFAULT_SERVER_VERSION` 作为「manifest 缺失时」的回退（开发与损坏树）。

- [ ] **Step 2: 将 `gtr.config.json` 的 `server_version` 改为与 `mcp/version_manifest.json` 的 `current_version` 相同**

当前 manifest 为 `0.3.0.0`，则：

```json
"server_version": "0.3.0.0"
```

- [ ] **Step 3: 新建测试 `tests/test_version_manifest_consistency.py`**

```python
import json
import subprocess
import sys
import unittest
from pathlib import Path


class VersionManifestConsistencyTests(unittest.TestCase):
    def test_cli_runtime_version_matches_manifest(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        manifest = json.loads((repo / "mcp" / "version_manifest.json").read_text(encoding="utf-8"))
        expected = str(manifest.get("current_version", "")).strip()
        self.assertTrue(expected)
        proc = subprocess.run(
            [sys.executable, str(repo / "mcp" / "server.py"), "--tool", "get_mcp_runtime_info", "--args", "{}"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload.get("ok"), payload)
        got = str(payload["result"]["server_version"])
        self.assertEqual(got, expected, f"CLI server_version {got!r} != manifest {expected!r}")

    def test_gtr_config_version_matches_manifest(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        manifest = json.loads((repo / "mcp" / "version_manifest.json").read_text(encoding="utf-8"))
        expected = str(manifest.get("current_version", "")).strip()
        gtr = json.loads((repo / "gtr.config.json").read_text(encoding="utf-8"))
        self.assertEqual(str(gtr.get("server_version", "")).strip(), expected)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: 运行**

Run: `python -m unittest tests.test_version_manifest_consistency -v`

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add mcp/server.py gtr.config.json tests/test_version_manifest_consistency.py
git commit -m "fix: derive default server_version from version_manifest.json; align gtr.config"
```

---

### Task 5: 强化 `gameplay_runnability`（在现有 runtime 检查之上）

**现状核对:** `mcp/basic_flow_contracts.py` 中 `_gameplay_runnability_from_execution_report` 已要求 `runtime_mode == "play_mode"`、`runtime_gate_passed`、`input_mode == "in_engine_virtual_input"`、`not os_input_interference`。本任务补齐分析中提到的「关键证据」与「过短流程降级」。

**Files:**
- Modify: `mcp/basic_flow_contracts.py`
- Modify: `tests/test_basic_flow_dual_conclusions.py`（新建）
- Modify: `tests/test_natural_language_basic_flow_commands.py`（若已有双结论断言则扩展）

- [ ] **Step 1: 扩展 `_gameplay_runnability_from_execution_report`**

在 `passed` 布尔表达式中追加（变量从 `execution_report` 读取，缺省安全）：

```python
def _gameplay_runnability_from_execution_report(execution_report: dict[str, Any]) -> dict[str, Any]:
    st = str(execution_report.get("status", ""))
    step_count = int(execution_report.get("step_count") or 0)
    runtime_mode = str(execution_report.get("runtime_mode", ""))
    runtime_entry = str(execution_report.get("runtime_entry", ""))
    runtime_gate_passed = bool(execution_report.get("runtime_gate_passed", False))
    input_mode = str(execution_report.get("input_mode", ""))
    os_input_interference = bool(execution_report.get("os_input_interference", True))
    sbs = execution_report.get("step_broadcast_summary") if isinstance(execution_report.get("step_broadcast_summary"), dict) else {}
    protocol_mode = str(sbs.get("protocol_mode", ""))
    fail_fast_on_verify = sbs.get("fail_fast_on_verify")
    cov_raw = execution_report.get("phase_coverage") if isinstance(execution_report.get("phase_coverage"), dict) else {}
    started = int(cov_raw.get("started") or 0)
    result_n = int(cov_raw.get("result") or 0)
    verify_n = int(cov_raw.get("verify") or 0)

    min_steps_for_full_path = 2
    phase_ok = started >= 1 and result_n >= 1 and verify_n >= 1
    broadcast_ok = protocol_mode == "three_phase" and fail_fast_on_verify is True
    not_trivial_flow = step_count >= min_steps_for_full_path

    base_runtime_ok = (
        st == "passed"
        and step_count >= 1
        and runtime_mode == "play_mode"
        and runtime_gate_passed
        and input_mode == "in_engine_virtual_input"
        and not os_input_interference
    )
    passed = base_runtime_ok and phase_ok and broadcast_ok and not_trivial_flow

    return {
        "passed": passed,
        "evidence": {
            "status": st,
            "step_count": step_count,
            "runtime_mode": runtime_mode,
            "runtime_entry": runtime_entry,
            "runtime_gate_passed": runtime_gate_passed,
            "input_mode": input_mode,
            "os_input_interference": os_input_interference,
            "step_broadcast_summary": {
                "protocol_mode": protocol_mode,
                "fail_fast_on_verify": fail_fast_on_verify,
            },
            "phase_coverage": {"started": started, "result": result_n, "verify": verify_n},
            "min_steps_for_full_path": min_steps_for_full_path,
        },
    }
```

- [ ] **Step 2: 新建失败用例测试**

构造 `execution_report` 字典：`status` 为 `passed` 且 runtime 字段全满足，但 `step_count=1` 或 `protocol_mode` 非 `three_phase`，断言 `build_dual_conclusions(rep)["gameplay_runnability"]["passed"] is False`。

再构造 `step_count=2`、`phase_coverage` 齐全、`step_broadcast_summary` 符合的报告，断言为 `True`。

- [ ] **Step 3: 运行**

Run: `python -m unittest tests.test_basic_flow_dual_conclusions tests.test_natural_language_basic_flow_commands -v`

Expected: 若现有集成测试依赖「单步即 gameplay 通过」，需同步调整 mock 流程 JSON 或测试期望（这是预期内的连锁修改）。

- [ ] **Step 4: Commit**

```bash
git add mcp/basic_flow_contracts.py tests/
git commit -m "feat: tighten gameplay_runnability using phase coverage and step broadcast evidence"
```

---

### Task 6: 扩展自然语言意图路由

**Files:**
- Modify: `mcp/nl_intent_router.py`
- Modify: `tests/test_nl_intent_router_expanded.py`（新建）

- [ ] **Step 1: 将 `route_nl_intent` 改为多层规则（保留原 `_ALIASES` 精确匹配）**

在 `_ALIASES` 之后增加有序规则列表（示例结构）：

```python
def route_nl_intent(text: str) -> IntentRoute:
    norm = str(text or "").strip()
    if norm in _ALIASES:
        return _ALIASES[norm]

    def has(*keys: str) -> bool:
        return any(k in norm for k in keys)

    # 自动修复
    if has("自动修", "自动修复", "auto fix", "bug") and has("修", "修复", "fix", "点不了", "无法点击", "没反应"):
        return IntentRoute("auto_fix_game_bug", "auto_fix_fuzzy")
    if has("按钮") and has("点不了", "无法点击", "没反应", "自动"):
        return IntentRoute("auto_fix_game_bug", "auto_fix_button_fuzzy")

    # UI / Figma
    if has("figma", "设计稿", "UI", "界面对比", "画面对比") and has("对比", "比较", "核查", "检查"):
        return IntentRoute("compare_figma_game_ui", "figma_compare_fuzzy")

    # 跑流程 / 验证可玩
    if has("冒烟", "smoke", "还能玩", "能不能玩", "是否正常", "验证", "检查") and has("版本", "这版", "当前", "游戏", "流程"):
        if has("设计", "生成", "创建", "做一个") and has("流程", "测试"):
            return IntentRoute("design_game_basic_test_flow", "play_check_design_mixed")
        return IntentRoute("run_game_basic_test_flow_by_current_state", "play_check_run_fuzzy")

    if "基础测试流程" in norm and has("跑", "执行", "运行"):
        return IntentRoute("run_game_basic_test_flow_by_current_state", "basic_flow_run_fuzzy")
    if "基础测试流程" in norm and has("设计", "生成", "创建"):
        return IntentRoute("design_game_basic_test_flow", "basic_flow_design_fuzzy")

    if has("开局", "开始游戏", "主菜单", "进入游戏") and has("流程", "测试", "检查", "走一遍"):
        return IntentRoute("run_game_basic_test_flow_by_current_state", "opening_flow_fuzzy")

    return IntentRoute("unknown", "no_match")
```

（实现时按「更具体的规则在前」排序，避免误伤；并用单元测试锁定优先级。）

- [ ] **Step 2: 至少 20 条中文用例**

在 `tests/test_nl_intent_router_expanded.py` 中：

```python
import unittest
from pathlib import Path
import sys

# 确保可从 tests 导入 mcp 包：若项目以 repo 根为 cwd，可用：
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "mcp"))

from nl_intent_router import route_nl_intent  # noqa: E402


class NlIntentRouterExpandedTests(unittest.TestCase):
    def test_basic_flow_and_play_checks(self) -> None:
        cases = [
            ("跑一下基础流程", "run_game_basic_test_flow_by_current_state"),
            ("帮我验证一下这个版本", "run_game_basic_test_flow_by_current_state"),
            ("做一个开局流程检查", "run_game_basic_test_flow_by_current_state"),
            ("检查大改后还能不能正常玩", "run_game_basic_test_flow_by_current_state"),
            ("设计一个基础测试流程", "design_game_basic_test_flow"),
            # ... 至少补齐到 20 条 (text, expected_tool)
        ]
        for text, tool in cases:
            with self.subTest(text=text):
                self.assertEqual(route_nl_intent(text).target_tool, tool)
```

根据 Step 1 实际规则填满 20 条并固定 `target_tool`。

- [ ] **Step 3: 运行**

Run: `python -m unittest tests.test_nl_intent_router_expanded -v`

- [ ] **Step 4: Commit**

```bash
git add mcp/nl_intent_router.py tests/test_nl_intent_router_expanded.py
git commit -m "feat: expand NL intent routing for common Chinese phrasings"
```

---

### Task 7: 扩展自动修复策略（≥3 个新策略）

**Files:**
- Modify: `mcp/bug_fix_strategies.py`
- Modify: `mcp/bug_fix_loop.py`（若需传递策略列表或诊断字段）
- Modify: `tests/test_bug_auto_fix_loop.py`

**建议策略（规则化、可测）:**

1. **`UiDisabledTrueStrategy`**：`issue` 含 `disabled` / `禁用` / `灰掉`；在 `.tscn` 中查找目标 `Button` 的 `disabled = true`（需约定从 `verification` 或 issue 中提取节点名，或使用项目中第一个 `disabled = true` 的按钮 —— 测试里用最小场景固定路径）。
2. **`MouseFilterStopStrategy`**：issue 含 `mouse_filter` / `鼠标` / `点击穿透`；将 `mouse_filter = 2`（STOP）改为 `0`（MOUSE_FILTER_STOP→IGNORE 需查 Godot 枚举；以项目内实际数字为准）。
3. **`SignalConnectionHintStrategy`**：issue 含 `信号` / `signal` / `未连接`；**不盲目改场景**，仅返回结构化 `diagnose` 并在 `apply_patch` 写入 `pointer_gpf/reports/signal_hint_<slug>.json` 或在注释中插入 `TODO` —— 若坚持「必须改代码通过复测」，可在测试项目里放一个已知「未连接信号」的 `.tscn` 补丁。

每个策略实现 `BugFixStrategy` 协议，并加入：

```python
DEFAULT_STRATEGIES: tuple[BugFixStrategy, ...] = (
    ButtonNotClickableStrategy(),
    UiDisabledTrueStrategy(),
    MouseFilterStopStrategy(),
    # ...
)
```

- [ ] **Step 1: 为每个策略写失败 → 补丁 → 成功的集成测试**

沿用 `tests/test_bug_auto_fix_loop.py` 的临时目录 Godot 项目模式；`issue` 字符串触发对应 `matches()`。

- [ ] **Step 2: 运行**

Run: `python -m unittest tests.test_bug_auto_fix_loop -v`

- [ ] **Step 3: Commit**

```bash
git add mcp/bug_fix_strategies.py mcp/bug_fix_loop.py tests/test_bug_auto_fix_loop.py
git commit -m "feat: add additional rule-based bug fix strategies with tests"
```

---

### Task 8: 文档区分「一次性人工准备」与「可自动执行」

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `docs/quickstart.md`

- [ ] **Step 1: 在「安装 / 使用」章节前增加固定小节**

```markdown
## 自动化边界说明

**一次性人工准备（环境未就绪前无法省略）**
- 在 Cursor（或其他客户端）中配置 MCP 与启动参数
- 目标 Godot 工程中启用 PointerGPF 插件
- 需要文件桥时：由编辑器或自动化拉起进入可响应的运行态（见运行门禁）

**准备完成后可由工具链自动执行**
- 初始化/刷新项目上下文、生成与执行基础测试流程
- 自然语言路由触发的上述工具（在路由命中时）
- 自动修复循环（在策略匹配且验证可重入时）

**必须保留人工决策的环节**
- UI/Figma 修复方案的批准（`approve_ui_fix_plan`）
```

- [ ] **Step 2: 将原文中 `You must do this manually` 段落引用链接到该小节**

- [ ] **Step 3: Commit**

```bash
git add README.md README.zh-CN.md docs/quickstart.md
git commit -m "docs: clarify human-only setup vs agent-executable MCP actions"
```

---

### Task 9: stdio 坏输入：计数阈值 + JSON-RPC 错误响应

**Files:**
- Modify: `mcp/server.py`（`_read_mcp_message` / `_run_stdio_mcp`）
- Modify: `tests/test_mcp_transport_protocol.py`

- [ ] **Step 1: 在 `_read_mcp_message` 中增加连续帧错误计数**

模块级：` _STDIO_PARSE_ERRORS = 0`，阈值例如 `8`。每次 `continue`（非法 JSON 行、缺 Content-Length、非法长度、body 非 JSON）前 `+= 1`，成功解析 dict 后清零。超过阈值时向 stderr 打印明确消息并 `sys.exit(2)` **或** 返回特殊哨兵让 `_run_stdio_mcp` 写一条 `jsonrpc` error（推荐 exit，便于 CI 快速失败）。

伪代码：

```python
_STDIO_SOFT_ERROR_CAP = 8
_stdio_soft_errors = 0

def _read_mcp_message() -> dict[str, Any] | None:
    global _stdio_soft_errors, _MCP_IO_MODE
    while True:
        ...
        except JSONDecodeError:
            _stdio_soft_errors += 1
            if _stdio_soft_errors >= _STDIO_SOFT_ERROR_CAP:
                print("MCP stdio: too many consecutive framing/parse errors", file=sys.stderr)
                sys.exit(2)
            continue
```

- [ ] **Step 2: 测试向子进程 stdin 写入 9 行垃圾后进程在超时内退出且 returncode != 0**

使用 `subprocess.Popen` + `communicate(input=...)`，`timeout=5`。

- [ ] **Step 3: Commit**

```bash
git add mcp/server.py tests/test_mcp_transport_protocol.py
git commit -m "fix: fail fast on repeated stdio parse/framing errors"
```

---

### Task 10: `project_root` 必须像 Godot 项目（可配置豁免）

**Files:**
- Modify: `mcp/server.py`（`_resolve_project_root`）
- Modify: `tests/test_flow_execution_runtime.py`（负例：无 `project.godot`）
- Modify: `docs/configuration.md`（记录 `skip_godot_project_check` 或所选参数名）

- [ ] **Step 1: 在 `_resolve_project_root` 末尾、`return root` 之前**

```python
    skip_godot_check = bool(arguments.get("skip_godot_project_check", False))
    if not skip_godot_check:
        pg = root / "project.godot"
        if not pg.is_file():
            raise AppError(
                "INVALID_GODOT_PROJECT",
                f"project.godot not found under project_root: {root}",
                {"project_root": str(root), "fix": "point project_root at Godot project root, or pass skip_godot_project_check=true for rare non-standard layouts"},
            )
    return root
```

- [ ] **Step 2: 全仓库搜索调用 `_resolve_project_root` 的测试临时目录**

凡使用临时目录且**未**放置 `project.godot` 的，要么创建最小 `project.godot`，要么传入 `skip_godot_project_check=true`（仅用于非 Godot 单测若存在）。

- [ ] **Step 3: 运行全量 `unittest`**

Run: `python -m unittest discover -s tests -v`

- [ ] **Step 4: Commit**

```bash
git add mcp/server.py tests/ docs/configuration.md
git commit -m "feat: require project.godot under project_root unless explicitly skipped"
```

---

## Self-Review

**1. Spec coverage（对照分析结论）**

| 分析项 | Task |
| --- | --- |
| 测试写死 python；Windows 上 PowerShell 脚本测试 | 1, 2 |
| CI 默认契约测试 | 3 |
| 版本分叉 | 4 |
| gameplay_runnability 偏弱 | 5（并注明已有 runtime 检查） |
| NL 路由窄 | 6 |
| 策略窄 | 7 |
| README 人工步骤预期 | 8 |
| stdio 宽容 | 9 |
| project_root 边界 | 10 |
| 非 Windows 场景 | **不在范围内**；`game-test-runner` 等继续使用 Windows 专用命令与本计划一致，不单独开「多平台抽象」类 Task |

**2. Placeholder scan:** 本计划未使用 TBD；Task 6/7 中策略与用例需在实现时把注释「...」替换为完整列表（执行子 agent 时逐条填满）。

**3. Type consistency:** `route_nl_intent` 仍返回 `IntentRoute`；`AppError` 码 `INVALID_GODOT_PROJECT` 在文档与测试中保持一致。

---

## Execution Handoff

**计划已保存至** `docs/superpowers/plans/2026-04-10-mcp-analysis-gap-remediation.md`。

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 派生子代理，任务间做简短审查。  
   **必须配合技能：** `superpowers:subagent-driven-development`。

2. **本会话内联执行** — 使用 `superpowers:executing-plans` 分批执行并设检查点。

你更倾向哪一种？
