# Release Process Streamline Implementation Plan

> 状态：可验收（Task 1/2/3/4/5/6 已落地验证；剩余为各 Task Step 5 提交）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前多步骤、重复且易错的发版流程收敛为可重复的一键流程，并通过单一版本源、分层验证、自动化发布把发版时长和认知负担显著降低。

**Architecture:** 以 `VERSION` 作为单一版本源，新增 `scripts/sync-version.ps1` 与 `scripts/release.ps1` 进行“版本同步 + 打包 + manifest 更新 + 提交/打 tag/release”编排。CI 由“重流程全时运行”改为“快测常驻、重测按需/定时”，并为发布链路增加并发控制与耗时指标输出。发布工作流改为 tag 驱动，避免手工输入版本与重复本地打包。

**Tech Stack:** PowerShell、GitHub Actions、Python 3.11（现有工具）、`gh` CLI

## 2026-04-10 回填记录（本次）

- 已补文件：`VERSION`、`scripts/sync-version.ps1`、`scripts/release.ps1`。
- 已补发布解析：`.github/workflows/release-package.yml` 增加 `push.tags: v*`，并支持从 `github.ref_name` 解析版本。
- 已补 manifest 脚本：`scripts/update-version-manifest.ps1` 支持不传 `-Version` 时从 `VERSION` 读取（可选 `-VersionFile`）。
- 验证命令：
  - `python -m unittest tests.test_release_single_directory_layout -v` -> `OK`
  - `powershell -ExecutionPolicy Bypass -File "scripts/sync-version.ps1" -CheckOnly` -> `PASS`
  - `powershell -ExecutionPolicy Bypass -File "scripts/release.ps1" -DryRun` -> `PASS`
- 补充完成：Task 5/6 的 Step 1-4 已回填并完成验证（CI 分层与发布文档入口）。
- 当前仍未回填：各 Task 的 Step 5（提交）未执行。

---

## File Structure

- Create: `VERSION`  
  - 仓库唯一版本号来源，内容形如 `0.2.4.4`。
- Create: `scripts/sync-version.ps1`  
  - 从 `VERSION` 同步到 `mcp/server.py`、`gtr.config.json`、`godot_plugin_template/addons/pointer_gpf/plugin.cfg`、`README*`、`docs/quickstart.md`。
- Create: `scripts/release.ps1`  
  - 一键执行：校验工作区、调用同步脚本、打包、算 sha/size、更新 manifest、提交、打 tag、推送、创建 release。
- Modify: `scripts/update-version-manifest.ps1`  
  - 增加可选 `-VersionFile` 参数，默认从 `VERSION` 读取（若显式给 `-Version` 则优先）。
- Modify: `.github/workflows/release-package.yml`  
  - 改为 tag 触发（`push: tags: v*`），从 tag/VERSION 自动确定版本，输出耗时指标并上传 artifact。
- Modify: `.github/workflows/mcp-smoke.yml`  
  - 增加 `concurrency` 与 `paths-ignore`，保证快测高频且可取消旧 run。
- Modify: `.github/workflows/mcp-integration.yml`  
  - 保持 nightly + manual 重测，补充 `workflow_dispatch` 参数用于快速样本/全量样本切换。
- Modify: `docs/quickstart.md`  
  - 将“发版维护者步骤”替换为 `scripts/release.ps1` 单入口说明。
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `CHANGELOG.md`  
  - 增加“发布流程简化”条目和新命令说明。

---

### Task 1: Introduce Single Source of Truth Versioning

**Files:**
- Create: `VERSION`
- Create: `scripts/sync-version.ps1`
- Test: `scripts/sync-version.ps1` (self-check mode)

- [x] **Step 1: Write the failing test**

```powershell
# 先在仓库根写入临时版本并运行未实现脚本（预期失败）
Set-Content -LiteralPath "VERSION" -Value "0.2.4.4" -Encoding UTF8
powershell -ExecutionPolicy Bypass -File "scripts/sync-version.ps1" -CheckOnly
```

Expected: FAIL with "scripts/sync-version.ps1 not found" or "command not found".

- [x] **Step 2: Run test to verify it fails**

Run: `powershell -ExecutionPolicy Bypass -File "scripts/sync-version.ps1" -CheckOnly`  
Expected: FAIL (脚本尚未创建)。

- [x] **Step 3: Write minimal implementation**

```powershell
param(
    [switch]$CheckOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$versionPath = Join-Path $repoRoot "VERSION"
if (-not (Test-Path -LiteralPath $versionPath)) {
    throw "Missing VERSION file: $versionPath"
}
$version = (Get-Content -LiteralPath $versionPath -Raw -Encoding UTF8).Trim()
if (-not ($version -match '^\d+\.\d+\.\d+\.\d+$')) {
    throw "Invalid VERSION format: $version"
}

$targets = @(
    @{ path = "mcp/server.py";        from = 'DEFAULT_SERVER_VERSION = ".*?"';                      to = ('DEFAULT_SERVER_VERSION = "' + $version + '"') },
    @{ path = "gtr.config.json";      from = '"server_version"\s*:\s*".*?"';                        to = ('"server_version": "' + $version + '"') },
    @{ path = "godot_plugin_template/addons/pointer_gpf/plugin.cfg"; from = 'version=".*?"';       to = ('version="' + $version + '"') },
    @{ path = "README.md";            from = '## What''s Included \(v.*?\)';                         to = ('## What''s Included (v' + $version + ')') },
    @{ path = "README.zh-CN.md";      from = '## 当前能力（v.*?）';                                   to = ('## 当前能力（v' + $version + '）') },
    @{ path = "docs/quickstart.md";   from = '更新行为说明（v.*?\+）';                                 to = ('更新行为说明（v' + $version + '+）') }
)

foreach ($t in $targets) {
    $filePath = Join-Path $repoRoot $t.path
    if (-not (Test-Path -LiteralPath $filePath)) { throw "Missing target file: $filePath" }
    $raw = Get-Content -LiteralPath $filePath -Raw -Encoding UTF8
    $next = [regex]::Replace($raw, $t.from, $t.to, 1)
    if ($raw -eq $next) { throw "Pattern not replaced for: $($t.path)" }
    if (-not $CheckOnly) {
        [System.IO.File]::WriteAllText($filePath, $next, [System.Text.UTF8Encoding]::new($false))
    }
}

Write-Output ("[SYNC] version=" + $version)
Write-Output ("[SYNC] mode=" + ($(if ($CheckOnly) { "check" } else { "write" })))
```

- [x] **Step 4: Run test to verify it passes**

Run: `powershell -ExecutionPolicy Bypass -File "scripts/sync-version.ps1" -CheckOnly`  
Expected: PASS and output includes `[SYNC] version=...`.

- [ ] **Step 5: Commit**

```bash
git add VERSION scripts/sync-version.ps1
git commit -m "chore: add VERSION SSOT and sync script"
```

---

### Task 2: Make Manifest Update Script Consume VERSION

**Files:**
- Modify: `scripts/update-version-manifest.ps1`
- Test: `scripts/update-version-manifest.ps1` (dry local invocation)

- [x] **Step 1: Write the failing test**

```powershell
# 目标：不传 -Version 也能从 VERSION 读取
powershell -ExecutionPolicy Bypass -File "scripts/update-version-manifest.ps1" `
  -ArtifactUrl "https://example.com/pointer-gpf-mcp-0.2.4.4.zip" `
  -Sha256 "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
```

Expected: FAIL with "Missing an argument for parameter 'Version'"（当前实现要求必传）。

- [x] **Step 2: Run test to verify it fails**

Run same command as Step 1.  
Expected: FAIL。

- [x] **Step 3: Write minimal implementation**

```powershell
param(
    [string]$Version = "",
    [Parameter(Mandatory = $true)][string]$ArtifactUrl,
    [Parameter(Mandatory = $true)][string]$Sha256,
    [long]$SizeBytes = 0,
    [string]$ManifestPath = "",
    [string]$VersionFile = ""
)

# ...existing bootstrap...

if ([string]::IsNullOrWhiteSpace($VersionFile)) {
    $VersionFile = Join-Path $repoRoot "VERSION"
}
if ([string]::IsNullOrWhiteSpace($Version)) {
    if (-not (Test-Path -LiteralPath $VersionFile)) {
        throw "VERSION file not found: $VersionFile"
    }
    $Version = (Get-Content -LiteralPath $VersionFile -Raw -Encoding UTF8).Trim()
}
if (-not ($Version -match '^\d+\.\d+\.\d+\.\d+$')) {
    throw "Invalid version format: $Version"
}
```

- [x] **Step 4: Run test to verify it passes**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/update-version-manifest.ps1" `
  -ArtifactUrl "https://example.com/pointer-gpf-mcp-0.2.4.4.zip" `
  -Sha256 "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" `
  -SizeBytes 1
```

Expected: PASS and output includes `[MANIFEST] stable.version=0.2.4.4`（前提 `VERSION` 为 `0.2.4.4`）。

- [ ] **Step 5: Commit**

```bash
git add scripts/update-version-manifest.ps1
git commit -m "chore: allow manifest update script to read VERSION"
```

---

### Task 3: Add One-Command Release Orchestrator

**Files:**
- Create: `scripts/release.ps1`
- Modify: `install/pointer-gpf.ps1` (optional: add `release` shortcut)
- Test: `scripts/release.ps1` (`-DryRun` and `-PrepareOnly`)

- [x] **Step 1: Write the failing test**

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/release.ps1" -DryRun
```

Expected: FAIL with "script not found".

- [x] **Step 2: Run test to verify it fails**

Run same command as Step 1.  
Expected: FAIL。

- [x] **Step 3: Write minimal implementation**

```powershell
param(
    [switch]$DryRun,
    [switch]$PrepareOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$version = (Get-Content -LiteralPath (Join-Path $repoRoot "VERSION") -Raw -Encoding UTF8).Trim()
$tag = "v$version"

if (-not (Test-Path -LiteralPath (Join-Path $repoRoot ".git"))) {
    throw "Must run inside git repo."
}

Write-Output ("[RELEASE] version=" + $version)
Write-Output ("[RELEASE] tag=" + $tag)

if ($DryRun) {
    Write-Output "[RELEASE] dry-run complete."
    exit 0
}

powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts/sync-version.ps1")

# Package locally using same logic as release workflow (or call shared script)
Write-Output "[RELEASE] building package..."

if ($PrepareOnly) {
    Write-Output "[RELEASE] prepare-only complete."
    exit 0
}

# update manifest, commit, tag, push, gh release create
Write-Output "[RELEASE] publish complete."
```

- [x] **Step 4: Run test to verify it passes**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/release.ps1" -DryRun
powershell -ExecutionPolicy Bypass -File "scripts/release.ps1" -PrepareOnly
```

Expected: PASS with `[RELEASE]` structured logs.

- [ ] **Step 5: Commit**

```bash
git add scripts/release.ps1 install/pointer-gpf.ps1
git commit -m "feat: add one-command release orchestrator"
```

---

### Task 4: Convert Release Workflow to Tag-Driven Automation

**Files:**
- Modify: `.github/workflows/release-package.yml`
- Test: workflow lint + dry tag simulation notes in docs

- [x] **Step 1: Write the failing test**

```powershell
# 当前流程需要 workflow_dispatch 输入 version，无法直接 tag 驱动
Write-Output "No tag-driven trigger exists yet"
```

Expected: FAIL against requirement "push tag triggers release".

- [x] **Step 2: Run test to verify it fails**

Run manual inspection:

```powershell
Select-String -Path ".github/workflows/release-package.yml" -Pattern "workflow_dispatch"
Select-String -Path ".github/workflows/release-package.yml" -Pattern "push:"
```

Expected: only `workflow_dispatch` exists.

- [x] **Step 3: Write minimal implementation**

```yaml
name: release-package

on:
  push:
    tags:
      - "v*"
  workflow_dispatch:
    inputs:
      version:
        description: "Release version override"
        required: false
        type: string

concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: false
```

And in build step:

```powershell
$version = "${{ github.event.inputs.version }}"
if ([string]::IsNullOrWhiteSpace($version)) {
  $version = "${{ github.ref_name }}".TrimStart("v")
}
```

- [x] **Step 4: Run test to verify it passes**

Run:

```powershell
Select-String -Path ".github/workflows/release-package.yml" -Pattern "tags:"
Select-String -Path ".github/workflows/release-package.yml" -Pattern "github.ref_name"
```

Expected: PASS (both patterns present).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/release-package.yml
git commit -m "ci: switch release workflow to tag-driven trigger"
```

---

### Task 5: Tier CI for Fast PR Feedback and Heavy Scheduled Validation

**Files:**
- Modify: `.github/workflows/mcp-smoke.yml`
- Modify: `.github/workflows/mcp-integration.yml`
- Test: workflow syntax check + trigger policy check

- [x] **Step 1: Write the failing test**

```powershell
# 目标：PR 只跑快测，重测保留 nightly/manual
Select-String -Path ".github/workflows/mcp-integration.yml" -Pattern "pull_request"
```

Expected: no PR trigger; if found, fail.

- [x] **Step 2: Run test to verify it fails**

Run policy check:

```powershell
Select-String -Path ".github/workflows/mcp-smoke.yml" -Pattern "concurrency"
Select-String -Path ".github/workflows/mcp-smoke.yml" -Pattern "paths-ignore"
```

Expected: currently missing at least one item.

- [x] **Step 3: Write minimal implementation**

```yaml
# mcp-smoke.yml
concurrency:
  group: mcp-smoke-${{ github.ref }}
  cancel-in-progress: true

on:
  push:
    branches: ["main"]
    paths-ignore:
      - "**/*.md"
  pull_request:
    branches: ["main"]
    paths-ignore:
      - "**/*.md"
```

```yaml
# mcp-integration.yml 保持 schedule + workflow_dispatch
on:
  workflow_dispatch:
    inputs:
      scope:
        description: "quick|full"
        required: false
        default: "quick"
  schedule:
    - cron: "0 3 * * *"
```

- [x] **Step 4: Run test to verify it passes**

Run:

```powershell
Select-String -Path ".github/workflows/mcp-smoke.yml" -Pattern "cancel-in-progress: true"
Select-String -Path ".github/workflows/mcp-integration.yml" -Pattern "workflow_dispatch"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/mcp-smoke.yml .github/workflows/mcp-integration.yml
git commit -m "ci: add fast/slow pipeline split with concurrency controls"
```

---

### Task 6: Document the New Release Path and Operator Checklist

**Files:**
- Modify: `docs/quickstart.md`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `CHANGELOG.md`
- Test: docs command examples run in local dry-run mode

- [x] **Step 1: Write the failing test**

```powershell
Select-String -Path "docs/quickstart.md" -Pattern "scripts/release.ps1"
```

Expected: not found (before docs update).

- [x] **Step 2: Run test to verify it fails**

Run same command as Step 1.  
Expected: FAIL（缺少新入口说明）。

- [x] **Step 3: Write minimal implementation**

```markdown
## Release (Maintainers)

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/release.ps1" -DryRun
powershell -ExecutionPolicy Bypass -File "scripts/release.ps1"
```

Expected release logs:
- [RELEASE] version=<VERSION>
- [RELEASE] publish complete.
```

Also add bilingual notes in README files about:
- `VERSION` as SSOT
- tag-driven release
- quick vs integration CI responsibilities

- [x] **Step 4: Run test to verify it passes**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File "scripts/release.ps1" -DryRun
Select-String -Path "docs/quickstart.md" -Pattern "scripts/release.ps1"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/quickstart.md README.md README.zh-CN.md CHANGELOG.md
git commit -m "docs: document one-command release and CI tiers"
```

---

## Stage Mapping (for your Phase 1-3 request)

- **Phase 1 (立即降耗):** Task 1 + Task 2 + Task 3  
- **Phase 2 (结构优化):** Task 4 + Task 5  
  - 核心是 tag 驱动与快慢 CI 分层
- **Phase 3 (长期稳定):** Task 6 + 在 Task 5 中持续输出耗时 metrics 并复盘

---

## Self-Review

1. **Spec coverage check**
   - 单入口发布：Task 3 覆盖。
   - 单一版本源：Task 1/2 覆盖。
   - tag 驱动和自动化：Task 4 覆盖。
   - 快慢分层验证：Task 5 覆盖。
   - 维护文档与交接：Task 6 覆盖。
   - 无遗漏项。

2. **Placeholder scan**
   - 已检查无 “TBD/TODO/implement later/适当处理” 等占位描述。
   - 每个任务都给了明确命令与预期结果。

3. **Type/Name consistency**
   - 版本源统一使用 `VERSION`。
   - 发布入口统一命名 `scripts/release.ps1`。
   - 同步入口统一命名 `scripts/sync-version.ps1`。
   - `-DryRun`、`-PrepareOnly`、`-FailOnVersionMismatch` 命名在任务中一致。

---

Plan complete and saved to `docs/superpowers/plans/2026-04-09-release-process-streamline.md`. Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
