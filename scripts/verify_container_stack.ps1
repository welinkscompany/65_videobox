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

# api·web은 videobox-workspace 한 서비스로 합쳐졌다. 옛 이름을 요구하면
# 스택이 멀쩡해도 이 검증이 항상 실패하고, 항상 실패하는 검증은 아무도 안 돌린다.
$services = docker compose -f $ComposeFile ps --format json | ConvertFrom-Json
foreach ($name in "videobox-postgres", "videobox-workspace") {
    $service = @($services | Where-Object Service -eq $name)
    if ($service.Count -ne 1 -or $service[0].State -ne "running") {
        throw "Required service is not running: $name"
    }
}

# postgres는 호스트 포트를 아예 열지 않는다.
$postgresContainer = (docker compose -f $ComposeFile ps -q "videobox-postgres").Trim()
if (-not $postgresContainer) { throw "Missing container for videobox-postgres" }
if (@(docker port $postgresContainer).Count -gt 0) { throw "videobox-postgres exposes a host port" }

# workspace는 웹 포트 하나를, 그것도 루프백(127.0.0.1)으로만 연다.
$workspaceContainer = (docker compose -f $ComposeFile ps -q "videobox-workspace").Trim()
if (-not $workspaceContainer) { throw "Missing container for videobox-workspace" }
$workspacePorts = @(docker port $workspaceContainer)
if ($workspacePorts.Count -eq 0) { throw "videobox-workspace publishes no web port" }
foreach ($line in $workspacePorts) {
    if ($line -notmatch "127\.0\.0\.1") { throw "videobox-workspace publishes a non-loopback port: $line" }
}

$projects = (Invoke-RestMethod "http://127.0.0.1:$WebPort/api/projects").projects
if (@($projects).Count -lt 1) { throw "Proxy API returned no imported projects" }

[pscustomobject]@{
    project_count = @($projects).Count
    snapshot_file_count = @($manifest.file_hashes.PSObject.Properties).Count
    source_preserved = [bool]$manifest.source_preserved
    web_url = "http://127.0.0.1:$WebPort"
} | ConvertTo-Json -Compress
