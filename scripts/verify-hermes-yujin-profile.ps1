[CmdletBinding()]
param(
    [switch]$StaticOnly,
    [string]$ProfileRoot
)

$ErrorActionPreference = "Stop"
if (-not $StaticOnly) {
    throw "Yujin profile verification supports -StaticOnly only."
}
if ([string]::IsNullOrWhiteSpace($ProfileRoot)) {
    $ProfileRoot = Join-Path (Split-Path -Parent $PSScriptRoot) "config/hermes/yujin"
}
if (-not (Test-Path -LiteralPath $ProfileRoot -PathType Container)) {
    throw "The Yujin profile source is missing."
}

$resolvedRoot = (Resolve-Path -LiteralPath $ProfileRoot).Path
$rootItem = Get-Item -LiteralPath $resolvedRoot -Force
if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw "The Yujin profile source must not be a reparse point."
}

$items = @(Get-ChildItem -LiteralPath $resolvedRoot -Recurse -Force)
foreach ($item in $items) {
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "The Yujin profile source contains an unsafe reparse point."
    }
}

$manifestPath = Join-Path $resolvedRoot "distribution.yaml"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "The Yujin distribution manifest is missing."
}
$expectedManifest = @'
name: videobox-yujin
version: 1.0.0
hermes_requires: ">=0.18.0"
distribution_owned:
  - SOUL.md
  - config.yaml
  - skills/
'@
$actualManifest = [IO.File]::ReadAllText($manifestPath).Replace("`r`n", "`n").Trim()
if ($actualManifest -cne $expectedManifest.Replace("`r`n", "`n").Trim()) {
    throw "The Yujin distribution manifest does not match the pinned contract."
}

$requiredFiles = @(
    "distribution.yaml"
    "SOUL.md"
    "config.yaml"
    "skills/videobox-editor/SKILL.md"
)
foreach ($relativePath in $requiredFiles) {
    $candidate = Join-Path $resolvedRoot $relativePath
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "The Yujin distribution is missing a required owned file."
    }
}

$executableExtensions = @(
    ".bat", ".cmd", ".com", ".dll", ".exe", ".jar", ".js", ".msi",
    ".ps1", ".py", ".sh", ".vbs"
)
$secretPatterns = @(
    '(?i)\bapi[\s_-]*key\b|\bsk-[A-Za-z0-9_-]{8,}'
    '(?i)\b(?:oauth|access_token|refresh_token|bearer)\b'
    '(?i)\b(?:password|passwd|비밀번호)\b'
    '(?i)\bmem0(?:[\s_-]*api[\s_-]*key)?\b'
    '(?im)(?:^|[\s"''=:])(?:[A-Za-z]:[\\/]|\\\\)'
    '(?im)(?:^|[\s"''=:])/(?:home|users)/'
)

$files = @($items | Where-Object { -not $_.PSIsContainer })
foreach ($file in $files) {
    $relativePath = $file.FullName.Substring($resolvedRoot.Length).TrimStart('\', '/').Replace('\', '/')
    $isDeclared = (
        $relativePath -ceq "distribution.yaml" -or
        $relativePath -ceq "SOUL.md" -or
        $relativePath -ceq "config.yaml" -or
        $relativePath.StartsWith("skills/", [StringComparison]::Ordinal)
    )
    if (-not $isDeclared -or $relativePath.Contains("../") -or $relativePath.Contains("..\")) {
        throw "The Yujin distribution contains a file outside declared ownership."
    }
    if ($executableExtensions -contains $file.Extension) {
        throw "The Yujin distribution contains an undeclared executable file."
    }

    $content = [IO.File]::ReadAllText($file.FullName)
    foreach ($pattern in $secretPatterns) {
        if ($content -match $pattern) {
            throw "The Yujin distribution contains forbidden sensitive or local-path material."
        }
    }
}

Write-Output "Hermes Yujin profile ownership and secret-free contents verified."
