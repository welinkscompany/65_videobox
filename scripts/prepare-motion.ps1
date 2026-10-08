<#
.SYNOPSIS
    설명 모션 도구를 처음 한 번 준비한다(하이퍼프레임 0.8.140 설치 + 그릴 브라우저 받기).

.DESCRIPTION
    약 120MB(설치)와 약 270MB(브라우저, ~/.cache/hyperframes)를 인터넷에서 받는다.
    owner-ready.ps1이 준비가 안 된 것을 보면 이 스크립트를 숨은 창으로 띄운다 --
    VideoBox 켜기를 몇 분씩 붙잡지 않으려고 따로 돈다. 단계마다 시간 상한이 있고,
    넘으면 자식까지 끊고 실패로 끝난다(조용히 매달리지 않는다).

    BridgeRoot / LockPath / NodePath / NpmPath는 시험이 가짜 도구로 이 흐름을 실제로
    돌려 보려고 연 이음매다. 평소에는 건드리지 않는다.

    LogPath는 숨은 창으로 띄울 때 쓴다. 띄우는 쪽이 출력을 리다이렉트하면 부른 쪽의 파이프가
    이 창에 상속돼 부른 쪽이 준비가 끝나기를 기다리게 된다 -- 그래서 로그는 여기서 스스로 남긴다.
#>
[CmdletBinding()]
param(
    [int]$InstallTimeoutSeconds = 300,
    [int]$BrowserTimeoutSeconds = 900,
    [string]$BridgeRoot = '',
    [string]$LockPath = '',
    [string]$NodePath = '',
    [string]$NpmPath = '',
    [string]$LogPath = ''
)

$ErrorActionPreference = 'Stop'
if ($LogPath) { try { Start-Transcript -LiteralPath $LogPath -Force | Out-Null } catch { } }
$bridgeRoot = if ($BridgeRoot) { $BridgeRoot } else { Join-Path $PSScriptRoot 'motion-bridge' }
$lock = if ($LockPath) { $LockPath } else { Join-Path ([System.IO.Path]::GetTempPath()) 'videobox-motion-prepare.lock' }

# 같은 준비를 두 번 돌리지 않는다. **잠금은 한 번에 만들고 검사한다**(CreateNew) --
# "있나 보고, 없으면 만든다"는 두 줄 사이에 두 번째 실행이 끼어들 수 있다.
# 잠금 파일은 끝날 때까지 열어 둔다(FileShare.None). 30분 넘은 잠금은 죽은 것으로 본다.
function Open-PrepareLock([string]$Path) {
    return [System.IO.File]::Open($Path, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
}
$lockStream = $null
for ($attempt = 0; $attempt -lt 2 -and $null -eq $lockStream; $attempt++) {
    try {
        $lockStream = Open-PrepareLock $lock
    } catch [System.IO.IOException] {
        $age = $null
        try { $age = ((Get-Date) - (Get-Item -LiteralPath $lock -ErrorAction Stop).LastWriteTime).TotalMinutes } catch { $age = $null }
        if ($null -eq $age -and $attempt -eq 0) { continue }   # 그새 지워졌다 -- 한 번 더 만든다
        if ($null -ne $age -and $age -ge 30) {
            try { Remove-Item -LiteralPath $lock -Force -ErrorAction Stop } catch { }
            continue
        }
        Write-Host "모션 도구를 이미 준비하고 있습니다." -ForegroundColor Yellow
        exit 0
    }
}
if ($null -eq $lockStream) {
    Write-Host "모션 도구를 이미 준비하고 있습니다." -ForegroundColor Yellow
    exit 0
}

function Format-Argument([string]$Value) {
    # Start-Process는 배열을 그냥 공백으로 이어 붙인다 -- 공백이 든 경로는 따옴표로 감싼다.
    if ($Value -match '[\s"]') { return '"' + $Value.Replace('"', '\"') + '"' }
    return $Value
}

function Invoke-Bounded([string]$File, [string[]]$Arguments, [int]$Seconds, [string]$Label) {
    $quoted = @($Arguments | ForEach-Object { Format-Argument $_ })
    $startArguments = @{ FilePath = $File; ArgumentList = $quoted; WorkingDirectory = $bridgeRoot; NoNewWindow = $true; PassThru = $true }
    $childLog = $null
    if ($LogPath) {
        # 로그 파일로 모은다 -- 끝난 뒤 한꺼번에 기록에 옮긴다.
        $childLog = [System.IO.Path]::GetTempFileName()
        $startArguments.RedirectStandardOutput = $childLog
        $startArguments.RedirectStandardError = $childLog + '.err'
    }
    $process = Start-Process @startArguments
    # Windows PowerShell 5.1: Handle을 먼저 건드리지 않으면 끝난 뒤 ExitCode가 $null로 읽힌다.
    $null = $process.Handle
    if (-not $process.WaitForExit($Seconds * 1000)) {
        & taskkill.exe /PID $process.Id /T /F 2>&1 | Out-Null
        if ($childLog) { Remove-Item -LiteralPath $childLog, ($childLog + '.err') -Force -ErrorAction SilentlyContinue }
        throw "$Label 이(가) $Seconds 초 안에 끝나지 않아 멈췄습니다. 인터넷 연결을 확인한 뒤 다시 실행하세요."
    }
    $process.WaitForExit()   # 시간 제한 없는 호출이 출력 비움까지 마치고 종료 코드를 확정한다
    if ($childLog) {
        foreach ($part in @($childLog, ($childLog + '.err'))) {
            try { Get-Content -LiteralPath $part -ErrorAction Stop | ForEach-Object { Write-Host $_ } } catch { }
            Remove-Item -LiteralPath $part -Force -ErrorAction SilentlyContinue
        }
    }
    $code = $process.ExitCode
    if ($null -eq $code) {
        throw "$Label 의 종료 코드를 읽지 못했습니다. 성공으로 치지 않습니다."
    }
    if ($code -ne 0) {
        throw "$Label 에 실패했습니다(종료 코드 $code)."
    }
}

try {
    $node = if ($NodePath) { $NodePath } else { (Get-Command node -ErrorAction SilentlyContinue).Source }
    $npm = if ($NpmPath) { $NpmPath } else { (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source }
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
    try { $lockStream.Dispose() } catch { }
    Remove-Item -LiteralPath $lock -Force -ErrorAction SilentlyContinue
    if ($LogPath) { try { Stop-Transcript | Out-Null } catch { } }
}
