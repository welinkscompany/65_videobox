<#
.SYNOPSIS
    VideoBox를 켜고 화면을 연다. 바탕화면 바로가기가 이걸 부른다.

.DESCRIPTION
    한 번 눌러 끝나게 하는 것이 목적이다. 순서는 이렇다.

      1) VideoBox 컨테이너를 켠다 (`owner-ready.ps1 -Mode Start`)
      2) 목소리 프로그램을 켠다 (있으면. 없으면 조용히 건너뛴다)
      3) 브라우저로 화면을 연다

    **목소리 프로그램이 없어도 멈추지 않는다.** 자막·편집·완성본은 목소리
    없이도 다 되고, 더빙만 "목소리 프로그램을 켜 주세요"라고 말한다.
    켜는 데 실패했다고 VideoBox까지 못 쓰게 만들 이유가 없다.

    설치형(Tauri) 대신 이 길을 고른 이유는 `docs/decisions/`에 있다 --
    설치형이 주는 것은 "두 번 클릭"뿐인데 코드 서명 인증서가 필요하고
    Windows Smart App Control이 여전히 막을 수 있다.
#>
[CmdletBinding()]
param(
    # 목소리 프로그램을 안 켜고 VideoBox만 켠다.
    [switch]$SkipVoice
)

$ErrorActionPreference = 'Stop'
$scriptRoot = $PSScriptRoot
$ownerReady = Join-Path $scriptRoot 'owner-ready.ps1'

Write-Host 'VideoBox를 켜는 중입니다. 처음 한 번은 조금 걸립니다.' -ForegroundColor Cyan
& $ownerReady -Mode Start
if ($LASTEXITCODE -ne 0) {
    Write-Host 'VideoBox를 켜지 못했습니다. 위의 안내를 읽어 주세요.' -ForegroundColor Red
    Read-Host '엔터를 누르면 닫힙니다'
    exit 1
}

if (-not $SkipVoice) {
    # 이미 켜져 있으면 또 켜지 않는다 -- 두 번 켜면 8199 포트를 다투다 죽는다.
    $alive = $false
    try {
        $probe = Invoke-WebRequest -Uri 'http://127.0.0.1:8199/health' -TimeoutSec 3 -UseBasicParsing
        $alive = $probe.StatusCode -eq 200
    } catch { $alive = $false }

    if ($alive) {
        Write-Host '목소리 프로그램이 이미 켜져 있습니다.'
    } else {
        $voice = Join-Path $scriptRoot 'start-voice.ps1'
        if (Test-Path $voice) {
            Write-Host '목소리 프로그램을 켭니다(내 목소리 더빙용). 이 창은 켜 둔 채로 두세요.'
            # 별도 창으로 띄운다. 여기서 붙들면 브라우저를 못 연다.
            Start-Process -FilePath 'pwsh' -ArgumentList @('-NoExit', '-NoProfile', '-File', $voice) | Out-Null
        }
    }
}

Write-Host 'VideoBox 화면을 엽니다.' -ForegroundColor Cyan
& $ownerReady -Mode Open
