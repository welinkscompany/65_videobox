<#
VideoBox MCP HTTP 전송을 호스트 프로세스로 띄운다 (컨테이너 아님 -- 스펙 §2).
AK-System Hermes 쪽 .mcp.json이 http://127.0.0.1:8901/mcp로 붙는다.
#>
param(
    [string]$VideoBoxApiBaseUrl = "http://127.0.0.1:5173",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8901
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    throw "가상환경이 없습니다: $venvPython (requirements-mcp.txt를 먼저 설치하세요)"
}
if (-not $env:VIDEOBOX_MCP_HTTP_TOKEN) {
    throw "VIDEOBOX_MCP_HTTP_TOKEN 환경변수가 없습니다. AK-Hermes .mcp.json과 같은 값을 먼저 설정하세요."
}

$env:VIDEOBOX_API_BASE_URL = $VideoBoxApiBaseUrl
$env:VIDEOBOX_MCP_HTTP_HOST = $BindHost
$env:VIDEOBOX_MCP_HTTP_PORT = $Port
$env:VIDEOBOX_MCP_TRANSPORT = "http"
$env:PYTHONPATH = Join-Path $repoRoot "services\mcp\src"

Write-Host "VideoBox MCP HTTP 서버를 http://$BindHost`:$Port/mcp 에 띄웁니다..."
& $venvPython -m videobox_mcp.server
