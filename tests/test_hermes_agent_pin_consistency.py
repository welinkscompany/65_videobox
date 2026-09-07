import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
PIN_FILE = ROOT / "config/hermes/agent-pin.env"
THIS_FILE = Path(__file__)

# `config/hermes/agent-pin.env`가 정답이다. 여기 나열된 파일들은 전부 같은
# 다이제스트를 손으로 복사해 들고 있고(docker-compose 변수치환이나 Dockerfile
# ARG로 한 곳을 가리키게 배선하지 않았다 -- 그 배선 자체가 위험이 더 크다고
# 판단했다), 그래서 하나라도 갱신을 놓치면 어긋난 채로 조용히 남는다.
# 2026-08-27에 실제로 11개 파일에 같은 다이제스트가 흩어져 있는 걸 보고 나서
# 이 테스트를 만들었다 -- SSOT 파일을 고치고 이 테스트를 초록으로 만드는 것이
# "전부 옮겼다"의 증거가 되게 하려는 목적이다.
CONSUMER_FILES = [
    ROOT / "compose.yaml",
    ROOT / "compose.hermes-yujin.yaml",
    ROOT / "docker/hermes-memory-adapter.Dockerfile",
    ROOT / "scripts/start-hermes-yujin.ps1",
    ROOT / "scripts/verify-hermes-yujin-runtime.ps1",
    ROOT / "scripts/verify-hermes-yujin-zero-tools.ps1",
    ROOT / "scripts/verify-hermes-oauth-bootstrap.ps1",
    ROOT / "tests/test_compose_contract.py",
    ROOT / "tests/test_hermes_yujin_compose_contract.py",
    ROOT / "tests/test_hermes_zero_tools_verifier.py",
    ROOT / "tests/test_platform_only_hermes_dashboard_contract.py",
]


def _pin_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in PIN_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def test_pin_file_has_the_three_required_values() -> None:
    values = _pin_values()
    assert values["HERMES_AGENT_VERSION_TAG"].startswith("v")
    assert values["HERMES_AGENT_IMAGE_DIGEST"].startswith("sha256:")
    assert values["HERMES_AGENT_IMAGE_REF"] == (
        "nousresearch/hermes-agent@" + values["HERMES_AGENT_IMAGE_DIGEST"]
    )


def test_every_known_consumer_matches_the_pin_file() -> None:
    # 일부 소비자(`tests/test_hermes_zero_tools_verifier.py`)는 다이제스트를
    # `"...sha256:"` + `"<hex>"`처럼 문자열을 나눠서 들고 있어서 "sha256:<hex>"가
    # 한 줄에 붙어 있지 않다. 그래서 접두사 없이 순수 hex 64자만으로 대조한다.
    digest_hex = _pin_values()["HERMES_AGENT_IMAGE_DIGEST"].removeprefix("sha256:")
    stale: list[str] = []
    for path in CONSUMER_FILES:
        text = path.read_text(encoding="utf-8")
        if digest_hex not in text:
            stale.append(str(path.relative_to(ROOT)))
    assert stale == [], f"SSOT({PIN_FILE.relative_to(ROOT)})와 다이제스트가 어긋난 파일: {stale}"


_DIGEST_LITERAL = re.compile(r"\b[0-9a-f]{64}\b")


def test_no_stray_hermes_agent_digest_outside_the_known_consumer_list() -> None:
    """활성 코드·설정 파일 어딘가에 SSOT와 다른 다이제스트가 새로 생기면 잡는다.

    `scripts/new-hermes-yujin-secrets.ps1`는 다이제스트를 정규식
    `[0-9a-f]{64}`로 검사할 뿐 특정 값을 박아두지 않아서(어떤 pin으로 바뀌어도
    그대로 맞는다) 제외한다.
    """
    digest_hex = _pin_values()["HERMES_AGENT_IMAGE_DIGEST"].removeprefix("sha256:")
    known = {p.resolve() for p in [*CONSUMER_FILES, PIN_FILE, THIS_FILE]}
    excluded_dynamic = {(ROOT / "scripts/new-hermes-yujin-secrets.ps1").resolve()}
    active_globs = [
        "compose*.yaml",
        "docker/**/*.Dockerfile",
        "scripts/**/*.ps1",
        "tests/**/*.py",
        "services/**/*.py",
        "packages/**/*.py",
    ]
    offenders: list[str] = []
    for pattern in active_globs:
        for path in ROOT.glob(pattern):
            resolved = path.resolve()
            if resolved in known or resolved in excluded_dynamic or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "hermes-agent" not in text:
                continue
            # 64자리 hex 전부를 비교 대상으로 삼으면 이 저장소의 다른 provenance/
            # content hash와 섞여 오탐이 난다(2026-08-27에 실제로 겪었다) --
            # "hermes-agent"가 등장하는 파일로 먼저 좁힌 뒤에도, 그 문자열
            # 근처(200자 이내)에 있는 hex만 Hermes 다이제스트 후보로 본다.
            candidate_digests: set[str] = set()
            for anchor in re.finditer(r"hermes-agent", text):
                window = text[max(0, anchor.start() - 100) : anchor.end() + 100]
                candidate_digests |= {m.group(0) for m in _DIGEST_LITERAL.finditer(window)}
            if candidate_digests and digest_hex not in candidate_digests:
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"목록에 없는 곳에서 다른 Hermes 다이제스트 발견: {offenders}"
