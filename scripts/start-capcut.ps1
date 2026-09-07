<#
.SYNOPSIS
    만든 초안을 캡컷으로 넘길 수 있게 캡컷 다리를 켠다.

.DESCRIPTION
    캡컷 프로젝트 폴더는 컨테이너가 아니라 **이 컴퓨터**에 있다
    (`%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft`).
    컨테이너는 그 폴더를 못 보기 때문에, 목소리 다리(8199)와 같은 방식으로
    이 컴퓨터에서 도는 작은 서비스를 켠다. 캡컷은 **8200**이다.

    VideoBox를 켜면 `owner-ready.ps1`이 이 다리를 창 없이 함께 띄운다.
    손으로 켤 일은 그게 실패했을 때뿐이다.
#>
[CmdletBinding()]
param(
    [int]$Port = 8200
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

# **이미 켜져 있으면 여기서 끝낸다** (목소리 다리와 같은 이유: 창이 계속 뜬다).
try {
    $probe = New-Object System.Net.Sockets.TcpClient
    $probe.Connect('127.0.0.1', $Port)
    if ($probe.Connected) {
        $probe.Close()
        Write-Host "캡컷 다리가 이미 켜져 있습니다 (127.0.0.1:$Port)." -ForegroundColor Green
        exit 0
    }
    $probe.Close()
} catch { }

$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Host "파이썬을 찾지 못했습니다: $python" -ForegroundColor Red
    exit 1
}

# 컨테이너가 자기 자료 밖의 폴더를 캡컷으로 복사하도록 시킬 수 없어야 한다.
# 받아 줄 폴더는 `.env.container`가 이미 정해 둔 그 자리다.
$allowRoot = $null
$envFile = Join-Path $repoRoot '.env.container'
if (Test-Path $envFile) {
    $line = Select-String -Path $envFile -Pattern '^\s*VIDEOBOX_CONTAINER_DATA_ROOT\s*=\s*(.+)$' |
        Select-Object -First 1
    if ($line) {
        $dataRoot = $line.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
        if ($dataRoot) { $allowRoot = Join-Path $dataRoot 'runtime' }
    }
}

$service = Join-Path $PSScriptRoot 'host_capcut_service.py'
$arguments = @($service, '--port', $Port)
if ($allowRoot) { $arguments += @('--allow-root', $allowRoot) }

Write-Host "캡컷 다리를 켭니다 (127.0.0.1:$Port)." -ForegroundColor Cyan
if ($allowRoot) { Write-Host "  받아 줄 자리: $allowRoot" -ForegroundColor DarkGray }

& $python @arguments
exit $LASTEXITCODE
