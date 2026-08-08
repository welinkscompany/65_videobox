<#
.SYNOPSIS
유진 에이전트를 켜는 데 필요한 비밀값을 이 컴퓨터에서 만들어 .env.container 에 채운다.

.DESCRIPTION
compose.hermes-yujin.yaml 이 요구하는 값 중 이 컴퓨터에서 만들 수 있는 것은 전부 다음 6가지다.

  VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64   게이트웨이가 권한을 서명하는 개인키
  VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64    작업 서비스가 서명을 확인하는 공개키
  VIDEOBOX_HERMES_CAPABILITY_KEY_ID            그 키쌍의 이름
  VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN         작업 서비스 → 게이트웨이 호출 암호
  VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN         게이트웨이 → 기억 어댑터 호출 암호
  HERMES_YUJIN_GATEWAY_USERNAME / _PASSWORD / _PASSWORD_HASH   게이트웨이 → 유진 로그인

MEM0_API_KEY 는 외부 계정 값이라 여기서 만들 수 없다. 없으면 유진은 로컬 기억만 쓴다.

값은 이 컴퓨터에서만 만들어지고 화면에 찍지 않는다. 비밀번호 해시는 유진 이미지 안에서
Hermes 자신의 해시 함수로 계산하므로, 평문 비밀번호는 파일 밖으로 나가지 않는다.
이미 진짜 값이 들어 있으면 덮어쓰지 않는다(-Force 로만 교체).
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$EnvFile,
    [string]$PythonExecutable,
    [string]$DockerExecutable = "docker",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($EnvFile)) {
    $EnvFile = Join-Path $repositoryRoot ".env.container"
}
if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
    throw "환경 파일을 찾지 못했습니다: $EnvFile"
}
if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
    $PythonExecutable = Join-Path $repositoryRoot ".venv/Scripts/python.exe"
}
if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
    throw "파이썬 실행 파일을 찾지 못했습니다: $PythonExecutable"
}

$overlayFile = Join-Path $repositoryRoot "compose.hermes-yujin.yaml"
$overlayText = Get-Content -LiteralPath $overlayFile -Raw -Encoding UTF8
if ($overlayText -notmatch "(?m)^\s*image:\s*(nousresearch/hermes-agent@sha256:[0-9a-f]{64})\s*$") {
    throw "compose.hermes-yujin.yaml 에서 고정된 유진 이미지를 읽지 못했습니다."
}
$pinnedHermesImage = $Matches[1]

if (-not $PSCmdlet.ShouldProcess($EnvFile, "유진 비밀값 생성")) {
    return
}

# 값 자체는 파이썬 안에서만 다루고 표준출력으로 내보내지 않는다.
$helper = @'
import base64
import os
import re
import secrets
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

PLACEHOLDERS = ("changeme", "replace-before-starting", "replace_me", "placeholder")
KEY_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,254}\Z", re.ASCII)

PRIVATE_KEY = "VIDEOBOX_HERMES_CAPABILITY_PRIVATE_KEY_B64"
PUBLIC_KEY = "VIDEOBOX_HERMES_CAPABILITY_PUBLIC_KEY_B64"
KEY_ID = "VIDEOBOX_HERMES_CAPABILITY_KEY_ID"
GATEWAY_TOKEN = "VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN"
ADAPTER_TOKEN = "VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN"
GATEWAY_USERNAME = "HERMES_YUJIN_GATEWAY_USERNAME"
GATEWAY_PASSWORD = "HERMES_YUJIN_GATEWAY_PASSWORD"
GATEWAY_PASSWORD_HASH = "HERMES_YUJIN_GATEWAY_PASSWORD_HASH"

LOCAL_KEYS = (
    PRIVATE_KEY,
    PUBLIC_KEY,
    KEY_ID,
    GATEWAY_TOKEN,
    ADAPTER_TOKEN,
    GATEWAY_USERNAME,
    GATEWAY_PASSWORD,
)
MANAGED_KEYS = LOCAL_KEYS + (GATEWAY_PASSWORD_HASH,)


def read_env(path):
    with open(path, encoding="utf-8", newline="") as handle:
        text = handle.read()
    lines = text.split("\n")
    values = {}
    for line in lines:
        if line.lstrip().startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        values[name.strip()] = value.strip()
    return lines, values


def write_env(path, lines, updates):
    replaced = 0
    for index, line in enumerate(lines):
        if line.lstrip().startswith("#") or "=" not in line:
            continue
        name = line.split("=", 1)[0].strip()
        if name in updates:
            lines[index] = name + "=" + updates[name]
            replaced += 1
    if replaced != len(updates):
        print("env_replace_incomplete=%d" % replaced)
        raise SystemExit(3)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="") as handle:
        handle.write("\n".join(lines))
    os.replace(temporary, path)


def looks_real(name, value):
    if not value or any(marker in value.lower() for marker in PLACEHOLDERS):
        return False
    if name.endswith("_B64"):
        try:
            return len(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))) == 32
        except Exception:
            return False
    if name in (GATEWAY_TOKEN, ADAPTER_TOKEN):
        # 게이트웨이 클라이언트가 32바이트 이상과 서로 다른 문자 8종을 요구한다.
        stripped = value == value.strip()
        return stripped and len(value.encode("utf-8")) >= 32 and len(set(value)) >= 8
    if name == GATEWAY_PASSWORD_HASH:
        unescaped = value.replace("$$", "$")
        return unescaped.startswith("scrypt$") and len(unescaped.split("$")) == 6
    if name == KEY_ID:
        return KEY_ID_PATTERN.fullmatch(value) is not None
    return True


def encode(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


stage = sys.argv[1]
env_path = sys.argv[2]
lines, values = read_env(env_path)

missing = [name for name in MANAGED_KEYS if name not in values]
if missing:
    print("env_missing_keys=" + ",".join(missing))
    raise SystemExit(2)

if stage == "local":
    force = sys.argv[3] == "force"
    if not force and all(looks_real(name, values[name]) for name in MANAGED_KEYS):
        print("already_provisioned=true")
        raise SystemExit(0)

    private_key = Ed25519PrivateKey.generate()
    raw_private = private_key.private_bytes(
        Encoding.Raw, PrivateFormat.Raw, NoEncryption()
    )
    raw_public = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    updates = {
        PRIVATE_KEY: encode(raw_private),
        PUBLIC_KEY: encode(raw_public),
        KEY_ID: "videobox-yujin-" + secrets.token_hex(8),
        GATEWAY_TOKEN: secrets.token_urlsafe(48),
        ADAPTER_TOKEN: secrets.token_urlsafe(48),
        GATEWAY_USERNAME: "videobox-gateway",
        GATEWAY_PASSWORD: secrets.token_urlsafe(32),
    }
    for name, value in updates.items():
        if not looks_real(name, value):
            print("generated_value_invalid=" + name)
            raise SystemExit(4)
    write_env(env_path, lines, updates)
    print("provisioned=true")
    raise SystemExit(0)

if stage == "hash":
    password_hash = sys.argv[3]
    if not looks_real(GATEWAY_PASSWORD_HASH, password_hash):
        print("password_hash_invalid=true")
        raise SystemExit(5)
    # scrypt 해시는 `scrypt$n$r$p$salt$dk` 라 `$1` 같은 조각이 들어 있다.
    # docker compose 는 env 파일 값의 `$` 를 변수로 보고 지워 버리므로,
    # 이스케이프하지 않으면 유진이 5칸짜리 망가진 해시를 받는다.
    escaped = password_hash.replace("$", "$$")  # GATEWAY_PASSWORD_HASH 전용
    write_env(env_path, lines, {GATEWAY_PASSWORD_HASH: escaped})
    print("hashed=true")
    raise SystemExit(0)

print("unknown_stage=" + stage)
raise SystemExit(6)
'@

$helperFile = Join-Path ([System.IO.Path]::GetTempPath()) (
    "videobox-yujin-secrets-" + [Guid]::NewGuid().ToString("N") + ".py"
)
Set-Content -LiteralPath $helperFile -Value $helper -Encoding UTF8
try {
    $mode = if ($Force) { "force" } else { "keep" }
    $localOutput = & $PythonExecutable $helperFile "local" $EnvFile $mode 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "비밀값을 만들지 못했습니다: $localOutput"
    }
    if ($localOutput -match "already_provisioned=true") {
        Write-Host "유진 비밀값이 이미 준비돼 있습니다. 바꾸려면 -Force 를 주세요."
        return
    }

    # 평문 비밀번호는 컨테이너 환경으로만 전달하고, 밖으로는 해시만 나온다.
    $hashCode = (
        "import os; from plugins.dashboard_auth.basic import hash_password; " +
        "print('HASH=' + hash_password(os.environ['HERMES_YUJIN_GATEWAY_PASSWORD']))"
    )
    $hashOutput = & $DockerExecutable @(
        "run"
        "--rm"
        "--network", "none"
        "--env-file", $EnvFile
        "--entrypoint", "python"
        $pinnedHermesImage
        "-c", $hashCode
    ) 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "비밀번호 해시를 계산하지 못했습니다: $hashOutput"
    }
    $hashLine = ($hashOutput | Where-Object { $_ -is [string] -and $_.StartsWith("HASH=") } | Select-Object -Last 1)
    if (-not $hashLine) {
        throw "비밀번호 해시를 읽지 못했습니다."
    }
    $passwordHash = $hashLine.Substring(5)

    $hashWrite = & $PythonExecutable $helperFile "hash" $EnvFile $passwordHash 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "비밀번호 해시를 저장하지 못했습니다: $hashWrite"
    }
} finally {
    Remove-Item -LiteralPath $helperFile -Force -ErrorAction SilentlyContinue
}

Write-Host "유진 비밀값을 이 컴퓨터에서 새로 만들어 $EnvFile 에 넣었습니다."
Write-Host "값은 화면에 표시하지 않습니다. MEM0_API_KEY 는 외부 계정 값이라 직접 넣어야 합니다."
