<#
.SYNOPSIS
    설명 모션 도구를 처음 한 번 준비한다(하이퍼프레임 0.8.140 설치 + 그릴 브라우저 받기).

.DESCRIPTION
    약 120MB(설치)와 약 270MB(브라우저, ~/.cache/hyperframes)를 인터넷에서 받는다.
    owner-ready.ps1이 준비가 안 된 것을 보면 이 스크립트를 숨은 창으로 띄운다 --
    VideoBox 켜기를 몇 분씩 붙잡지 않으려고 따로 돈다. 단계마다 시간 상한이 있고,
    넘으면 자식까지 끊고 실패로 끝난다(조용히 매달리지 않는다).
#>
[CmdletBinding()]
param(
    [int]$InstallTimeoutSeconds = 300,
    [int]$BrowserTimeoutSeconds = 900
)

$ErrorActionPreference = 'Stop'
$bridgeRoot = Join-Path $PSScriptRoot 'motion-bridge'
$lock = Join-Path ([System.IO.Path]::GetTempPath()) 'videobox-motion-prepare.lock'

# 같은 준비를 두 번 돌리지 않는다. 30분 넘은 잠금은 죽은 것으로 본다.
if (Test-Path $lock) {
    if (((Get-Date) - (Get-Item $lock).LastWriteTime).TotalMinutes -lt 30) {
        Write-Host "모션 도구를 이미 준비하고 있습니다." -ForegroundColor Yellow
        exit 0
    }
    Remove-Item $lock -Force
}
New-Item -ItemType File -Path $lock -Force | Out-Null

function Invoke-Bounded([string]$File, [string[]]$Arguments, [int]$Seconds, [string]$Label) {
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -WorkingDirectory $bridgeRoot -NoNewWindow -PassThru
    if (-not $process.WaitForExit($Seconds * 1000)) {
        & taskkill.exe /PID $process.Id /T /F | Out-Null
        throw "$Label 이(가) $Seconds 초 안에 끝나지 않아 멈췄습니다. 인터넷 연결을 확인한 뒤 다시 실행하세요."
    }
    if ($process.ExitCode -ne 0) {
        throw "$Label 에 실패했습니다(종료 코드 $($process.ExitCode))."
    }
}

try {
    $node = (Get-Command node -ErrorAction SilentlyContinue).Source
    $npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
    if (-not $node -or -not $npm) { throw "node를 찾지 못했습니다. Node.js 24를 설치한 뒤 다시 실행하세요." }
    $env:HYPERFRAMES_NO_TELEMETRY = '1'
    $env:DO_NOT_TRACK = '1'
    $env:HYPERFRAMES_SKIP_SKILLS = '1'
    $env:HYPERFRAMES_NO_UPDATE_CHECK = '1'
    $env:HYPERFRAMES_NO_AUTO_INSTALL = '1'

    $installed = Join-Path $bridgeRoot 'node_modules\hyperframes\package.json'
    $version = $null
    if (Test-Path $installed) { $version = (Get-Content -LiteralPath $installed -Raw | ConvertFrom-Json).version }
    if ($version -ne '0.8.140') {
        Write-Host "모션 도구를 처음 한 번 설치합니다(약 120MB)." -ForegroundColor Cyan
        Invoke-Bounded $npm @('ci', '--ignore-scripts', '--no-audit', '--no-fund') $InstallTimeoutSeconds '모션 도구 설치'
    }
    Write-Host "모션을 그릴 브라우저를 처음 한 번 받습니다(약 270MB, 몇 분)." -ForegroundColor Cyan
    $cli = Join-Path $bridgeRoot 'node_modules\hyperframes\bin\hyperframes.mjs'
    Invoke-Bounded $node @($cli, 'browser', 'ensure') $BrowserTimeoutSeconds '브라우저 받기'
    Write-Host "모션 도구 준비가 끝났습니다." -ForegroundColor Green
    exit 0
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
} finally {
    Remove-Item $lock -Force -ErrorAction SilentlyContinue
}
