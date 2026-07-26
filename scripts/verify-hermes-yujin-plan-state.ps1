[CmdletBinding()]
param(
    [string]$RepositoryRoot
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Split-Path -Parent $PSScriptRoot
}

$masterPlan = "docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-master-plan.md"
$childPlans = @(
    "docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-runtime-chat-vertical-slice.md"
    "docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-creator-tools.md"
    "docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-realtime-reliability.md"
    "docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-mem0-memory.md"
)
$planPaths = @($masterPlan) + $childPlans
$expectedTaskIds = @(
    "P0-1", "P0-2",
    "A1", "A2", "A3", "A4",
    "B1", "B2", "B3", "B4", "B5",
    "C1", "C2", "C3", "C4",
    "D1", "D2", "D3", "D4",
    "F1"
)
$taskPattern = '^- \[( |~|x|!)\] \*\*(P0-[12]|A[1-4]|B[1-5]|C[1-4]|D[1-4]|F1)\*\*'
$taskLikePattern = '^- \[( |~|x|!)\] \*\*([A-Za-z0-9-]+)\*\*'
$placeholderPattern = '(?i)\b(TODO|TBD|FIXME|XXX)\b|\[(?:PLACEHOLDER|FILL[ -]?IN)\]|\{\{[^}\r\n]+\}\}'
$errors = [System.Collections.Generic.List[string]]::new()
$states = @{}

function Add-VerificationError {
    param([string]$Message)
    $errors.Add($Message)
}

function Get-ExpectedPercent {
    param(
        [int]$Numerator,
        [int]$Denominator
    )
    return [math]::Round(
        (100.0 * $Numerator) / $Denominator,
        1,
        [MidpointRounding]::AwayFromZero
    )
}

function Test-ReportedProgress {
    param(
        [string]$RelativePath,
        [string[]]$Lines,
        [object[]]$Tasks,
        [bool]$IsMaster
    )

    $progressPattern = if ($IsMaster) {
        '^Current initiative progress: \*\*(\d+)/(\d+) \((\d+\.\d)%\), remaining (\d+\.\d)%\*\*\.'
    }
    else {
        '^Child progress: \*\*(\d+)/(\d+) tasks \((\d+\.\d)%\), remaining (\d+\.\d)%\*\*\.'
    }
    $progressMatches = @($Lines | Where-Object { $_ -match $progressPattern })
    if ($progressMatches.Count -ne 1) {
        Add-VerificationError "$RelativePath progress line count is $($progressMatches.Count); expected 1."
        return
    }

    $match = [regex]::Match($progressMatches[0], $progressPattern)
    $reportedNumerator = [int]$match.Groups[1].Value
    $reportedDenominator = [int]$match.Groups[2].Value
    $reportedPercent = [double]::Parse(
        $match.Groups[3].Value,
        [Globalization.CultureInfo]::InvariantCulture
    )
    $reportedRemaining = [double]::Parse(
        $match.Groups[4].Value,
        [Globalization.CultureInfo]::InvariantCulture
    )
    $completedCount = @($Tasks | Where-Object { $_.Status -eq "x" }).Count
    $expectedDenominator = if ($IsMaster) { 20 } else { $Tasks.Count }

    if ($reportedNumerator -ne $completedCount) {
        Add-VerificationError (
            "$RelativePath completed numerator is $reportedNumerator; " +
            "[x] count is $completedCount."
        )
    }
    if ($reportedDenominator -ne $expectedDenominator) {
        Add-VerificationError (
            "$RelativePath denominator is $reportedDenominator; " +
            "expected $expectedDenominator."
        )
    }
    if ($expectedDenominator -gt 0) {
        $expectedPercent = Get-ExpectedPercent $completedCount $expectedDenominator
        $expectedRemaining = Get-ExpectedPercent (
            $expectedDenominator - $completedCount
        ) $expectedDenominator
        if ([math]::Abs($reportedPercent - $expectedPercent) -gt 0.001) {
            Add-VerificationError (
                "$RelativePath completed percentage is $reportedPercent%; " +
                "expected $expectedPercent%."
            )
        }
        if ([math]::Abs($reportedRemaining - $expectedRemaining) -gt 0.001) {
            Add-VerificationError (
                "$RelativePath remaining percentage is $reportedRemaining%; " +
                "expected $expectedRemaining%."
            )
        }
    }
}

foreach ($relativePath in $planPaths) {
    $fullPath = Join-Path $RepositoryRoot $relativePath
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        Add-VerificationError "Missing required plan: $relativePath"
        $states[$relativePath] = [pscustomobject]@{
            Lines = @()
            Tasks = @()
        }
        continue
    }

    $lines = [IO.File]::ReadAllLines($fullPath)
    $tasks = [System.Collections.Generic.List[object]]::new()
    for ($index = 0; $index -lt $lines.Count; $index++) {
        $line = $lines[$index]
        if ($line -match $placeholderPattern) {
            $marker = [regex]::Match($line, $placeholderPattern).Value
            Add-VerificationError (
                "${relativePath}:$($index + 1) unfinished placeholder marker '$marker'."
            )
        }
        if ($line -match $taskPattern) {
            $tasks.Add([pscustomobject]@{
                Id = $Matches[2]
                Status = $Matches[1]
                Path = $relativePath
            })
        }
        elseif ($line -match $taskLikePattern) {
            Add-VerificationError (
                "${relativePath}:$($index + 1) unexpected task ID $($Matches[2])."
            )
        }
    }
    $states[$relativePath] = [pscustomobject]@{
        Lines = $lines
        Tasks = @($tasks)
    }
}

$masterTasks = @($states[$masterPlan].Tasks)
$masterGroups = @($masterTasks | Group-Object Id)
foreach ($group in $masterGroups | Where-Object { $_.Count -gt 1 }) {
    Add-VerificationError "Master duplicate task ID $($group.Name) occurs $($group.Count) times."
}

$masterIds = @($masterGroups.Name)
$missingMasterIds = @($expectedTaskIds | Where-Object { $_ -notin $masterIds })
$unexpectedMasterIds = @($masterIds | Where-Object { $_ -notin $expectedTaskIds })
if ($missingMasterIds.Count -gt 0) {
    Add-VerificationError "Master missing task IDs: $($missingMasterIds -join ', ')."
}
if ($unexpectedMasterIds.Count -gt 0) {
    Add-VerificationError "Master unexpected task IDs: $($unexpectedMasterIds -join ', ')."
}
if ($masterTasks.Count -ne 20 -or $masterIds.Count -ne 20) {
    Add-VerificationError (
        "Master must contain exactly 20 unique task IDs; " +
        "found $($masterTasks.Count) task lines and $($masterIds.Count) unique IDs."
    )
}

$childTasks = @(
    foreach ($childPlan in $childPlans) {
        $states[$childPlan].Tasks
    }
)
$childGroups = @($childTasks | Group-Object Id)
$childIds = @($childGroups.Name)
foreach ($expectedTaskId in $expectedTaskIds) {
    $matchingGroup = @($childGroups | Where-Object { $_.Name -eq $expectedTaskId })
    $childCount = if ($matchingGroup.Count -eq 1) { $matchingGroup[0].Count } else { 0 }
    if ($childCount -ne 1) {
        Add-VerificationError (
            "Child task ID $expectedTaskId must occur exactly once; found $childCount."
        )
    }
}
$unexpectedChildIds = @($childIds | Where-Object { $_ -notin $expectedTaskIds })
if ($unexpectedChildIds.Count -gt 0) {
    Add-VerificationError "Children contain unexpected task IDs: $($unexpectedChildIds -join ', ')."
}

foreach ($expectedTaskId in $expectedTaskIds) {
    $masterTask = @($masterTasks | Where-Object { $_.Id -eq $expectedTaskId })
    $childTask = @($childTasks | Where-Object { $_.Id -eq $expectedTaskId })
    if ($masterTask.Count -eq 1 -and $childTask.Count -eq 1) {
        if ($masterTask[0].Status -ne $childTask[0].Status) {
            Add-VerificationError (
                "Task $expectedTaskId status mismatch: " +
                "master=[$($masterTask[0].Status)], child=[$($childTask[0].Status)]."
            )
        }
    }
}

Test-ReportedProgress `
    -RelativePath $masterPlan `
    -Lines $states[$masterPlan].Lines `
    -Tasks $masterTasks `
    -IsMaster $true
foreach ($childPlan in $childPlans) {
    Test-ReportedProgress `
        -RelativePath $childPlan `
        -Lines $states[$childPlan].Lines `
        -Tasks @($states[$childPlan].Tasks) `
        -IsMaster $false
}

if ($errors.Count -gt 0) {
    foreach ($verificationError in $errors) {
        [Console]::Error.WriteLine("ERROR: $verificationError")
    }
    exit 1
}

Write-Output (
    "Hermes Yujin plan state verified: 20 unique master task IDs; " +
    "all 20 occur exactly once across four children; statuses and progress agree."
)
exit 0
