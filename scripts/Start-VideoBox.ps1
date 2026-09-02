<#
.SYNOPSIS
아이콘 하나로 VideoBox를 켠다.

.DESCRIPTION
2026-08-17 첫 사용 점검의 결론은 "웹이라서 불편한 것은 두 가지뿐"이었다 --
도커를 띄우고 주소를 쳐야 켜지는 것, 파일 경로를 타이핑해야 하는 것. 이 스크립트는
그중 **첫 번째만** 푼다. 두 번째는 화면이 이미 네이티브 파일 선택창을 쓰고 있어
따로 할 일이 없다(끌어다 놓기, 폴더째 고르기 포함).

컨테이너는 직접 다루지 않는다. `scripts/owner-ready.ps1`에 넘긴다 -- `CLAUDE.md` §3이
컨테이너 조작을 그 스크립트 하나로 못박고 있고, 여기서 `docker compose`를 또 치면
시작 방법이 두 벌이 되어 그중 하나가 조용히 낡는다.

브라우저는 주소창 없는 앱 창으로 연다. 첫 사용 점검에서 "프로그램이 아니라 웹페이지
한 장으로 보인다"고 한 것이 이것이다.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Uri]$VideoBoxUri = "http://127.0.0.1:5173/",
    # 이미지를 새로 만들어야 할 때는 몇 분이 걸린다. 넉넉히 잡되 무한정 기다리지는 않는다.
    [ValidateRange(5, 1800)]
    [int]$TimeoutSec = 300,
    [switch]$Json,
    [switch]$SkipBrowser,
    # 목소리 프로그램(내 목소리 더빙)을 안 켜고 VideoBox만 켠다.
    [switch]$SkipVoice,
    [Uri]$VoiceUri = "http://127.0.0.1:8199/health",
    # 모델을 싣는 데 걸리는 시간. 못 기다려도 계속 간다.
    [ValidateRange(0, 600)]
    [int]$VoiceTimeoutSec = 40,
    [string]$VoiceScript = "",
    [string]$DockerExecutable = "docker",
    [string]$DockerDesktopExecutable = "",
    [string]$OwnerReadyScript = "",
    [string]$BrowserExecutable = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding

$repositoryRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($OwnerReadyScript)) {
    $OwnerReadyScript = Join-Path $PSScriptRoot "owner-ready.ps1"
}
if ([string]::IsNullOrWhiteSpace($VoiceScript)) {
    $VoiceScript = Join-Path $PSScriptRoot "start-voice.ps1"
}
if ([string]::IsNullOrWhiteSpace($DockerDesktopExecutable)) {
    $DockerDesktopExecutable = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
}

$script:steps = @()

function Test-VoiceAnswering {
    # 목소리 프로그램이 대답하는가. 켜져 있으면 또 켜지 않기 위해 먼저 묻는다.
    try {
        return (Invoke-WebRequest -Uri $VoiceUri.AbsoluteUri -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200
    } catch {
        return $false
    }
}

function Add-Step {
    param(
        [string]$Id,
        [ValidateSet("pass", "skipped", "fail")]
        [string]$Status,
        [string]$Summary,
        [hashtable]$Evidence = @{}
    )
    $script:steps += [pscustomobject]@{ id = $Id; status = $Status; summary = $Summary; evidence = $Evidence }
    if (-not $Json) {
        $mark = switch ($Status) { "pass" { "  " } "skipped" { "  " } default { "!!" } }
        Write-Host "$mark $Summary"
    }
}

function Write-Result {
    param([string]$Overall)
    $payload = [pscustomobject]@{
        script = "Start-VideoBox"
        overall = $Overall
        address = $VideoBoxUri.AbsoluteUri
        steps = $script:steps
    }
    if ($Json) {
        $payload | ConvertTo-Json -Depth 6
    }
    elseif ($Overall -ceq "ready") {
        Write-Host ""
        Write-Host "VideoBox가 켜졌어요. 창이 안 뜨면 이 주소를 여세요: $($VideoBoxUri.AbsoluteUri)"
    }
    else {
        Write-Host ""
        Write-Host "VideoBox를 켜지 못했어요. 위에 !! 표시가 있는 줄이 막힌 지점이에요."
    }
    exit $(if ($Overall -ceq "ready") { 0 } else { 2 })
}

<# 응답이 오기만 하면 켜진 것으로 본다. 404여도 웹 서버는 살아 있다는 뜻이고,
   여기서 판단하려는 것은 "화면을 열 수 있느냐"뿐이다. #>
function Test-VideoBoxAnswering {
    try {
        Invoke-WebRequest -Uri $VideoBoxUri.AbsoluteUri -UseBasicParsing -TimeoutSec 3 -Method Head | Out-Null
        return $true
    }
    catch [System.Net.WebException] {
        return $null -ne $_.Exception.Response
    }
    catch {
        if ($_.Exception.PSObject.Properties.Name -contains "Response" -and $null -ne $_.Exception.Response) { return $true }
        return $false
    }
}

function Test-DockerEngine {
    # 이 함수는 실행 환경이 뜰 때까지 2초마다 다시 불린다. 임시 파일을 호출마다
    # 만들고 안 지우면 도커가 느린 날 %TEMP%에 수백 개가 쌓인다.
    $outFile = [System.IO.Path]::GetTempFileName()
    $errFile = [System.IO.Path]::GetTempFileName()
    try {
        $process = Start-Process -FilePath $DockerExecutable -ArgumentList @("info", "--format", "{{.ServerVersion}}") `
            -NoNewWindow -Wait -PassThru -RedirectStandardOutput $outFile -RedirectStandardError $errFile
        return $process.ExitCode -eq 0
    }
    catch {
        return $false
    }
    finally {
        foreach ($path in @($outFile, $errFile)) {
            try { Remove-Item -LiteralPath $path -Force -ErrorAction Stop } catch { }
        }
    }
}

function Wait-Until {
    param([scriptblock]$Condition, [int]$Seconds)
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Condition) { return $true }
        Start-Sleep -Seconds 2
    }
    return & $Condition
}

if ($PSBoundParameters.ContainsKey("WhatIf")) {
    Add-Step -Id "plan" -Status "pass" -Summary "켜는 순서를 확인만 했어요. 실제로 켜지는 않았어요." -Evidence @{
        owner_ready_script = $OwnerReadyScript
        address = $VideoBoxUri.AbsoluteUri
        opens_browser = (-not $SkipBrowser)
        what_if = $true
    }
    Write-Result -Overall "ready"
}

if (-not (Test-Path -LiteralPath $OwnerReadyScript)) {
    Add-Step -Id "owner_ready" -Status "fail" -Summary "VideoBox를 켜는 스크립트를 찾지 못했어요: $OwnerReadyScript" -Evidence @{ found = $false }
    Write-Result -Overall "blocked"
}

# 1. 이미 켜져 있으면 더 할 일이 없다. 두 번 눌러도 두 번 켜지지 않는다.
if (Test-VideoBoxAnswering) {
    Add-Step -Id "already_running" -Status "pass" -Summary "VideoBox가 이미 켜져 있어요." -Evidence @{ answering = $true }
}
else {
    # 2. 도커가 떠 있어야 한다. 안 떠 있으면 대신 띄우고 기다린다 -- owner가 손으로
    #    Docker Desktop을 먼저 켜야 했던 것이 첫 번째 불편이었다.
    if (Test-DockerEngine) {
        Add-Step -Id "engine" -Status "pass" -Summary "실행 환경이 준비돼 있어요." -Evidence @{ started_by_us = $false }
    }
    else {
        if (-not (Test-Path -LiteralPath $DockerDesktopExecutable)) {
            Add-Step -Id "engine" -Status "fail" -Summary "실행 환경(Docker Desktop)을 찾지 못했어요: $DockerDesktopExecutable" -Evidence @{ found = $false }
            Write-Result -Overall "blocked"
        }
        if (-not $Json) { Write-Host "   실행 환경을 켜는 중이에요. 처음이면 1~2분 걸려요." }
        Start-Process -FilePath $DockerDesktopExecutable | Out-Null
        if (-not (Wait-Until -Condition { Test-DockerEngine } -Seconds $TimeoutSec)) {
            Add-Step -Id "engine" -Status "fail" -Summary "실행 환경이 제때 준비되지 않았어요." -Evidence @{ started_by_us = $true; timeout_sec = $TimeoutSec }
            Write-Result -Overall "blocked"
        }
        Add-Step -Id "engine" -Status "pass" -Summary "실행 환경을 켰어요." -Evidence @{ started_by_us = $true }
    }

    # 3. 시작은 owner-ready.ps1에 맡긴다. 여기서 compose를 직접 치지 않는다.
    if (-not $Json) { Write-Host "   VideoBox를 켜는 중이에요." }
    $startOutput = & powershell -NoProfile -ExecutionPolicy Bypass -File $OwnerReadyScript -Mode Start -Json -TimeoutSec $TimeoutSec 2>&1
    $startExitCode = $LASTEXITCODE
    if ($startExitCode -ne 0) {
        Add-Step -Id "start" -Status "fail" -Summary "VideoBox를 켜지 못했어요." -Evidence @{ exit_code = $startExitCode }
        if (-not $Json) { Write-Host ($startOutput | Out-String) }
        Write-Result -Overall "blocked"
    }
    Add-Step -Id "start" -Status "pass" -Summary "VideoBox를 켰어요." -Evidence @{ exit_code = 0; delegated_to = "owner-ready.ps1" }

    # 4. 켰다고 바로 화면이 뜨지는 않는다. 응답할 때까지 기다린 뒤에 연다 --
    #    안 기다리면 브라우저가 먼저 열려 "연결할 수 없음"을 보여 준다.
    if (-not (Wait-Until -Condition { Test-VideoBoxAnswering } -Seconds $TimeoutSec)) {
        Add-Step -Id "ready" -Status "fail" -Summary "VideoBox가 제때 응답하지 않았어요." -Evidence @{ timeout_sec = $TimeoutSec }
        Write-Result -Overall "blocked"
    }
    Add-Step -Id "ready" -Status "pass" -Summary "VideoBox가 응답해요." -Evidence @{ answering = $true }
}

# 4-B. 목소리 프로그램을 켠다(내 목소리 더빙용).
#
# **여기서 실패해도 VideoBox는 계속 켠다.** 자막·편집·완성본은 목소리 없이도
# 다 되고, 더빙만 화면에서 "목소리 프로그램을 켜 주세요"라고 말한다. 그것 하나
# 때문에 아이콘이 아무것도 안 켜 주면 훨씬 나쁘다.
if ($SkipVoice) {
    Add-Step -Id "voice" -Status "skipped" -Summary "목소리 프로그램은 켜지 않았어요." -Evidence @{ started = $false }
} elseif (Test-VoiceAnswering) {
    # 이미 켜져 있으면 또 켜지 않는다 -- 두 번 켜면 같은 포트를 다투다 죽는다.
    Add-Step -Id "voice" -Status "pass" -Summary "목소리 프로그램이 이미 켜져 있어요." -Evidence @{ started_by_us = $false }
} elseif (-not (Test-Path -LiteralPath $VoiceScript)) {
    Add-Step -Id "voice" -Status "skipped" -Summary "목소리 프로그램이 없어요. 더빙 말고는 다 쓸 수 있어요." -Evidence @{ found = $false }
} else {
    Start-Process -FilePath "pwsh" -ArgumentList @("-NoExit", "-NoProfile", "-File", $VoiceScript) -WindowStyle Minimized | Out-Null
    # 모델을 싣는 데 시간이 걸린다. 여기서 오래 붙들면 화면이 늦게 열리므로
    # 짧게만 기다리고, 못 기다렸어도 계속 간다 -- 뒤늦게 켜지면 그대로 쓰인다.
    if (Wait-Until -Condition { Test-VoiceAnswering } -Seconds $VoiceTimeoutSec) {
        Add-Step -Id "voice" -Status "pass" -Summary "내 목소리로 더빙할 준비가 됐어요." -Evidence @{ started_by_us = $true; ready = $true }
    } else {
        # `pass`로 둔다. **VideoBox는 멀쩡히 켜졌기 때문이다** -- 여기서 fail을
        # 내면 전체가 `blocked`가 되어 아이콘이 실패한 것처럼 보인다.
        # 아직 준비 안 됐다는 것은 문구로 말한다.
        Add-Step -Id "voice" -Status "pass" -Summary "목소리 프로그램을 켜는 중이에요. 더빙은 조금 뒤에 눌러 주세요." -Evidence @{ started_by_us = $true; ready = $false; waited_sec = $VoiceTimeoutSec }
    }
}

# 5. 주소창 없는 앱 창으로 연다.
if ($SkipBrowser) {
    Add-Step -Id "open" -Status "skipped" -Summary "화면은 열지 않았어요." -Evidence @{ opened = $false }
    Write-Result -Overall "ready"
}

$browserCandidates = @()
if (-not [string]::IsNullOrWhiteSpace($BrowserExecutable)) { $browserCandidates += $BrowserExecutable }
$browserCandidates += @(
    (Join-Path ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe"),
    (Join-Path $env:ProgramFiles "Microsoft\Edge\Application\msedge.exe"),
    (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe")
)
$browser = $browserCandidates | Where-Object { -not [string]::IsNullOrWhiteSpace($_) -and (Test-Path -LiteralPath $_) } | Select-Object -First 1

try {
    if ($browser) {
        Start-Process -FilePath $browser -ArgumentList @("--app=$($VideoBoxUri.AbsoluteUri)") | Out-Null
        Add-Step -Id "open" -Status "pass" -Summary "VideoBox 창을 열었어요." -Evidence @{ opened = $true; window = "app"; browser = $browser }
    }
    else {
        # 앱 창을 못 만들면 기본 브라우저 탭으로라도 연다. 주소를 치게 하는 것보다 낫다.
        Start-Process -FilePath $VideoBoxUri.AbsoluteUri | Out-Null
        Add-Step -Id "open" -Status "pass" -Summary "VideoBox를 기본 브라우저로 열었어요." -Evidence @{ opened = $true; window = "tab" }
    }
}
catch {
    Add-Step -Id "open" -Status "fail" -Summary "VideoBox 창을 열지 못했어요. 주소를 직접 여세요: $($VideoBoxUri.AbsoluteUri)" -Evidence @{ opened = $false }
    Write-Result -Overall "blocked"
}

Write-Result -Overall "ready"
