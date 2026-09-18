from __future__ import annotations

import inspect

from videobox_api import yujin_memory_service


def test_memory_is_always_configured_now_that_mem0_is_gone() -> None:
    """옛 이름은 `test_switched_off_and_failed_do_not_share_one_word` --
    게이트웨이(외부 provider)가 아예 안 실려서 "꺼짐"과 "고장"이 헷갈리던
    상태를 검증했었다. 2026-09-18에 Mem0를 걷어내며 `YujinMemoryService`가
    더 이상 게이트웨이를 갖지 않는다 -- 저장은 항상 로컬이라 "꺼져 있다"는
    상태 자체가 없어졌다(`docs/decisions/2026-09-18-mem0-removed-native-memory-librarian.ko.md`).
    그 사실을 소스로 고정한다: `self._gateway` 개념이 없고, `store_candidate`/
    `delete_candidate_memory`는 로컬 쓰기 실패(`memory_store_unavailable`/
    `memory_delete_unavailable`)만 던진다.
    """
    source = inspect.getsource(yujin_memory_service.YujinMemoryService)
    assert "self._gateway" not in source
    assert "memory_not_configured" not in source
    assert "memory_store_unavailable" in source
    assert "memory_delete_unavailable" in source


def test_the_screen_says_it_is_switched_off_rather_than_broken() -> None:
    from pathlib import Path

    panel = Path("apps/web/src/features/editor/workbench/YujinMemoryPanel.tsx").read_text(encoding="utf-8")
    assert "기억 기능이 아직 켜져 있지 않아요" in panel
    # 원래 문구는 진짜 실패에 그대로 남는다 -- 덜 말하게 만드는 게 목적이 아니다.
    assert "기억을 저장하지 못했어요" in panel
