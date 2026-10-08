"""설명 모션 템플릿 목록과 변수 검사 -- 들어오는 것은 숫자·글뿐이고, 판에 맞는 길이만 받는다."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from videobox_core_engine.motion_templates import (
    MAX_MOTION_DURATION_SEC,
    MIN_MOTION_DURATION_SEC,
    MOTION_TEMPLATE_KEYS,
    MOTION_TEMPLATES,
    MotionTemplateUnknown,
    MotionVariablesInvalid,
    motion_default_title,
    parse_motion_variables,
    resolve_motion_template,
)

ROOT = Path(__file__).resolve().parents[1]
GOOD = {
    "bar_compare": {"title": "월 수익 비교", "unit": "만", "bars": [{"label": "쿠팡", "value": 1280}, {"label": "자사몰", "value": 430}]},
    "money_counter": {"lead": "첫 달 순매출", "amount": 12345678},
    "step_list": {"title": "처음 시작하는 3단계", "steps": ["소싱", "상세페이지", "정산"]},
}


def _problems(key: str, variables: dict) -> str:
    with pytest.raises(MotionVariablesInvalid) as caught:
        parse_motion_variables(key, variables)
    return " / ".join(caught.value.problems)


def test_three_templates_live_in_one_place() -> None:
    assert tuple(t.key for t in MOTION_TEMPLATES) == MOTION_TEMPLATE_KEYS == ("bar_compare", "money_counter", "step_list")
    assert [t.korean_name for t in MOTION_TEMPLATES] == ["막대 비교", "금액 카운터", "단계 목록"]


def test_the_catalog_matches_the_bridge_and_the_template_folders() -> None:
    """파이썬 목록·다리·템플릿 폴더가 따로 놀면 화면에 있는 종류가 다리에서 400이 된다."""
    spec = importlib.util.spec_from_file_location("motion_bridge_catalog_check", ROOT / "scripts" / "host_motion_service.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["motion_bridge_catalog_check"] = module
    spec.loader.exec_module(module)
    assert module.TEMPLATE_KEYS == MOTION_TEMPLATE_KEYS
    assert (module.MIN_DURATION_SEC, module.MAX_DURATION_SEC) == (MIN_MOTION_DURATION_SEC, MAX_MOTION_DURATION_SEC)
    for key in MOTION_TEMPLATE_KEYS:
        assert (ROOT / "scripts" / "motion-bridge" / "templates" / key / "index.html").is_file()


@pytest.mark.parametrize("key", MOTION_TEMPLATE_KEYS)
def test_a_normal_request_is_accepted(key: str) -> None:
    parsed = parse_motion_variables(key, GOOD[key])
    assert parsed.model_dump(mode="json")


@pytest.mark.parametrize(
    ("key", "variables"),
    [
        ("bar_compare", {**GOOD["bar_compare"], "title": "<b>굵게</b>"}),
        ("bar_compare", {**GOOD["bar_compare"], "bars": [{"label": "<script>", "value": 1}, {"label": "b", "value": 2}]}),
        ("money_counter", {**GOOD["money_counter"], "caption": "a>b"}),
        ("step_list", {**GOOD["step_list"], "steps": ["정상", "<img src=x onerror=alert(1)>"]}),
    ],
)
def test_markup_is_refused_in_every_text(key: str, variables: dict) -> None:
    assert "< > 기호" in _problems(key, variables)


def test_control_characters_are_refused() -> None:
    assert "쓸 수 없는 글자" in _problems("step_list", {"title": "줄\n바꿈", "steps": ["a", "b"]})


def test_korean_text_longer_than_the_board_is_refused() -> None:
    assert "제목: 24자까지" in _problems("bar_compare", {**GOOD["bar_compare"], "title": "가" * 25})
    assert "이름: 10자까지" in _problems("bar_compare", {**GOOD["bar_compare"], "bars": [{"label": "나" * 11, "value": 1}, {"label": "b", "value": 2}]})


@pytest.mark.parametrize(("key", "variables", "expected"), [
    ("bar_compare", {**GOOD["bar_compare"], "bars": [{"label": "a", "value": 1}]}, "막대: 2개 이상"),
    ("bar_compare", {**GOOD["bar_compare"], "bars": [{"label": "a", "value": 1}] * 6}, "막대: 5개까지"),
    ("step_list", {"title": "t", "steps": ["a"] * 6}, "단계: 5개까지"),
])
def test_counts_are_bounded(key: str, variables: dict, expected: str) -> None:
    assert expected in _problems(key, variables)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 1e13])
def test_bar_values_must_be_real_numbers_in_range(value: float) -> None:
    assert "값" in _problems("bar_compare", {**GOOD["bar_compare"], "bars": [{"label": "a", "value": value}, {"label": "b", "value": 2}]})


@pytest.mark.parametrize("amount", [-1, 10**12 + 1, 1.5])
def test_money_must_be_a_whole_amount_in_range(amount) -> None:
    assert "금액" in _problems("money_counter", {"amount": amount})


def test_unknown_fields_are_refused() -> None:
    assert "알 수 없는 칸" in _problems("step_list", {**GOOD["step_list"], "script": "alert(1)"})


def test_all_zero_bars_say_so() -> None:
    assert "0보다 커야" in _problems("bar_compare", {"title": "t", "bars": [{"label": "a", "value": 0}, {"label": "b", "value": 0}]})


def test_an_unknown_template_is_refused() -> None:
    with pytest.raises(MotionTemplateUnknown):
        resolve_motion_template("free_form")


def test_the_default_title_comes_from_what_was_written() -> None:
    assert motion_default_title("bar_compare", parse_motion_variables("bar_compare", GOOD["bar_compare"])) == "월 수익 비교"
    assert motion_default_title("money_counter", parse_motion_variables("money_counter", GOOD["money_counter"])) == "첫 달 순매출"
    assert motion_default_title("money_counter", parse_motion_variables("money_counter", {"amount": 5})) == "금액 카운터"
