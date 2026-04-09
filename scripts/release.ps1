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
        throw "[RELEASE] Not a git repository (expected clone/worktree at: $Root)"
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

    $payloadDir = Join-Path $stageDir "pointer_gpf"
    New-Item -ItemType Directory -Path $payloadDir -Force | Out-Null

    Copy-Item -LiteralPath (Join-Path $Root "mcp") -Destination (Join-Path $payloadDir "mcp") -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $Root "install") -Destination (Join-Path $payloadDir "install") -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $Root "godot_plugin_template") -Destination (Join-Path $payloadDir "godot_plugin_template") -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $Root "docs") -Destination (Join-Path $payloadDir "docs") -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $Root "examples") -Destination (Join-Path $payloadDir "examples") -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $Root "tools/game-test-runner") -Destination (Join-Path $payloadDir "tools/game-test-runner") -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $Root "flows") -Destination (Join-Path $payloadDir "flows") -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $Root "README.md") -Destination (Join-Path $stageDir "README.md") -Force
    Copy-Item -LiteralPath (Join-Path $Root "gtr.config.json") -Destination (Join-Path $payloadDir "gtr.config.json") -Force
    Copy-Item -LiteralPath (Join-Path $Root ".gitignore") -Destination (Join-Path $payloadDir ".gitignore") -Force
    Copy-Item -LiteralPath (Join-Path $Root "pointer-gpf.cmd") -Destination (Join-Path $stageDir "pointer-gpf.cmd") -Force

    $cacheDirs = Get-ChildItem -LiteralPath (Join-Path $payloadDir "examples") -Directory -Recurse -Force | Where-Object { $_.Name -eq ".godot" }
    foreach ($dir in $cacheDirs) {
        Remove-Item -LiteralPath $dir.FullName -Recurse -Force
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

Write-ReleaseLog ("repoRoot=" + $repoRoot)
Test-GitRepository -Root $repoRoot

$version = Get-VersionFromFile -Path $versionPath
$tag = "v" + $version
$repoSlug = Get-RepositorySlugFromManifest -Path $manifestPath
$artifactUrl = "https://github.com/$repoSlug/releases/download/$tag/pointer-gpf-mcp-$version.zip"

if ($DryRun) {
    Write-ReleaseLog ("version=$version tag=$tag")
    Write-ReleaseLog "dry-run complete."
    exit 0
}

Write-ReleaseLog ("version=$version tag=$tag PrepareOnly=$PrepareOnly")
& $syncScript
if (-not $?) {
    throw "[RELEASE] sync-version.ps1 failed."
}

$built = Build-ReleasePackage -Root $repoRoot -Version $version
Write-ReleaseLog ("zip=" + $built.ZipPath)
Write-ReleaseLog ("sha256=" + $built.Sha256)
Write-ReleaseLog ("size_bytes=" + $built.SizeBytes)

& $manifestScript -ArtifactUrl $artifactUrl -Sha256 $built.Sha256 -SizeBytes $built.SizeBytes
if (-not $?) {
    throw "[RELEASE] update-version-manifest.ps1 failed."
}

if ($PrepareOnly) {
    Write-ReleaseLog "prepare-only complete."
    exit 0
}

Write-ReleaseLog "publish steps (commit/tag/push/release) should be executed by maintainer policy."
exit 0
