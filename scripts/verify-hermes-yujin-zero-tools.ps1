[CmdletBinding()]
param(
    [string]$DockerExecutable = "docker",
    [string[]]$DockerPrefixArguments = @()
)

$ErrorActionPreference = "Stop"

$image = "nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787"
$proof = @'
from agent.context_compressor import ContextCompressor
from agent.context_engine import ContextEngine
from model_tools import get_tool_definitions
from tui_gateway.server import _load_enabled_toolsets

assert ContextCompressor.get_tool_schemas is ContextEngine.get_tool_schemas
assert get_tool_definitions(
    enabled_toolsets=["context_engine"],
    quiet_mode=True,
) == []
assert _load_enabled_toolsets() == ["context_engine"]
print("hermes_yujin_zero_tools=verified")
'@

$prior = $env:HERMES_TUI_TOOLSETS
try {
    $env:HERMES_TUI_TOOLSETS = "context_engine"
    $processInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $processInfo.FileName = $DockerExecutable
    $processInfo.UseShellExecute = $false
    $processInfo.CreateNoWindow = $true
    $processInfo.RedirectStandardInput = $true
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    $arguments = @($DockerPrefixArguments) + @(
        "run",
        "--rm",
        "--interactive",
        "--network",
        "none",
        "--env",
        "HERMES_TUI_TOOLSETS=context_engine",
        "--entrypoint",
        "python",
        $image,
        "-"
    )
    if ($null -ne $processInfo.ArgumentList) {
        foreach ($argument in $arguments) {
            [void]$processInfo.ArgumentList.Add($argument)
        }
    }
    else {
        if ($DockerPrefixArguments.Count -ne 0 -or $DockerExecutable -ne "docker") {
            throw "Pinned Hermes zero-tool proof test seam requires ArgumentList."
        }
        # Windows PowerShell 5.1 has no ArgumentList.  Every value here is a
        # fixed, non-secret literal; the Python proof still travels via stdin.
        $processInfo.Arguments = (
            'run --rm --interactive --network none ' +
            '--env HERMES_TUI_TOOLSETS=context_engine ' +
            '--entrypoint python "' + $image + '" -'
        )
    }

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $processInfo
    if (-not $process.Start()) {
        throw "Pinned Hermes zero-tool proof failed."
    }
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.StandardInput.Write($proof)
    $process.StandardInput.Close()
    $process.WaitForExit()
    [System.Threading.Tasks.Task]::WaitAll(
        [System.Threading.Tasks.Task[]]@($stdoutTask, $stderrTask)
    )
    $captured = $stdoutTask.Result + "`n" + $stderrTask.Result
    if ($process.ExitCode -ne 0) {
        throw "Pinned Hermes zero-tool proof failed."
    }
    if ($captured -notmatch "hermes_yujin_zero_tools=verified") {
        throw "Pinned Hermes zero-tool proof did not emit its success marker."
    }
    "hermes_yujin_zero_tools=verified"
}
finally {
    if ($null -eq $prior) {
        Remove-Item Env:HERMES_TUI_TOOLSETS -ErrorAction SilentlyContinue
    }
    else {
        $env:HERMES_TUI_TOOLSETS = $prior
    }
}
