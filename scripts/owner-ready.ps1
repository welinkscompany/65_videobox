[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet("Check", "Start", "Smoke", "Open", "OpenCapCut")]
    [string]$Mode = "Check",
    [switch]$Json,
    # 유진 기억을 Mem0에 연결한다 (owner 승인 2026-08-08, `§10.14` 조항 2-A).
    # 기본은 꺼짐 -- 켜면 대화 기억이 외부로 나가고, 게이트웨이가 죽으면
    # 폴백이 없어 과거 기억을 못 꺼낸다. 켤 때만 명시적으로 지정한다.
    [switch]$WithYujinMemory,
    [Uri]$VideoBoxUri = "http://127.0.0.1:5173/",
    [Uri]$HermesDashboardUri = "http://127.0.0.1:9119/",
    [ValidateRange(1, 180)]
    [int]$TimeoutSec = 30,
    [string]$EnvFile = "",
    [string]$PythonExecutable = "",
    [string]$DockerExecutable = "docker",
    [string]$GitExecutable = "git",
    [string]$NodeExecutable = "node",
    [string]$NpmExecutable = "npm",
    [string]$FfmpegExecutable = "ffmpeg",
    [string]$FfprobeExecutable = "ffprobe",
    [string]$LocalAppData = "",
    [string]$ReceiptRoot = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $repositoryRoot "compose.yaml"
$yujinMemoryComposeFile = Join-Path $repositoryRoot "compose.hermes-yujin.yaml"
# 기본 스택은 compose.yaml 하나다. -WithYujinMemory 를 줬을 때만 Mem0 경로를 얹는다.
$composeFileArguments = @("-f", $composeFile)
$composeProfileArguments = @()
if ($WithYujinMemory) {
    $composeFileArguments += @("-f", $yujinMemoryComposeFile)
    $composeProfileArguments = @("--profile", "hermes-yujin")
}
$exampleEnvFile = Join-Path $repositoryRoot ".env.container.example"
if ([string]::IsNullOrWhiteSpace($EnvFile)) {
    $EnvFile = Join-Path $repositoryRoot ".env.container"
}
if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
    $PythonExecutable = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
}
if ([string]::IsNullOrWhiteSpace($LocalAppData)) {
    $LocalAppData = [string]$env:LOCALAPPDATA
}
if ([string]::IsNullOrWhiteSpace($ReceiptRoot)) {
    $ReceiptRoot = Join-Path $repositoryRoot "artifacts\owner-ready"
}

function New-OwnerReadyResult {
    param(
        [string]$Id,
        [ValidateSet("pass", "blocked", "fail")]
        [string]$Status,
        [string]$Summary,
        [string]$Action,
        [hashtable]$Evidence = @{}
    )
    return [pscustomobject]@{
        id = $Id
        status = $Status
        summary = $Summary
        action = $Action
        evidence = $Evidence
    }
}

function Quote-ProcessArgument {
    param([string]$Value)
    if ($null -eq $Value) {
        return '""'
    }
    return '"' + $Value.Replace('"', '\"') + '"'
}

function Resolve-ProcessFilePath {
    param([string]$FilePath)
    if (Test-Path -LiteralPath $FilePath -PathType Leaf) {
        return (Resolve-Path -LiteralPath $FilePath).Path
    }
    if ([string]::IsNullOrWhiteSpace([IO.Path]::GetExtension($FilePath))) {
        foreach ($extension in @(".exe", ".cmd", ".bat")) {
            $candidate = "$FilePath$extension"
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                return (Resolve-Path -LiteralPath $candidate).Path
            }
            $resolvedCommand = Get-Command $candidate -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($null -ne $resolvedCommand) {
                return $resolvedCommand.Source
            }
        }
    }
    $command = Get-Command $FilePath -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $command) {
        return $command.Source
    }
    return $FilePath
}

function Invoke-CapturedProcess {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [int]$CommandTimeoutSec = $TimeoutSec
    )
    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = Resolve-ProcessFilePath -FilePath $FilePath
    $processInfo.Arguments = ($Arguments | ForEach-Object { Quote-ProcessArgument $_ }) -join " "
    $processInfo.WorkingDirectory = $repositoryRoot
    $processInfo.UseShellExecute = $false
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    $processInfo.CreateNoWindow = $true
    try {
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $processInfo
        if (-not $process.Start()) {
            return [pscustomobject]@{ ExitCode = 127; StdOut = "" }
        }
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($CommandTimeoutSec * 1000)) {
            if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
                try {
                    $taskKillInfo = New-Object System.Diagnostics.ProcessStartInfo
                    $taskKillInfo.FileName = Join-Path $env:SystemRoot "System32\taskkill.exe"
                    $taskKillInfo.Arguments = "/PID $($process.Id) /T /F"
                    $taskKillInfo.UseShellExecute = $false
                    $taskKillInfo.RedirectStandardOutput = $true
                    $taskKillInfo.RedirectStandardError = $true
                    $taskKillInfo.CreateNoWindow = $true
                    $taskKill = New-Object System.Diagnostics.Process
                    $taskKill.StartInfo = $taskKillInfo
                    if ($taskKill.Start()) {
                        if (-not $taskKill.WaitForExit(2000)) {
                            try { $taskKill.Kill() } catch { }
                        }
                    }
                    $taskKill.Dispose()
                }
                catch { }
            }
            try {
                if (-not $process.HasExited) { $process.Kill() }
            }
            catch { }
            try { [void]$process.WaitForExit(2000) } catch { }
            try { $process.StandardOutput.Dispose() } catch { }
            try { $process.StandardError.Dispose() } catch { }
            $process.Dispose()
            return [pscustomobject]@{ ExitCode = 124; StdOut = "" }
        }
        $stdout = [string]$stdoutTask.GetAwaiter().GetResult()
        [void]$stderrTask.GetAwaiter().GetResult()
        $exitCode = $process.ExitCode
        $process.Dispose()
        if ($stdout.Length -gt 4096) {
            $stdout = $stdout.Substring(0, 4096)
        }
        return [pscustomobject]@{ ExitCode = $exitCode; StdOut = $stdout }
    }
    catch {
        return [pscustomobject]@{ ExitCode = 127; StdOut = "" }
    }
}

function Test-ExactLoopbackRoot {
    param([Uri]$Uri)
    if ($null -eq $Uri -or $Uri.Scheme -notin @("http", "https")) {
        return $false
    }
    $hostName = $Uri.Host.ToLowerInvariant()
    return (
        $hostName -in @("127.0.0.1", "localhost", "::1", "[::1]") -and
        [string]::IsNullOrEmpty($Uri.UserInfo) -and
        $Uri.AbsolutePath -ceq "/" -and
        [string]::IsNullOrEmpty($Uri.Query) -and
        [string]::IsNullOrEmpty($Uri.Fragment)
    )
}

function Get-OverallStatus {
    param([object[]]$Checks)
    if (@($Checks | Where-Object { $_.status -ceq "fail" }).Count -gt 0) {
        return "fail"
    }
    if (@($Checks | Where-Object { $_.status -ceq "blocked" }).Count -gt 0) {
        return "blocked"
    }
    return "pass"
}

function Write-OwnerReadyPayload {
    param(
        [object[]]$Checks,
        [string]$PayloadMode = $Mode,
        [hashtable]$Extra = @{},
        [ValidateSet("", "pass", "blocked", "fail")]
        [string]$OverallStatusOverride = ""
    )
    $overall = if ([string]::IsNullOrEmpty($OverallStatusOverride)) {
        Get-OverallStatus -Checks $Checks
    }
    else {
        $OverallStatusOverride
    }
    $payload = [ordered]@{
        schema_version = "videobox-owner-ready-v1"
        mode = $PayloadMode
        overall_status = $overall
        generated_at = [DateTimeOffset]::UtcNow.ToString("o")
        external_provider_calls = 0
        checks = @($Checks)
    }
    foreach ($key in $Extra.Keys) {
        $payload[$key] = $Extra[$key]
    }
    if ($Json) {
        Write-Output ($payload | ConvertTo-Json -Depth 8 -Compress)
    }
    else {
        $title = switch ($overall) {
            "pass" { "바로 사용할 준비가 됐습니다." }
            "blocked" { "몇 가지 준비가 더 필요합니다." }
            default { "설정을 다시 확인해야 합니다." }
        }
        Write-Output "VideoBox owner-ready: $title"
        foreach ($check in $Checks) {
            Write-Output ("[{0}] {1} - {2}" -f $check.status.ToUpperInvariant(), $check.summary, $check.action)
        }
    }
    if ($overall -ceq "pass") { exit 0 }
    if ($overall -ceq "blocked") { exit 2 }
    exit 1
}

function Test-SmokeSuccessMarker {
    param([object]$Definition, [string]$StdOut)
    $lines = @(
        $StdOut -split "`r?`n" |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
    if (-not [string]::IsNullOrEmpty($Definition.ExactLine)) {
        return @($lines | Where-Object { $_ -ceq $Definition.ExactLine }).Count -eq 1
    }

    $prefix = [string]$Definition.MarkerPrefix
    $markerLines = @(
        $lines | Where-Object {
            $_.StartsWith("$prefix ", [StringComparison]::Ordinal)
        }
    )
    if ($markerLines.Count -ne 1) {
        return $false
    }
    $fieldText = $markerLines[0].Substring($prefix.Length + 1)
    $tokens = @($fieldText -split " ")
    $fields = @{}
    foreach ($token in $tokens) {
        if ($token -notmatch '^([a-z][a-z0-9_]*)=([a-z0-9_-]+)$') {
            return $false
        }
        $name = [string]$Matches[1]
        if ($fields.ContainsKey($name)) {
            return $false
        }
        $fields[$name] = [string]$Matches[2]
    }
    $expected = $Definition.ExpectedFields
    if ($fields.Count -ne $expected.Count) {
        return $false
    }
    foreach ($name in $expected.Keys) {
        if (-not $fields.ContainsKey($name) -or $fields[$name] -cne [string]$expected[$name]) {
            return $false
        }
    }
    return $true
}

function Get-ScriptSha256 {
    param([string]$LiteralPath)
    $hashStream = $null
    $sha256 = $null
    try {
        if (-not (Test-Path -LiteralPath $LiteralPath -PathType Leaf)) {
            return "unavailable"
        }
        $hashStream = [IO.File]::OpenRead($LiteralPath)
        $sha256 = [Security.Cryptography.SHA256]::Create()
        $hashBytes = $sha256.ComputeHash($hashStream)
        $hash = [BitConverter]::ToString($hashBytes).Replace("-", "").ToLowerInvariant()
        if ($hash -match '^[0-9a-f]{64}$') {
            return $hash
        }
    }
    catch { }
    finally {
        if ($null -ne $sha256) { $sha256.Dispose() }
        if ($null -ne $hashStream) { $hashStream.Dispose() }
    }
    return "unavailable"
}

function Test-UnescapedEnvInterpolation {
    param([string]$Value)
    for ($index = 0; $index -lt $Value.Length; $index++) {
        if ($Value.Substring($index, 1) -cne '$') {
            continue
        }
        if ($index + 1 -ge $Value.Length) {
            continue
        }
        $next = $Value.Substring($index + 1, 1)
        if ($next -ceq '$') {
            $index += 1
            continue
        }
        if ($next -ceq '{' -or $next -cmatch '^[A-Za-z_]$') {
            return $true
        }
    }
    return $false
}

function Write-ExclusiveReceiptTempFile {
    param(
        [string]$FinalPath,
        [string]$Content
    )

    $directory = [IO.Path]::GetDirectoryName($FinalPath)
    $leafName = [IO.Path]::GetFileName($FinalPath)
    for ($attempt = 0; $attempt -lt 4; $attempt++) {
        $candidate = Join-Path $directory "$leafName.$([Guid]::NewGuid().ToString('N')).tmp"
        $stream = $null
        try {
            $stream = [IO.File]::Open(
                $candidate,
                [IO.FileMode]::CreateNew,
                [IO.FileAccess]::Write,
                [IO.FileShare]::None
            )
        }
        catch [IO.IOException] {
            if ($attempt -eq 3) {
                throw
            }
            continue
        }

        $writeSucceeded = $false
        try {
            $encoding = New-Object System.Text.UTF8Encoding($false)
            $bytes = $encoding.GetBytes($Content)
            $stream.Write($bytes, 0, $bytes.Length)
            $stream.Flush($true)
            $writeSucceeded = $true
        }
        finally {
            if ($null -ne $stream) {
                $stream.Dispose()
            }
            if (-not $writeSucceeded) {
                Remove-Item -LiteralPath $candidate -Force -ErrorAction SilentlyContinue
            }
        }
        return $candidate
    }
}

function Get-HermesCredentialStatus {
    param([string]$LiteralPath)
    if (-not (Test-Path -LiteralPath $LiteralPath -PathType Leaf)) {
        return "missing"
    }

    $requiredKeys = @(
        "HERMES_YUJIN_GATEWAY_USERNAME",
        "HERMES_YUJIN_GATEWAY_PASSWORD",
        "HERMES_YUJIN_GATEWAY_PASSWORD_HASH",
        "VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN",
        "VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64",
        "VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64",
        "VIDEOBOX_HERMES_CAPABILITY_KEY_ID",
        "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN"
    )
    $placeholderSentinels = @(
        "replace-before-starting",
        "replace_before_starting",
        "replace_me",
        "placeholder",
        "change-me",
        "change_me",
        "changeme",
        "sentinel"
    )
    $counts = @{}
    foreach ($requiredKey in $requiredKeys) {
        $counts[$requiredKey] = 0
    }

    $stream = $null
    $reader = $null
    $invalid = $false
    try {
        $stream = [IO.File]::Open(
            $LiteralPath,
            [IO.FileMode]::Open,
            [IO.FileAccess]::Read,
            [IO.FileShare]::Read
        )
        if ($stream.Length -gt 65536) {
            return "invalid"
        }
        $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
        $reader = New-Object System.IO.StreamReader($stream, $strictUtf8, $false, 1024, $false)
        $charactersRead = 0
        $lineNumber = 0
        while ($null -ne ($line = $reader.ReadLine())) {
            $charactersRead += $line.Length + 1
            if ($charactersRead -gt 65536) {
                return "invalid"
            }
            if ($lineNumber -eq 0 -and $line.Length -gt 0 -and [int]$line[0] -eq 0xFEFF) {
                $line = $line.Substring(1)
            }
            $lineNumber += 1
            if ($line -cnotmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') {
                continue
            }
            $key = [string]$Matches[1]
            if ($requiredKeys -cnotcontains $key) {
                continue
            }
            $counts[$key] = [int]$counts[$key] + 1
            if ([int]$counts[$key] -ne 1) {
                $invalid = $true
                continue
            }

            $rawValue = [string]$Matches[2]
            if ($rawValue -match '[\p{Cc}]') {
                $invalid = $true
                continue
            }
            $trimmedStart = $rawValue.TrimStart()
            $value = ""
            $quoteMode = "unquoted"
            if ($trimmedStart.Length -gt 0 -and $trimmedStart.Substring(0, 1) -in @('"', "'")) {
                $quote = $trimmedStart.Substring(0, 1)
                $quoteMode = if ($quote -ceq "'") { "single" } else { "double" }
                $closingIndex = $trimmedStart.IndexOf($quote, 1, [StringComparison]::Ordinal)
                if ($closingIndex -lt 1) {
                    $invalid = $true
                    continue
                }
                $innerValue = $trimmedStart.Substring(1, $closingIndex - 1)
                $tail = $trimmedStart.Substring($closingIndex + 1)
                if (
                    $innerValue.IndexOf('"', [StringComparison]::Ordinal) -ge 0 -or
                    $innerValue.IndexOf("'", [StringComparison]::Ordinal) -ge 0 -or
                    $tail -notmatch '^\s*(?:#.*)?$'
                ) {
                    $invalid = $true
                    continue
                }
                $value = $innerValue.Trim()
            }
            else {
                if (
                    $rawValue.IndexOf('"', [StringComparison]::Ordinal) -ge 0 -or
                    $rawValue.IndexOf("'", [StringComparison]::Ordinal) -ge 0
                ) {
                    $invalid = $true
                    continue
                }
                $comment = [regex]::Match($rawValue, '\s+#.*$')
                if ($comment.Success) {
                    $rawValue = $rawValue.Substring(0, $comment.Index)
                }
                $value = $rawValue.Trim()
            }
            if (
                [string]::IsNullOrWhiteSpace($value) -or
                ($quoteMode -cne "single" -and (Test-UnescapedEnvInterpolation -Value $value))
            ) {
                $invalid = $true
                continue
            }
            foreach ($sentinel in $placeholderSentinels) {
                if ($value.IndexOf($sentinel, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                    $invalid = $true
                    break
                }
            }
        }
    }
    catch {
        return "invalid"
    }
    finally {
        if ($null -ne $reader) { $reader.Dispose() }
        elseif ($null -ne $stream) { $stream.Dispose() }
    }

    foreach ($requiredKey in $requiredKeys) {
        if ([int]$counts[$requiredKey] -ne 1) {
            return "invalid"
        }
    }
    if ($invalid) {
        return "invalid"
    }
    return "present_unverified"
}

function Get-WorkspaceChecks {
    $rootResult = Invoke-CapturedProcess -FilePath $GitExecutable -Arguments @("rev-parse", "--show-toplevel")
    $branchResult = Invoke-CapturedProcess -FilePath $GitExecutable -Arguments @("branch", "--show-current")
    $upstreamResult = Invoke-CapturedProcess -FilePath $GitExecutable -Arguments @(
        "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"
    )
    $branch = $branchResult.StdOut.Trim()
    $upstream = $upstreamResult.StdOut.Trim()
    $divergenceResult = if ($upstreamResult.ExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($upstream)) {
        Invoke-CapturedProcess -FilePath $GitExecutable -Arguments @(
            "rev-list", "--left-right", "--count", "HEAD...$upstream"
        )
    }
    else {
        [pscustomobject]@{ ExitCode = 1; StdOut = "" }
    }
    $expectedRoot = [IO.Path]::GetFullPath($repositoryRoot).TrimEnd('\', '/')
    $actualRoot = if ($rootResult.ExitCode -eq 0) {
        try { [IO.Path]::GetFullPath($rootResult.StdOut.Trim()).TrimEnd('\', '/') } catch { "" }
    }
    else { "" }
    $rootMatches = -not [string]::IsNullOrWhiteSpace($actualRoot) -and $actualRoot.Equals(
        $expectedRoot, [StringComparison]::OrdinalIgnoreCase
    )
    $branchAttached = $branchResult.ExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($branch) -and $branch -cne "HEAD"
    $matchingUpstream = $upstreamResult.ExitCode -eq 0 -and $branchAttached -and $upstream -ceq "origin/$branch"
    $parts = @($divergenceResult.StdOut.Trim() -split '\s+' | Where-Object { $_ -ne "" })
    $upstreamSynced = (
        $matchingUpstream -and $divergenceResult.ExitCode -eq 0 -and
        $parts.Count -eq 2 -and $parts[0] -ceq "0" -and $parts[1] -ceq "0"
    )
    $workspaceStatus = if ($rootMatches -and $branchAttached -and $upstreamSynced) { "pass" } else { "blocked" }
    $workspace = New-OwnerReadyResult -Id "workspace" -Status $workspaceStatus `
        -Summary $(if ($workspaceStatus -ceq "pass") { "현재 작업 위치와 원격 기준이 맞습니다." } else { "현재 작업 위치 또는 원격 기준을 맞춰야 합니다." }) `
        -Action $(if ($workspaceStatus -ceq "pass") { "추가 조치가 없습니다." } else { "지정된 VideoBox 브랜치와 upstream 동기화를 확인하세요." }) `
        -Evidence @{ branch_attached = [bool]$branchAttached; upstream_synced = [bool]$upstreamSynced }

    $statusResult = Invoke-CapturedProcess -FilePath $GitExecutable -Arguments @(
        "status", "--short", "--untracked-files=normal"
    )
    $protected = @(
        ".tmp-final-fence-debug/",
        ".tmp-real-video-dogfood/",
        "apps/web/.tmp-real-video-dogfood/"
    )
    $protectedCount = 0
    $otherCount = 0
    if ($statusResult.ExitCode -eq 0) {
        foreach ($line in ($statusResult.StdOut -split "`r?`n")) {
            if ([string]::IsNullOrWhiteSpace($line)) { continue }
            $normalized = if ($line.Length -ge 4) { $line.Substring(3).Trim().Replace('\', '/') } else { "" }
            if ($line.StartsWith("?? ") -and $normalized -in $protected) {
                $protectedCount += 1
            }
            else {
                $otherCount += 1
            }
        }
    }
    else {
        $otherCount = 1
    }
    $treeStatus = if ($otherCount -eq 0) { "pass" } else { "blocked" }
    $workingTree = New-OwnerReadyResult -Id "working_tree" -Status $treeStatus `
        -Summary $(if ($treeStatus -ceq "pass") { "보존할 진단 자료만 남아 있습니다." } else { "확인되지 않은 변경이 남아 있습니다." }) `
        -Action $(if ($treeStatus -ceq "pass") { "보호된 자료는 그대로 두세요." } else { "변경 내용을 확인하고 이번 작업 범위와 분리하세요." }) `
        -Evidence @{ protected_residue_count = $protectedCount; other_change_count = $otherCount }
    return @($workspace, $workingTree)
}

function Get-ToolCheck {
    param(
        [string]$Id,
        [string]$DisplayName,
        [string]$Executable,
        [string[]]$Arguments,
        [string]$VersionPattern
    )
    $result = Invoke-CapturedProcess -FilePath $Executable -Arguments $Arguments
    $match = if ($result.ExitCode -eq 0) { [regex]::Match($result.StdOut, $VersionPattern) } else { $null }
    if ($null -ne $match -and $match.Success) {
        return New-OwnerReadyResult -Id $Id -Status "pass" `
            -Summary "$DisplayName 도구를 사용할 수 있습니다." -Action "추가 조치가 없습니다." `
            -Evidence @{ available = $true; version = $match.Value.Trim() }
    }
    return New-OwnerReadyResult -Id $Id -Status "blocked" `
        -Summary "$DisplayName 도구를 찾거나 실행할 수 없습니다." `
        -Action "$DisplayName 설치와 PATH를 확인한 뒤 다시 진단하세요." `
        -Evidence @{ available = $false }
}

function Get-ComposeChecks {
    $docker = Get-ToolCheck -Id "docker" -DisplayName "Docker" -Executable $DockerExecutable `
        -Arguments @("version", "--format", "{{.Server.Version}}") -VersionPattern '[0-9]+\.[0-9]+(?:\.[0-9]+)?'
    $composeStatus = "blocked"
    if ($docker.status -ceq "pass" -and (Test-Path -LiteralPath $composeFile -PathType Leaf) -and (Test-Path -LiteralPath $exampleEnvFile -PathType Leaf)) {
        $composeResult = Invoke-CapturedProcess -FilePath $DockerExecutable -Arguments @(
            @("compose") + $composeFileArguments + @("--env-file", $exampleEnvFile) + $composeProfileArguments + @("config", "--quiet")
        )
        $composeStatus = if ($composeResult.ExitCode -eq 0) { "pass" } else { "fail" }
    }
    $compose = New-OwnerReadyResult -Id "compose" -Status $composeStatus `
        -Summary $(if ($composeStatus -ceq "pass") { "VideoBox 실행 구성을 읽을 수 있습니다." } elseif ($composeStatus -ceq "fail") { "VideoBox 실행 구성에 오류가 있습니다." } else { "VideoBox 실행 구성을 아직 확인할 수 없습니다." }) `
        -Action $(if ($composeStatus -ceq "pass") { "추가 조치가 없습니다." } elseif ($composeStatus -ceq "fail") { "compose.yaml과 예제 환경 설정을 확인하세요." } else { "Docker를 준비한 뒤 다시 진단하세요." }) `
        -Evidence @{ parsed = ($composeStatus -ceq "pass"); raw_config_recorded = $false }
    return @($docker, $compose)
}

function Get-DataRootChecks {
    $script:resolvedDataRoot = $null
    if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
        return @(
            (New-OwnerReadyResult -Id "container_env" -Status "blocked" `
                -Summary "로컬 실행 설정 파일이 아직 없습니다." `
                -Action ".env.container.example을 복사해 전용 데이터 폴더와 DB 설정을 입력하세요." `
                -Evidence @{ configured = $false }),
            (New-OwnerReadyResult -Id "data_root" -Status "blocked" `
                -Summary "VideoBox 데이터 폴더를 아직 확인할 수 없습니다." `
                -Action "로컬 실행 설정을 준비한 뒤 다시 진단하세요." `
                -Evidence @{ configured = $false; exists = $false; readable = $false }),
            (New-OwnerReadyResult -Id "path_headroom" -Status "blocked" `
                -Summary "Windows 경로 여유를 아직 계산할 수 없습니다." `
                -Action "로컬 실행 설정을 준비한 뒤 다시 진단하세요." `
                -Evidence @{ checked = $false })
        )
    }
    $dataRootValues = @()
    try {
        foreach ($line in [IO.File]::ReadLines((Resolve-Path -LiteralPath $EnvFile).Path)) {
            if ($line -match '^\s*VIDEOBOX_CONTAINER_DATA_ROOT\s*=\s*(.+?)\s*$') {
                $dataRootValues += $Matches[1]
            }
        }
    }
    catch { }
    if ($dataRootValues.Count -ne 1) {
        return @(
            (New-OwnerReadyResult -Id "container_env" -Status "fail" `
                -Summary "전용 데이터 폴더 설정을 하나로 확인할 수 없습니다." `
                -Action ".env.container의 VIDEOBOX_CONTAINER_DATA_ROOT 항목을 한 번만 설정하세요." `
                -Evidence @{ configured = $false }),
            (New-OwnerReadyResult -Id "data_root" -Status "blocked" `
                -Summary "VideoBox 데이터 폴더를 아직 확인할 수 없습니다." `
                -Action "데이터 폴더 설정을 고친 뒤 다시 진단하세요." `
                -Evidence @{ configured = $false; exists = $false; readable = $false }),
            (New-OwnerReadyResult -Id "path_headroom" -Status "blocked" `
                -Summary "Windows 경로 여유를 아직 계산할 수 없습니다." `
                -Action "데이터 폴더 설정을 고친 뒤 다시 진단하세요." `
                -Evidence @{ checked = $false })
        )
    }
    $rawPath = ([string]$dataRootValues[0]).Trim().Trim('"').Trim("'")
    $expandedPath = [Environment]::ExpandEnvironmentVariables($rawPath)
    $exists = Test-Path -LiteralPath $expandedPath -PathType Container
    $readable = $false
    $attributes = "unknown"
    $runtimeExists = $false
    $snapshotExists = $false
    if ($exists) {
        try {
            $script:resolvedDataRoot = (Resolve-Path -LiteralPath $expandedPath).Path
            $item = Get-Item -LiteralPath $script:resolvedDataRoot -Force
            $attributes = [string]$item.Attributes
            [void]([IO.Directory]::EnumerateFileSystemEntries($script:resolvedDataRoot).GetEnumerator().MoveNext())
            $readable = $true
            $runtimeExists = Test-Path -LiteralPath (Join-Path $script:resolvedDataRoot "runtime") -PathType Container
            $snapshotExists = Test-Path -LiteralPath (Join-Path $script:resolvedDataRoot "snapshot") -PathType Container
        }
        catch { $readable = $false }
    }
    $envCheck = New-OwnerReadyResult -Id "container_env" -Status "pass" `
        -Summary "로컬 실행 설정 파일이 준비돼 있습니다." -Action "추가 조치가 없습니다." `
        -Evidence @{ configured = $true; secret_values_recorded = $false }
    $dataStatus = if ($exists -and $readable -and $runtimeExists -and $snapshotExists) { "pass" } else { "blocked" }
    $data = New-OwnerReadyResult -Id "data_root" -Status $dataStatus `
        -Summary $(if ($dataStatus -ceq "pass") { "VideoBox 데이터 폴더를 읽을 수 있습니다." } else { "VideoBox 데이터 폴더 준비가 더 필요합니다." }) `
        -Action $(if ($dataStatus -ceq "pass") { "쓰기 검사는 하지 않았습니다. 실제 시작은 Start 모드에서만 진행하세요." } else { "전용 폴더의 runtime과 snapshot을 확인하세요." }) `
        -Evidence @{ configured = $true; exists = [bool]$exists; readable = [bool]$readable; attributes = $attributes; runtime_exists = [bool]$runtimeExists; snapshot_exists = [bool]$snapshotExists; write_probe_performed = $false }
    if ($null -eq $script:resolvedDataRoot) {
        $headroom = New-OwnerReadyResult -Id "path_headroom" -Status "blocked" `
            -Summary "Windows 경로 여유를 아직 계산할 수 없습니다." `
            -Action "데이터 폴더를 준비한 뒤 다시 진단하세요." -Evidence @{ checked = $false }
    }
    else {
        $reserve = "\runtime\projects\00000000-0000-0000-0000-000000000000\cache\browser\000000000000\000000000000000000000000.mp4"
        $remaining = 259 - ($script:resolvedDataRoot.Length + $reserve.Length)
        $headroomStatus = if ($remaining -ge 20) { "pass" } else { "blocked" }
        $headroom = New-OwnerReadyResult -Id "path_headroom" -Status $headroomStatus `
            -Summary $(if ($headroomStatus -ceq "pass") { "Windows 미리보기 경로 여유가 있습니다." } else { "Windows 미리보기 경로가 너무 길어질 수 있습니다." }) `
            -Action $(if ($headroomStatus -ceq "pass") { "추가 조치가 없습니다." } else { "드라이브 바로 아래처럼 더 짧은 전용 데이터 폴더를 사용하세요." }) `
            -Evidence @{ checked = $true; reserved_suffix_length = $reserve.Length; remaining_characters = $remaining; minimum_required = 20 }
    }
    return @($envCheck, $data, $headroom)
}

function Test-AllowedLoopbackLoginRedirect {
    param([Uri]$SourceUri, [System.Net.Http.HttpResponseMessage]$Response)
    if ([int]$Response.StatusCode -ne 302 -or $null -eq $Response.Headers.Location) {
        return $false
    }
    try {
        $target = [Uri]::new($SourceUri, $Response.Headers.Location)
        return (
            $target.Scheme -ceq $SourceUri.Scheme -and
            $target.Host.Equals($SourceUri.Host, [StringComparison]::OrdinalIgnoreCase) -and
            $target.Port -eq $SourceUri.Port -and
            [string]::IsNullOrEmpty($target.UserInfo) -and
            $target.AbsolutePath -ceq "/login" -and
            [string]::IsNullOrEmpty($target.Fragment)
        )
    }
    catch {
        return $false
    }
}

function Get-ConnectionUnavailableReason {
    param([Exception]$Exception)
    $current = $Exception
    while ($null -ne $current) {
        if ($current -is [System.Net.Sockets.SocketException]) {
            if (
                $current.SocketErrorCode -eq [System.Net.Sockets.SocketError]::ConnectionRefused -or
                $current.NativeErrorCode -eq 10061
            ) {
                return "connection_refused"
            }
            if ($current.SocketErrorCode -in @(
                [System.Net.Sockets.SocketError]::ConnectionReset,
                [System.Net.Sockets.SocketError]::HostDown,
                [System.Net.Sockets.SocketError]::HostNotFound,
                [System.Net.Sockets.SocketError]::NetworkDown,
                [System.Net.Sockets.SocketError]::NetworkUnreachable,
                [System.Net.Sockets.SocketError]::TimedOut
            )) {
                return "connection_unavailable"
            }
        }
        $current = $current.InnerException
    }
    return "request_invalid"
}

function Get-ConnectionProbeFailure {
    param([Exception]$Exception)
    $reason = Get-ConnectionUnavailableReason -Exception $Exception
    $state = if ($reason -in @("connection_refused", "connection_unavailable")) { "blocked" } else { "fail" }
    return [pscustomobject]@{ State = $state; Reason = $reason }
}

function Invoke-LoopbackProbe {
    param([Uri]$Uri, [switch]$AcceptLoginRedirectAsReachable, [switch]$RequireHealthJson)
    Add-Type -AssemblyName System.Net.Http
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.AllowAutoRedirect = $false
    $handler.UseProxy = $false
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [System.Threading.Timeout]::InfiniteTimeSpan
    $request = New-Object System.Net.Http.HttpRequestMessage([System.Net.Http.HttpMethod]::Get, $Uri)
    $cancellation = New-Object System.Threading.CancellationTokenSource
    $cancellation.CancelAfter([TimeSpan]::FromSeconds($TimeoutSec))
    $response = $null
    try {
        $response = $client.SendAsync(
            $request,
            [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead,
            $cancellation.Token
        ).GetAwaiter().GetResult()
        $statusCode = [int]$response.StatusCode
        $length = $response.Content.Headers.ContentLength
        if ($statusCode -ge 300 -and $statusCode -lt 400) {
            $allowedRedirect = $AcceptLoginRedirectAsReachable -and (Test-AllowedLoopbackLoginRedirect -SourceUri $Uri -Response $response)
            return [pscustomobject]@{
                State = $(if ($allowedRedirect) { "pass" } else { "fail" })
                StatusCode = $statusCode
                Reason = $(if ($allowedRedirect) { "login_redirect" } else { "redirect_rejected" })
            }
        }
        if ($null -ne $length -and [long]$length -gt 65536) {
            return [pscustomobject]@{ State = "fail"; StatusCode = $statusCode; Reason = "response_oversize" }
        }
        if ($statusCode -ne 200) {
            return [pscustomobject]@{ State = "fail"; StatusCode = $statusCode; Reason = "status_rejected" }
        }
        $stream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $buffer = New-Object byte[] 4096
        $body = New-Object System.IO.MemoryStream
        $totalBytes = 0
        try {
            while ($true) {
                $read = $stream.ReadAsync($buffer, 0, $buffer.Length, $cancellation.Token).GetAwaiter().GetResult()
                if ($read -eq 0) { break }
                $totalBytes += $read
                if ($totalBytes -gt 65536) {
                    return [pscustomobject]@{ State = "fail"; StatusCode = $statusCode; Reason = "response_oversize" }
                }
                if ($RequireHealthJson) {
                    $body.Write($buffer, 0, $read)
                }
            }
            if ($RequireHealthJson) {
                try {
                    $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
                    $bodyText = $strictUtf8.GetString($body.ToArray())
                    $health = $bodyText | ConvertFrom-Json -ErrorAction Stop
                    if ($null -eq $health -or [string]$health.status -cne "ok") {
                        return [pscustomobject]@{ State = "fail"; StatusCode = $statusCode; Reason = "body_invalid" }
                    }
                }
                catch {
                    return [pscustomobject]@{ State = "fail"; StatusCode = $statusCode; Reason = "body_invalid" }
                }
            }
        }
        finally {
            $body.Dispose()
            $stream.Dispose()
        }
        return [pscustomobject]@{ State = "pass"; StatusCode = $statusCode; Reason = "http_200" }
    }
    catch [System.Threading.Tasks.TaskCanceledException] {
        return [pscustomobject]@{ State = "blocked"; StatusCode = 0; Reason = "timeout" }
    }
    catch [System.OperationCanceledException] {
        return [pscustomobject]@{ State = "blocked"; StatusCode = 0; Reason = "timeout" }
    }
    catch {
        $failure = Get-ConnectionProbeFailure -Exception $_.Exception
        return [pscustomobject]@{
            State = $failure.State
            StatusCode = 0
            Reason = $failure.Reason
        }
    }
    finally {
        if ($null -ne $response) { $response.Dispose() }
        $cancellation.Dispose()
        $request.Dispose()
        $client.Dispose()
        $handler.Dispose()
    }
}

function Get-LoopbackCheck {
    param([string]$Id, [string]$DisplayName, [Uri]$Uri, [switch]$AcceptLoginRedirectAsReachable, [switch]$RequireHealthJson)
    $probe = Invoke-LoopbackProbe -Uri $Uri -AcceptLoginRedirectAsReachable:$AcceptLoginRedirectAsReachable -RequireHealthJson:$RequireHealthJson
    return New-OwnerReadyResult -Id $Id -Status $probe.State `
        -Summary $(if ($probe.State -ceq "pass") { "$DisplayName 주소에 연결할 수 있습니다." } elseif ($probe.State -ceq "blocked") { "$DisplayName 서비스가 아직 꺼져 있습니다." } else { "$DisplayName 응답을 안전하게 확인할 수 없습니다." }) `
        -Action $(if ($probe.State -ceq "pass") { "추가 조치가 없습니다." } elseif ($probe.State -ceq "blocked") { "필요하면 명시적으로 Start 모드를 실행한 뒤 다시 확인하세요." } else { "로컬 서비스 주소와 응답 상태를 확인하세요." }) `
        -Evidence @{ reachable = ($probe.State -ceq "pass"); status_code = $probe.StatusCode; probe_reason = $probe.Reason; redirects_followed = 0; external_request_count = 0 }
}

function Get-CapCutCheck {
    $appsRoot = if ([string]::IsNullOrWhiteSpace($LocalAppData)) { $null } else { Join-Path $LocalAppData "CapCut\Apps" }
    $candidates = @()
    if ($null -ne $appsRoot -and (Test-Path -LiteralPath $appsRoot -PathType Container)) {
        try { $candidates = @(Get-ChildItem -LiteralPath $appsRoot -Filter "CapCut.exe" -File -Recurse -ErrorAction Stop) } catch { $candidates = @() }
    }
    $selected = $null
    $version = $null
    foreach ($candidate in $candidates) {
        $candidateVersion = $candidate.Directory.Name
        if ($candidateVersion -notmatch '^\d+(?:\.\d+)+$') { continue }
        if ($null -eq $selected) {
            $selected = $candidate
            $version = $candidateVersion
            continue
        }
        try {
            if ([version]$candidateVersion -gt [version]$version) {
                $selected = $candidate
                $version = $candidateVersion
            }
        }
        catch { }
    }
    $projectRootExists = if ([string]::IsNullOrWhiteSpace($LocalAppData)) { $false } else {
        Test-Path -LiteralPath (Join-Path $LocalAppData "CapCut\User Data\Projects\com.lveditor.draft") -PathType Container
    }
    $ready = $null -ne $selected -and $projectRootExists
    $script:capCutExecutable = if ($null -ne $selected) { $selected.FullName } else { $null }
    return New-OwnerReadyResult -Id "capcut" -Status $(if ($ready) { "pass" } else { "blocked" }) `
        -Summary $(if ($ready) { "CapCut 설치와 프로젝트 폴더를 찾았습니다." } else { "CapCut 설치 또는 프로젝트 폴더를 더 확인해야 합니다." }) `
        -Action $(if ($ready) { "OpenCapCut 모드에서만 앱을 열 수 있습니다." } else { "CapCut을 설치하고 한 번 실행한 뒤 다시 진단하세요." }) `
        -Evidence @{ installed = ($null -ne $selected); version = $version; project_root_exists = [bool]$projectRootExists; write_probe_performed = $false }
}

if (-not (Test-ExactLoopbackRoot -Uri $VideoBoxUri) -or -not (Test-ExactLoopbackRoot -Uri $HermesDashboardUri)) {
    Write-OwnerReadyPayload -Checks @(
        (New-OwnerReadyResult -Id "network_boundary" -Status "fail" `
            -Summary "로컬 주소 설정을 확인할 수 없습니다." `
            -Action "VideoBox와 Hermes 주소를 127.0.0.1의 기본 주소로 되돌린 뒤 다시 확인하세요." `
            -Evidence @{ external_request_count = 0 })
    )
}

if ($Mode -ceq "Check") {
    $checks = @()
    $checks += @(Get-WorkspaceChecks)
    $checks += Get-ToolCheck -Id "python" -DisplayName "Python" -Executable $PythonExecutable -Arguments @("--version") -VersionPattern 'Python\s+[0-9]+\.[0-9]+(?:\.[0-9]+)?'
    $checks += Get-ToolCheck -Id "node" -DisplayName "Node" -Executable $NodeExecutable -Arguments @("--version") -VersionPattern 'v[0-9]+\.[0-9]+(?:\.[0-9]+)?'
    $checks += Get-ToolCheck -Id "npm" -DisplayName "npm" -Executable $NpmExecutable -Arguments @("--version") -VersionPattern '[0-9]+\.[0-9]+(?:\.[0-9]+)?'
    $checks += Get-ToolCheck -Id "ffmpeg" -DisplayName "FFmpeg" -Executable $FfmpegExecutable -Arguments @("-version") -VersionPattern 'ffmpeg\s+version\s+[^\s]+'
    $checks += Get-ToolCheck -Id "ffprobe" -DisplayName "ffprobe" -Executable $FfprobeExecutable -Arguments @("-version") -VersionPattern 'ffprobe\s+version\s+[^\s]+'
    $checks += @(Get-ComposeChecks)
    $checks += @(Get-DataRootChecks)
    $videoHealthUri = [Uri]::new($VideoBoxUri, "/health")
    $checks += Get-LoopbackCheck -Id "videobox_health" -DisplayName "VideoBox" -Uri $videoHealthUri -RequireHealthJson
    $checks += Get-LoopbackCheck -Id "hermes_dashboard" -DisplayName "Hermes 대시보드" -Uri $HermesDashboardUri -AcceptLoginRedirectAsReachable
    $checks += Get-CapCutCheck
    Write-OwnerReadyPayload -Checks $checks
}

if ($Mode -ceq "Start") {
    $checks = @()
    $checks += @(Get-ComposeChecks)
    $checks += @(Get-DataRootChecks)
    $preflightStatus = Get-OverallStatus -Checks $checks
    if ($preflightStatus -cne "pass") {
        Write-OwnerReadyPayload -Checks $checks
    }
    $actualComposeResult = Invoke-CapturedProcess -FilePath $DockerExecutable -Arguments @(
        @("compose") + $composeFileArguments + @("--env-file", $EnvFile) + $composeProfileArguments + @("config", "--quiet")
    )
    $actualComposeStatus = if ($actualComposeResult.ExitCode -eq 0) { "pass" } else { "fail" }
    $checks += New-OwnerReadyResult -Id "start_compose" -Status $actualComposeStatus `
        -Summary $(if ($actualComposeStatus -ceq "pass") { "현재 로컬 실행 설정을 안전하게 읽었습니다." } else { "현재 로컬 실행 설정에 오류가 있습니다." }) `
        -Action $(if ($actualComposeStatus -ceq "pass") { "추가 조치가 없습니다." } else { ".env.container의 필수 항목을 확인한 뒤 다시 실행하세요." }) `
        -Evidence @{ parsed = ($actualComposeStatus -ceq "pass"); raw_config_recorded = $false }
    if ($actualComposeStatus -cne "pass") {
        Write-OwnerReadyPayload -Checks $checks
    }
    $serviceNames = @("videobox-postgres", "videobox-workspace")
    if ($WithYujinMemory) {
        # 게이트웨이가 유진 에이전트와 메모리 어댑터에 의존한다.
        $serviceNames += @("videobox-hermes-yujin", "videobox-hermes-memory-adapter", "videobox-agent-gateway")
    }
    if ($PSBoundParameters.ContainsKey("WhatIf")) {
        $checks += New-OwnerReadyResult -Id "start" -Status "pass" `
            -Summary "VideoBox 시작 대상을 안전하게 확인했습니다." `
            -Action "실제로 시작하려면 -WhatIf 없이 Start 모드를 다시 실행하세요." `
            -Evidence @{ started = $false; services = $serviceNames; what_if = $true }
        Write-OwnerReadyPayload -Checks $checks
    }
    if (-not $PSCmdlet.ShouldProcess("local VideoBox services", "start")) {
        $checks += New-OwnerReadyResult -Id "start" -Status "blocked" `
            -Summary "VideoBox 시작이 취소됐습니다." `
            -Action "준비가 되면 Start 모드를 다시 실행하세요." `
            -Evidence @{ started = $false; services = $serviceNames }
        Write-OwnerReadyPayload -Checks $checks
    }
    if ($WithYujinMemory) {
        # 프로필이 이미지 안에 없다. 설치를 건너뛰면 유진 컨테이너가
        # "Profile 'videobox-yujin' does not exist" 로 즉시 종료하고
        # 게이트웨이까지 연쇄로 못 뜬다. 설치는 여러 번 실행해도 안전하다.
        & (Join-Path $PSScriptRoot "install-hermes-yujin-profile.ps1") `
            -EnvFile $EnvFile `
            -ComposeFile $composeFile `
            -OverlayFile $yujinMemoryComposeFile `
            -DockerExecutable $DockerExecutable
        if ($LASTEXITCODE -ne 0) {
            $checks += New-OwnerReadyResult -Id "start" -Status "fail" `
                -Summary "유진 기억 프로필을 설치하지 못했습니다." `
                -Action "Docker Desktop 상태를 확인한 뒤 다시 실행하세요." `
                -Evidence @{ started = $false; services = $serviceNames; profile_installed = $false }
            Write-OwnerReadyPayload -Checks $checks
        }
    }
    $upResult = Invoke-CapturedProcess -FilePath $DockerExecutable -CommandTimeoutSec $TimeoutSec -Arguments @(
        @("compose") + $composeFileArguments + @("--env-file", $EnvFile) + $composeProfileArguments + @("up", "-d") + $serviceNames
    )
    if ($upResult.ExitCode -ne 0) {
        $checks += New-OwnerReadyResult -Id "start" -Status "fail" `
            -Summary "VideoBox 서비스를 시작하지 못했습니다." `
            -Action "Docker Desktop과 compose 상태를 확인한 뒤 다시 실행하세요." `
            -Evidence @{ started = $false; services = $serviceNames; health_status_code = 0 }
        Write-OwnerReadyPayload -Checks $checks
    }
    $healthUri = [Uri]::new($VideoBoxUri, "/health")
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSec)
    $health = [pscustomobject]@{ State = "blocked"; StatusCode = 0 }
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        $health = Invoke-LoopbackProbe -Uri $healthUri -RequireHealthJson
        if ($health.State -ceq "pass" -or $health.State -ceq "fail") { break }
        Start-Sleep -Milliseconds 250
    }
    if ($health.State -ceq "pass") {
        $checks += New-OwnerReadyResult -Id "start" -Status "pass" `
            -Summary "VideoBox가 시작됐고 화면 연결 준비가 끝났습니다." `
            -Action "Open 모드로 VideoBox 화면을 열 수 있습니다." `
            -Evidence @{ started = $true; services = $serviceNames; health_status_code = $health.StatusCode }
    }
    else {
        $checks += New-OwnerReadyResult -Id "start" -Status "fail" `
            -Summary "VideoBox 시작 명령은 끝났지만 연결 준비를 확인하지 못했습니다." `
            -Action "Docker 상태를 확인하고 잠시 뒤 Check를 다시 실행하세요." `
            -Evidence @{ started = $true; services = $serviceNames; health_status_code = $health.StatusCode }
    }
    Write-OwnerReadyPayload -Checks $checks
}

if ($Mode -ceq "Smoke") {
    $powerShellExecutable = (Get-Process -Id $PID).Path
    $startHeadResult = Invoke-CapturedProcess -FilePath $GitExecutable -Arguments @("rev-parse", "HEAD")
    $startCommit = $startHeadResult.StdOut.Trim().ToLowerInvariant()
    $startCommitValid = (
        $startHeadResult.ExitCode -eq 0 -and
        $startCommit -match '^(?:[0-9a-f]{40}|[0-9a-f]{64})$'
    )
    $baselineCommit = if ($startCommitValid) { $startCommit } else { "0000000000000000000000000000000000000000" }
    $commit = if ($startCommitValid) { $startCommit } else { "unknown" }
    $shortCommit = if ($startCommitValid) { $startCommit.Substring(0, 8) } else { "unknown" }
    $definitions = @(
        [pscustomobject]@{
            Id = "creator_flow_non_live"
            File = "smoke-hermes-yujin-creator-flow.ps1"
            Arguments = @()
            ReceiptMode = "non_live"
            PublicMarker = "creator_non_live_pass"
            MarkerPrefix = "HERMES_YUJIN_CREATOR_NON_LIVE_PASS"
            ExactLine = ""
            ExpectedFields = [ordered]@{
                sse_completed = "true"
                proposal_ready = "true"
                session_file_bound = "true"
                mutation_before_apply = "0"
                session_revision_delta = "1"
                caption_changes = "1"
                playback_manifest_checked = "true"
                output_readiness_checked = "true"
                output_jobs = "0"
                external_provider_calls = "0"
            }
        },
        [pscustomobject]@{
            Id = "chat_non_live"
            File = "smoke-hermes-yujin-chat.ps1"
            Arguments = @()
            ReceiptMode = "non_live"
            PublicMarker = "chat_non_live_zero_calls"
            MarkerPrefix = "HERMES_YUJIN_CANARY_NON_LIVE"
            ExactLine = ""
            ExpectedFields = [ordered]@{
                network_calls = "0"
                proposal_calls = "0"
                provider_body_recorded = "false"
            }
        },
        [pscustomobject]@{
            Id = "mem0_non_live"
            File = "smoke-hermes-yujin-mem0.ps1"
            Arguments = @()
            ReceiptMode = "non_live"
            PublicMarker = "mem0_non_live_zero_calls"
            MarkerPrefix = "HERMES_YUJIN_MEM0_NON_LIVE"
            ExactLine = ""
            ExpectedFields = [ordered]@{
                network_calls = "0"
                provider_calls = "0"
                credentials_printed = "false"
            }
        },
        [pscustomobject]@{
            Id = "plan_state"
            File = "verify-hermes-yujin-plan-state.ps1"
            Arguments = @()
            ReceiptMode = "non_live"
            PublicMarker = "plan_state_verified"
            MarkerPrefix = ""
            ExactLine = "Hermes Yujin plan state verified: 20 unique master task IDs; all 20 occur exactly once across four children; statuses and progress agree."
            ExpectedFields = [ordered]@{}
        },
        [pscustomobject]@{
            Id = "profile_static"
            File = "verify-hermes-yujin-profile.ps1"
            Arguments = @("-StaticOnly")
            ReceiptMode = "static_only"
            PublicMarker = "profile_static_verified"
            MarkerPrefix = ""
            ExactLine = "Hermes Yujin profile ownership and secret-free contents verified."
            ExpectedFields = [ordered]@{}
        },
        [pscustomobject]@{
            Id = "runtime_static"
            File = "verify-hermes-yujin-runtime.ps1"
            Arguments = @("-StaticOnly")
            ReceiptMode = "static_only"
            PublicMarker = "runtime_static_verified"
            MarkerPrefix = ""
            ExactLine = "Hermes Yujin D2 static topology verified: exact chat, gateway, and optional memory adapter boundaries."
            ExpectedFields = [ordered]@{}
        }
    )
    $checks = @()
    $receiptChecks = @()
    foreach ($definition in $definitions) {
        $scriptPath = Join-Path $PSScriptRoot $definition.File
        $relativeScriptPath = "scripts/$($definition.File)"
        $exitCode = 127
        $stdout = ""
        $preScriptSha256 = Get-ScriptSha256 -LiteralPath $scriptPath
        $preTrackedResult = Invoke-CapturedProcess -FilePath $GitExecutable -Arguments @(
            "ls-files", "--error-unmatch", "--", $relativeScriptPath
        )
        $preUnchangedResult = Invoke-CapturedProcess -FilePath $GitExecutable -Arguments @(
            "diff", "--quiet", $baselineCommit, "--", $relativeScriptPath
        )
        $preTrackedAndUnchanged = (
            $startCommitValid -and
            $preTrackedResult.ExitCode -eq 0 -and
            $preUnchangedResult.ExitCode -eq 0
        )
        if (Test-Path -LiteralPath $scriptPath -PathType Leaf) {
            $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $scriptPath)
            $arguments += @($definition.Arguments)
            $child = Invoke-CapturedProcess -FilePath $powerShellExecutable -Arguments $arguments -CommandTimeoutSec $TimeoutSec
            $exitCode = $child.ExitCode
            $stdout = $child.StdOut
        }
        $postScriptSha256 = Get-ScriptSha256 -LiteralPath $scriptPath
        $postTrackedResult = Invoke-CapturedProcess -FilePath $GitExecutable -Arguments @(
            "ls-files", "--error-unmatch", "--", $relativeScriptPath
        )
        $postUnchangedResult = Invoke-CapturedProcess -FilePath $GitExecutable -Arguments @(
            "diff", "--quiet", $baselineCommit, "--", $relativeScriptPath
        )
        $postTrackedAndUnchanged = (
            $startCommitValid -and
            $postTrackedResult.ExitCode -eq 0 -and
            $postUnchangedResult.ExitCode -eq 0
        )
        $markerValid = Test-SmokeSuccessMarker -Definition $definition -StdOut $stdout
        $status = if (
            $exitCode -eq 0 -and
            $markerValid -and
            $preScriptSha256 -ne "unavailable" -and
            $preScriptSha256 -ceq $postScriptSha256 -and
            $preTrackedAndUnchanged -and
            $postTrackedAndUnchanged
        ) { "pass" } else { "fail" }
        $action = if ($status -ceq "pass") { "추가 조치가 없습니다." } else { "해당 검증기를 따로 실행해 고정 오류 코드를 확인하세요." }
        $checks += New-OwnerReadyResult -Id $definition.Id -Status $status `
            -Summary $(if ($status -ceq "pass") { "로컬 검증 항목을 확인했습니다." } else { "로컬 검증 항목을 확인하지 못했습니다." }) `
            -Action $action `
            -Evidence @{ live = $false; static_only = ($definition.Arguments -contains "-StaticOnly"); raw_output_recorded = $false }
        $receiptChecks += [ordered]@{
            id = $definition.Id
            mode = $definition.ReceiptMode
            status = $status
            marker = $(if ($status -ceq "pass") { $definition.PublicMarker } else { "invalid" })
            script_sha256 = $preScriptSha256
            action = $action
        }
    }
    $dashboardProbe = Invoke-LoopbackProbe -Uri $HermesDashboardUri -AcceptLoginRedirectAsReachable
    $dashboardStatus = if ($dashboardProbe.State -ceq "pass") {
        "ready"
    }
    elseif ($dashboardProbe.State -ceq "blocked" -and $dashboardProbe.Reason -ceq "connection_refused") {
        "not_running"
    }
    else {
        "invalid"
    }
    $credentialStatus = Get-HermesCredentialStatus -LiteralPath $EnvFile
    $finalHeadResult = Invoke-CapturedProcess -FilePath $GitExecutable -Arguments @("rev-parse", "HEAD")
    $finalHead = $finalHeadResult.StdOut.Trim().ToLowerInvariant()
    $headStable = (
        $startCommitValid -and
        $finalHeadResult.ExitCode -eq 0 -and
        $finalHead -ceq $startCommit
    )
    for ($index = 0; $index -lt $definitions.Count; $index++) {
        $definition = $definitions[$index]
        $scriptPath = Join-Path $PSScriptRoot $definition.File
        $relativeScriptPath = "scripts/$($definition.File)"
        $currentScriptSha256 = Get-ScriptSha256 -LiteralPath $scriptPath
        $currentTrackedResult = Invoke-CapturedProcess -FilePath $GitExecutable -Arguments @(
            "ls-files", "--error-unmatch", "--", $relativeScriptPath
        )
        $currentUnchangedResult = Invoke-CapturedProcess -FilePath $GitExecutable -Arguments @(
            "diff", "--quiet", $baselineCommit, "--", $relativeScriptPath
        )
        $currentEvidenceValid = (
            $headStable -and
            $currentTrackedResult.ExitCode -eq 0 -and
            $currentUnchangedResult.ExitCode -eq 0 -and
            $currentScriptSha256 -ne "unavailable" -and
            $currentScriptSha256 -ceq [string]$receiptChecks[$index]["script_sha256"]
        )
        if (-not $currentEvidenceValid) {
            $checks[$index].status = "fail"
            $checks[$index].summary = "로컬 검증 항목을 확인하지 못했습니다."
            $checks[$index].action = "해당 검증기를 따로 실행해 고정 오류 코드를 확인하세요."
            $receiptChecks[$index]["status"] = "fail"
            $receiptChecks[$index]["marker"] = "invalid"
            $receiptChecks[$index]["action"] = "해당 검증기를 따로 실행해 고정 오류 코드를 확인하세요."
        }
    }
    $staticNonLiveChecksPassed = @($checks | Where-Object { $_.status -cne "pass" }).Count -eq 0
    $readinessStatus = if (-not $staticNonLiveChecksPassed) {
        "not_ready"
    }
    elseif ($dashboardStatus -ceq "invalid") {
        "not_ready"
    }
    elseif ($credentialStatus -in @("missing", "invalid")) {
        "credential_blocked"
    }
    elseif ($dashboardStatus -cne "ready") {
        "not_ready"
    }
    else {
        "local_ready"
    }
    $overallStatus = if ($readinessStatus -ceq "local_ready") {
        "pass"
    }
    elseif ($readinessStatus -ceq "credential_blocked") {
        "blocked"
    }
    else {
        "fail"
    }
    $receiptPayload = [ordered]@{
        schema_version = "videobox-hermes-readiness-v1"
        mode = "Smoke"
        readiness_status = $readinessStatus
        static_non_live_checks_passed = $staticNonLiveChecksPassed
        dashboard_status = $dashboardStatus
        credential_status = $credentialStatus
        live_canary_status = "not_run"
        generated_at = [DateTimeOffset]::UtcNow.ToString("o")
        commit = $commit
        external_provider_calls = 0
        external_network_calls = 0
        checks = $receiptChecks
    }
    $timestamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMdd'T'HHmmssfff'Z'")
    $fileName = "owner-ready-smoke-$timestamp-$shortCommit.json"
    $temporaryPath = $null
    $receiptWritten = $false
    try {
        [IO.Directory]::CreateDirectory($ReceiptRoot) | Out-Null
        $finalPath = Join-Path $ReceiptRoot $fileName
        $receiptText = $receiptPayload | ConvertTo-Json -Depth 8 -Compress
        $temporaryPath = Write-ExclusiveReceiptTempFile -FinalPath $finalPath -Content $receiptText
        $publishHeadResult = Invoke-CapturedProcess -FilePath $GitExecutable -Arguments @("rev-parse", "HEAD")
        $publishHead = $publishHeadResult.StdOut.Trim().ToLowerInvariant()
        $publishHeadStable = (
            $startCommitValid -and
            $publishHeadResult.ExitCode -eq 0 -and
            $publishHead -ceq $startCommit
        )
        for ($index = 0; $index -lt $definitions.Count; $index++) {
            $definition = $definitions[$index]
            $scriptPath = Join-Path $PSScriptRoot $definition.File
            $relativeScriptPath = "scripts/$($definition.File)"
            $publishScriptSha256 = Get-ScriptSha256 -LiteralPath $scriptPath
            $publishTrackedResult = Invoke-CapturedProcess -FilePath $GitExecutable -Arguments @(
                "ls-files", "--error-unmatch", "--", $relativeScriptPath
            )
            $publishUnchangedResult = Invoke-CapturedProcess -FilePath $GitExecutable -Arguments @(
                "diff", "--quiet", $baselineCommit, "--", $relativeScriptPath
            )
            $publishEvidenceValid = (
                $publishHeadStable -and
                $publishTrackedResult.ExitCode -eq 0 -and
                $publishUnchangedResult.ExitCode -eq 0 -and
                $publishScriptSha256 -ne "unavailable" -and
                $publishScriptSha256 -ceq [string]$receiptChecks[$index]["script_sha256"]
            )
            if (-not $publishEvidenceValid) {
                $checks[$index].status = "fail"
                $checks[$index].summary = "로컬 검증 항목을 확인하지 못했습니다."
                $checks[$index].action = "해당 검증기를 따로 실행해 고정 오류 코드를 확인하세요."
                $receiptChecks[$index]["status"] = "fail"
                $receiptChecks[$index]["marker"] = "invalid"
                $receiptChecks[$index]["action"] = "해당 검증기를 따로 실행해 고정 오류 코드를 확인하세요."
            }
        }
        if (-not $publishHeadStable -or @($checks | Where-Object { $_.status -cne "pass" }).Count -gt 0) {
            $staticNonLiveChecksPassed = $false
            $readinessStatus = "not_ready"
            $overallStatus = "fail"
            $receiptPayload["readiness_status"] = $readinessStatus
            $receiptPayload["static_non_live_checks_passed"] = $staticNonLiveChecksPassed
            $receiptPayload["checks"] = $receiptChecks
            $receiptText = $receiptPayload | ConvertTo-Json -Depth 8 -Compress
            [IO.File]::WriteAllText($temporaryPath, $receiptText, (New-Object System.Text.UTF8Encoding($false)))
        }
        [IO.File]::Move($temporaryPath, $finalPath)
        $receiptWritten = $true
    }
    catch {
        if ($null -ne $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
        }
        $checks += New-OwnerReadyResult -Id "receipt" -Status "fail" `
            -Summary "검증 결과 파일을 안전하게 저장하지 못했습니다." `
            -Action "artifacts 폴더의 디스크 공간과 권한을 확인하세요." `
            -Evidence @{ written = $false }
    }
    if (-not $receiptWritten) {
        $readinessStatus = "not_ready"
        $overallStatus = "fail"
    }
    Write-OwnerReadyPayload -Checks $checks -OverallStatusOverride $overallStatus -Extra @{
        readiness_status = $readinessStatus
        static_non_live_checks_passed = $staticNonLiveChecksPassed
        dashboard_status = $dashboardStatus
        credential_status = $credentialStatus
        live_canary_status = "not_run"
        external_network_calls = 0
        receipt = @{ written = $receiptWritten; file_name = $(if ($receiptWritten) { $fileName } else { $null }) }
    }
}

if ($Mode -ceq "Open") {
    $checks = @()
    if ($PSBoundParameters.ContainsKey("WhatIf")) {
        $checks += New-OwnerReadyResult -Id "open" -Status "pass" `
            -Summary "VideoBox 화면을 열 대상을 안전하게 확인했습니다." `
            -Action "실제로 열려면 -WhatIf 없이 Open 모드를 다시 실행하세요." `
            -Evidence @{ opened = $false; target = "videobox_loopback"; what_if = $true }
        Write-OwnerReadyPayload -Checks $checks
    }
    try {
        if ($PSCmdlet.ShouldProcess("VideoBox loopback page", "open")) {
            Start-Process -FilePath $VideoBoxUri.AbsoluteUri
            $checks += New-OwnerReadyResult -Id "open" -Status "pass" `
                -Summary "VideoBox 화면 열기를 요청했습니다." `
                -Action "브라우저에서 프로젝트를 선택하세요." `
                -Evidence @{ opened = $true; target = "videobox_loopback" }
        }
        else {
            $checks += New-OwnerReadyResult -Id "open" -Status "blocked" `
                -Summary "VideoBox 화면 열기가 취소됐습니다." `
                -Action "준비가 되면 Open 모드를 다시 실행하세요." `
                -Evidence @{ opened = $false; target = "videobox_loopback" }
        }
    }
    catch {
        $checks += New-OwnerReadyResult -Id "open" -Status "fail" `
            -Summary "VideoBox 화면을 열지 못했습니다." `
            -Action "기본 브라우저 설정을 확인한 뒤 다시 실행하세요." `
            -Evidence @{ opened = $false; target = "videobox_loopback" }
    }
    Write-OwnerReadyPayload -Checks $checks
}

if ($Mode -ceq "OpenCapCut") {
    $checks = @()
    $capCutCheck = Get-CapCutCheck
    $checks += $capCutCheck
    if ($capCutCheck.status -cne "pass") {
        Write-OwnerReadyPayload -Checks $checks
    }
    if ($PSBoundParameters.ContainsKey("WhatIf")) {
        $checks = @(
            (New-OwnerReadyResult -Id "open" -Status "pass" `
                -Summary "CapCut을 열 대상을 안전하게 확인했습니다." `
                -Action "실제로 열려면 -WhatIf 없이 OpenCapCut 모드를 다시 실행하세요." `
                -Evidence @{ opened = $false; target = "capcut"; arguments = 0; what_if = $true })
        )
        Write-OwnerReadyPayload -Checks $checks
    }
    try {
        if ($PSCmdlet.ShouldProcess("CapCut application", "open")) {
            Start-Process -FilePath $script:capCutExecutable
            $checks = @(
                (New-OwnerReadyResult -Id "open" -Status "pass" `
                    -Summary "CapCut 열기를 요청했습니다." `
                    -Action "프로젝트 선택은 CapCut 화면에서 직접 진행하세요." `
                    -Evidence @{ opened = $true; target = "capcut"; arguments = 0 })
            )
        }
        else {
            $checks = @(
                (New-OwnerReadyResult -Id "open" -Status "blocked" `
                    -Summary "CapCut 열기가 취소됐습니다." `
                    -Action "준비가 되면 OpenCapCut 모드를 다시 실행하세요." `
                    -Evidence @{ opened = $false; target = "capcut"; arguments = 0 })
            )
        }
    }
    catch {
        $checks = @(
            (New-OwnerReadyResult -Id "open" -Status "fail" `
                -Summary "CapCut을 열지 못했습니다." `
                -Action "CapCut 설치 상태를 확인한 뒤 다시 실행하세요." `
                -Evidence @{ opened = $false; target = "capcut"; arguments = 0 })
        )
    }
    Write-OwnerReadyPayload -Checks $checks
}

Write-OwnerReadyPayload -Checks @(
    (New-OwnerReadyResult -Id "mode" -Status "fail" `
        -Summary "선택한 실행 모드는 아직 준비되지 않았습니다." `
        -Action "기본 Check 모드로 현재 상태를 먼저 확인하세요." `
        -Evidence @{ requested_mode = $Mode })
)
