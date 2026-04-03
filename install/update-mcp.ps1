param(
    [string]$Channel = "stable",
    [string]$PackageDir = "",
    [switch]$CheckUpdateOnly,
    [switch]$ForceRemote
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$manifestPath = Join-Path $repoRoot "mcp/version_manifest.json"
$mcpDir = Join-Path $repoRoot "mcp"

if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Missing version manifest: $manifestPath"
}
if (-not (Test-Path -LiteralPath $mcpDir)) {
    throw "Missing mcp directory: $mcpDir"
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not ($manifest.channels.PSObject.Properties.Name -contains $Channel)) {
    throw "Unknown channel: $Channel"
}
$repoSlug = [string]$manifest.repository
$targetVersion = [string]$manifest.channels.$Channel.version
$artifact = $manifest.channels.$Channel.artifact
$artifactUrl = [string]$artifact.url
$artifactSha = [string]$artifact.sha256
$artifactFilename = [string]$artifact.filename

function Resolve-ReleaseAssetFromGitHub {
    param(
        [Parameter(Mandatory = $true)][string]$Repository,
        [Parameter(Mandatory = $true)][string]$Version,
        [string]$ExpectedZipName = ""
    )

    $tagUrl = "https://api.github.com/repos/$Repository/releases/tags/v$Version"
    $latestUrl = "https://api.github.com/repos/$Repository/releases/latest"
    $release = $null
    try {
        $release = Invoke-RestMethod -Method Get -Uri $tagUrl -UseBasicParsing
    }
    catch {
        try {
            $release = Invoke-RestMethod -Method Get -Uri $latestUrl -UseBasicParsing
        }
        catch {
            throw "No GitHub release found for $Repository (tag v$Version or latest). Publish release-package first."
        }
    }
    if ($null -eq $release) {
        throw "Failed to resolve release from GitHub API."
    }

    $zipAsset = $null
    if (-not [string]::IsNullOrWhiteSpace($ExpectedZipName)) {
        $zipAsset = $release.assets | Where-Object { $_.name -eq $ExpectedZipName } | Select-Object -First 1
    }
    if ($null -eq $zipAsset) {
        $zipAsset = $release.assets | Where-Object { [string]$_.name -like "*.zip" } | Select-Object -First 1
    }
    if ($null -eq $zipAsset) {
        throw "No .zip asset found in release."
    }
    $shaAsset = $release.assets | Where-Object { [string]$_.name -eq "sha256.txt" } | Select-Object -First 1

    return @{
        zipName = [string]$zipAsset.name
        zipUrl = [string]$zipAsset.browser_download_url
        shaUrl = if ($null -eq $shaAsset) { "" } else { [string]$shaAsset.browser_download_url }
        tagName = [string]$release.tag_name
    }
}

if ($CheckUpdateOnly) {
    Write-Output ("[UPDATE] channel=" + $Channel + " version=" + $targetVersion)
    Write-Output ("[UPDATE] artifact_url=" + $artifactUrl)
    Write-Output ("[UPDATE] artifact_sha256=" + $artifactSha)
    exit 0
}

$workDir = Join-Path $repoRoot (".mcp-update-work-" + (Get-Date -Format "yyyyMMddTHHmmss"))
New-Item -ItemType Directory -Path $workDir | Out-Null

$sourceMcp = ""
if ((-not [string]::IsNullOrWhiteSpace($PackageDir)) -and (-not $ForceRemote)) {
    if (-not (Test-Path -LiteralPath $PackageDir)) {
        throw "PackageDir not found: $PackageDir"
    }
    $sourceMcp = Join-Path $PackageDir "mcp"
    if (-not (Test-Path -LiteralPath $sourceMcp)) {
        throw "PackageDir must contain mcp/ folder: $sourceMcp"
    }
}
elseif (-not [string]::IsNullOrWhiteSpace($artifactUrl)) {
    $zipPath = Join-Path $workDir "pointer-gpf-mcp.zip"
    Write-Output ("[UPDATE] downloading artifact: " + $artifactUrl)
    Invoke-WebRequest -Uri $artifactUrl -OutFile $zipPath -UseBasicParsing
    if (-not [string]::IsNullOrWhiteSpace($artifactSha)) {
        $expected = $artifactSha.ToLowerInvariant().Replace("sha256:", "")
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash.ToLowerInvariant()
        if ($actual -ne $expected) {
            throw "Artifact sha256 mismatch. expected=$expected actual=$actual"
        }
    }
    $extractDir = Join-Path $workDir "extract"
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force
    $sourceMcp = Join-Path $extractDir "mcp"
    if (-not (Test-Path -LiteralPath $sourceMcp)) {
        throw "Downloaded package missing mcp/ directory: $sourceMcp"
    }
}
elseif ($ForceRemote) {
    if ([string]::IsNullOrWhiteSpace($repoSlug)) {
        throw "version_manifest.json missing repository field."
    }
    $resolved = Resolve-ReleaseAssetFromGitHub -Repository $repoSlug -Version $targetVersion -ExpectedZipName $artifactFilename
    $artifactUrl = [string]$resolved.zipUrl
    if ([string]::IsNullOrWhiteSpace($artifactUrl)) {
        throw "Resolved release has empty zip url."
    }
    Write-Output ("[UPDATE] resolved release tag=" + [string]$resolved.tagName)
    Write-Output ("[UPDATE] resolved artifact url=" + $artifactUrl)

    if ([string]::IsNullOrWhiteSpace($artifactSha) -and -not [string]::IsNullOrWhiteSpace([string]$resolved.shaUrl)) {
        $shaPath = Join-Path $workDir "sha256.txt"
        Invoke-WebRequest -Uri ([string]$resolved.shaUrl) -OutFile $shaPath -UseBasicParsing
        $shaRaw = (Get-Content -LiteralPath $shaPath -Raw -Encoding UTF8).Trim()
        if (-not [string]::IsNullOrWhiteSpace($shaRaw)) {
            $artifactSha = $shaRaw
        }
    }

    $zipPath = Join-Path $workDir "pointer-gpf-mcp.zip"
    Write-Output ("[UPDATE] downloading artifact: " + $artifactUrl)
    Invoke-WebRequest -Uri $artifactUrl -OutFile $zipPath -UseBasicParsing
    if (-not [string]::IsNullOrWhiteSpace($artifactSha)) {
        $expected = $artifactSha.ToLowerInvariant().Replace("sha256:", "")
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash.ToLowerInvariant()
        if ($actual -ne $expected) {
            throw "Artifact sha256 mismatch. expected=$expected actual=$actual"
        }
    }
    $extractDir = Join-Path $workDir "extract"
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force
    $sourceMcp = Join-Path $extractDir "mcp"
    if (-not (Test-Path -LiteralPath $sourceMcp)) {
        throw "Downloaded package missing mcp/ directory: $sourceMcp"
    }
}
else {
    throw "No update source available. Provide -PackageDir or publish artifact.url in version_manifest.json."
}

$backupDir = Join-Path $repoRoot (".mcp-backup-" + (Get-Date -Format "yyyyMMddTHHmmss"))
New-Item -ItemType Directory -Path $backupDir | Out-Null
Copy-Item -Path $mcpDir -Destination (Join-Path $backupDir "mcp") -Recurse -Force

try {
    Copy-Item -Path (Join-Path $sourceMcp "*") -Destination $mcpDir -Recurse -Force
    Write-Output ("[UPDATE] updated to channel=" + $Channel + " version=" + $targetVersion)
    Write-Output ("[UPDATE] backup=" + $backupDir)
}
catch {
    Write-Output "[UPDATE] failed, rolling back..."
    Remove-Item -LiteralPath $mcpDir -Recurse -Force
    Copy-Item -Path (Join-Path $backupDir "mcp") -Destination $mcpDir -Recurse -Force
    throw
}
finally {
    if (Test-Path -LiteralPath $workDir) {
        Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
