<#
.SYNOPSIS
    인포그래픽을 그릴 수 있게 그림 다리를 켠다.

.DESCRIPTION
    컨테이너 안에는 브라우저가 없다. 그런데 이 컴퓨터에는 크롬이 이미 깔려 있다.
    그래서 목소리 다리(8199)·캡컷 다리(8200)와 같은 방식으로, 이 컴퓨터에서 도는
    작은 서비스를 켠다. 인포그래픽은 **8201**이다.

    VideoBox를 켜면 `owner-ready.ps1`이 이 다리를 창 없이 함께 띄운다.
    손으로 켤 일은 그게 실패했을 때뿐이다.

    캡컷 다리와 달리 `--allow-root`가 없다. 이 서비스는 이 컴퓨터에 아무것도
    남기지 않기 때문이다 -- 임시 폴더에 그리고, 읽어서 돌려주고, 지운다.
#>
[CmdletBinding()]
param(
    [int]$Port = 8201
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

# **이미 켜져 있으면 여기서 끝낸다** (목소리·캡컷 다리와 같은 이유: 창이 계속 뜬다).
try {
    $probe = New-Object System.Net.Sockets.TcpClient
    $probe.Connect('127.0.0.1', $Port)
    if ($probe.Connected) {
        $probe.Close()
        Write-Host "그림 다리가 이미 켜져 있습니다 (127.0.0.1:$Port)." -ForegroundColor Green
        exit 0
    }
    $probe.Close()
} catch { }

$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Host "파이썬을 찾지 못했습니다: $python" -ForegroundColor Red
    exit 1
}

$service = Join-Path $PSScriptRoot 'host_infographic_service.py'

Write-Host "그림 다리를 켭니다 (127.0.0.1:$Port)." -ForegroundColor Cyan
& $python $service --port $Port
exit $LASTEXITCODE
