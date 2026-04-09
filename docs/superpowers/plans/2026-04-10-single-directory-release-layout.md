# PointerGPF 单目录发布整合 Implementation Plan

> 状态：草案（计划文档，未声明已全部落地）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将所有 PointerGPF 相关实现与资产统一收纳到 `pointer_gpf/` 目录下，仅保留根目录最小入口文件，保证 release 安装后用户工作区整洁且功能不回退。

**Architecture:** 发布包改为“单目录载荷”结构：`pointer_gpf/**` 承载全部功能文件，根目录只保留入口文件（如 `pointer-gpf.cmd`）。更新脚本从 `zip_layout=pointer_gpf_root` 解析并同步整目录，再通过兼容入口调用内部脚本。通过“解包后工具清单 + legacy 调用 + 路径洁净”三类测试建立阻断门禁。

**Tech Stack:** Python unittest、PowerShell、GitHub Actions、zip 发布链路、MCP CLI

---

## Scope Check

本需求聚焦单一子系统：**发布包结构与安装更新链路的一致性治理**。虽然涉及 workflow、安装脚本、版本清单、测试与文档，但目标一致，不拆成多个计划。

---

## 文件结构与职责锁定

- 新增 `tests/test_release_single_directory_layout.py`：单目录发布契约测试（结构、工具可用、根目录最小入口）。
- 修改 `.github/workflows/release-package.yml`：输出 `pointer_gpf/` 单目录载荷并补齐 legacy 依赖目录。
- 修改 `install/update-mcp.ps1`：识别并处理 `zip_layout=pointer_gpf_root`，默认同步 `pointer_gpf/` 全目录。
- 修改 `install/pointer-gpf.ps1` 与 `pointer-gpf.cmd`：保持根入口，但将执行落到 `pointer_gpf/install/*`。
- 修改 `mcp/version_manifest.json`：更新 `zip_layout` 与 release 说明。
- 修改 `docs/quickstart.md` 与 `docs/design/99-tools/15-mcp-full-audit-critical-task-2026-04-10.md`：同步用户可见安装路径与发布约束。
- 修改 `.github/workflows/mcp-smoke.yml`（可选最小改动）：新增“单目录 layout smoke”检查。

---

### Task 1: 建立单目录发布契约测试（先红后绿）

**Files:**
- Create: `tests/test_release_single_directory_layout.py`
- Modify: `tests/test_ci_legacy_coverage.py`
- Test: `tests/test_release_single_directory_layout.py`

- [ ] **Step 1: 写失败测试（单目录结构 + 关键能力）**

```python
import json
import tempfile
import unittest
import zipfile
from pathlib import Path


class ReleaseSingleDirectoryLayoutTests(unittest.TestCase):
    def test_manifest_zip_layout_is_pointer_gpf_root(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        payload = json.loads((repo / "mcp" / "version_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["channels"]["stable"]["artifact"]["zip_layout"], "pointer_gpf_root")

    def test_release_workflow_packages_pointer_gpf_root(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        wf = (repo / ".github" / "workflows" / "release-package.yml").read_text(encoding="utf-8")
        self.assertIn('Join-Path $stageDir "pointer_gpf"', wf)
        self.assertIn('Copy-Item -LiteralPath "tools/game-test-runner"', wf)
        self.assertIn('Copy-Item -LiteralPath "flows"', wf)

    def test_root_keeps_minimal_entry_only(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        cmd = (repo / "pointer-gpf.cmd").read_text(encoding="utf-8")
        self.assertIn("pointer_gpf\\install\\pointer-gpf.ps1", cmd)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m unittest tests.test_release_single_directory_layout -v`  
Expected: FAIL（当前 `zip_layout` 与 workflow 尚未改为单目录）

- [ ] **Step 3: 补充 legacy 覆盖测试（防止路径改造后能力回退）**

```python
class CiLegacyCoverageTests(unittest.TestCase):
    def test_workflows_include_legacy_gameplayflow_commands(self) -> None:
        repo = Path(__file__).resolve().parents[1]
        smoke = (repo / ".github" / "workflows" / "mcp-smoke.yml").read_text(encoding="utf-8")
        integ = (repo / ".github" / "workflows" / "mcp-integration.yml").read_text(encoding="utf-8")
        release = (repo / ".github" / "workflows" / "release-package.yml").read_text(encoding="utf-8")
        combined = smoke + integ + release
        self.assertIn("run_game_flow", combined)
        self.assertIn("start_stepwise_flow", combined)
        self.assertIn("pull_cursor_chat_plugin", combined)
```

- [ ] **Step 4: 运行本任务测试集**

Run: `python -m unittest tests.test_release_single_directory_layout tests.test_ci_legacy_coverage -v`  
Expected: 初次 FAIL；完成后 PASS。

- [ ] **Step 5: 提交**

```bash
git add tests/test_release_single_directory_layout.py tests/test_ci_legacy_coverage.py
git commit -m "test: add single-directory release layout contract checks"
```

---

### Task 2: 改造 release-package 为单目录载荷并补齐依赖

**Files:**
- Modify: `.github/workflows/release-package.yml`
- Test: `tests/test_release_single_directory_layout.py`

- [ ] **Step 1: 写失败断言（发布包必须包含 pointer_gpf 根）**

```python
def test_release_workflow_copies_all_gpf_assets_into_pointer_dir(self) -> None:
    repo = Path(__file__).resolve().parents[1]
    wf = (repo / ".github" / "workflows" / "release-package.yml").read_text(encoding="utf-8")
    required = [
        'Copy-Item -LiteralPath "mcp" -Destination (Join-Path $payloadDir "mcp")',
        'Copy-Item -LiteralPath "install" -Destination (Join-Path $payloadDir "install")',
        'Copy-Item -LiteralPath "godot_plugin_template" -Destination (Join-Path $payloadDir "godot_plugin_template")',
        'Copy-Item -LiteralPath "tools/game-test-runner" -Destination (Join-Path $payloadDir "tools/game-test-runner")',
        'Copy-Item -LiteralPath "flows" -Destination (Join-Path $payloadDir "flows")',
    ]
    for item in required:
        self.assertIn(item, wf)
```

- [ ] **Step 2: 修改 workflow 最小实现**

```yaml
- name: Build package zip
  shell: pwsh
  run: |
    $version = "${{ github.event.inputs.version }}"
    $outDir = "dist"
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    $zip = Join-Path $outDir ("pointer-gpf-mcp-" + $version + ".zip")
    $stageDir = Join-Path $outDir "package-root"
    $payloadDir = Join-Path $stageDir "pointer_gpf"
    if (Test-Path -LiteralPath $stageDir) { Remove-Item -LiteralPath $stageDir -Recurse -Force }
    New-Item -ItemType Directory -Path $payloadDir -Force | Out-Null

    Copy-Item -LiteralPath "mcp" -Destination (Join-Path $payloadDir "mcp") -Recurse -Force
    Copy-Item -LiteralPath "install" -Destination (Join-Path $payloadDir "install") -Recurse -Force
    Copy-Item -LiteralPath "godot_plugin_template" -Destination (Join-Path $payloadDir "godot_plugin_template") -Recurse -Force
    Copy-Item -LiteralPath "tools/game-test-runner" -Destination (Join-Path $payloadDir "tools/game-test-runner") -Recurse -Force
    Copy-Item -LiteralPath "flows" -Destination (Join-Path $payloadDir "flows") -Recurse -Force
    Copy-Item -LiteralPath "docs" -Destination (Join-Path $payloadDir "docs") -Recurse -Force
    Copy-Item -LiteralPath "examples" -Destination (Join-Path $payloadDir "examples") -Recurse -Force
    Copy-Item -LiteralPath "gtr.config.json" -Destination (Join-Path $payloadDir "gtr.config.json") -Force
```

- [ ] **Step 3: 保留根目录最小入口文件**

```yaml
    Copy-Item -LiteralPath "pointer-gpf.cmd" -Destination (Join-Path $stageDir "pointer-gpf.cmd") -Force
    Copy-Item -LiteralPath "README.md" -Destination (Join-Path $stageDir "README.md") -Force
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_release_single_directory_layout -v`  
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add .github/workflows/release-package.yml tests/test_release_single_directory_layout.py
git commit -m "build: package pointer_gpf as single release root"
```

---

### Task 3: 更新 update/install 链路以支持 pointer_gpf_root 布局

**Files:**
- Modify: `install/update-mcp.ps1`
- Modify: `install/pointer-gpf.ps1`
- Modify: `pointer-gpf.cmd`
- Test: `tests/test_release_single_directory_layout.py`

- [ ] **Step 1: 写失败测试（入口脚本必须指向 pointer_gpf/install）**

```python
def test_pointer_cmd_targets_nested_install_script(self) -> None:
    repo = Path(__file__).resolve().parents[1]
    cmd = (repo / "pointer-gpf.cmd").read_text(encoding="utf-8")
    self.assertIn('pointer_gpf\\install\\pointer-gpf.ps1', cmd)
```

- [ ] **Step 2: 修改 `pointer-gpf.cmd` 为根入口转发**

```bat
@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0pointer_gpf\install\pointer-gpf.ps1" %*
exit /b %ERRORLEVEL%
```

- [ ] **Step 3: 修改 `install/update-mcp.ps1` 的布局解析与同步目标**

```powershell
$payloadRoot = Join-Path $repoRoot "pointer_gpf"
$manifestPath = Join-Path $payloadRoot "mcp/version_manifest.json"
$mcpDir = Join-Path $payloadRoot "mcp"
$gtrConfigPath = Join-Path $payloadRoot "gtr.config.json"
$pluginTemplateDir = Join-Path $payloadRoot "godot_plugin_template"

function Resolve-PackageRoot {
    param([string]$BaseDir, [string]$SourceLabel)
    $directPayload = Join-Path $BaseDir "pointer_gpf"
    if (Test-Path -LiteralPath $directPayload) { return $directPayload }
    throw "$SourceLabel missing pointer_gpf/ directory."
}
```

- [ ] **Step 4: 运行测试与脚本冒烟**

Run:
- `python -m unittest tests.test_release_single_directory_layout -v`
- `powershell -ExecutionPolicy Bypass -File "install/update-mcp.ps1" -CheckUpdateOnly`

Expected:
- unittest PASS
- 输出 channel/version/artifact 正常，无路径异常

- [ ] **Step 5: 提交**

```bash
git add install/update-mcp.ps1 install/pointer-gpf.ps1 pointer-gpf.cmd tests/test_release_single_directory_layout.py
git commit -m "feat: support pointer_gpf_root package layout in update path"
```

---

### Task 4: 修复版本清单与发布口径，防止旧布局回流

**Files:**
- Modify: `mcp/version_manifest.json`
- Modify: `docs/quickstart.md`
- Modify: `docs/design/99-tools/15-mcp-full-audit-critical-task-2026-04-10.md`
- Test: `tests/test_release_single_directory_layout.py`

- [ ] **Step 1: 写失败测试（manifest layout 值）**

```python
def test_manifest_zip_layout_is_pointer_gpf_root(self) -> None:
    repo = Path(__file__).resolve().parents[1]
    payload = json.loads((repo / "mcp/version_manifest.json").read_text(encoding="utf-8"))
    self.assertEqual(payload["channels"]["stable"]["artifact"]["zip_layout"], "pointer_gpf_root")
```

- [ ] **Step 2: 更新 manifest**

```json
{
  "channels": {
    "stable": {
      "artifact": {
        "zip_layout": "pointer_gpf_root"
      }
    }
  }
}
```

- [ ] **Step 3: 更新文档路径示例为单目录口径**

```markdown
- 发布包解压后结构：
  - `pointer-gpf.cmd`（根入口，可选）
  - `pointer_gpf/`（全部 PointerGPF 实现与资产）
- 常用命令：
  - `powershell -ExecutionPolicy Bypass -File "pointer_gpf/install/start-mcp.ps1"`
```

- [ ] **Step 4: 运行测试**

Run: `python -m unittest tests.test_release_single_directory_layout -v`  
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add mcp/version_manifest.json docs/quickstart.md docs/design/99-tools/15-mcp-full-audit-critical-task-2026-04-10.md tests/test_release_single_directory_layout.py
git commit -m "docs: align release and quickstart with single-directory layout"
```

---

### Task 5: 增加 release 解包后验收（真正验证生效面）

**Files:**
- Modify: `.github/workflows/release-package.yml`
- Create: `scripts/verify-release-package-layout.py`
- Test: `tests/test_release_single_directory_layout.py`

- [ ] **Step 1: 写失败测试（要求存在解包验证步骤）**

```python
def test_release_workflow_contains_unpack_validation_step(self) -> None:
    repo = Path(__file__).resolve().parents[1]
    wf = (repo / ".github" / "workflows" / "release-package.yml").read_text(encoding="utf-8")
    self.assertIn("verify-release-package-layout.py", wf)
```

- [ ] **Step 2: 新增验证脚本（检查 zip 内路径与关键工具）**

```python
#!/usr/bin/env python3
import json
import sys
import zipfile
from pathlib import Path

zip_path = Path(sys.argv[1]).resolve()
with zipfile.ZipFile(zip_path, "r") as zf:
    names = set(zf.namelist())
required = {
    "pointer_gpf/mcp/server.py",
    "pointer_gpf/tools/game-test-runner/mcp/server.py",
    "pointer_gpf/flows/internal/contract_force_fail_invalid_scene.json",
}
missing = sorted(p for p in required if p not in names)
if missing:
    raise SystemExit(f"missing required entries: {missing}")
print(json.dumps({"ok": True, "checked": sorted(required)}, ensure_ascii=False))
```

- [ ] **Step 3: 在 `release-package.yml` 中接入解包校验**

```yaml
- name: Verify packaged layout and legacy assets
  shell: pwsh
  run: |
    python "scripts/verify-release-package-layout.py" "$env:ZIP_PATH"
```

- [ ] **Step 4: 运行测试**

Run:
- `python -m unittest tests.test_release_single_directory_layout -v`
- `python scripts/verify-release-package-layout.py dist/pointer-gpf-mcp-<version>.zip`

Expected:
- unittest PASS
- verify script 输出 `{"ok": true, ...}`

- [ ] **Step 5: 提交**

```bash
git add .github/workflows/release-package.yml scripts/verify-release-package-layout.py tests/test_release_single_directory_layout.py
git commit -m "ci: verify single-directory release package after build"
```

---

## 全量回归与验收

- [ ] 运行核心回归：
  - `python -m unittest tests.test_mcp_transport_protocol -v`
  - `python -m unittest tests.test_flow_execution_runtime -v`
  - `python -m unittest tests.test_mcp_gap_audit tests.test_legacy_tool_surface tests.test_legacy_runner_pipeline tests.test_flow_assets_contract tests.test_legacy_stepwise_fixloop_live tests.test_godot_test_orchestrator_packaging tests.test_ci_legacy_coverage tests.test_restoration_status_document tests.test_release_single_directory_layout -v`
- [ ] 本地打包并验证 zip：
  - `python scripts/verify-release-package-layout.py dist/pointer-gpf-mcp-<version>.zip`
- [ ] 远端发布后验证：
  - `powershell -ExecutionPolicy Bypass -File "install/update-mcp.ps1" -CheckUpdateOnly`
  - 下载 stable zip，确认包含 `pointer_gpf/**` 并可执行 `pointer_gpf/mcp/server.py --tool get_mcp_runtime_info`

---

## 自检

1. **需求覆盖**：已覆盖单目录硬约束、release 生效面一致性、legacy 能力不回退、文档口径一致。  
2. **占位符扫描**：无 TBD/TODO/“后续补充”类占位语句。  
3. **命名一致性**：统一使用 `pointer_gpf_root`、`pointer_gpf/`、`tests/test_release_single_directory_layout.py`。

---

## 执行结果记录（2026-04-10）

- 已按 Subagent-Driven 方式执行并完成核心任务（单目录发布链路、兼容工具面补齐、release 门禁脚本）。
- 发布 workflow（`release-package.yml`）已支持：
  - 打包载荷根目录：`pointer_gpf/`
  - 打包后自动执行 `scripts/verify-release-package-layout.py`
- 已恢复根 MCP 兼容项：`check_test_runner_environment`。
- 已完成重新发布与回填：
  - 发布版本：`v0.3.0.0`
  - Actions run: `https://github.com/bainelee/Godot-PointerGPF/actions/runs/24203516497`
  - `mcp/version_manifest.json` 已更新到 `0.3.0.0` 且 `zip_layout=pointer_gpf_root`
- 发布后验收：
  - `python scripts/verify-release-manifest-artifact.py` 返回 `ok=true`
  - `powershell -ExecutionPolicy Bypass -File "install/update-mcp.ps1" -CheckUpdateOnly` 显示 stable=`0.3.0.0`

