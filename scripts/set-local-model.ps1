<#
.SYNOPSIS
    로컬 LLM 모델 이름을 SSOT 하나로 바꾸는 도구.

.DESCRIPTION
    모델 이름은 `tests/test_local_model_name_is_one_value.py`가 지키는 셋(기억
    추출 기본값 · 유진 두뇌 · 코드에 박힌 마지막 기본값)에 `.env.container`의
    `VIDEOBOX_LOCAL_MODEL_NAME`까지 더해 실제로는 자리가 여러 곳이다. 한 곳만
    고치면 옛 모델과 새 모델을 둘 다 LM Studio에 올려 둬야 하고, 그러면 기계가
    느려진다 -- 이 스크립트가 나오게 된 이유다(2026-09-11).

    이 스크립트는 아래 여섯 자리를 한 번에 맞춘다.
      - .env.container (VIDEOBOX_LOCAL_MODEL_NAME)
      - compose.hermes-yujin.yaml (기억 추출 기본값의 안쪽 리터럴)
      - config/hermes/yujin/config.yaml (유진 두뇌)
      - services/agent-gateway/.../hermes_memory_adapter.py (코드에 박힌 마지막 기본값)
      - tests/test_hermes_yujin_compose_contract.py (계약 시험 리터럴 2곳)
      - tests/test_hermes_yujin_profile_distribution.py, tests/test_start_hermes_yujin_script.py
        (계약 시험 리터럴 각 1곳)

    LM Studio는 요청에 실린 model 필드가 실제로 로드된 것과 달라도 조용히 지금
    켜진 모델로 응답한다(실측, `docs` 인계 기록). 그래서 이름만 바꾸고 LM Studio에
    그 모델을 불러오는 걸 잊으면 겉으로는 문제가 없어 보이다가 나중에 모델을
    두 개 이상 동시에 띄우는 순간에야 조용히 엉뚱한 모델이 응답한다. 이 스크립트는
    그 사고를 막으려고 기본적으로 LM Studio에 그 모델이 실제로 로드돼 있는지
    먼저 확인하고, 아니면 무엇이 로드돼 있는지 보여주고 멈춘다. `-Force`로만
    건너뛸 수 있다.

.PARAMETER ModelId
    LM Studio 모델 id (예: qwen/qwen3.8-27b). 보수적인 모양 검사를 통과해야 한다.

.PARAMETER Force
    LM Studio에 그 모델이 실제로 로드돼 있는지 확인하지 않고 강행한다.

.PARAMETER RepositoryRoot
    대상 저장소 경로. 생략하면 이 스크립트가 있는 위치의 부모 폴더(실제 저장소
    루트)를 쓴다. 시험은 임시로 복사한 저장소를 가리켜 실제 파일을 건드리지 않는다.

.PARAMETER LocalModelApiUri
    LM Studio의 모델 목록 API. `scripts/owner-ready.ps1`의 `Get-LocalModelCheck`가
    쓰는 것과 같은 끝점·같은 응답 모양(`models[].type`, `.key`, `.loaded_instances`)이다.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$ModelId,
    [switch]$Force,
    [string]$RepositoryRoot = "",
    [Uri]$LocalModelApiUri = "http://127.0.0.1:1234/api/v1/models"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding

# LM Studio 모델 id는 보통 "org/model-name" 또는 "model-name" 모양이다 -- 영숫자,
# 점, 밑줄, 붙임표, 그리고 슬래시 한 번(조직/모델)만 허용한다. 공백·따옴표·셸
# 특수문자(`;`, `` ` ``, `$`, `|` 등)·상위 경로 이동(`..`)·슬래시 두 번 이상을
# 전부 막는다. 각 조각은 영숫자로 시작해야 하고 최대 128자다.
$script:ModelIdPattern = '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}(/[A-Za-z0-9][A-Za-z0-9._-]{0,127})?$'

if ($ModelId -notmatch $script:ModelIdPattern) {
    Write-Error "모델 id 모양이 이상합니다: '$ModelId' (허용 모양: $script:ModelIdPattern)"
    exit 1
}

if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = Split-Path -Parent $PSScriptRoot
}
if (-not (Test-Path -LiteralPath $RepositoryRoot -PathType Container)) {
    Write-Error "저장소 경로를 찾을 수 없습니다: $RepositoryRoot"
    exit 1
}
$RepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path

$envContainerPath = Join-Path $RepositoryRoot ".env.container"
$composeOverlayPath = Join-Path $RepositoryRoot "compose.hermes-yujin.yaml"
$yujinConfigPath = Join-Path $RepositoryRoot "config/hermes/yujin/config.yaml"
$adapterPath = Join-Path $RepositoryRoot "services/agent-gateway/src/videobox_agent_gateway/hermes_memory_adapter.py"
$composeContractTestPath = Join-Path $RepositoryRoot "tests/test_hermes_yujin_compose_contract.py"
$profileDistributionTestPath = Join-Path $RepositoryRoot "tests/test_hermes_yujin_profile_distribution.py"
$startScriptTestPath = Join-Path $RepositoryRoot "tests/test_start_hermes_yujin_script.py"

foreach ($requiredFile in @(
        $composeOverlayPath,
        $yujinConfigPath,
        $adapterPath,
        $composeContractTestPath,
        $profileDistributionTestPath,
        $startScriptTestPath
    )) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        Write-Error "필요한 자리가 없습니다: $requiredFile"
        exit 1
    }
}
if (-not (Test-Path -LiteralPath $envContainerPath -PathType Leaf)) {
    Write-Error ".env.container 파일이 없습니다. .env.container.example을 복사해 먼저 값을 채우세요."
    exit 1
}

if (-not $Force) {
    try {
        $response = Invoke-RestMethod -Uri $LocalModelApiUri -TimeoutSec 5 -ErrorAction Stop
    }
    catch {
        Write-Error "LM Studio(${LocalModelApiUri})에 연결할 수 없어 '$ModelId'이 실제로 로드돼 있는지 확인하지 못했습니다. LM Studio를 켜거나 -Force로 강행하세요."
        exit 1
    }
    $loadedLlmKeys = @(
        $response.models |
            Where-Object { $_.type -eq "llm" -and $_.loaded_instances.Count -gt 0 } |
            ForEach-Object { $_.key }
    )
    if ($loadedLlmKeys -notcontains $ModelId) {
        $loadedSummary = if ($loadedLlmKeys.Count -gt 0) { $loadedLlmKeys -join ", " } else { "(없음)" }
        Write-Error "'$ModelId'은 지금 LM Studio에 로드돼 있지 않습니다. 지금 로드된 모델: $loadedSummary. LM Studio에서 '$ModelId'을 불러오거나 -Force로 강행하세요."
        exit 1
    }
}

# 정규식 치환을 하나의 캡처 그룹으로만 쓰고, 치환 문자열은 .NET Regex.Replace의
# `$1`/`${name}` 템플릿 해석을 타지 않도록 문자열 이어붙이기(스플라이스)로
# 직접 박아 넣는다 -- 새 모델 id 자체에는 그런 문자가 없지만(위 정규식이 막는다),
# 이 방식이 "치환 문자열 안의 $ 처리"라는 클래스의 함정 자체를 원천적으로 없앤다.
function Set-SingleCaptureReplacement {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Pattern,
        [Parameter(Mandatory = $true)][string]$NewValue,
        [Parameter(Mandatory = $true)][string]$Description
    )
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $original = [IO.File]::ReadAllText($Path, $utf8NoBom)
    $match = [System.Text.RegularExpressions.Regex]::Match($original, $Pattern)
    if (-not $match.Success) {
        throw "패턴을 찾지 못해 바꾸지 못했습니다 ($Description): $Path"
    }
    $group = $match.Groups[1]
    $updated = $original.Substring(0, $group.Index) + $NewValue + `
        $original.Substring($group.Index + $group.Length)
    [IO.File]::WriteAllText($Path, $updated, $utf8NoBom)
}

# --- .env.container: 있으면 그 줄을 고치고, 없으면 새 줄을 더한다 ---
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$envOriginal = [IO.File]::ReadAllText($envContainerPath, $utf8NoBom)
$envKeyPattern = '(?m)^VIDEOBOX_LOCAL_MODEL_NAME=(.*)$'
$envMatch = [System.Text.RegularExpressions.Regex]::Match($envOriginal, $envKeyPattern)
if ($envMatch.Success) {
    $group = $envMatch.Groups[1]
    $envUpdated = $envOriginal.Substring(0, $group.Index) + $ModelId + `
        $envOriginal.Substring($group.Index + $group.Length)
}
else {
    $separator = if ($envOriginal.Length -gt 0 -and -not $envOriginal.EndsWith("`n")) { "`n" } else { "" }
    $envUpdated = $envOriginal + $separator + "VIDEOBOX_LOCAL_MODEL_NAME=$ModelId`n"
}
[IO.File]::WriteAllText($envContainerPath, $envUpdated, $utf8NoBom)

# --- compose.hermes-yujin.yaml: 기억 추출 기본값의 안쪽(진짜 SSOT) 리터럴 ---
Set-SingleCaptureReplacement -Path $composeOverlayPath `
    -Pattern 'VIDEOBOX_MEM0_LLM_MODEL: \$\{VIDEOBOX_MEM0_LLM_MODEL:-\$\{VIDEOBOX_LOCAL_MODEL_NAME:-([^}]+)\}\}' `
    -NewValue $ModelId `
    -Description "compose.hermes-yujin.yaml 기억 추출 기본값"

# --- config/hermes/yujin/config.yaml: 유진 두뇌 ---
Set-SingleCaptureReplacement -Path $yujinConfigPath `
    -Pattern '(?m)^\s*name:\s*(.+)$' `
    -NewValue $ModelId `
    -Description "유진 프로필의 model.name"

# --- hermes_memory_adapter.py: 코드에 박힌 마지막 기본값 ---
Set-SingleCaptureReplacement -Path $adapterPath `
    -Pattern '_LOCAL_MEM0_LLM_MODEL = "([^"]+)"' `
    -NewValue $ModelId `
    -Description "hermes_memory_adapter.py 코드 기본값"

# --- 계약 시험 리터럴 넷 (시험 스위트가 계속 초록이려면 여기도 같이 옮겨야 한다) ---
Set-SingleCaptureReplacement -Path $composeContractTestPath `
    -Pattern '\$\{VIDEOBOX_MEM0_LLM_MODEL:-\$\{VIDEOBOX_LOCAL_MODEL_NAME:-([^}]+)\}\}' `
    -NewValue $ModelId `
    -Description "test_hermes_yujin_compose_contract.py 기억 추출 기본값 리터럴"

Set-SingleCaptureReplacement -Path $composeContractTestPath `
    -Pattern '"name": "([^"]+)"' `
    -NewValue $ModelId `
    -Description "test_hermes_yujin_compose_contract.py 유진 두뇌 리터럴"

Set-SingleCaptureReplacement -Path $profileDistributionTestPath `
    -Pattern '"name": "([^"]+)"' `
    -NewValue $ModelId `
    -Description "test_hermes_yujin_profile_distribution.py 유진 두뇌 리터럴"

Set-SingleCaptureReplacement -Path $startScriptTestPath `
    -Pattern '"VIDEOBOX_MEM0_LLM_MODEL": "([^"]+)"' `
    -NewValue $ModelId `
    -Description "test_start_hermes_yujin_script.py 기억 추출 기본값 리터럴"

Write-Output "'$ModelId'로 로컬 모델을 맞췄습니다. 바꾼 자리:"
Write-Output "  - .env.container (VIDEOBOX_LOCAL_MODEL_NAME)"
Write-Output "  - compose.hermes-yujin.yaml (기억 추출 기본값)"
Write-Output "  - config/hermes/yujin/config.yaml (유진 두뇌)"
Write-Output "  - hermes_memory_adapter.py (코드에 박힌 마지막 기본값)"
Write-Output "  - 계약 시험 리터럴 4곳 (compose·profile·start 스크립트 시험)"
Write-Output ""
Write-Output "다음 한 걸음: scripts/owner-ready.ps1 -Mode Start -Rebuild -WithYujinMemory"
