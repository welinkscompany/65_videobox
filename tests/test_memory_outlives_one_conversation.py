from __future__ import annotations

import inspect

from videobox_api import yujin_memory_service
from videobox_storage import _store_yujin_memory


def test_an_approved_memory_is_not_locked_inside_one_conversation() -> None:
    """실측(2026-08-20): 대화 A에서 `자막은 두 줄을 넘기지 않게`를 저장하고 대화
    B에서 물으니 유진이 못 꺼냈다. 조회가 `conversation_id`로 묶여 있어서다.

    기억은 대화가 끝나도 남으라고 만든 것이다. 대화마다 다시 가르쳐야 하면
    기억이 아니라 그 대화의 메모다 -- owner는 새 대화를 열 때마다 같은 취향을
    다시 말해야 한다.

    **넓히면서도 지켜야 하는 것:** 게이트웨이가 돌려준 항목 중 로컬에 승인·저장
    기록이 있는 것만 채택한다(CLAUDE.md §6). 이 대조가 외부가 기억을 주입하지
    못하게 막는다. 범위는 프로젝트로 넓히되 대조는 그대로다.
    """
    query = inspect.getsource(_store_yujin_memory.YujinMemoryMixin.list_yujin_memory_retrieval_rows)
    candidates = query[query.index("FROM yujin_memory_candidates"):]
    assert "conversation_id" not in candidates.split("ORDER BY")[0], candidates
    assert "status = 'approved'" in candidates and "storage_status = 'stored'" in candidates
    # 실재하는 대화인지 보는 확인은 남는다 -- 없는 대화 id로 남의 프로젝트
    # 기억을 긁어 갈 수 있으면 넓힌 게 아니라 열어 둔 것이다.
    assert "FROM director_conversations" in query
    assert "WHERE project_id = ? AND conversation_id = ?" in query

    eligibility = inspect.getsource(yujin_memory_service.YujinMemoryService._eligible_local_memories)
    # 대조는 살아 있어야 한다 -- 넓히면서 문을 열어 두면 안 된다.
    assert 'row.get("status") != "approved"' in eligibility
    assert 'row.get("storage_status") != "stored"' in eligibility
    assert 'row.get("project_id") != project_id' in eligibility
    assert 'row.get("conversation_id") != conversation_id' not in eligibility
