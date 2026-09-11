"""숏폼에 넣을 장면을 유진이 고른다 -- 자막 글자 수가 아니라.

**진짜 모델을 부르지 않는다.** `tests/test_yujin_local_conversation.py`와 같은 틀로
`generate_structured`만 가진 가짜 런타임을 끼운다. LM Studio가 떠 있든 말든 결과가
같아야 한다.

**243을 곱해 본다.** 지금 컨테이너의 최대 장면 수는 5개라, 작은 입력만으로는 이
기능의 가장 어려운 부분(유진이 영상의 앞부분만 보는 것)이 시험에 닿지 않는다.
"""

from __future__ import annotations

import json

import pytest

from videobox_core_engine.short_form_scene_pick import (
    JUDGE_BATCH_SIZE,
    MAX_JUDGED_SCENES,
    pick_short_form_scenes,
)
from videobox_provider_interfaces.llm import LLMProviderError, StructuredLLMResponse


class _JudgeRuntime:
    """묶음을 받아 장면을 고르는 가짜 유진. 자막 길이는 보지 않는다.

    `pick`은 `(번호, 자막)`을 받아 고를지 말지 정한다.
    """

    def __init__(self, pick=None, *, raise_error: Exception | None = None) -> None:
        self._pick = pick or (lambda _number, caption: "결론" in caption or any(c.isdigit() for c in caption))
        self._raise_error = raise_error
        self.prompts: list[str] = []

    def generate_structured(self, *, project_id, task_type, prompt, response_schema):
        self.prompts.append(prompt)
        if self._raise_error is not None:
            raise self._raise_error
        picks = []
        for line in prompt.split("고를 장면:", 1)[1].splitlines():
            stripped = line.strip()
            if not stripped[:1].isdigit():
                continue
            number_text, _, caption = stripped.partition(". ")
            if self._pick(int(number_text), caption):
                picks.append({"scene": int(number_text), "worth": 5, "why": "conclusion"})
        output = {"schema_version": "videobox.short-form-scene-pick.v1", "picks": picks}
        return StructuredLLMResponse(
            provider_name="local_qwen",
            model_name="qwen3-35b",
            output_data=output,
            raw_text=json.dumps(output, ensure_ascii=False),
            metadata={},
        )

    @property
    def shown_captions(self) -> list[str]:
        shown: list[str] = []
        for prompt in self.prompts:
            for line in prompt.split("고를 장면:", 1)[1].splitlines():
                stripped = line.strip()
                if stripped[:1].isdigit():
                    shown.append(stripped.partition(". ")[2])
        return shown


class _ExplodingRuntime:
    def generate_structured(self, **kwargs):  # noqa: ANN003
        raise AssertionError("유진을 부르지 않기로 한 자리에서 불렀다")


def _long_form(count: int = 243) -> list[dict[str, object]]:
    """장면 243개짜리 롱폼. 결론은 **맨 뒤**에, 숫자는 뒤쪽 3/4 지점에 있다."""

    segments: list[dict[str, object]] = []
    for index in range(count):
        if index == count - 1:
            caption = "결론은 이겁니다"
        elif index == (count * 3) // 4:
            caption = "매출이 3배 늘었어요"
        else:
            # 앞쪽일수록 말이 빽빽하게 -- 밀도만 보면 앞부분이 다 이긴다.
            caption = "그래서 말인데요 " * (6 if index < 32 else 1)
        segments.append(
            {
                "segment_id": f"timeline_001:{index:03d}",
                "caption_text": caption,
                "start_sec": float(index * 5),
                "end_sec": float(index * 5 + 5),
            }
        )
    return segments


def test_yujin_picks_a_thin_conclusion_over_a_dense_filler() -> None:
    segments = [
        {"segment_id": "seg-filler", "caption_text": "그래서 뭐 아무튼 그냥 이렇게 저렇게 해봤고요 네", "start_sec": 0.0, "end_sec": 2.0},
        {"segment_id": "seg-conclusion", "caption_text": "결론은 이겁니다", "start_sec": 2.0, "end_sec": 12.0},
    ]

    result = pick_short_form_scenes(segments, project_id="proj-1", runtime=_JudgeRuntime())

    assert result.segment_ids == ("seg-conclusion",)
    assert result.judged_by == "yujin"


def test_yujin_reads_scenes_from_the_whole_video_not_just_the_opening() -> None:
    """천장의 핵심. 앞 32장면만 읽으면 결론도 숫자도 못 본다."""

    segments = _long_form()
    runtime = _JudgeRuntime()

    result = pick_short_form_scenes(segments, project_id="proj-1", runtime=runtime)

    assert "결론은 이겁니다" in runtime.shown_captions
    assert "매출이 3배 늘었어요" in runtime.shown_captions
    assert result.scenes_total == 243
    assert result.scenes_read_by_yujin <= MAX_JUDGED_SCENES
    # 유진을 부르는 횟수에 상한이 있어야 한다 -- 프록시 330초 벽 때문이다.
    assert len(runtime.prompts) <= -(-MAX_JUDGED_SCENES // JUDGE_BATCH_SIZE)
    assert result.segment_ids
    # 고른 것이 영상 앞부분만이면 요구를 못 맞춘 것이다.
    picked_indexes = [int(segment_id.split(":")[1]) for segment_id in result.segment_ids]
    assert max(picked_indexes) > 32


def test_shortlist_keeps_the_ending_even_when_its_captions_are_thin() -> None:
    """추리는 단계가 밀도만 보면 결론을 유진에게 보여주지도 못한다."""

    segments = _long_form()
    runtime = _JudgeRuntime(pick=lambda _number, _caption: False)

    pick_short_form_scenes(segments, project_id="proj-1", runtime=runtime)

    assert "결론은 이겁니다" in runtime.shown_captions


def test_short_form_stays_short_even_for_a_twenty_minute_long_form() -> None:
    """243장면 * 5초 = 20분. 그 40%면 8분이고, 그건 숏폼이 아니다."""

    segments = _long_form()
    runtime = _JudgeRuntime(pick=lambda _number, _caption: True)

    result = pick_short_form_scenes(segments, project_id="proj-1", runtime=runtime)

    picked = {str(item["segment_id"]) for item in segments} & set(result.segment_ids)
    total = sum(
        float(item["end_sec"]) - float(item["start_sec"])
        for item in segments
        if str(item["segment_id"]) in picked
    )
    assert total <= 65.0, total


def test_picked_scenes_come_back_in_time_order() -> None:
    segments = _long_form(count=40)
    runtime = _JudgeRuntime(pick=lambda _number, _caption: True)

    result = pick_short_form_scenes(segments, project_id="proj-1", runtime=runtime)

    assert list(result.segment_ids) == sorted(result.segment_ids)


def test_when_yujin_cannot_answer_it_says_so_and_never_claims_her_judgement() -> None:
    """유진이 못 고를 때 **조용히** 글자 수 세기로 내려가지 않는다."""

    segments = _long_form(count=40)
    runtime = _JudgeRuntime(raise_error=LLMProviderError(provider_name="local_qwen", message="꺼져 있음"))

    result = pick_short_form_scenes(segments, project_id="proj-1", runtime=runtime)

    assert result.judged_by == "caption_density"
    assert result.fallback_reason == "yujin_unavailable"
    assert result.segment_ids  # 만들기 자체는 되돌릴 수 있는 동작이라 막지 않는다
    assert "유진이 고른" not in result.notice
    assert "자막" in result.notice


def test_without_a_runtime_nothing_claims_yujin_judged() -> None:
    segments = _long_form(count=12)

    result = pick_short_form_scenes(segments, project_id="proj-1", runtime=None)

    assert result.judged_by == "caption_density"
    assert result.fallback_reason == "yujin_engine_off"
    assert result.scenes_read_by_yujin == 0
    assert "유진" not in result.notice.replace("유진이 지금 도와줄 수 없어서", "")


def test_a_broken_answer_is_not_dressed_up_as_yujins_choice() -> None:
    """모양이 깨진 응답을 반쯤 믿고 유진의 판단이라고 말하지 않는다."""

    class _GarbageRuntime:
        def __init__(self) -> None:
            self.prompts: list[str] = []

        def generate_structured(self, *, project_id, task_type, prompt, response_schema):
            self.prompts.append(prompt)
            return StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="qwen3-35b",
                output_data={"picks": "전부 다요"},
                raw_text="{}",
                metadata={},
            )

    result = pick_short_form_scenes(_long_form(count=12), project_id="proj-1", runtime=_GarbageRuntime())

    assert result.judged_by == "caption_density"
    assert result.fallback_reason == "yujin_answer_unusable"


def test_out_of_range_scene_numbers_are_dropped_not_guessed() -> None:
    segments = [
        {"segment_id": "seg-1", "caption_text": "결론은 이겁니다", "start_sec": 0.0, "end_sec": 5.0},
        {"segment_id": "seg-2", "caption_text": "그냥 하는 말", "start_sec": 5.0, "end_sec": 10.0},
    ]

    class _OutOfRangeRuntime:
        def generate_structured(self, *, project_id, task_type, prompt, response_schema):
            output = {
                "schema_version": "videobox.short-form-scene-pick.v1",
                "picks": [{"scene": 1, "worth": 5, "why": "conclusion"}, {"scene": 99, "worth": 5, "why": "hook"}],
            }
            return StructuredLLMResponse(
                provider_name="local_qwen", model_name="qwen3-35b",
                output_data=output, raw_text="{}", metadata={},
            )

    result = pick_short_form_scenes(segments, project_id="proj-1", runtime=_OutOfRangeRuntime())

    assert result.segment_ids == ("seg-1",)
    assert result.judged_by == "yujin"


def test_the_prompt_actually_asks_for_what_the_owner_calls_marketing_worthy() -> None:
    """배선 검증. 훅·결론·숫자를 묻지 않으면 유진은 밀도를 흉내 낼 뿐이다."""

    runtime = _JudgeRuntime()

    pick_short_form_scenes(_long_form(count=6), project_id="proj-1", runtime=runtime)

    prompt = runtime.prompts[0]
    assert "훅" in prompt
    assert "결론" in prompt
    assert "숫자" in prompt


def test_empty_input_asks_nobody() -> None:
    result = pick_short_form_scenes([], project_id="proj-1", runtime=_ExplodingRuntime())

    assert result.segment_ids == ()
    assert result.judged_by == "caption_density"


@pytest.mark.parametrize("count", [1, 5, 32, 33, 243])
def test_every_size_returns_at_least_one_scene_when_there_is_one(count: int) -> None:
    result = pick_short_form_scenes(_long_form(count=count), project_id="proj-1", runtime=_JudgeRuntime())

    assert result.segment_ids
    assert set(result.segment_ids) <= {f"timeline_001:{index:03d}" for index in range(count)}


def test_yujin_reading_and_finding_nothing_is_not_the_same_as_being_off() -> None:
    """읽고도 못 찾은 것과 못 부른 것은 원인이 다르다. 문구도 달라야 한다."""

    runtime = _JudgeRuntime(pick=lambda _number, _caption: False)

    result = pick_short_form_scenes(_long_form(count=12), project_id="proj-1", runtime=runtime)

    assert result.judged_by == "caption_density"
    assert result.fallback_reason == "yujin_found_nothing"
    assert "읽어 봤지만" in result.notice
    assert "유진이 고른" not in result.notice


def test_a_scene_the_owner_already_cut_is_never_shown_to_yujin_or_picked() -> None:
    """뺀 장면을 고르면 숏폼 안에 **그 길이만큼 죽은 시간**이 생긴다.

    `composition_plan`이 `cut_action="remove"` 클립을 버리는데 자리는 이미
    내줬기 때문이다. 고르는 쪽에서 애초에 안 보여 주는 것이 맞다.
    """

    segments = [
        {
            "segment_id": "seg-cut",
            "caption_text": "매출이 3배 늘었어요",
            "start_sec": 0.0,
            "end_sec": 5.0,
            "cut_action": "remove",
        },
        {
            "segment_id": "seg-keep",
            "caption_text": "결론은 이겁니다",
            "start_sec": 5.0,
            "end_sec": 10.0,
        },
    ]
    runtime = _JudgeRuntime()

    result = pick_short_form_scenes(segments, project_id="proj-1", runtime=runtime)

    assert "seg-cut" not in result.segment_ids
    assert "매출이 3배 늘었어요" not in runtime.shown_captions
    # 안내문의 "전체 N개"도 뺀 장면을 세면 안 된다.
    assert result.scenes_total == 1


def test_a_cut_scene_is_not_picked_by_the_caption_density_fallback_either() -> None:
    segments = [
        {
            "segment_id": "seg-cut",
            "caption_text": "아주 빽빽하게 말이 많은 장면입니다 정말로",
            "start_sec": 0.0,
            "end_sec": 5.0,
            "cut_action": "remove",
        },
        {
            "segment_id": "seg-keep",
            "caption_text": "남은 장면",
            "start_sec": 5.0,
            "end_sec": 10.0,
        },
    ]

    result = pick_short_form_scenes(segments, project_id="proj-1", runtime=None)

    assert "seg-cut" not in result.segment_ids
    assert result.scenes_total == 1


def test_a_fallback_that_kept_every_scene_does_not_say_it_chose() -> None:
    """자막이 하나도 없으면 밀도 대비책은 **전체를 그대로 돌려준다**.

    선택 = 전부라 하나도 안 짧아지는데 화면이 "자막이 많은 장면 위주로
    골랐어요"라고 말하면 거짓이다. 안 골랐으면 골랐다고 말하지 않는다.
    """

    segments = [
        {"segment_id": "seg-1", "caption_text": "", "start_sec": 0.0, "end_sec": 5.0},
        {"segment_id": "seg-2", "caption_text": "", "start_sec": 5.0, "end_sec": 10.0},
    ]

    result = pick_short_form_scenes(segments, project_id="proj-1", runtime=None)

    assert result.segment_ids == ("seg-1", "seg-2")
    assert "골랐어요" not in result.notice
    assert "그대로" in result.notice


def test_a_failed_batch_is_not_described_as_a_shortlist() -> None:
    """48개 이하면 추리기를 **안 한다.** 한 묶음이 실패해 덜 읽은 것뿐이다."""

    class _FirstBatchFails:
        def __init__(self) -> None:
            self.calls = 0

        def generate_structured(self, *, project_id, task_type, prompt, response_schema):
            self.calls += 1
            if self.calls == 1:
                raise LLMProviderError(provider_name="local_qwen", message="한 묶음 실패")
            output = {
                "schema_version": "videobox.short-form-scene-pick.v1",
                "picks": [{"scene": 1, "worth": 5, "why": "conclusion"}],
            }
            return StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="qwen3-35b",
                output_data=output,
                raw_text="{}",
                metadata={},
            )

    segments = _long_form(count=2 * JUDGE_BATCH_SIZE)
    assert len(segments) <= MAX_JUDGED_SCENES

    result = pick_short_form_scenes(segments, project_id="proj-1", runtime=_FirstBatchFails())

    assert result.judged_by == "yujin"
    assert result.scenes_read_by_yujin == JUDGE_BATCH_SIZE
    assert "추린" not in result.notice
    assert "확인하지 못했어요" in result.notice
