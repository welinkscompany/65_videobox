<#
.SYNOPSIS
    바탕화면에 VideoBox 바로가기를 만든다.

.DESCRIPTION
    설치형(Tauri) 대신 고른 길이다. 설치형이 주는 것은 "두 번 클릭해서 켜는
    편함" 하나인데, 그걸 얻으려면 코드 서명 인증서를 사야 하고(연 단위 갱신)
    그래도 Windows Smart App Control이 막을 수 있다(2026-08-31 실측).
    바로가기는 그 편함을 인증서 없이 준다.

    `pwsh`를 창 숨김으로 부르지 않는다 -- 처음 켤 때는 몇 분이 걸리고,
    창이 없으면 창작자는 눌렸는지도 모른 채 계속 누른다.
#>
[CmdletBinding()]
param(
    [string]$Name = 'VideoBox'
)

$ErrorActionPreference = 'Stop'
$scriptRoot = $PSScriptRoot
$starter = Join-Path $scriptRoot 'start-videobox.ps1'
if (-not (Test-Path $starter)) { throw "시작 스크립트를 찾지 못했습니다: $starter" }

$pwshPath = (Get-Command pwsh -ErrorAction SilentlyContinue)?.Source
if (-not $pwshPath) { $pwshPath = (Get-Command powershell).Source }

$desktop = [Environment]::GetFolderPath('Desktop')
$linkPath = Join-Path $desktop "$Name.lnk"

$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($linkPath)
$link.TargetPath = $pwshPath
$link.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$starter`""
# 작업 폴더를 저장소로 둔다 -- owner-ready.ps1이 상대 경로를 쓴다.
$link.WorkingDirectory = Split-Path -Parent $scriptRoot
$link.Description = 'VideoBox를 켜고 화면을 엽니다'
$link.WindowStyle = 1
# 아이콘은 pwsh 것을 그대로 쓴다. 전용 아이콘은 아직 임시라 넣지 않는다.
$link.IconLocation = "$pwshPath,0"
$link.Save()

Write-Host "바탕화면에 '$Name' 바로가기를 만들었습니다." -ForegroundColor Green
Write-Host "위치: $linkPath"
