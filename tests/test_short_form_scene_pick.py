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
    MAX_SCAN_CALLS,
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

    def generate_structured(self, *, project_id, task_type, prompt, response_schema):
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
