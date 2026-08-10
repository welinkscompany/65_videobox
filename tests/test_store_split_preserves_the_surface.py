"""쪼개도 겉모습이 그대로여야 한다.

`local_project_store.py`는 11,473줄에 메서드 320개다. 이번 세션에 직접 헤맸고,
존재하지 않는 헬퍼를 있다고 착각해 코드를 잘못 짰다. 갈래별로 뗄 때 **동작은
한 줄도 바꾸지 않는다** -- 이 테스트가 그것을 잠근다.

`PostgresProjectStore`가 상속하므로 상속 순서가 바뀐다. 그쪽 겉모습도 함께 본다.
"""

from __future__ import annotations

import json
from pathlib import Path

from videobox_storage.local_project_store import LocalProjectStore

_SNAPSHOT = Path(__file__).with_name("store_public_surface.json")


def _surface(cls: type) -> list[str]:
    return sorted(
        name for name in dir(cls)
        if not name.startswith("__") and callable(getattr(cls, name, None))
    )


def test_the_public_surface_is_unchanged() -> None:
    current = _surface(LocalProjectStore)
    if not _SNAPSHOT.is_file():
        _SNAPSHOT.write_text(json.dumps(current, indent=2), encoding="utf-8")
    expected = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))

    missing = sorted(set(expected) - set(current))
    assert not missing, f"쪼개면서 사라진 메서드: {missing}"


def test_the_postgres_store_still_sees_everything() -> None:
    # 상속 순서가 바뀌면 조용히 빠지는 것이 생긴다.
    from videobox_storage.postgres_project_store import PostgresProjectStore

    missing = sorted(set(_surface(LocalProjectStore)) - set(_surface(PostgresProjectStore)))
    assert not missing, f"Postgres 쪽에서 안 보이는 메서드: {missing}"
