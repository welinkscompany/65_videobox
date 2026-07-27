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

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$pythonExecutable = Join-Path $repositoryRoot ".venv/Scripts/python.exe"
$contentVerifier = Join-Path $PSScriptRoot "verify_hermes_yujin_profile_content.py"
if (
    -not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf) -or
    -not (Test-Path -LiteralPath $contentVerifier -PathType Leaf)
) {
    throw "The canonical Yujin profile content verifier is unavailable."
}
& $pythonExecutable $contentVerifier $resolvedRoot
if ($LASTEXITCODE -ne 0) {
    throw "The Yujin distribution content failed strict static verification."
}

$manifestPath = Join-Path $resolvedRoot "distribution.yaml"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "The Yujin distribution manifest is missing."
}
$expectedManifest = @'
name: videobox-yujin
version: 1.1.0
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
    "skills/videobox-creator/SKILL.md"
)
foreach ($relativePath in $requiredFiles) {
    $candidate = Join-Path $resolvedRoot $relativePath
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "The Yujin distribution is missing a required owned file."
    }
}

$allowedContentExtensions = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::OrdinalIgnoreCase
)
foreach ($extension in @(
    ".md", ".yaml", ".yml"
)) {
    [void]$allowedContentExtensions.Add($extension)
}

function Test-IsDisallowedContentPayload {
    param(
        [IO.FileInfo]$File,
        [byte[]]$Bytes
    )

    if (-not $allowedContentExtensions.Contains($File.Extension)) {
        return $true
    }
    if (
        $Bytes.Length -ge 2 -and
        $Bytes[0] -eq 0x23 -and
        $Bytes[1] -eq 0x21
    ) {
        return $true
    }
    if ($Bytes.Length -ge 2 -and $Bytes[0] -eq 0x4D -and $Bytes[1] -eq 0x5A) {
        return $true
    }
    if (
        $Bytes.Length -ge 4 -and
        $Bytes[0] -eq 0x7F -and
        $Bytes[1] -eq 0x45 -and
        $Bytes[2] -eq 0x4C -and
        $Bytes[3] -eq 0x46
    ) {
        return $true
    }
    return $false
}

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
    $bytes = [IO.File]::ReadAllBytes($file.FullName)
    if (Test-IsDisallowedContentPayload -File $file -Bytes $bytes) {
        throw "The Yujin distribution contains a disallowed content type or executable payload."
    }
}

Write-Output "Hermes Yujin profile ownership and secret-free contents verified."
