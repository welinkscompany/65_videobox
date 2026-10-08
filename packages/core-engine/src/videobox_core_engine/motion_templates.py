"""설명 모션 템플릿 목록과 변수 검사.

## 왜 엄격한가

모션은 템플릿 HTML에 **숫자와 글만** 채워 그린다. 모델(유진)이 HTML이나 코드를 쓰지
않는다 -- 그래서 들어오는 글에서 `<`·`>`·제어 문자를 막으면 템플릿 밖으로 새는 길이
없다. 글 길이도 판에 맞게 막는다: 한국어는 넘치면 잘리거나 겹치므로 그리기 전에
"몇 자까지"를 돌려준다.

3단계의 유진도 이 함수(`parse_motion_variables`)를 그대로 쓴다. 검사를 두 벌 만들지 않는다.
다리(`scripts/host_motion_service.py`)와 템플릿 폴더가 같은 목록을 가져야 하고,
`tests/test_motion_templates.py`가 셋의 일치를 지킨다.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BeforeValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

MOTION_TEMPLATE_KEYS = ("bar_compare", "money_counter", "step_list")
MIN_MOTION_DURATION_SEC = 3.0
MAX_MOTION_DURATION_SEC = 30.0
MOTION_LAYOUTS = ("full", "overlay")


def check_safe_text(value: str) -> str:
    """`<`·`>`와 제어·서식·대리 문자를 거절한다."""

    if "<" in value or ">" in value:
        raise ValueError("text_has_markup")
    if any(unicodedata.category(ch) in ("Cc", "Cf", "Cs") for ch in value):
        raise ValueError("text_has_control")
    return value


def _check_if_text(value: Any) -> Any:
    """길이 검사보다 **먼저** 돈다 -- 길이도 넘고 `<`도 있는 글에서 진짜 이유(기호)를
    가리지 않게 한다. 글이 아닌 값은 그대로 두어 형식 오류가 제 이름으로 나온다."""

    return check_safe_text(value) if isinstance(value, str) else value


def _text(max_length: int, *, min_length: int = 0) -> Any:
    return Annotated[
        str,
        StringConstraints(strict=True, strip_whitespace=True, min_length=min_length, max_length=max_length),
        BeforeValidator(_check_if_text),
        # 강제 변환(bytes -> str)으로 앞 검사를 비켜 가는 길을 막는다. strict와 함께 이중 방어다.
        AfterValidator(check_safe_text),
    ]


class BarItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: _text(10, min_length=1)  # type: ignore[valid-type]
    value: float = Field(ge=0, le=1e12, allow_inf_nan=False, strict=True)


class BarCompareVariables(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: _text(24, min_length=1)  # type: ignore[valid-type]
    subtitle: _text(40) = ""  # type: ignore[valid-type]
    unit: _text(4) = ""  # type: ignore[valid-type]
    bars: list[BarItem] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def _not_all_zero(self) -> "BarCompareVariables":
        if all(bar.value == 0 for bar in self.bars):
            raise ValueError("bars_all_zero")
        return self


class MoneyCounterVariables(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead: _text(20) = ""  # type: ignore[valid-type]
    amount: int = Field(ge=0, le=10**12, strict=True)
    prefix: Literal["₩", "$", ""] = "₩"
    suffix: _text(4) = ""  # type: ignore[valid-type]
    caption: _text(30) = ""  # type: ignore[valid-type]


class StepListVariables(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: _text(24, min_length=1)  # type: ignore[valid-type]
    steps: list[_text(24, min_length=1)] = Field(min_length=2, max_length=5)  # type: ignore[valid-type]


@dataclass(frozen=True)
class MotionTemplate:
    key: str
    korean_name: str
    description: str
    default_duration_sec: float
    variables_model: type[BaseModel]
    limits: Mapping[str, int]


MOTION_TEMPLATES: tuple[MotionTemplate, ...] = (
    MotionTemplate(
        "bar_compare", "막대 비교", "숫자 몇 개를 막대로 견줘요", 6.0, BarCompareVariables,
        {"title": 24, "subtitle": 40, "unit": 4, "label": 10, "min_items": 2, "max_items": 5},
    ),
    MotionTemplate(
        "money_counter", "금액 카운터", "금액이 0부터 올라가요", 5.0, MoneyCounterVariables,
        {"lead": 20, "suffix": 4, "caption": 30},
    ),
    MotionTemplate(
        "step_list", "단계 목록", "순서를 하나씩 보여 줘요", 6.0, StepListVariables,
        {"title": 24, "step": 24, "min_items": 2, "max_items": 5},
    ),
)


class MotionTemplateUnknown(KeyError):
    """목록에 없는 템플릿."""


class MotionVariablesInvalid(ValueError):
    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def resolve_motion_template(key: str) -> MotionTemplate:
    for template in MOTION_TEMPLATES:
        if template.key == key:
            return template
    raise MotionTemplateUnknown(key)


_LABELS = {
    "title": "제목", "subtitle": "작은 설명", "unit": "단위", "bars": "막대", "label": "이름",
    "value": "값", "lead": "위 문구", "amount": "금액", "prefix": "기호",
    "suffix": "뒤에 붙일 말", "caption": "아래 문구", "steps": "단계",
}


def _describe(error: Mapping[str, Any]) -> str:
    label = "내용"
    for part in reversed(tuple(error.get("loc") or ())):
        if isinstance(part, str):
            label = _LABELS.get(part, "내용")
            break
    kind = str(error.get("type") or "")
    ctx = error.get("ctx") or {}
    message = str(error.get("msg") or "")
    if kind == "extra_forbidden":
        return "알 수 없는 칸이 있어요"
    if kind == "string_too_long":
        text = f"{ctx.get('max_length')}자까지 써요"
    elif kind in ("string_too_short", "missing"):
        text = "적어 주세요"
    elif kind == "too_long":
        text = f"{ctx.get('max_length')}개까지예요"
    elif kind == "too_short":
        text = f"{ctx.get('min_length')}개 이상 필요해요"
    elif kind == "value_error" and "text_has_markup" in message:
        text = "< > 기호는 쓸 수 없어요"
    elif kind == "value_error" and "text_has_control" in message:
        text = "쓸 수 없는 글자가 있어요"
    elif kind == "value_error" and "bars_all_zero" in message:
        label, text = "막대", "하나는 0보다 커야 해요"
    elif kind == "string_type":
        text = "글로 적어 주세요"
    elif kind in ("float_type", "int_type"):
        text = "숫자로 적어 주세요(따옴표 없이)"
    elif kind == "literal_error":
        text = "다시 골라 주세요"
    else:
        text = "숫자를 다시 확인해 주세요"
    return f"{label}: {text}"


def parse_motion_variables(template_key: str, variables: Mapping[str, Any]) -> BaseModel:
    template = resolve_motion_template(template_key)
    if not isinstance(variables, Mapping):
        raise MotionVariablesInvalid(("내용: 칸을 채워 주세요",))
    try:
        return template.variables_model.model_validate(dict(variables))
    except ValidationError as exc:
        problems = tuple(dict.fromkeys(_describe(error) for error in exc.errors()))
        raise MotionVariablesInvalid(problems) from exc


def motion_default_title(template_key: str, parsed: BaseModel) -> str:
    if template_key in ("bar_compare", "step_list"):
        return str(getattr(parsed, "title", "") or "")
    return str(getattr(parsed, "lead", "") or getattr(parsed, "caption", "") or "금액 카운터")


__all__ = [
    "MAX_MOTION_DURATION_SEC", "MIN_MOTION_DURATION_SEC", "MOTION_LAYOUTS",
    "MOTION_TEMPLATES", "MOTION_TEMPLATE_KEYS", "BarCompareVariables", "BarItem",
    "MoneyCounterVariables", "MotionTemplate", "MotionTemplateUnknown",
    "MotionVariablesInvalid", "StepListVariables", "check_safe_text",
    "motion_default_title", "parse_motion_variables", "resolve_motion_template",
]
