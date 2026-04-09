param(
    [switch]$DryRun,
    [switch]$PrepareOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-ReleaseLog {
    param([string]$Message)
    Write-Host ("[RELEASE] " + $Message)
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$versionPath = Join-Path $repoRoot "VERSION"
$syncScript = Join-Path $repoRoot "scripts\sync-version.ps1"
$manifestScript = Join-Path $repoRoot "scripts\update-version-manifest.ps1"
$manifestPath = Join-Path $repoRoot "mcp\version_manifest.json"

function Test-GitRepository {
    param([string]$Root)
    $out = [string](git -C $Root rev-parse --is-inside-work-tree 2>$null)
    if ($LASTEXITCODE -ne 0 -or $out.Trim() -ne "true") {
        throw "[RELEASE] Not a git repository (expected a clone/worktree at: $Root)"
    }
}

function Get-VersionFromFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "[RELEASE] VERSION file not found: $Path"
    }
    $v = (Get-Content -LiteralPath $Path -Raw -Encoding UTF8).Trim()
    if ([string]::IsNullOrWhiteSpace($v)) {
        throw "[RELEASE] VERSION is empty."
    }
    if ($v -notmatch '^\d+\.\d+\.\d+\.\d+$') {
        throw ('[RELEASE] VERSION must match ^\d+\.\d+\.\d+\.\d+$ ; got: ' + $v)
    }
    return $v
}

function Get-RepositorySlugFromManifest {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "[RELEASE] Manifest not found: $Path"
    }
    $json = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    $repo = $json.repository
    if ([string]::IsNullOrWhiteSpace($repo)) {
        throw "[RELEASE] version_manifest.json missing non-empty repository field."
    }
    return [string]$repo
}

function Build-ReleasePackage {
    param(
        [string]$Root,
        [string]$Version
    )
    $outDir = Join-Path $Root "dist"
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    $zip = Join-Path $outDir ("pointer-gpf-mcp-" + $Version + ".zip")
    $stageDir = Join-Path $outDir "package-root"
    if (Test-Path -LiteralPath $stageDir) {
        Remove-Item -LiteralPath $stageDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $stageDir -Force | Out-Null

    $copyPairs = @(
        @{ Src = "mcp"; Dst = "mcp" },
        @{ Src = "install"; Dst = "install" },
        @{ Src = "godot_plugin_template"; Dst = "godot_plugin_template" },
        @{ Src = "docs"; Dst = "docs" },
        @{ Src = "examples"; Dst = "examples" },
        @{ Src = "README.md"; Dst = "README.md" },
        @{ Src = "gtr.config.json"; Dst = "gtr.config.json" },
        @{ Src = ".gitignore"; Dst = ".gitignore" }
    )
    foreach ($pair in $copyPairs) {
        $srcPath = Join-Path $Root $pair.Src
        if (-not (Test-Path -LiteralPath $srcPath)) {
            throw "[RELEASE] Package source missing: $srcPath"
        }
        $dstPath = Join-Path $stageDir $pair.Dst
        if ($pair.Src -eq "examples") {
            # Skip .godot during copy: deep shader-cache paths can exceed Windows MAX_PATH with Copy-Item.
            $null = New-Item -ItemType Directory -Path $dstPath -Force
            & robocopy.exe $srcPath $dstPath /E /XD .godot /R:1 /W:1 /NFL /NDL /NJH /NJS /NC /NS /NP 2>&1 | Out-Null
            $rc = $LASTEXITCODE
            if ($rc -ge 8) {
                throw ("[RELEASE] robocopy examples failed with exit code {0}" -f $rc)
            }
        }
        else {
            Copy-Item -LiteralPath $srcPath -Destination $dstPath -Recurse -Force
        }
    }

    Compress-Archive -Path (Join-Path $stageDir "*") -DestinationPath $zip -Force
    $sha = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLowerInvariant()
    $shaFile = Join-Path $outDir "sha256.txt"
    [System.IO.File]::WriteAllText($shaFile, $sha, [System.Text.UTF8Encoding]::new($false))
    $sizeBytes = (Get-Item -LiteralPath $zip).Length

    return [pscustomobject]@{
        ZipPath   = $zip
        ShaPath   = $shaFile
        Sha256    = $sha
        SizeBytes = $sizeBytes
    }
}

function Get-ReleaseStagePaths {
    return @(
        "mcp/server.py",
        "gtr.config.json",
        "godot_plugin_template/addons/pointer_gpf/plugin.cfg",
        "README.md",
        "README.zh-CN.md",
        "docs/quickstart.md",
        "mcp/version_manifest.json",
        "VERSION"
    )
}

function Get-StagedPaths {
    param([string]$Root)
    $out = [string](git -C $Root diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) {
        throw "[RELEASE] Failed to inspect staged changes."
    }
    if ([string]::IsNullOrWhiteSpace($out)) {
        return @()
    }
    return @(
        $out -split "`r?`n" |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
}

function Assert-NoPreStagedChanges {
    param([string]$Root)
    [array]$staged = @(Get-StagedPaths -Root $Root)
    if ($staged.Length -gt 0) {
        $detail = ($staged | ForEach-Object { "  - $_" }) -join "`n"
        throw ("[RELEASE] Detected pre-staged files before release run. Please clean index first to avoid accidental mixed release commit:`n{0}" -f $detail)
    }
}

function Assert-TagAvailable {
    param(
        [string]$Root,
        [string]$Tag
    )
    git -C $Root rev-parse --quiet --verify ("refs/tags/" + $Tag) 1>$null 2>$null
    if ($LASTEXITCODE -eq 0) {
        throw ("[RELEASE] Local tag already exists: {0}" -f $Tag)
    }

    $remoteRef = [string](git -C $Root ls-remote --tags origin ("refs/tags/" + $Tag))
    if ($LASTEXITCODE -ne 0) {
        throw ("[RELEASE] Failed to query remote tag from origin: {0}" -f $Tag)
    }
    if (-not [string]::IsNullOrWhiteSpace($remoteRef)) {
        throw ("[RELEASE] Remote tag already exists on origin: {0}" -f $Tag)
    }
}

Write-ReleaseLog ("repoRoot=" + $repoRoot)
if ($DryRun -and $PrepareOnly) {
    Write-ReleaseLog "Both -DryRun and -PrepareOnly specified; DryRun takes precedence (no file writes)."
}

Test-GitRepository -Root $repoRoot

$version = Get-VersionFromFile -Path $versionPath
$tag = "v" + $version
$repoSlug = Get-RepositorySlugFromManifest -Path $manifestPath
$artifactUrl = "https://github.com/$repoSlug/releases/download/$tag/pointer-gpf-mcp-$version.zip"
$zipPath = Join-Path $repoRoot ("dist\pointer-gpf-mcp-" + $version + ".zip")
$shaPath = Join-Path $repoRoot "dist\sha256.txt"

if ($DryRun) {
    Write-ReleaseLog "DryRun=1: printing planned actions only (no sync, no package, no manifest/git/gh)."
    Write-ReleaseLog ("version=$version tag=$tag")
    Write-ReleaseLog ("Would run: sync-version.ps1 (version sync to tracked sources)")
    Write-ReleaseLog ("Would build zip (CI parity): $zipPath")
    Write-ReleaseLog ("Would write sha256.txt: $shaPath")
    Write-ReleaseLog ("Would compute size_bytes from zip; sha256 from zip hash")
    Write-ReleaseLog ("Would run: update-version-manifest.ps1 -ArtifactUrl `"$artifactUrl`" -Sha256 <computed> -SizeBytes <computed>")
    if ($PrepareOnly) {
        Write-ReleaseLog "PrepareOnly: plan stops after manifest update (no git commit/tag/push)."
    }
    else {
        $dryStage = Get-ReleaseStagePaths
        Write-ReleaseLog "Would fail if staged changes already exist before release run."
        Write-ReleaseLog ("Would check local/remote tag availability before tagging: " + $tag)
        Write-ReleaseLog ("Would git add: " + ($dryStage -join ', '))
        Write-ReleaseLog ("Would git commit: chore(release): $tag")
        Write-ReleaseLog ("Would git tag: $tag")
        Write-ReleaseLog "Would git push --atomic: current branch + tag to origin"
        Write-ReleaseLog "Would NOT run gh release create locally (avoids race with CI)."
        Write-ReleaseLog "After tag push, GitHub Release + zip 上传由 .github/workflows/release-package.yml（push tags v*）自动执行。"
    }
    exit 0
}

Write-ReleaseLog ("version=$version tag=$tag PrepareOnly=$PrepareOnly")

Write-ReleaseLog "Invoking sync-version.ps1"
& $syncScript
if (-not $?) {
    throw "[RELEASE] sync-version.ps1 failed."
}

Write-ReleaseLog "Building release package (release-package.yml parity)"
$built = Build-ReleasePackage -Root $repoRoot -Version $version
Write-ReleaseLog ("zip=" + $built.ZipPath)
Write-ReleaseLog ("sha256=" + $built.Sha256)
Write-ReleaseLog ("size_bytes=" + $built.SizeBytes)

Write-ReleaseLog "Invoking update-version-manifest.ps1"
& $manifestScript -ArtifactUrl $artifactUrl -Sha256 $built.Sha256 -SizeBytes $built.SizeBytes
if (-not $?) {
    throw "[RELEASE] update-version-manifest.ps1 failed."
}

if ($PrepareOnly) {
    Write-ReleaseLog "PrepareOnly=1: stopping before git commit/tag/push."
    exit 0
}

Assert-NoPreStagedChanges -Root $repoRoot

$paths = Get-ReleaseStagePaths
foreach ($rel in $paths) {
    $full = Join-Path $repoRoot $rel
    if (-not (Test-Path -LiteralPath $full)) {
        throw "[RELEASE] Cannot stage missing path: $full"
    }
    git -C $repoRoot add -- $rel
    if ($LASTEXITCODE -ne 0) {
        throw "[RELEASE] git add failed for: $rel"
    }
}

git -C $repoRoot diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    throw "[RELEASE] Nothing to commit after staging release files. Bump VERSION or resolve working tree state."
}

$branch = [string](git -C $repoRoot rev-parse --abbrev-ref HEAD)
if ($LASTEXITCODE -ne 0) {
    throw "[RELEASE] Could not resolve current branch name."
}
$branch = $branch.Trim()
Write-ReleaseLog ("committing on branch=" + $branch)

git -C $repoRoot commit -m ("chore(release): " + $tag)
if ($LASTEXITCODE -ne 0) {
    throw "[RELEASE] git commit failed."
}

Assert-TagAvailable -Root $repoRoot -Tag $tag

git -C $repoRoot tag -a $tag -m ("Release " + $tag)
if ($LASTEXITCODE -ne 0) {
    throw "[RELEASE] git tag failed (tag may already exist locally)."
}

Write-ReleaseLog ("pushing branch " + $branch + " and tag " + $tag + " with --atomic")
git -C $repoRoot push --atomic origin $branch $tag
if ($LASTEXITCODE -ne 0) {
    throw "[RELEASE] git push --atomic failed."
}

Write-ReleaseLog "本地 release 脚本已完成：已推送分支与标签 $tag。"
Write-ReleaseLog "未执行 gh release create（默认由 CI 发布，避免与 workflow 竞态）。"
Write-ReleaseLog "GitHub Release 与制品上传将由 .github/workflows/release-package.yml 在检测到 tag push（v*）后自动运行；请在 Actions 中确认该工作流成功。"

Write-ReleaseLog "Release pipeline finished."
exit 0
