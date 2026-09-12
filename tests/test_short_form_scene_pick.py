"""숏폼에 넣을 장면을 유진이 고른다 -- 자막 글자 수가 아니라.

**진짜 모델을 부르지 않는다.** `tests/test_yujin_local_conversation.py`와 같은 틀로
`generate_structured`만 가진 가짜 런타임을 끼운다. LM Studio가 떠 있든 말든 결과가
같아야 한다.

**243을 곱해 본다.** 지금 컨테이너의 최대 장면 수는 5개라, 작은 입력만으로는 이
기능의 가장 어려운 부분(유진이 영상의 앞부분만 보는 것)이 시험에 닿지 않는다.
"""

from __future__ import annotations

import json
import logging
import threading

import pytest

from videobox_core_engine.short_form_scene_pick import (
    BACKGROUND_BUDGET_SECONDS,
    COMPOSE_MIN_WAIT_SECONDS,
    JUDGE_BATCH_SIZE,
    MAX_JUDGED_SCENES,
    MAX_SCAN_CALLS,
    SCAN_WAIT_CEILING_SECONDS,
    SYNCHRONOUS_BUDGET_SECONDS,
    compose_wait_seconds,
    pick_short_form_scenes,
    scan_wait_seconds,
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

    def generate_structured(self, *, project_id, task_type, prompt, response_schema, wait_seconds=None):
        if self._raise_error is not None:
            self.prompts.append(prompt)
            raise self._raise_error
        if "고를 대목:" in prompt:
            # 짜기 단계. 훑기에서 고른 대목을 그대로 이어 붙인 후보 하나를 준다.
            lines = [
                int(line.strip().partition(". ")[0])
                for line in prompt.split("고를 대목:", 1)[1].splitlines()
                if line.strip()[:1].isdigit()
            ]
            output = {
                "thinking": "가짜 유진이 생각한다",
                "candidates": [{"lines": lines, "reason": "퍼질 이유"}],
                "chosen": 1,
                "schema_version": "videobox.short-form-compose.v1",
            }
            return StructuredLLMResponse(
                provider_name="local_qwen", model_name="qwen3-35b",
                output_data=output, raw_text=json.dumps(output, ensure_ascii=False), metadata={},
            )
        self.prompts.append(prompt)
        picks = []
        for line in prompt.split("고를 장면:", 1)[1].splitlines():
            stripped = line.strip()
            if not stripped[:1].isdigit():
                continue
            number_text, _, caption = stripped.partition(". ")
            # 프롬프트 줄은 `번호. (N초) 글`이다. 시각 표시를 떼고 글만 본다 --
            # 안 떼면 `(0초)`의 숫자가 "숫자가 있다"로 세어진다.
            if caption.startswith("("):
                caption = caption.partition(") ")[2]
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
    def shown_text(self) -> str:
        """유진에게 실제로 보인 글 전부. 대목이 여러 발화·장면을 묶기 때문에
        낱개 목록이 아니라 **글 전체에 대고** 찾는다."""
        return "\n".join(self.prompts)


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

    assert "결론은 이겁니다" in runtime.shown_text
    assert "매출이 3배 늘었어요" in runtime.shown_text
    assert result.scenes_total == 243
    # 2026-09-12부터 상한은 **읽는 장면 수**가 아니라 **부르는 횟수**다.
    # 대목을 합쳐 줄이기 때문에 어느 구간도 빠지지 않는다.
    assert result.scenes_read_by_yujin == result.scenes_total
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

    assert "결론은 이겁니다" in runtime.shown_text


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

        def generate_structured(self, *, project_id, task_type, prompt, response_schema, wait_seconds=None):
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
        def generate_structured(self, *, project_id, task_type, prompt, response_schema, wait_seconds=None):
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


def test_the_prompt_asks_whether_it_spreads_and_the_compose_step_asks_for_a_hook() -> None:
    """배선 검증. 2026-09-12부터 기준은 형식이 아니라 **확산**이다.

    훅은 이제 낱개 장면의 분류표가 아니라 **짜기 단계**의 요건이다 -- 퍼지는
    숏폼은 첫 1~2초에 붙잡는 것이고, 그건 이어진 하나에 대한 요구다.
    """

    runtime = _JudgeRuntime()

    pick_short_form_scenes(_long_form(count=6), project_id="proj-1", runtime=runtime)

    scan = runtime.prompts[0]
    assert "퍼질" in scan
    assert "평평한 결론" in scan
    assert "숫자가 없어도 퍼질 수 있다" in scan


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
    assert "매출이 3배 늘었어요" not in runtime.shown_text
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

        def generate_structured(self, *, project_id, task_type, prompt, response_schema, wait_seconds=None):
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


# ---------------------------------------------------------------------------
# 2026-09-12: 자르는 게 아니라 **퍼질까를 판단한다**
#
# owner 지시: "단순히 자르는것보다 자극적으로 숏폼이 확산할수 있을정도로 llm 이
# 구분 하도록 생각하면서 만들어야지." 그리고 발화에서 자른다.
# ---------------------------------------------------------------------------


class _SpreadRuntime:
    """두 단계를 다 하는 가짜 유진 -- 훑기(대목마다 점수)와 짜기(후보 숏폼).

    `spreads`는 대목의 글을 받아 퍼질지 정한다. 자막 길이도, 숫자 낱말도 안 본다.
    """

    def __init__(self, spreads=None, *, compose_reason="첫마디가 통념을 뒤집고 끝이 결과로 닫혀요") -> None:
        self._spreads = spreads or (lambda text: "퍼질" in text)
        self._compose_reason = compose_reason
        self.scan_prompts: list[str] = []
        self.compose_prompts: list[str] = []

    @staticmethod
    def _lines(prompt: str, marker: str) -> list[tuple[int, str]]:
        rows: list[tuple[int, str]] = []
        for line in prompt.split(marker, 1)[1].splitlines():
            stripped = line.strip()
            if not stripped[:1].isdigit():
                continue
            number_text, _, rest = stripped.partition(". ")
            rows.append((int(number_text), rest))
        return rows

    def generate_structured(self, *, project_id, task_type, prompt, response_schema, wait_seconds=None):
        if "고를 대목:" in prompt:
            self.compose_prompts.append(prompt)
            rows = self._lines(prompt, "고를 대목:")
            output = {
                "thinking": "손을 멈추게 하는 건 통념을 뒤집는 첫마디다",
                "candidates": [
                    {"lines": [number for number, _ in rows], "reason": self._compose_reason}
                ],
                "chosen": 1,
                "schema_version": "videobox.short-form-compose.v1",
            }
        else:
            self.scan_prompts.append(prompt)
            picks = [
                {"scene": number, "worth": 5}
                for number, text in self._lines(prompt, "고를 장면:")
                if self._spreads(text)
            ]
            output = {"schema_version": "videobox.short-form-spread-scan.v1", "picks": picks}
        return StructuredLLMResponse(
            provider_name="local_qwen",
            model_name="qwen/qwen3.8-27b",
            output_data=output,
            raw_text=json.dumps(output, ensure_ascii=False),
            metadata={},
        )

    @property
    def shown_text(self) -> str:
        return "\n".join(self.scan_prompts)


def _board(count: int, *, scene_sec: float = 12.0) -> list[dict[str, object]]:
    """장면 `count`개. 자막은 비어 있다 -- 판단 재료는 전사에서 온다."""

    return [
        {
            "segment_id": f"timeline_001:{index:03d}",
            "caption_text": "",
            "start_sec": float(index) * scene_sec,
            "end_sec": float(index + 1) * scene_sec,
            "source_offset_sec": float(index) * scene_sec,
        }
        for index in range(count)
    ]


def _owner_shaped_utterances() -> list[dict[str, object]]:
    """대표님 실제 영상의 모양. **퍼지는 한마디에 숫자도 결과 낱말도 없다.**

    `"그걸 알면 제가 팔지 뭐하러 알려 줄까요?"`(55~60초)가 실제로 그렇다.
    """

    rows: list[dict[str, object]] = []
    cursor = 0.0
    def add(text: str, seconds: float) -> None:
        nonlocal cursor
        rows.append({"start_sec": cursor, "end_sec": cursor + seconds, "text": text})
        cursor += seconds

    add("오늘은 세 가지를 알려드릴게요 목차는 이렇습니다", 10.0)
    add("안녕하세요 오랜만에 영상을 찍네요 구독 부탁드립니다", 10.0)
    # 여기가 핵심 -- 퍼질 만하지만 숫자·결과 낱말이 하나도 없다.
    add("그걸 알면 제가 팔지 뭐하러 알려 줄까요 퍼질 한마디", 10.0)
    add("카테고리를 정하고 데이터를 보고 테스트를 반복하면 됩니다", 10.0)
    add("정리하면 3단계 루틴을 꾸준히 반복해야 된다는 점입니다", 10.0)
    add("더보기란에 무료 자료가 준비되어 있으니 확인해 보세요", 10.0)
    return rows


def test_a_passage_that_would_spread_without_number_words_is_not_hidden_from_yujin() -> None:
    """**기준 바꾸기의 핵심.** 숫자·결과 낱말이 없어도 유진 눈에 와야 한다.

    옛 추리기는 낱말로 먼저 걸렀다. 그래서 대표님 영상에서 가장 퍼질 한마디를
    유진이 볼 기회조차 없을 수 있었다.
    """

    runtime = _SpreadRuntime()

    result = pick_short_form_scenes(
        _board(6),
        project_id="proj-1",
        runtime=runtime,
        utterances=_owner_shaped_utterances(),
    )

    assert "뭐하러 알려 줄까요" in runtime.shown_text
    # 그리고 실제로 골라졌다 -- 24~36초 구간의 장면이다.
    assert "timeline_001:002" in result.segment_ids
    assert result.judged_by == "yujin"


def test_yujin_composes_one_short_and_the_reason_reaches_the_result() -> None:
    """낱개 점수의 합이 아니라 **이어진 하나**를 판단하고, 이유를 남긴다."""

    runtime = _SpreadRuntime()

    result = pick_short_form_scenes(
        _board(6),
        project_id="proj-1",
        runtime=runtime,
        utterances=_owner_shaped_utterances(),
    )

    assert len(runtime.compose_prompts) == 1, "후보를 짜라고 한 번은 물어야 한다"
    assert result.spread_reason == "첫마디가 통념을 뒤집고 끝이 결과로 닫혀요"


def test_the_compose_step_is_given_a_platform_range_not_a_fixed_target() -> None:
    runtime = _SpreadRuntime()

    pick_short_form_scenes(
        _board(6), project_id="proj-1", runtime=runtime, utterances=_owner_shaped_utterances()
    )

    prompt = runtime.compose_prompts[0]
    assert "20초" in prompt
    assert "60초" in prompt


def test_the_criterion_asks_whether_it_would_spread_not_what_shape_it_is() -> None:
    """형식(훅/결론/숫자 분류)을 묻지 않는다. 퍼질지를 묻는다."""

    runtime = _SpreadRuntime()

    pick_short_form_scenes(
        _board(6), project_id="proj-1", runtime=runtime, utterances=_owner_shaped_utterances()
    )

    prompt = runtime.scan_prompts[0]
    assert "퍼질" in prompt
    assert "number_or_result" not in prompt, "형식 분류표를 다시 들고 오지 마라"
    assert "평평한 결론" in prompt


def test_every_stretch_of_the_video_reaches_yujin_no_matter_how_long() -> None:
    """**버리지 않고 굵게 만든다.** 낱말로 거르지 않으니 전 구간이 유진에게 간다."""

    runtime = _SpreadRuntime(spreads=lambda text: True)
    board = _board(243, scene_sec=5.0)
    utterances = [
        {"start_sec": float(index) * 5.0, "end_sec": float(index + 1) * 5.0, "text": f"{index}번째 말"}
        for index in range(243)
    ]

    result = pick_short_form_scenes(
        board, project_id="proj-1", runtime=runtime, utterances=utterances
    )

    assert result.scenes_total == 243
    assert result.scenes_read_by_yujin == 243, "어느 구간도 유진 눈에서 빠지면 안 된다"
    # 예산: 훑기 `MAX_SCAN_CALLS`번 + 짜기 1번. 로컬 런타임 요청 상한이 30초라
    # 느린 호출은 길어지는 대신 끊기므로, 이 호출 수가 곧 벽시계 상한이다 --
    # **기록된 330초 프록시 벽을 넘을 수 없다는 것이 여기서 증명된다.**
    assert len(runtime.scan_prompts) <= MAX_SCAN_CALLS
    assert len(runtime.compose_prompts) <= 1
    worst_case_sec = (MAX_SCAN_CALLS + 1) * 30
    assert worst_case_sec < 330, worst_case_sec
    assert "242번째 말" in runtime.shown_text


def test_the_short_never_overshoots_the_platform_ceiling() -> None:
    """60초는 **상한**이다. 넘긴 뒤에 멈추면 그건 목표다.

    2026-09-12 실물에서 61.48초가 나왔다. 장면 길이가 60을 딱 나누지 않으면
    지금 코드는 마지막 장면을 담고 나서야 멈춘다.
    """

    board = _board(40, scene_sec=7.0)
    utterances = [
        {"start_sec": float(index) * 7.0, "end_sec": float(index + 1) * 7.0, "text": f"{index}번 퍼질 말"}
        for index in range(40)
    ]
    runtime = _SpreadRuntime(spreads=lambda text: True)

    result = pick_short_form_scenes(
        board, project_id="proj-1", runtime=runtime, utterances=utterances
    )

    duration_by_id = {
        str(segment["segment_id"]): float(segment["end_sec"]) - float(segment["start_sec"])
        for segment in board
    }
    total = sum(duration_by_id[segment_id] for segment_id in result.segment_ids)
    assert total <= 60.0, total
    assert result.segment_ids


def test_a_short_is_still_cut_when_the_project_has_no_transcript() -> None:
    """전사가 없으면 장면 자막을 읽는다. **경로는 하나다.**"""

    segments = [
        {"segment_id": "seg-1", "caption_text": "퍼질 한마디입니다", "start_sec": 0.0, "end_sec": 10.0},
        {"segment_id": "seg-2", "caption_text": "그냥 하는 말", "start_sec": 10.0, "end_sec": 20.0},
    ]
    runtime = _SpreadRuntime()

    result = pick_short_form_scenes(segments, project_id="proj-1", runtime=runtime, utterances=None)

    assert result.segment_ids == ("seg-1",)
    assert result.judged_by == "yujin"
    assert "장면 자막" in result.notice


class _FakeClock:
    """가짜 벽시계.

    **더하지 않고 `max`로 민다.** 동시에 도는 호출 둘이 각자 150초를 쓰면 벽시계는
    150초를 지나는 것이지 300초가 아니다 -- 더하면 이 시험이 동시에 묻는 이득을
    못 보고 예산을 두 배로 세게 된다.
    """

    def __init__(self) -> None:
        self._now = 0.0
        self._lock = threading.Lock()

    def __call__(self) -> float:
        return self._now

    def reach(self, moment: float) -> None:
        with self._lock:
            self._now = max(self._now, moment)


class _WaitingRuntime:
    """호출마다 **실제로 기다리는** 가짜 유진. 시계는 가짜다.

    2026-09-12 실물이 가르쳐 준 것: 훑기 한 호출이 26~130초, 짜기 한 호출이
    267초다(대표님 기계에 모델 둘이 올라가 있어 초당 1~2낱말). 30초 상한으로는
    전부 끊긴다. 이 대역이 그 모양을 시험에 들여온다 -- 받은 상한만큼 가짜 시계를
    밀고, 상한보다 오래 걸리는 호출은 `LLMProviderError`를 던진다.
    """

    def __init__(self, *, scan_needs: float, compose_needs: float, clock: _FakeClock) -> None:
        self._scan_needs = scan_needs
        self._compose_needs = compose_needs
        self._clock = clock
        self.waits: list[tuple[str, int]] = []
        self.in_flight = 0
        self.max_in_flight = 0
        self._lock = threading.Lock()
        # 묶음 둘이 **동시에** 여기 있는지 실제로 확인한다. 차례로 부르면 둘째가
        # 첫째를 기다리므로 이 문이 5초에 깨진다.
        self._gate = threading.Barrier(2, timeout=5)

    def generate_structured(
        self, *, project_id, task_type, prompt, response_schema, wait_seconds=None
    ):
        stage = "compose" if "고를 대목:" in prompt else "scan"
        entered_at = self._clock()
        with self._lock:
            self.waits.append((stage, int(wait_seconds or 0)))
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if stage == "scan":
                try:
                    self._gate.wait()
                except threading.BrokenBarrierError:
                    pass
            needs = self._scan_needs if stage == "scan" else self._compose_needs
            allowed = float(wait_seconds or 0)
            self._clock.reach(entered_at + min(needs, allowed))
            if needs > allowed:
                raise LLMProviderError(
                    provider_name="local_qwen",
                    message="Local Qwen request timed out.",
                    retryable=True,
                    error_code="LOCAL_TIMEOUT",
                )
            if stage == "compose":
                rows = _SpreadRuntime._lines(prompt, "고를 대목:")
                output = {
                    "thinking": "생각",
                    "candidates": [
                        {"lines": [number for number, _ in rows], "reason": "퍼질 이유"}
                    ],
                    "chosen": 1,
                    "schema_version": "videobox.short-form-compose.v1",
                }
            else:
                output = {
                    "schema_version": "videobox.short-form-spread-scan.v1",
                    "picks": [
                        {"scene": number, "worth": 5}
                        for number, _ in _SpreadRuntime._lines(prompt, "고를 장면:")
                    ],
                }
            return StructuredLLMResponse(
                provider_name="local_qwen",
                model_name="qwen/qwen3.8-27b",
                output_data=output,
                raw_text=json.dumps(output, ensure_ascii=False),
                metadata={},
            )
        finally:
            with self._lock:
                self.in_flight -= 1


def _two_batch_board():
    """묶음 둘이 나오는 판(대목 아홉 = 8 + 1)."""

    board = _board(18, scene_sec=5.0)
    utterances = [
        {"start_sec": float(index) * 5.0, "end_sec": float(index + 1) * 5.0, "text": f"{index}번 퍼질 말"}
        for index in range(18)
    ]
    return board, utterances


def test_the_log_says_whether_each_batch_answered_or_never_came_back(caplog) -> None:
    """**"못 찾았다"와 "못 물어봤다"를 로그로 가른다.**

    기록된 사고: 유진이 "없다"고 할 때 후보가 안 간 것인지 갔는데 못 고른 것인지
    가릴 로그가 없어 네 겹을 헛돌았다. 실물에서도 똑같이 걸렸다 -- 묶음 여섯 중
    넷이 시간 초과했는데 문구는 "유진이 읽어 봤지만 못 찾아서"라고 말했다(2026-09-12).
    """

    board, utterances = _two_batch_board()
    clock = _FakeClock()
    runtime = _WaitingRuntime(scan_needs=10.0, compose_needs=10.0, clock=clock)

    with caplog.at_level(logging.INFO, logger="videobox_core_engine.short_form_scene_pick"):
        pick_short_form_scenes(
            board, project_id="proj-1", runtime=runtime, utterances=utterances, clock=clock
        )

    text = caplog.text
    assert "훑기 묶음 1/2" in text, "어느 묶음이 어떻게 됐는지 로그가 말해야 한다"
    assert "훑기 묶음 2/2" in text
    assert "고른 대목" in text, "유진이 무엇을 돌려줬는지 로그에 있어야 한다"
    assert "짜기" in text
    assert "묶음 2/2 답함" in text, "몇 묶음이 답했는지 한 줄로 요약해야 한다"


def test_the_log_names_the_reason_a_batch_never_answered(caplog) -> None:
    """시간 초과는 **시간 초과로** 로그에 남아야 한다. 조용히 넘기면 실물에서
    무엇이 막혔는지 아무도 모른다."""

    board, utterances = _two_batch_board()
    clock = _FakeClock()
    # 필요한 시간이 상한보다 길다 -- 두 묶음 다 끊긴다.
    runtime = _WaitingRuntime(
        scan_needs=SCAN_WAIT_CEILING_SECONDS + 10.0, compose_needs=10.0, clock=clock
    )

    with caplog.at_level(logging.INFO, logger="videobox_core_engine.short_form_scene_pick"):
        result = pick_short_form_scenes(
            board, project_id="proj-1", runtime=runtime, utterances=utterances, clock=clock
        )

    assert result.fallback_reason == "yujin_unavailable"
    assert "LOCAL_TIMEOUT" in caplog.text, "무엇 때문에 못 받았는지 로그가 말해야 한다"


def test_the_found_nothing_notice_says_how_much_yujin_actually_read() -> None:
    """**문구와 숫자가 어긋나면 안 된다.**

    2026-09-12 실물: 문구는 "유진이 읽어 봤지만"인데 `scenes_read_by_yujin`은 0이었다.
    이 기능의 정직성 계약은 "누가 골랐는지·얼마나 읽었는지를 속이지 않는다"이고,
    읽지 않았는데 읽었다고 말하는 것은 반대 방향으로 그 계약을 깬다.
    """

    runtime = _SpreadRuntime(spreads=lambda text: False)

    result = pick_short_form_scenes(
        _board(6), project_id="proj-1", runtime=runtime, utterances=_owner_shaped_utterances()
    )

    assert result.judged_by == "caption_density"
    assert result.fallback_reason == "yujin_found_nothing"
    assert "읽어" in result.notice, "읽고 못 찾은 것과 못 물어본 것은 다르다"
    assert result.scenes_read_by_yujin > 0, "읽었다고 말했으면 숫자도 읽은 것이어야 한다"
    assert f"{result.scenes_read_by_yujin}개" in result.notice


def test_a_notice_that_names_yujin_reading_never_comes_with_a_zero_count() -> None:
    """반대 방향도 막는다. 아무것도 못 읽었으면 읽었다고 쓰지 않는다."""

    for spreads in (lambda text: False, lambda text: True):
        runtime = _SpreadRuntime(spreads=spreads)
        result = pick_short_form_scenes(
            _board(6), project_id="proj-1", runtime=runtime, utterances=_owner_shaped_utterances()
        )
        if any(word in result.notice for word in ("읽어", "읽고", "읽었")):
            assert result.scenes_read_by_yujin > 0, result.notice


def test_the_batches_are_read_at_the_same_time_so_each_one_can_wait_longer() -> None:
    """**기다리기를 프록시 벽 안에 넣는 방법.**

    실측(2026-09-12, 대표님 영상): 훑기 한 호출이 26~130초다. 차례로 부르면
    여섯 묶음이 최악 780초가 되어 nginx 330초 벽을 넘는다. 동시에 부르면
    벽시계가 **가장 느린 한 호출**이 된다(실측 129.8초, 여섯 묶음 다 답함).
    """

    board, utterances = _two_batch_board()
    clock = _FakeClock()
    runtime = _WaitingRuntime(scan_needs=20.0, compose_needs=20.0, clock=clock)

    pick_short_form_scenes(
        board, project_id="proj-1", runtime=runtime, utterances=utterances, clock=clock
    )

    assert runtime.max_in_flight >= 2, "묶음을 차례로 부르면 기다릴 시간이 안 남는다"
    scan_waits = [wait for stage, wait in runtime.waits if stage == "scan"]
    expected = scan_wait_seconds(SYNCHRONOUS_BUDGET_SECONDS)
    assert scan_waits and all(wait == expected for wait in scan_waits), scan_waits
    assert any(stage == "compose" for stage, _ in runtime.waits)


def test_the_background_path_waits_longer_per_batch_than_one_request_can_afford() -> None:
    """**한 묶음을 얼마나 기다릴지는 예산이 정한다.**

    실물(2026-09-12, 대표님 영상): 여섯 묶음을 동시에 물었더니 셋은 42~143초에
    답하고 셋은 150초 상한에서 끊겨 **94장면 중 44개만** 읽혔다. 뒤에서 도는
    자리에는 벽이 없으니 더 기다릴 수 있다 -- 그리고 **빠른 날에는 공짜다.**
    묶음이 동시에 도니까 훑기 단계는 상한만큼 걸리는 게 아니라 **가장 느린 한
    호출이 끝나면** 끝난다(실측 129.8초).

    같은 요청 안에서 도는 자리는 예산의 절반까지만 쓴다 -- 나머지 절반이 짜기
    몫이다. 한 호출에 예산을 다 주면 짜기가 아예 못 돌아 "왜 퍼질까"가 사라진다.
    """

    assert scan_wait_seconds(BACKGROUND_BUDGET_SECONDS) > scan_wait_seconds(
        SYNCHRONOUS_BUDGET_SECONDS
    ), "뒤에서 돌 때 더 기다리지 않으면 영상 절반이 유진 눈에서 빠진다"
    assert scan_wait_seconds(BACKGROUND_BUDGET_SECONDS) == SCAN_WAIT_CEILING_SECONDS
    # 짜기 몫이 남아야 한다. 실측 짜기 266.8~295.0초.
    for budget in (SYNCHRONOUS_BUDGET_SECONDS, BACKGROUND_BUDGET_SECONDS):
        assert budget - scan_wait_seconds(budget) >= COMPOSE_MIN_WAIT_SECONDS, budget


def test_the_compose_step_gets_more_time_than_one_request_could_ever_give_it() -> None:
    """짜기도 예산이 정한다. **330초로는 실물에서 끊겼다.**

    실측(2026-09-12, 대표님 영상): 짜기 한 호출이 266.8초·295.0초에 답했고, 다른
    작업이 같은 모델을 쓰는 동안에는 330초 상한에서 끊겼다 -- 그때 화면에는
    "후보를 여러 개 짜 보지는 못해서 퍼질 이유는 남기지 못했어요"가 나갔다.
    뒤에서 도는 자리에는 벽이 없으니 프록시가 줄 수 있는 것보다 더 준다.

    같은 요청 안에서 도는 자리는 예산 안에 갇힌다 -- 벽을 넘으면 대표님이 우리
    문구 대신 프록시의 504 HTML을 본다.
    """

    # 실측대로 훑기가 221.5초를 쓴 뒤.
    assert compose_wait_seconds(BACKGROUND_BUDGET_SECONDS, 221.5) > 330, (
        "330초로는 실물에서 끊겼다 -- 그러면 화면에 나갈 퍼질 이유가 사라진다"
    )
    sync_spent = float(scan_wait_seconds(SYNCHRONOUS_BUDGET_SECONDS))
    assert (
        sync_spent + compose_wait_seconds(SYNCHRONOUS_BUDGET_SECONDS, sync_spent)
        <= SYNCHRONOUS_BUDGET_SECONDS
    ), "같은 요청 안에서는 예산을 넘을 수 없다"


def test_the_judgement_stops_before_the_proxy_cuts_the_owner_off() -> None:
    """같은 요청 안에서 도는 부르는 쪽(유진 채팅·처음 만들기)은 예산을 넘지 않는다.

    넘기면 대표님은 우리 한국말 대신 nginx의 504 HTML을 본다 -- 제품이 고장 난
    것으로 보인다. 그래서 짜기를 시작할 시간이 없으면 **시작하지 않고** 그 사실을
    문구로 말한다(인포그래픽의 `TOTAL_BUDGET_SECONDS`와 같은 방식).
    """

    board, utterances = _two_batch_board()
    clock = _FakeClock()
    # 훑기가 예산을 거의 다 쓴다 -- 짜기를 시작할 자리가 없다.
    budget = 2.0 * (COMPOSE_MIN_WAIT_SECONDS - 5.0)
    runtime = _WaitingRuntime(
        scan_needs=float(scan_wait_seconds(budget)), compose_needs=10.0, clock=clock
    )

    result = pick_short_form_scenes(
        board,
        project_id="proj-1",
        runtime=runtime,
        utterances=utterances,
        clock=clock,
        budget_seconds=budget,
    )

    assert clock() <= budget, clock()
    assert not any(stage == "compose" for stage, _ in runtime.waits), "예산이 없으면 짜기를 시작하지 않는다"
    assert result.spread_reason is None
    assert "퍼질 이유는 남기지 못했어요" in result.notice


def test_the_background_budget_lets_yujin_wait_longer_than_one_request_can() -> None:
    """화면의 `다시 만들기`는 뒤에서 돌아 프록시 벽이 없다 -- 그래서 더 기다린다.

    실측(2026-09-12): 훑기 129.8초 + 짜기 266.8초 = 약 400초. **한 요청 안에서는
    절대 안 끝난다**(330초 벽). 뒤에서 돌면 끝난다.
    """

    board, utterances = _two_batch_board()
    clock = _FakeClock()
    runtime = _WaitingRuntime(scan_needs=130.0, compose_needs=267.0, clock=clock)

    result = pick_short_form_scenes(
        board,
        project_id="proj-1",
        runtime=runtime,
        utterances=utterances,
        clock=clock,
        budget_seconds=BACKGROUND_BUDGET_SECONDS,
    )

    assert result.judged_by == "yujin"
    assert result.spread_reason == "퍼질 이유", "뒤에서 돌면 왜 퍼질지가 살아 온다"
    assert clock() > 330, "한 요청 안에서는 못 끝내는 일이라는 것이 이 시험의 뜻이다"
