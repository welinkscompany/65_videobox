"""e2e가 상대하는 **가짜 서버**가 진짜 API와 어긋나지 않는지.

2026-08-19에 재 보니 e2e 48개가 전부 손으로 쓴 318줄짜리
`apps/web/e2e/support/fake-api-server.mjs`를 상대하고 있었다. 실제 FastAPI를
한 번도 부르지 않는다. 즉 **백엔드가 경로를 바꾸거나 없애도 e2e는 전부 초록**이고,
화면은 배포된 뒤에야 깨진다.

가짜를 없애자는 뜻이 아니다. 가짜 서버는 e2e를 빠르고 결정적으로 만든다. 다만
그것이 진짜와 같은 모양인지는 누군가 재야 하고, 지금까지 아무도 재지 않았다.

**여기서 못 하는 것:** 응답 본문의 키까지 대조하려면 가짜 서버를 띄워 HTTP로
불러야 하는데, `tests/conftest.py`가 테스트의 모든 네트워크 연결을 막는다
(`"Tests must not open network connections."`). 그 가드는 옳으므로 뚫지 않았다.
경로 대조까지가 이 파일의 몫이다.
"""

from __future__ import annotations

import re
from pathlib import Path

from starlette.routing import Match

from videobox_api.main import create_app

ROOT = Path(__file__).parents[1]
FAKE_SERVER = ROOT / "apps" / "web" / "e2e" / "support" / "fake-api-server.mjs"
PLAYWRIGHT_CONFIG = ROOT / "apps" / "web" / "playwright.config.mjs"

# 가짜 서버 파일에서 경로처럼 생긴 문자열을 전부 걷어온다. 자리표시자를 손으로
# 되돌리려다 실패했다 -- 진짜 쪽은 `{job_id}`·`{readiness_id}`처럼 이름이 제각각이라
# 규칙으로 맞출 수 없다. 그래서 **라우터에게 직접 묻는다**(_serves_ 참고).
_PATH_IN_SOURCE = re.compile(r"""["'`](/api/[^"'`?\s${}]*)""")


def _serves(app: object, path: str) -> bool:
    """진짜 앱에 이 경로를 받는 라우트가 있는가.

    정규식으로 흉내 내지 않고 Starlette의 매처를 그대로 쓴다. 메서드가 달라
    `PARTIAL`이 나와도 **경로는 있는 것**이므로 통과시킨다 -- 여기서 재려는 것은
    경로의 존재이지 메서드가 아니다.
    """
    scope = {"type": "http", "method": "GET", "path": path, "path_params": {}}
    for route in app.routes:  # type: ignore[attr-defined]
        match, _ = route.matches(scope)
        if match in (Match.FULL, Match.PARTIAL):
            return True
    return False


def test_the_fake_server_never_serves_a_path_the_real_api_does_not_have(tmp_path: Path) -> None:
    """가짜가 **진짜에 없는 경로**를 흉내 내면, 화면이 그 경로를 믿고 만들어진다.

    실제 배포에서는 404가 되지만 e2e는 초록이다. 그 조합이 가장 늦게 발견된다.
    """
    app = create_app(projects_root=tmp_path / "projects")

    # 끝이 `/`인 문자열은 `startsWith(...)`용 **접두사**다 -- "여기에 한 조각이 더
    # 붙는다"는 뜻이므로, 깎아내지 말고 한 조각을 붙여서 재야 한다.
    served = sorted({
        f"{path}probe" if path.endswith("/") else path
        for path in _PATH_IN_SOURCE.findall(FAKE_SERVER.read_text(encoding="utf-8"))
        if path.rstrip("/") != "/api"
    })
    assert served, "가짜 서버에서 경로를 하나도 못 읽었다 -- 이 가드가 헛돌고 있다"

    unknown = [path for path in served if not _serves(app, path)]

    assert not unknown, (
        "가짜 서버가 진짜 API에 없는 경로를 흉내 낸다 -- 화면이 그것을 믿고 만들어지고, "
        f"e2e는 초록인 채로 배포된 뒤에 404가 된다: {unknown}"
    )


def test_the_escape_hatch_that_lets_e2e_reach_a_real_backend_stays_wired() -> None:
    """가짜를 끄고 진짜 백엔드로 e2e를 돌릴 수 있는 길이 남아 있는지.

    `PLAYWRIGHT_SKIP_FAKE_API=1`이 그 길이다. 이 갈래가 사라지면 e2e는
    **영원히** 가짜만 상대하게 되고, 되돌릴 방법이 코드 수정밖에 없어진다.
    """
    config = PLAYWRIGHT_CONFIG.read_text(encoding="utf-8")

    assert "PLAYWRIGHT_SKIP_FAKE_API" in config, (
        "가짜 API를 끄는 스위치가 사라졌다 -- e2e가 진짜 백엔드를 밟을 길이 없다"
    )
