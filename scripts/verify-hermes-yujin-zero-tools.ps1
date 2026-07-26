[CmdletBinding()]
param()

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
    $output = @(
        & docker run --rm --network none `
            --env HERMES_TUI_TOOLSETS=context_engine `
            --entrypoint python `
            $image -c $proof 2>&1
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Pinned Hermes zero-tool proof failed."
    }
    if (($output -join "`n") -notmatch "hermes_yujin_zero_tools=verified") {
        throw "Pinned Hermes zero-tool proof did not emit its success marker."
    }
    $output
}
finally {
    if ($null -eq $prior) {
        Remove-Item Env:HERMES_TUI_TOOLSETS -ErrorAction SilentlyContinue
    }
    else {
        $env:HERMES_TUI_TOOLSETS = $prior
    }
}
