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
