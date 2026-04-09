param(
    [Parameter()][string]$Version,
    [Parameter(Mandatory = $true)][string]$ArtifactUrl,
    [Parameter(Mandatory = $true)][string]$Sha256,
    [Parameter()][Nullable[long]]$SizeBytes,
    [string]$ManifestPath = "",
    [string]$VersionFile = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

if ([string]::IsNullOrWhiteSpace($ManifestPath)) {
    $ManifestPath = Join-Path $repoRoot "mcp/version_manifest.json"
}
if ([string]::IsNullOrWhiteSpace($VersionFile)) {
    $VersionFile = Join-Path $repoRoot "VERSION"
}
if (-not (Test-Path -LiteralPath $ManifestPath)) {
    throw "Manifest not found: $ManifestPath"
}

[string]$resolvedVersion = $null
if ($PSBoundParameters.ContainsKey("Version")) {
    if ([string]::IsNullOrWhiteSpace($Version)) {
        throw "-Version was specified but is empty."
    }
    $resolvedVersion = $Version.Trim()
} else {
    if (-not (Test-Path -LiteralPath $VersionFile)) {
        throw "Version file not found: $VersionFile (pass -Version or create VERSION at repo root)."
    }
    $resolvedVersion = (Get-Content -LiteralPath $VersionFile -Raw -Encoding UTF8).Trim()
}

if ($resolvedVersion -notmatch '^\d+\.\d+\.\d+\.\d+$') {
    throw "Invalid version format (expected ^\d+\.\d+\.\d+\.\d+$): $resolvedVersion"
}

$shaTrimmed = $Sha256.Trim()
$shaHex = [regex]::Replace($shaTrimmed, '^(?i)sha256:', '')
if ($shaHex -notmatch '^[0-9a-fA-F]{64}$') {
    throw "Invalid Sha256: after optional 'sha256:' prefix, value must be exactly 64 hexadecimal characters."
}
$shaNormalized = $shaHex.ToLowerInvariant()

$json = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($null -eq $json.channels.stable) {
    throw "Manifest missing channels.stable section."
}
if ($null -eq $json.channels.stable.artifact) {
    throw "Manifest missing channels.stable.artifact object; cannot update artifact fields."
}

$json.current_version = $resolvedVersion
$json.channels.stable.version = $resolvedVersion
$json.channels.stable.min_compatible_version = $resolvedVersion
$json.channels.stable.published_at_utc = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
$json.channels.stable.artifact.filename = ("pointer-gpf-mcp-" + $resolvedVersion + ".zip")
$json.channels.stable.artifact.url = $ArtifactUrl
$json.channels.stable.artifact.sha256 = $shaNormalized
if ($PSBoundParameters.ContainsKey("SizeBytes")) {
    $json.channels.stable.artifact.size_bytes = $SizeBytes
}

$output = $json | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($ManifestPath, $output, [System.Text.UTF8Encoding]::new($false))

Write-Output ("[MANIFEST] updated: " + $ManifestPath)
Write-Output ("[MANIFEST] stable.version=" + $resolvedVersion)
if ($PSBoundParameters.ContainsKey("SizeBytes")) {
    Write-Output ("[MANIFEST] size_bytes set to " + $SizeBytes)
} else {
    Write-Output "[MANIFEST] SizeBytes not specified; size_bytes left unchanged."
}
