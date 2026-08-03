param(
    [string]$SourcePath
)

$RepoRoot = Split-Path -Parent $PSScriptRoot
$PythonBinary = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Verifier = Join-Path $PSScriptRoot "verify_task23a_browser_preview.py"

if (-not (Test-Path -LiteralPath $PythonBinary -PathType Leaf)) {
    throw "VideoBox virtual environment Python was not found."
}

$Arguments = @($Verifier, "--json")
if ($SourcePath) {
    $ResolvedSource = (Resolve-Path -LiteralPath $SourcePath -ErrorAction Stop).Path
    $Arguments += @("--source", $ResolvedSource)
}

& $PythonBinary @Arguments
if ($LASTEXITCODE -ne 0) {
    throw "Task 23A browser preview verification failed."
}
