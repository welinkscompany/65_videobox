from __future__ import annotations

import inspect

from videobox_api import yujin_memory_service
from videobox_api.routers import yujin_memory


def test_switched_off_and_failed_do_not_share_one_word() -> None:
    """유진의 기억 저장이 503 `memory_save_unavailable`로 막혔고 화면은 `기억을
    저장하지 못했어요`라고 했다. 실제로는 **기능이 켜져 있지 않았다** --
    workspace 컨테이너에 게이트웨이 주소가 실리지 않은 상태였다
    (`owner-ready.ps1 -WithYujinMemory`로만 실린다).

    고장과 꺼짐은 owner가 할 일이 다르다. 하나는 다시 눌러 보는 것이고 하나는
    켜는 것이다. 한 문장으로 말하면 owner는 켜면 되는 일을 안 되는 일로 안다.
    """
    source = inspect.getsource(yujin_memory_service.YujinMemoryService)
    for guard in ("if self._gateway is None:",):
        assert guard in source
    # 게이트웨이가 아예 없을 때만 쓰는 이름. 호출이 실패한 경우와 겹치면 안 된다.
    assert source.count('MemoryStoreUnavailable("memory_not_configured")') == 2
    assert 'MemoryStoreUnavailable("memory_store_unavailable")' not in source.split("if self._gateway is None:")[1].split("\n")[1]

    router_source = inspect.getsource(yujin_memory)
    assert '"memory_not_configured"' in router_source


def test_the_screen_says_it_is_switched_off_rather_than_broken() -> None:
    from pathlib import Path

    panel = Path("apps/web/src/features/editor/workbench/YujinMemoryPanel.tsx").read_text(encoding="utf-8")
    assert "기억 기능이 아직 켜져 있지 않아요" in panel
    # 원래 문구는 진짜 실패에 그대로 남는다 -- 덜 말하게 만드는 게 목적이 아니다.
    assert "기억을 저장하지 못했어요" in panel
