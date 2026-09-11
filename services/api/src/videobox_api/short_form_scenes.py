"""숏폼에 넣을 장면을 고르고 **다시 고르는** 한 자리.

## 왜 "다시 만들기"가 지우고 새로 만드는 것이 아닌가

숏폼 모양은 `(project_id, source_session_id, kind)`가 유일하다(`sqlite_schema.py`).
그래서 한 편집본에 숏폼은 하나뿐이고, 두 번째 만들기는 유일 제약에 걸린다.
2026-09-11 실물 측정에서 그 위반을 아무도 안 잡아 대표님에게 맨
`Internal Server Error`가 갔고, 화면 단추는 한 번 쓰면 조용히 죽어 있었다.

**지우는 문을 내지 않는다.** 지우기를 만들면 "되돌릴 길이 없다"는 문제가 다시
열린다 -- 앞선 조각이 유진에게 모양을 **만들** 권한을 주지 않기로 한 이유가
그것이었다. 대신 다시 만들기는 **이미 있는 모양의 장면 목록을 다시 판단해
갈아 끼우는 일**로 정의한다. 그러면

- 새 문을 안 낸다. `apply_variant_patch`가 이미 `selected_segment_ids`를 통째로
  받는다(세로 하이라이트에서만).
- 되돌리기가 이미 있다. 화면의 `전체 장면으로 되돌리기`가 같은 통째 목록 PATCH다.
- 유일 제약을 건드리지 않는다. 행을 더 만들지 않으므로 충돌할 것이 없다.

## 왜 한 모듈에 모으는가

장면을 고르는 일을 부르는 자리가 **셋**이다 -- 숏폼 만들기(`create_variant`),
숏폼 다시 만들기(`repick_short_form_route`), 유진에게 말해서 다시 만들기
(`director_proposals.batch_apply`의 `remake_short_form`). 이 저장소는 같은 로직이
둘로 갈라져 한쪽만 고쳐지는 함정에 이미 여러 번 걸렸다(`output_variants.py`의
`build_variant_timeline_payload`·`output_variant_from_row` 머리말). 그래서 셋이
이 모듈을 부른다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from videobox_core_engine.output_variants import (
    VariantInvariantError,
    apply_variant_patch,
    output_variant_from_row,
)
from videobox_core_engine.short_form_scene_pick import (
    ShortFormScenePick,
    pick_short_form_scenes,
)
from videobox_domain_models.output_variants import OutputVariant


def short_form_scene_pick(
    *,
    store: Any,
    project_id: str,
    session_id: str,
    runtime: Any | None,
) -> ShortFormScenePick:
    """편집본을 읽어 숏폼에 넣을 장면을 고른다. 누가 골랐는지도 함께 돌려준다.

    저장소에는 런타임이 없어서 고르는 일은 저장소 밖에서 한다(2026-09-11).
    """
    session = store.get_editing_session(project_id=project_id, session_id=session_id)
    return pick_short_form_scenes(
        [segment for segment in session.get("segments", []) if isinstance(segment, dict)],
        project_id=project_id,
        runtime=runtime,
    )


def remade_short_form_variant(
    *,
    store: Any,
    project_id: str,
    variant_row: Mapping[str, object],
    runtime: Any | None,
    expected_variant_revision: int | None = None,
) -> tuple[OutputVariant, ShortFormScenePick]:
    """숏폼 장면을 다시 판단해 갈아 끼운 모양을 돌려준다. **저장은 부르는 쪽이 한다.**

    저장을 여기서 하지 않는 이유는 쓰는 문이 둘이기 때문이다 -- 화면 경로는
    `update_output_variant`, 유진 경로는 제안 수명까지 한 트랜잭션으로 닫는
    `apply_director_variant_proposal_transaction`이다.

    **다시 판단했는데 결과가 같을 수 있다.** `apply_variant_patch`는 목록이 같으면
    버전을 **안 올린** 원본을 그대로 돌려주는데, 저장소 두 문은 둘 다 버전이
    정확히 1 올라야 받는다(`variant_revision_must_advance_by_one`) -- 그대로
    넘기면 판단은 정상이었는데 화면에 실패로 보인다. 그래서 결과가 같아도 여기서
    버전을 올린다. 부르는 쪽마다 따로 판단하게 두면 두 경로가 갈리고, 이 저장소는
    바로 그 함정에 반복해서 걸렸다.
    """
    variant = output_variant_from_row(variant_row)
    if variant.kind != "vertical_highlight":
        # 장면 구성을 바꿀 수 있는 모양은 숏폼뿐이다. `apply_variant_patch`도
        # 같은 이유로 막지만, 여기서 먼저 막아야 유진을 헛부르지 않는다.
        raise VariantInvariantError("only_vertical_highlight_can_be_remade")
    pick = short_form_scene_pick(
        store=store,
        project_id=project_id,
        session_id=variant.source_session_id,
        runtime=runtime,
    )
    if not pick.segment_ids:
        # 고를 장면이 하나도 없으면 목록을 비우지 않는다. 빈 목록은
        # `apply_variant_patch`가 거부하고, 억지로 넣으면 숏폼이 렌더 못 하는
        # 모양이 된다. 지금 모양을 그대로 두고 사유를 말한다.
        raise VariantInvariantError("short_form_has_no_scene_to_pick")
    updated = apply_variant_patch(
        variant,
        {"selected_segment_ids": list(pick.segment_ids)},
        expected_variant_revision=expected_variant_revision,
    )
    if updated.variant_revision == variant.variant_revision:
        updated = updated.model_copy(
            update={"variant_revision": variant.variant_revision + 1}
        )
    return updated, pick


def scene_pick_payload(pick: ShortFormScenePick) -> dict[str, object]:
    """화면이 문구를 고르는 데 쓰는 값. **누가 골랐는지**가 핵심이다.

    자막 밀도로 고른 결과를 "유진이 골랐어요"라고 말하면 이 기능에서 가장 나쁜
    결과가 된다 -- 그래서 `judged_by`가 항상 같이 간다.
    """
    return {
        "judged_by": pick.judged_by,
        "notice": pick.notice,
        "scenes_total": pick.scenes_total,
        "scenes_read_by_yujin": pick.scenes_read_by_yujin,
    }
