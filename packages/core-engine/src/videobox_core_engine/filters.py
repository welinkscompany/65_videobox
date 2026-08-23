"""화면 클립의 색감 -- 필터.

**왜 여섯 개뿐인가.** 캡컷 필터 탭에는 이름표가 열다섯 개 넘게 있고 분류만
열셋이다(`docs/reference/capcut-observed-2026-08-22.ko.md` §5). 그런데 그건
전환과 같은 사정이다 -- **캡컷이 자기 서버에서 받아 두는 자원을 가리키는
이름표**이지 픽셀이 아니다. 우리 ffmpeg 렌더러는 그 이름으로 아무것도 못 그린다.

그래서 목록을 옮겨 오지 않고, **ffmpeg가 직접 그려 주는 것** 중에서 서로
생김새가 겹치지 않는 여섯 갈래를 골랐다. 갈래가 겹치면 고르는 사람에게
선택지가 느는 게 아니라 고민만 는다(`transitions.py`와 같은 기준).

**범위 확인.** `implementation-plan.ko.md` §2.1은 "전문 색보정"을 범위 밖으로
둔다. 여기 있는 것은 색보정 도구가 아니라 **한 번 눌러 고르는 색감 여섯 개**다.
곡선·LUT·채널별 조정 같은 것은 여전히 범위 밖이고, 여기 넣지 않는다.

**추가하려면** `FILTER_CATALOG`에 한 줄 넣으면 된다. 렌더러는 이 표만 본다.
다만 넣기 전에 컨테이너의 ffmpeg에서 실제로 도는지 재 볼 것 -- 개발 기기와
컨테이너의 ffmpeg 판이 달라서 로컬만 통과한 사고가 이미 있었다
(`ffmpeg_final_renderer.py`의 `settb` 주석).
"""
from __future__ import annotations

from typing import Any


# 고른 여섯 갈래와 그 ffmpeg 표현. 2026-08-23에 컨테이너 ffmpeg에서 여섯 개
# 전부 실제로 돌려 보고 넣었다.
FILTER_CATALOG: dict[str, dict[str, str]] = {
    # 색을 아예 뺀다. 다른 다섯과 절대 헷갈리지 않는 하나.
    "mono": {"label": "흑백으로", "family": "색 빼기", "ffmpeg": "hue=s=0"},
    # 오래된 필름 느낌. 색이 바래면서 대비가 눕는다.
    "vintage": {"label": "옛날 필름", "family": "옛날", "ffmpeg": "curves=preset=vintage"},
    # 노란빛으로 기울인다. 실내·저녁 장면에 쓴다.
    "warm": {"label": "따뜻하게", "family": "온도", "ffmpeg": "colortemperature=temperature=7000"},
    # 푸른빛으로 기울인다. 아침·바깥 장면에 쓴다.
    "cool": {"label": "차갑게", "family": "온도", "ffmpeg": "colortemperature=temperature=4500"},
    # 색과 대비를 함께 올린다. 음식·제품처럼 또렷해야 하는 것에.
    "vivid": {"label": "진하게", "family": "진하기", "ffmpeg": "eq=saturation=1.35:contrast=1.10"},
    # 색을 덜어 내고 어두운 쪽을 들어 올린다. 배경으로 깔 화면에.
    "faded": {"label": "옅게", "family": "진하기", "ffmpeg": "eq=saturation=0.72,curves=preset=lighter"},
    # 밝히면서 가장자리를 부드럽게 눕힌다. 얼굴이 나오는 화면에.
    # `unsharp`의 음수 amount가 흐리게 하는 쪽이다 -- 밝기만 올리면 뽀샤시가
    # 아니라 그냥 허옇게 뜬 화면이 된다.
    "bright": {"label": "뽀샤시하게", "family": "밝기",
               "ffmpeg": "eq=brightness=0.08:saturation=1.06:contrast=0.96,unsharp=7:7:-1.1:7:7:-0.6"},
    # 갈색 한 가지로 눕힌다. `vintage`는 원래 색이 남지만 이건 색을 갈아 끼운다.
    "sepia": {"label": "세피아", "family": "옛날",
              "ffmpeg": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131"},
    # 어두운 쪽은 푸르게, 밝은 쪽은 붉게. 영화에서 흔히 보는 그 나뉨이다.
    # `warm`/`cool`은 화면 전체를 한쪽으로 밀지만 이건 밝기에 따라 갈라 놓는다.
    "cinematic": {"label": "영화처럼", "family": "온도",
                  "ffmpeg": "curves=r=0/0 0.5/0.58 1/1:b=0/0 0.5/0.42 1/1,eq=saturation=1.08:contrast=1.06"},
}

FILTER_TYPES = frozenset(FILTER_CATALOG)

# 누가 골랐는가. `transitions.py`와 같은 이유로 자리를 미리 만들어 둔다 --
# 유진이 골라 준 것을 되돌리거나 설명하려면 출처가 남아 있어야 한다.
FILTER_CHOOSERS = frozenset({"owner", "yujin"})
DEFAULT_FILTER_CHOOSER = "owner"


def normalize_filter(value: object) -> dict[str, Any] | None:
    """색감 값 하나를 정규화한다. 없으면 ``None``.

    ``None``과 ``{"type": "none"}``을 **둘 다** "색감 없음"으로 받는다 --
    화면에서 골랐다가 다시 끄는 길이 있어야 하고, 그때 보내는 값이 무엇이든
    같은 뜻이어야 한다(`normalize_transition`과 같은 규칙).
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("filter_must_be_an_object")
    raw_type = str(value.get("type") or "").strip().lower()
    if not raw_type or raw_type == "none":
        return None
    if raw_type not in FILTER_TYPES:
        raise ValueError("filter type must be one of: " + ", ".join(sorted(FILTER_TYPES)))
    chosen_by = str(value.get("chosen_by") or DEFAULT_FILTER_CHOOSER).strip().lower()
    if chosen_by not in FILTER_CHOOSERS:
        raise ValueError("filter chosen_by must be one of: " + ", ".join(sorted(FILTER_CHOOSERS)))
    return {"type": raw_type, "chosen_by": chosen_by}


def filter_chain(value: object) -> str:
    """정규화한 색감을 ffmpeg 필터 문자열로. 없으면 빈 문자열.

    **표에 있는 것만 통과한다.** 이 값은 결국 필터 그래프 문자열에 그대로
    들어가므로, 모르는 값이 흘러가면 안 된다(`transitions.py`와 같은 이유).
    """
    normalized = normalize_filter(value)
    if normalized is None:
        return ""
    return FILTER_CATALOG[normalized["type"]]["ffmpeg"]
