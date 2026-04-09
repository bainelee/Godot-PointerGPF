param(
    [string]$Channel = "stable",
    [string]$PackageDir = "",
    [switch]$CheckUpdateOnly,
    [switch]$ForceRemote,
    [switch]$NoRootSync,
    [switch]$FailOnVersionMismatch
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
$gtrConfigPath = Join-Path $repoRoot "gtr.config.json"
$pluginTemplateDir = Join-Path $repoRoot "godot_plugin_template"

function Resolve-ReleaseAssetFromGitHub {
    param(
        [Parameter(Mandatory = $true)][string]$Repository,
        [Parameter(Mandatory = $true)][string]$Version,
        [string]$ExpectedZipName = "",
        [switch]$PreferLatest
    )

    $tagUrl = "https://api.github.com/repos/$Repository/releases/tags/v$Version"
    $latestUrl = "https://api.github.com/repos/$Repository/releases/latest"
    $release = $null
    if ($PreferLatest) {
        try {
            $release = Invoke-RestMethod -Method Get -Uri $latestUrl -UseBasicParsing
        }
        catch {
            try {
                $release = Invoke-RestMethod -Method Get -Uri $tagUrl -UseBasicParsing
            }
            catch {
                throw "No GitHub release found for $Repository (latest or tag v$Version). Publish release-package first."
            }
        }
    }
    else {
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

function Resolve-PackageRoot {
    param(
        [Parameter(Mandatory = $true)][string]$BaseDir,
        [Parameter(Mandatory = $true)][string]$SourceLabel
    )

    $directMcp = Join-Path $BaseDir "mcp"
    if (Test-Path -LiteralPath $directMcp) {
        return $BaseDir
    }

    $childMatches = @()
    $children = @(Get-ChildItem -LiteralPath $BaseDir -Directory -Force -ErrorAction SilentlyContinue)
    foreach ($child in $children) {
        $candidate = Join-Path $child.FullName "mcp"
        if (Test-Path -LiteralPath $candidate) {
            $childMatches += $child.FullName
        }
    }

    if ($childMatches.Count -eq 1) {
        return [string]$childMatches[0]
    }

    $candidateTips = @($directMcp) + ($childMatches | ForEach-Object { Join-Path $_ "mcp" })
    $tipText = if ($candidateTips.Count -gt 0) { ($candidateTips -join ", ") } else { "(none)" }
    throw "$SourceLabel missing mcp/ directory. Checked candidates: $tipText"
}

function Expand-PackageArchive {
    param(
        [Parameter(Mandatory = $true)][string]$ZipPath,
        [Parameter(Mandatory = $true)][string]$ExtractDir,
        [Parameter(Mandatory = $true)][string]$SourceLabel
    )

    try {
        Expand-Archive -LiteralPath $ZipPath -DestinationPath $ExtractDir -Force
    }
    catch {
        Write-Warning ("[UPDATE] Expand-Archive failed, trying selective zip extraction. source=" + $SourceLabel + " error=" + $_.Exception.Message)
        try {
            Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction SilentlyContinue
            $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
            try {
                foreach ($entry in $zip.Entries) {
                    $entryPath = [string]$entry.FullName
                    if ([string]::IsNullOrWhiteSpace($entryPath)) {
                        continue
                    }
                    $normalized = $entryPath.Replace("\", "/")
                    $isWanted = $normalized.StartsWith("mcp/") -or
                        $normalized.StartsWith("godot_plugin_template/") -or
                        ($normalized -eq "gtr.config.json")
                    if (-not $isWanted) {
                        continue
                    }
                    $target = Join-Path $ExtractDir $normalized
                    if ($normalized.EndsWith("/")) {
                        New-Item -ItemType Directory -Path $target -Force | Out-Null
                        continue
                    }
                    $targetDir = Split-Path -Parent $target
                    if (-not [string]::IsNullOrWhiteSpace($targetDir)) {
                        New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
                    }
                    $entryStream = $entry.Open()
                    try {
                        $fileStream = [System.IO.File]::Open($target, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
                        try {
                            $entryStream.CopyTo($fileStream)
                        }
                        finally {
                            $fileStream.Dispose()
                        }
                    }
                    finally {
                        $entryStream.Dispose()
                    }
                }
            }
            finally {
                $zip.Dispose()
            }
        }
        catch {
            throw "Failed to expand package from $SourceLabel. This can be caused by long paths in Windows archive extraction. zip=$ZipPath extract_dir=$ExtractDir error=$($_.Exception.Message)"
        }
    }
    return (Resolve-PackageRoot -BaseDir $ExtractDir -SourceLabel $SourceLabel)
}

function Download-ReleaseZip {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$ZipPath
    )
    Write-Output ("[UPDATE] downloading artifact: " + $Url)
    Invoke-WebRequest -Uri $Url -OutFile $ZipPath -UseBasicParsing
}

function Resolve-InstalledVersionInfo {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$ChannelName
    )

    $manifestVersion = ""
    $runtimeVersion = ""
    $manifestFile = Join-Path $RepoRoot "mcp/version_manifest.json"
    if (Test-Path -LiteralPath $manifestFile) {
        try {
            $installedManifest = Get-Content -LiteralPath $manifestFile -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($installedManifest.channels.PSObject.Properties.Name -contains $ChannelName) {
                $manifestVersion = [string]$installedManifest.channels.$ChannelName.version
            }
            if ([string]::IsNullOrWhiteSpace($manifestVersion)) {
                $manifestVersion = [string]$installedManifest.current_version
            }
        }
        catch {}
    }
    $runtimeConfigPath = Join-Path $RepoRoot "gtr.config.json"
    if (Test-Path -LiteralPath $runtimeConfigPath) {
        try {
            $cfg = Get-Content -LiteralPath $runtimeConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $runtimeVersion = [string]$cfg.server_version
        }
        catch {}
    }

    return @{
        manifestVersion = $manifestVersion
        runtimeVersion = $runtimeVersion
    }
}

function Test-VersionConsistency {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$ChannelName,
        [switch]$FailMismatch
    )

    $serverPath = Join-Path $RepoRoot "mcp/server.py"
    $manifestFile = Join-Path $RepoRoot "mcp/version_manifest.json"
    $pluginCfgPath = Join-Path $RepoRoot "godot_plugin_template/addons/pointer_gpf/plugin.cfg"

    $versionMap = [ordered]@{
        server_default = ""
        gtr_config = ""
        manifest_current = ""
        manifest_channel = ""
        plugin_cfg = ""
    }

    if (Test-Path -LiteralPath $serverPath) {
        $serverRaw = Get-Content -LiteralPath $serverPath -Raw -Encoding UTF8
        $match = [regex]::Match($serverRaw, 'DEFAULT_SERVER_VERSION\s*=\s*"([^"]+)"')
        if ($match.Success) {
            $versionMap.server_default = $match.Groups[1].Value
        }
    }
    if (Test-Path -LiteralPath $gtrConfigPath) {
        $gtr = Get-Content -LiteralPath $gtrConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $versionMap.gtr_config = [string]$gtr.server_version
    }
    if (Test-Path -LiteralPath $manifestFile) {
        $manifestNow = Get-Content -LiteralPath $manifestFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $versionMap.manifest_current = [string]$manifestNow.current_version
        if ($manifestNow.channels.PSObject.Properties.Name -contains $ChannelName) {
            $versionMap.manifest_channel = [string]$manifestNow.channels.$ChannelName.version
        }
    }
    if (Test-Path -LiteralPath $pluginCfgPath) {
        $pluginCfgRaw = Get-Content -LiteralPath $pluginCfgPath -Raw -Encoding UTF8
        $pluginMatch = [regex]::Match($pluginCfgRaw, 'version\s*=\s*"([^"]+)"')
        if ($pluginMatch.Success) {
            $versionMap.plugin_cfg = $pluginMatch.Groups[1].Value
        }
    }

    $effective = @($versionMap.Values | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
    $isConsistent = ($effective.Count -le 1)
    if (-not $isConsistent) {
        $details = ($versionMap.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "; "
        $message = "Version consistency check failed: $details"
        if ($FailMismatch) {
            throw $message
        }
        Write-Warning $message
    }

    return @{
        ok = $isConsistent
        details = $versionMap
    }
}

function Test-IsSamePath {
    param(
        [Parameter(Mandatory = $true)][string]$PathA,
        [Parameter(Mandatory = $true)][string]$PathB
    )

    $a = if (Test-Path -LiteralPath $PathA) { (Resolve-Path -LiteralPath $PathA).Path } else { [System.IO.Path]::GetFullPath($PathA) }
    $b = if (Test-Path -LiteralPath $PathB) { (Resolve-Path -LiteralPath $PathB).Path } else { [System.IO.Path]::GetFullPath($PathB) }
    return [string]::Equals($a, $b, [System.StringComparison]::OrdinalIgnoreCase)
}

if ($CheckUpdateOnly) {
    Write-Output ("[UPDATE] channel=" + $Channel + " version=" + $targetVersion)
    Write-Output ("[UPDATE] artifact_url=" + $artifactUrl)
    Write-Output ("[UPDATE] artifact_sha256=" + $artifactSha)
    exit 0
}

$workDir = Join-Path ([System.IO.Path]::GetTempPath()) ("pgpf-upd-" + (Get-Date -Format "yyyyMMddTHHmmss"))
New-Item -ItemType Directory -Path $workDir | Out-Null

$sourceRoot = ""
$resolvedTagName = ""
if ((-not [string]::IsNullOrWhiteSpace($PackageDir)) -and (-not $ForceRemote)) {
    if (-not (Test-Path -LiteralPath $PackageDir)) {
        throw "PackageDir not found: $PackageDir"
    }
    $sourceRoot = Resolve-PackageRoot -BaseDir $PackageDir -SourceLabel "PackageDir"
}
elseif ($ForceRemote) {
    if ([string]::IsNullOrWhiteSpace($repoSlug)) {
        throw "version_manifest.json missing repository field."
    }
    $manifestTargetVersion = $targetVersion
    $resolved = Resolve-ReleaseAssetFromGitHub -Repository $repoSlug -Version $targetVersion -ExpectedZipName $artifactFilename -PreferLatest
    $artifactUrl = [string]$resolved.zipUrl
    $resolvedTagName = [string]$resolved.tagName
    if ([string]::IsNullOrWhiteSpace($artifactUrl)) {
        throw "Resolved release has empty zip url."
    }
    $resolvedVersion = ""
    if (-not [string]::IsNullOrWhiteSpace($resolvedTagName)) {
        if ($resolvedTagName.StartsWith("v")) {
            $resolvedVersion = $resolvedTagName.Substring(1)
        }
        else {
            $resolvedVersion = $resolvedTagName
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($resolvedVersion) -and ($resolvedVersion -ne $targetVersion)) {
        Write-Warning ("[UPDATE] local manifest version " + $manifestTargetVersion + " lags remote release " + $resolvedVersion + "; using remote release metadata.")
        $targetVersion = $resolvedVersion
    }
    Write-Output ("[UPDATE] resolved release tag=" + $resolvedTagName)
    Write-Output ("[UPDATE] resolved artifact url=" + $artifactUrl)

    $shaFromRelease = ""
    if (-not [string]::IsNullOrWhiteSpace([string]$resolved.shaUrl)) {
        $shaPath = Join-Path $workDir "sha256.txt"
        Invoke-WebRequest -Uri ([string]$resolved.shaUrl) -OutFile $shaPath -UseBasicParsing
        $shaRaw = (Get-Content -LiteralPath $shaPath -Raw -Encoding UTF8).Trim()
        if (-not [string]::IsNullOrWhiteSpace($shaRaw)) {
            $shaMatch = [regex]::Match($shaRaw, '[0-9a-fA-F]{64}')
            if ($shaMatch.Success) {
                $shaFromRelease = $shaMatch.Value.ToLowerInvariant()
            }
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($shaFromRelease)) {
        $artifactSha = $shaFromRelease
        Write-Output "[UPDATE] using sha256 from release asset (sha256.txt)."
    }
    elseif (-not [string]::IsNullOrWhiteSpace($resolvedVersion) -and ($resolvedVersion -ne $manifestTargetVersion)) {
        if (-not [string]::IsNullOrWhiteSpace($artifactSha)) {
            Write-Warning "[UPDATE] sha256.txt missing/unreadable for remote release; ignoring stale local manifest sha256 to avoid false mismatch."
        }
        $artifactSha = ""
    }

    $zipPath = Join-Path $workDir "pointer-gpf-mcp.zip"
    Download-ReleaseZip -Url $artifactUrl -ZipPath $zipPath
    if (-not [string]::IsNullOrWhiteSpace($artifactSha)) {
        $expected = $artifactSha.ToLowerInvariant().Replace("sha256:", "")
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash.ToLowerInvariant()
        if ($actual -ne $expected) {
            throw "Artifact sha256 mismatch. expected=$expected actual=$actual"
        }
    }
    $extractDir = Join-Path $workDir "extract"
    $sourceRoot = Expand-PackageArchive -ZipPath $zipPath -ExtractDir $extractDir -SourceLabel "remote artifact"
}
elseif (-not [string]::IsNullOrWhiteSpace($artifactUrl)) {
    $zipPath = Join-Path $workDir "pointer-gpf-mcp.zip"
    Download-ReleaseZip -Url $artifactUrl -ZipPath $zipPath
    if (-not [string]::IsNullOrWhiteSpace($artifactSha)) {
        $expected = $artifactSha.ToLowerInvariant().Replace("sha256:", "")
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash.ToLowerInvariant()
        if ($actual -ne $expected) {
            throw "Artifact sha256 mismatch. expected=$expected actual=$actual"
        }
    }
    $extractDir = Join-Path $workDir "extract"
    $sourceRoot = Expand-PackageArchive -ZipPath $zipPath -ExtractDir $extractDir -SourceLabel "manifest artifact"
}
else {
    throw "No update source available. Provide -PackageDir or publish artifact.url in version_manifest.json."
}

$syncSpecs = @(
    @{
        name = "mcp"
        source = Join-Path $sourceRoot "mcp"
        destination = $mcpDir
        type = "dir"
    }
)

if (-not $NoRootSync) {
    $syncSpecs += @(
        @{
            name = "gtr.config.json"
            source = Join-Path $sourceRoot "gtr.config.json"
            destination = $gtrConfigPath
            type = "file"
        },
        @{
            name = "godot_plugin_template"
            source = Join-Path $sourceRoot "godot_plugin_template"
            destination = $pluginTemplateDir
            type = "dir"
        }
    )
}

foreach ($spec in $syncSpecs) {
    if (-not (Test-Path -LiteralPath ([string]$spec.source))) {
        throw "Update source missing required path: $([string]$spec.source)"
    }
}

$backupDir = Join-Path $repoRoot (".mcp-backup-" + (Get-Date -Format "yyyyMMddTHHmmss"))
New-Item -ItemType Directory -Path $backupDir | Out-Null

$restorePlans = @()
foreach ($spec in $syncSpecs) {
    $exists = Test-Path -LiteralPath ([string]$spec.destination)
    $backupPath = Join-Path $backupDir ([string]$spec.name)
    $restorePlans += @{
        name = [string]$spec.name
        destination = [string]$spec.destination
        backupPath = $backupPath
        existed = $exists
        type = [string]$spec.type
    }
    if ($exists) {
        Copy-Item -LiteralPath ([string]$spec.destination) -Destination $backupPath -Recurse -Force
    }
}

try {
    foreach ($spec in $syncSpecs) {
        $dest = [string]$spec.destination
        $src = [string]$spec.source
        if (Test-IsSamePath -PathA $src -PathB $dest) {
            Write-Output ("[UPDATE] skipped sync for " + [string]$spec.name + " (source and destination are identical)")
            continue
        }
        if (Test-Path -LiteralPath $dest) {
            Remove-Item -LiteralPath $dest -Recurse -Force
        }
        if ([string]$spec.type -eq "dir") {
            Copy-Item -LiteralPath $src -Destination $dest -Recurse -Force
        }
        else {
            $destParent = Split-Path -Parent $dest
            if (-not [string]::IsNullOrWhiteSpace($destParent)) {
                New-Item -ItemType Directory -Path $destParent -Force | Out-Null
            }
            Copy-Item -LiteralPath $src -Destination $dest -Force
        }
    }

    $installed = Resolve-InstalledVersionInfo -RepoRoot $repoRoot -ChannelName $Channel
    if ($NoRootSync -and $FailOnVersionMismatch) {
        Write-Warning "[UPDATE] -NoRootSync with -FailOnVersionMismatch may fail if root files are intentionally left on older versions."
    }
    $consistency = Test-VersionConsistency -RepoRoot $repoRoot -ChannelName $Channel -FailMismatch:$FailOnVersionMismatch

    Write-Output ("[UPDATE] updated channel=" + $Channel + " installed_manifest_version=" + [string]$installed.manifestVersion)
    if (-not [string]::IsNullOrWhiteSpace($resolvedTagName)) {
        Write-Output ("[UPDATE] installed_from_tag=" + $resolvedTagName)
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$installed.runtimeVersion)) {
        Write-Output ("[UPDATE] installed_runtime_version=" + [string]$installed.runtimeVersion)
    }
    if ($NoRootSync) {
        Write-Warning "[UPDATE] root sync disabled by -NoRootSync. Only mcp/ was updated."
    }
    if ($consistency.ok) {
        Write-Output "[UPDATE] version consistency check passed."
    }
    Write-Output ("[UPDATE] backup=" + $backupDir)
}
catch {
    Write-Output "[UPDATE] failed, rolling back..."
    foreach ($plan in $restorePlans) {
        $dest = [string]$plan.destination
        $backupPath = [string]$plan.backupPath
        $existed = [bool]$plan.existed
        if (Test-Path -LiteralPath $dest) {
            Remove-Item -LiteralPath $dest -Recurse -Force -ErrorAction SilentlyContinue
        }
        if ($existed -and (Test-Path -LiteralPath $backupPath)) {
            if ([string]$plan.type -eq "dir") {
                Copy-Item -LiteralPath $backupPath -Destination $dest -Recurse -Force
            }
            else {
                $destParent = Split-Path -Parent $dest
                if (-not [string]::IsNullOrWhiteSpace($destParent)) {
                    New-Item -ItemType Directory -Path $destParent -Force | Out-Null
                }
                Copy-Item -LiteralPath $backupPath -Destination $dest -Force
            }
        }
    }
    throw
}
finally {
    if (Test-Path -LiteralPath $workDir) {
        Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
