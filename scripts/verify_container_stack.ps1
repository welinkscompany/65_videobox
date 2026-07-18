param(
    [Parameter(Mandatory = $true)]
    [string]$DataRoot,
    [int]$WebPort = 5173,
    [string]$ComposeFile = "compose.yaml"
)

$ErrorActionPreference = "Stop"

function Get-Sha256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

$resolvedRoot = (Resolve-Path -LiteralPath $DataRoot).Path
$snapshotRoot = Join-Path $resolvedRoot "snapshot"
$runtimeRoot = Join-Path $resolvedRoot "runtime"
$manifestPath = Join-Path $snapshotRoot "container-migration-manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Container snapshot has no migration manifest: $snapshotRoot"
}
if (-not (Test-Path -LiteralPath $runtimeRoot -PathType Container)) {
    throw "Container runtime data directory is missing: $runtimeRoot"
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if (-not $manifest.source_preserved) {
    throw "Migration manifest does not prove source preservation."
}
if ($manifest.layout_version -ne 1 -or $manifest.snapshot_root -ne "snapshot") {
    throw "Migration manifest does not match the snapshot layout."
}

$expectedPaths = @($manifest.file_hashes.PSObject.Properties.Name)
$actualPaths = @(
    Get-ChildItem -LiteralPath $snapshotRoot -File -Recurse |
        Where-Object { $_.FullName -ne $manifestPath } |
        ForEach-Object { [IO.Path]::GetRelativePath($snapshotRoot, $_.FullName).Replace('\', '/') }
)
$extraPaths = @($actualPaths | Where-Object { $_ -notin $expectedPaths })
if ($extraPaths.Count -gt 0) {
    throw "Snapshot contains unmanifested file(s): $($extraPaths -join ', ')"
}

foreach ($entry in $manifest.file_hashes.PSObject.Properties) {
    $path = Join-Path $snapshotRoot $entry.Name.Replace('/', [IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Snapshot file is missing: $($entry.Name)"
    }
    if ((Get-Sha256 $path) -ne $entry.Value) {
        throw "Snapshot hash mismatch: $($entry.Name)"
    }
}

$services = docker compose -f $ComposeFile ps --format json | ConvertFrom-Json
foreach ($name in "videobox-postgres", "videobox-api", "videobox-web") {
    $service = @($services | Where-Object Service -eq $name)
    if ($service.Count -ne 1 -or $service[0].State -ne "running") {
        throw "Required service is not running: $name"
    }
}

foreach ($name in "videobox-api", "videobox-postgres") {
    $container = (docker compose -f $ComposeFile ps -q $name).Trim()
    if (-not $container) { throw "Missing container for $name" }
    $publishedPorts = @(docker port $container)
    if ($publishedPorts.Count -gt 0) { throw "$name exposes a host port" }
}

$projects = (Invoke-RestMethod "http://127.0.0.1:$WebPort/api/projects").projects
if (@($projects).Count -lt 1) { throw "Proxy API returned no imported projects" }

[pscustomobject]@{
    project_count = @($projects).Count
    snapshot_file_count = @($manifest.file_hashes.PSObject.Properties).Count
    source_preserved = [bool]$manifest.source_preserved
    web_url = "http://127.0.0.1:$WebPort"
} | ConvertTo-Json -Compress
