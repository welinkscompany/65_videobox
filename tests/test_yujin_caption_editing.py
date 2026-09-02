"""유진이 자막을 다듬는 길.

**보여 주지 않으면 다듬을 수 없다.** 2026-09-03까지 유진은 지금 자막이 뭐라고
적혀 있는지 못 봤다. 그래서 "짧게 다듬어 줘"는 늘 지어낸 문장이었다.

그리고 창작자가 보고 있는 언어를 고쳐야 한다. 영어를 보며 줄여 달라고 했는데
한국어가 고쳐지면 **눈에는 아무 일도 안 일어난다.**
"""

from __future__ import annotations

from typing import Any

from videobox_core_engine.caption_translation import apply_caption_translations
from videobox_core_engine.editing_session import (
    apply_yujin_editing_proposal,
    build_editing_session,
)
from videobox_core_engine.yujin_editing_proposal_adapter import YujinEditingContext
from videobox_core_engine.yujin_editing_proposal_service import _editing_prompt
from videobox_domain_models.yujin_editing_proposals import (
    SetCaptionTextOperation,
    YujinEditingProposal,
)


def _session() -> dict[str, Any]:
    return build_editing_session(
        project_id="project_001",
        timeline={"timeline_id": "timeline_001"},
        segments=[
            {"segment_id": "s1", "text": "요즘 영상 하나 만들려면 프로그램을 서너 개는 켜야 하죠", "start_sec": 0.0, "end_sec": 5.0},
        ],
    )


def _context(**overrides: Any) -> YujinEditingContext:
    defaults = {
        "session_id": "editing_session_001",
        "session_revision": 1,
        "segment_ids": ("s1",),
        "captions": (("s1", "요즘 영상 하나 만들려면 프로그램을 서너 개는 켜야 하죠"),),
    }
    return YujinEditingContext(**{**defaults, **overrides})


def test_yujin_is_shown_the_caption_it_is_asked_to_trim() -> None:
    prompt = _editing_prompt(instruction="1번 장면 자막을 짧게 다듬어 줘", context=_context())

    assert "요즘 영상 하나 만들려면" in prompt
    assert "1번 자막=" in prompt
    # 지어내지 말라고 못박는다 -- 그게 지금까지 벌어진 일이다.
    assert "새로 지어내지 말고" in prompt


def test_the_prompt_says_which_language_is_on_screen() -> None:
    """영어를 보고 있으면 영어를 다듬어야 한다."""
    prompt = _editing_prompt(
        instruction="줄여 줘",
        context=_context(caption_language="en", captions=(("s1", "You need three or four apps."),)),
    )

    assert "지금 자막(영어)" in prompt
    assert "You need three or four apps." in prompt


def test_no_captions_is_said_plainly() -> None:
    prompt = _editing_prompt(instruction="자막 줄여 줘", context=_context(captions=()))

    assert "자막이 있는 장면이 없다" in prompt


def test_a_trimmed_caption_lands_on_the_language_being_viewed() -> None:
    """**영어를 보며 줄였으면 영어가 줄어야 한다.** 한국어는 그대로 남는다."""
    session = apply_caption_translations(
        session=_session(), language="en",
        texts_by_segment={"s1": "You need three or four different apps to make one video."},
    )
    session["caption_language"] = "en"

    updated = apply_yujin_editing_proposal(
        session=session,
        proposal=YujinEditingProposal(
            proposal_id="p1", base_session_revision=int(session["session_revision"]),
            operations=[SetCaptionTextOperation(intent="set_caption_text", segment_id="s1", text="You need three or four apps.")],
        ),
    )

    segment = updated["segments"][0]
    assert segment["caption_translations"]["en"] == "You need three or four apps."
    assert segment["caption_text"] == "요즘 영상 하나 만들려면 프로그램을 서너 개는 켜야 하죠"


def test_without_a_chosen_language_the_original_is_edited() -> None:
    """원본을 보고 있으면 원본을 고친다 -- 전과 같다."""
    updated = apply_yujin_editing_proposal(
        session=_session(),
        proposal=YujinEditingProposal(
            proposal_id="p1", base_session_revision=1,
            operations=[SetCaptionTextOperation(intent="set_caption_text", segment_id="s1", text="프로그램 서너 개를 켜야 하죠")],
        ),
    )

    assert updated["segments"][0]["caption_text"] == "프로그램 서너 개를 켜야 하죠"


def _many_captions(count: int) -> YujinEditingContext:
    ids = tuple(f"s{index}" for index in range(1, count + 1))
    return YujinEditingContext(
        session_id="editing_session_001", session_revision=1, segment_ids=ids,
        captions=tuple((segment_id, f"{segment_id}번 장면의 자막입니다") for segment_id in ids),
    )


def test_a_long_video_does_not_dump_every_caption_into_the_prompt() -> None:
    """창작자의 실제 대본은 243문단이다(2026-09-03 실측).

    그대로 실으면 자막만 11,000자가 넘고, 모델은 뒤쪽을 안 본다 -- 자산 목록에
    40개 상한을 둔 것과 같은 이유다.
    """
    prompt = _editing_prompt(instruction="자막 다듬어 줘", context=_many_captions(243))

    # 글자 수로 재지 않는다 -- 프롬프트에는 장면 번호표처럼 자막이 아닌 것도
    # 들어 있어서 기준값이 금방 낡는다. **자막이 잘렸는가**를 직접 본다.
    assert "40번 자막=" in prompt
    assert "41번 자막=" not in prompt
    assert "243번 자막=" not in prompt
    # 안 보여 준 것이 있으면 그렇게 말한다. 조용히 자르면 지어낸다.
    assert "여기 없다" in prompt


def test_the_scene_the_creator_named_is_always_shown() -> None:
    """**말한 장면은 상한과 상관없이 보여 준다.**

    안 그러면 백 장면짜리 영상에서 "200번 장면 자막 줄여 줘"가 통하지 않고,
    유진은 목록에 없는 자막을 지어낸다 -- 방금 고친 그 결함이다.
    """
    prompt = _editing_prompt(
        instruction="200번 장면 자막을 짧게 줄여 줘", context=_many_captions(243),
    )

    assert "200번 자막=" in prompt


def test_a_short_video_still_shows_everything() -> None:
    prompt = _editing_prompt(instruction="자막 다듬어 줘", context=_many_captions(5))

    assert "5번 자막=" in prompt
    assert "여기 없다" not in prompt
