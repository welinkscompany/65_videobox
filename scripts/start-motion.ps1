<#
.SYNOPSIS
    설명 모션을 그릴 수 있게 모션 다리를 켠다.

.DESCRIPTION
    컨테이너 안에는 node도 헤드리스 브라우저도 없다. 하이퍼프레임과 그릴 브라우저는
    이 컴퓨터에만 있다. 그래서 목소리(8199)·캡컷(8200)·그림(8201) 다리와 같은 방식으로
    이 컴퓨터에서 도는 작은 서비스를 켠다. 모션은 **8202**다.

    VideoBox를 켜면 `owner-ready.ps1`이 이 다리를 창 없이 함께 띄운다.
    처음 한 번 하이퍼프레임 설치와 브라우저 받기는 `prepare-motion.ps1`이 한다.
    손으로 켤 일은 그게 실패했을 때뿐이다.

    이 서비스는 이 컴퓨터에 아무것도 남기지 않는다 -- 임시 폴더에 그리고, 읽어서 돌려주고, 지운다.
#>
[CmdletBinding()]
param(
    [int]$Port = 8202
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

# **이미 켜져 있으면 여기서 끝낸다** (목소리·캡컷 다리와 같은 이유: 창이 계속 뜬다).
try {
    $probe = New-Object System.Net.Sockets.TcpClient
    $probe.Connect('127.0.0.1', $Port)
    if ($probe.Connected) {
        $probe.Close()
        Write-Host "모션 다리가 이미 켜져 있습니다 (127.0.0.1:$Port)." -ForegroundColor Green
        exit 0
    }
    $probe.Close()
} catch { }

$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Host "파이썬을 찾지 못했습니다: $python" -ForegroundColor Red
    exit 1
}

$service = Join-Path $PSScriptRoot 'host_motion_service.py'

Write-Host "모션 다리를 켭니다 (127.0.0.1:$Port)." -ForegroundColor Cyan
& $python $service --port $Port
exit $LASTEXITCODE
