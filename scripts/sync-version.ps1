param(
    [switch]$CheckOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$versionPath = Join-Path $repoRoot "VERSION"
if (-not (Test-Path -LiteralPath $versionPath)) {
    throw "VERSION file not found: $versionPath"
}

$rawVersion = (Get-Content -LiteralPath $versionPath -Raw -Encoding UTF8).Trim()
if ([string]::IsNullOrWhiteSpace($rawVersion)) {
    throw "VERSION is empty."
}

$versionPattern = '^\d+\.\d+\.\d+\.\d+$'
if (-not [regex]::IsMatch($rawVersion, $versionPattern)) {
    throw "VERSION must match pattern $versionPattern ; got: $rawVersion"
}

$mode = if ($CheckOnly) { "check" } else { "write" }
Write-Host ("[SYNC] version=" + $rawVersion + " mode=" + $mode)

function Assert-VersionMatch {
    param(
        [string]$RelPath,
        [string]$Content,
        [string]$RegexPattern,
        [string]$ExpectedVersion
    )
    $m = [regex]::Match($Content, $RegexPattern)
    if (-not $m.Success) {
        throw ("No version match in {0} (pattern: {1})" -f $RelPath, $RegexPattern)
    }
    $found = $m.Groups[1].Value
    if ($found -ne $ExpectedVersion) {
        throw ("Version mismatch in {0}: expected {1}, found {2}" -f $RelPath, $ExpectedVersion, $found)
    }
}

function Sync-FileVersion {
    param(
        [string]$RelPath,
        [string]$ReplacePattern,
        [string]$Replacement,
        [string]$CheckRegex,
        [string]$ExpectedVersion
    )
    $fullPath = Join-Path $repoRoot $RelPath
    if (-not (Test-Path -LiteralPath $fullPath)) {
        throw "File not found: $fullPath"
    }
    $enc = [System.Text.UTF8Encoding]::new($false)
    $content = [System.IO.File]::ReadAllText($fullPath, $enc)
    $beforeCount = ([regex]::Matches($content, $ReplacePattern)).Count
    if ($beforeCount -lt 1) {
        throw ("No replace match in {0} (pattern: {1})" -f $RelPath, $ReplacePattern)
    }
    $newContent = [regex]::Replace($content, $ReplacePattern, $Replacement)
    Assert-VersionMatch -RelPath $RelPath -Content $newContent -RegexPattern $CheckRegex -ExpectedVersion $ExpectedVersion
    [System.IO.File]::WriteAllText($fullPath, $newContent, $enc)
}

$targets = @(
    @{
        RelPath    = "mcp/server.py"
        CheckRegex = 'DEFAULT_SERVER_VERSION = "(\d+\.\d+\.\d+\.\d+)"'
        ReplacePat = 'DEFAULT_SERVER_VERSION = "\d+\.\d+\.\d+\.\d+"'
        ReplaceWith = ('DEFAULT_SERVER_VERSION = "{0}"' -f $rawVersion)
    },
    @{
        RelPath    = "gtr.config.json"
        CheckRegex = '"server_version"\s*:\s*"(\d+\.\d+\.\d+\.\d+)"'
        ReplacePat = '"server_version"\s*:\s*"\d+\.\d+\.\d+\.\d+"'
        ReplaceWith = ('"server_version": "{0}"' -f $rawVersion)
    },
    @{
        RelPath    = "godot_plugin_template/addons/pointer_gpf/plugin.cfg"
        CheckRegex = 'version="(\d+\.\d+\.\d+\.\d+)"'
        ReplacePat = 'version="\d+\.\d+\.\d+\.\d+"'
        ReplaceWith = ('version="{0}"' -f $rawVersion)
    },
    @{
        RelPath    = "README.md"
        CheckRegex = '## What''s Included \(v(\d+\.\d+\.\d+\.\d+)\)'
        ReplacePat = '## What''s Included \(v\d+\.\d+\.\d+\.\d+\)'
        ReplaceWith = ('## What''s Included (v{0})' -f $rawVersion)
    },
    @{
        RelPath    = "README.zh-CN.md"
        CheckRegex = '## 当前能力（v(\d+\.\d+\.\d+\.\d+)）'
        ReplacePat = '## 当前能力（v\d+\.\d+\.\d+\.\d+）'
        ReplaceWith = ('## 当前能力（v{0}）' -f $rawVersion)
    },
    @{
        RelPath    = "docs/quickstart.md"
        CheckRegex = '更新行为说明（v(\d+\.\d+\.\d+\.\d+)\+）'
        ReplacePat = '更新行为说明（v\d+\.\d+\.\d+\.\d+\+）'
        ReplaceWith = ('更新行为说明（v{0}+）' -f $rawVersion)
    }
)

foreach ($t in $targets) {
    $fullPath = Join-Path $repoRoot $t.RelPath
    if (-not (Test-Path -LiteralPath $fullPath)) {
        throw "File not found: $fullPath"
    }
    $enc = [System.Text.UTF8Encoding]::new($false)
    $content = [System.IO.File]::ReadAllText($fullPath, $enc)

    if ($CheckOnly) {
        Assert-VersionMatch -RelPath $t.RelPath -Content $content -RegexPattern $t.CheckRegex -ExpectedVersion $rawVersion
    }
    else {
        Sync-FileVersion -RelPath $t.RelPath -ReplacePattern $t.ReplacePat -Replacement $t.ReplaceWith `
            -CheckRegex $t.CheckRegex -ExpectedVersion $rawVersion
    }
}
