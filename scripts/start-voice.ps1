<#
.SYNOPSIS
    내 목소리로 더빙할 수 있게 목소리 프로그램을 켠다.

.DESCRIPTION
    목소리를 복제하는 엔진은 컨테이너가 아니라 **이 컴퓨터**에 깔려 있다
    (그림 생성이 ComfyUI를 이 컴퓨터에서 부르는 것과 같다). 이 스크립트는
    깔려 있는 것 중 나은 것을 골라 켠다.

      1) .venv-chatterbox  -- chatterbox, MIT. 상업적으로 써도 된다.
      2) .venv             -- XTTS, 비상업용. chatterbox가 없을 때만.

    둘은 한 환경에 못 넣는다(chatterbox가 torch를 내려 XTTS를 깨뜨린다).
    그래서 환경을 나눠 두고 여기서 고른다.

    켠 뒤에는 VideoBox를 `VIDEOBOX_TTS_ENGINE=host_bridge`로 띄우면
    편집기의 `목소리 더빙`이 내 목소리로 읽는다.
#>
[CmdletBinding()]
param(
    # `chatterbox`(MIT)나 `local_xtts`(비상업용)를 손으로 고르고 싶을 때.
    [ValidateSet('auto', 'chatterbox', 'local_xtts')]
    [string]$Engine = 'auto'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
# 목소리 엔진은 **저장소 루트**에 깔려 있다. worktree의 .venv에는 없다 --
# 이걸 헷갈려서 "설치가 필요하다"고 잘못 판단한 적이 있다(2026-09-02).
$installRoot = if (Test-Path (Join-Path $repoRoot '.venv-chatterbox')) { $repoRoot }
               elseif (Test-Path (Join-Path (Split-Path -Parent (Split-Path -Parent $repoRoot)) '.venv-chatterbox')) {
                   Split-Path -Parent (Split-Path -Parent $repoRoot)
               } else { $repoRoot }

$chatterbox = Join-Path $installRoot '.venv-chatterbox\Scripts\python.exe'
$xtts       = Join-Path $installRoot '.venv\Scripts\python.exe'

switch ($Engine) {
    'chatterbox' { $python = $chatterbox; $chosen = 'chatterbox' }
    'local_xtts' { $python = $xtts;       $chosen = 'local_xtts' }
    default {
        if (Test-Path $chatterbox) { $python = $chatterbox; $chosen = 'chatterbox' }
        else                       { $python = $xtts;       $chosen = 'local_xtts' }
    }
}

if (-not (Test-Path $python)) {
    Write-Host "목소리 프로그램을 찾지 못했습니다: $python" -ForegroundColor Red
    Write-Host "먼저 아래를 실행해 주세요:" -ForegroundColor Yellow
    Write-Host "  python -m venv .venv-chatterbox"
    Write-Host "  .venv-chatterbox\Scripts\python -m pip install chatterbox-tts `"setuptools<81`""
    exit 1
}

$licence = if ($chosen -eq 'chatterbox') { 'MIT (상업적으로 써도 됩니다)' } else { '비상업용' }
Write-Host "목소리 엔진: $chosen · 라이선스: $licence"
Write-Host "이 창을 열어 둔 채로 VideoBox에서 `목소리 더빙`을 눌러 주세요."

$env:VIDEOBOX_HOST_TTS_ENGINE = $chosen
# XTTS는 첫 실행에 라이선스 동의를 물어 멈춘다. 미리 동의를 표시해 둔다.
$env:COQUI_TOS_AGREED = '1'
& $python (Join-Path $PSScriptRoot 'host_tts_service.py')
