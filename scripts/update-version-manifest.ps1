param(
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$ArtifactUrl,
    [Parameter(Mandatory = $true)][string]$Sha256,
    [long]$SizeBytes = 0,
    [string]$ManifestPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ManifestPath)) {
    $repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
    $ManifestPath = Join-Path $repoRoot "mcp/version_manifest.json"
}
if (-not (Test-Path -LiteralPath $ManifestPath)) {
    throw "Manifest not found: $ManifestPath"
}

$json = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($null -eq $json.channels.stable) {
    throw "Manifest missing channels.stable section."
}

$json.current_version = $Version
$json.channels.stable.version = $Version
$json.channels.stable.min_compatible_version = $Version
$json.channels.stable.published_at_utc = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
$json.channels.stable.artifact.filename = ("pointer-gpf-mcp-" + $Version + ".zip")
$json.channels.stable.artifact.url = $ArtifactUrl
$json.channels.stable.artifact.sha256 = $Sha256.ToLowerInvariant().Replace("sha256:", "")
if ($SizeBytes -gt 0) {
    $json.channels.stable.artifact.size_bytes = $SizeBytes
}

$output = $json | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($ManifestPath, $output, [System.Text.UTF8Encoding]::new($false))

Write-Output ("[MANIFEST] updated: " + $ManifestPath)
Write-Output ("[MANIFEST] stable.version=" + $Version)
