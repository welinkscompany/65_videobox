from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "new-hermes-yujin-secrets.ps1"


def test_password_hash_is_written_escaped_for_compose_interpolation() -> None:
    """scrypt 해시의 `$`를 그대로 두면 compose 가 변수로 먹어 버린다.

    해시는 `scrypt$n$r$p$salt$dk` 라 `$1` 같은 조각이 들어 있고,
    `docker compose --env-file` 은 이를 정의되지 않은 변수로 보고 지운다.
    그래서 유진 컨테이너는 6칸이 아니라 5칸짜리 해시를 받고 로그인이
    "Invalid credentials" 로 실패한다. 2026-08-08 실제로 재현했다.
    """
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'replace("$", "$$")' in source, (
        "해시를 이스케이프하지 않으면 compose 가 조각을 먹는다"
    )
    # 파일을 다시 읽어 검사하는 쪽은 반대로 풀어야 한다.
    assert 'replace("$$", "$")' in source, (
        "이스케이프한 값을 그대로 검사하면 형식 확인이 틀린다"
    )


def test_only_the_hash_is_escaped() -> None:
    """다른 값에는 `$`가 없다. 전부 이스케이프하면 오히려 값이 바뀐다."""
    source = SCRIPT.read_text(encoding="utf-8")

    escape_line = next(
        line for line in source.splitlines() if 'replace("$", "$$")' in line
    )
    assert "GATEWAY_PASSWORD_HASH" in escape_line
