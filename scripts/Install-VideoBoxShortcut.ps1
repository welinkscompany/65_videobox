<#
.SYNOPSIS
바탕화면에 VideoBox 바로가기를 만든다.

.DESCRIPTION
한 번만 실행하면 된다. 그 뒤로는 바탕화면 아이콘을 두 번 눌러 VideoBox를 켠다.
바로가기는 `VideoBox.cmd`를 가리키고, 실제 순서는 `scripts/Start-VideoBox.ps1`에 있다.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$ShortcutDirectory = "",
    [string]$ShortcutName = "VideoBox.lnk",
    [switch]$Json
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $repositoryRoot "VideoBox.cmd"
if ([string]::IsNullOrWhiteSpace($ShortcutDirectory)) {
    $ShortcutDirectory = [Environment]::GetFolderPath("Desktop")
}
$shortcutPath = Join-Path $ShortcutDirectory $ShortcutName

function Write-Result {
    param([string]$Status, [string]$Summary, [hashtable]$Evidence = @{})
    if ($Json) {
        [pscustomobject]@{ script = "Install-VideoBoxShortcut"; status = $Status; summary = $Summary; shortcut = $shortcutPath; target = $launcher; evidence = $Evidence } | ConvertTo-Json -Depth 5
    }
    else {
        Write-Host $Summary
    }
    exit $(if ($Status -ceq "pass") { 0 } else { 2 })
}

if (-not (Test-Path -LiteralPath $launcher)) {
    Write-Result -Status "fail" -Summary "켜는 파일을 찾지 못했어요: $launcher" -Evidence @{ launcher_found = $false }
}
if (-not (Test-Path -LiteralPath $ShortcutDirectory)) {
    Write-Result -Status "fail" -Summary "바로가기를 놓을 곳을 찾지 못했어요: $ShortcutDirectory" -Evidence @{ directory_found = $false }
}
if ($PSBoundParameters.ContainsKey("WhatIf")) {
    Write-Result -Status "pass" -Summary "만들 바로가기를 확인만 했어요: $shortcutPath" -Evidence @{ created = $false; what_if = $true }
}
if (-not $PSCmdlet.ShouldProcess($shortcutPath, "create shortcut")) {
    Write-Result -Status "fail" -Summary "바로가기 만들기가 취소됐어요." -Evidence @{ created = $false }
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcher
$shortcut.WorkingDirectory = $repositoryRoot
$shortcut.Description = "VideoBox 켜기"
# 창을 최소화해서 띄운다. owner가 볼 것은 검은 콘솔이 아니라 VideoBox 창이다.
$shortcut.WindowStyle = 7
$shortcut.Save()

Write-Result -Status "pass" -Summary "바탕화면에 VideoBox 아이콘을 만들었어요. 두 번 누르면 켜져요." -Evidence @{ created = $true }
