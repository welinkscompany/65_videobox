"""자막 화면의 칸 ↔ 완성본 픽셀을 맞대는 장치.

2026-08-20에 `배경 색` 칸이 화면에는 있는데 완성본에는 아무 일도 하지 않는 상태로
오래 있었다. 화면 테스트도 렌더 테스트도 각자 초록이었다 -- **이음매를 잰 것이
아무것도 없었기 때문이다.**

여기서 재는 이음매는 하나다. **화면이 바꿀 수 있는 칸은 구운 화면의 픽셀을
바꾸어야 한다.**

## 왜 ASS 문자열이 아니라 픽셀인가

"값을 바꾸면 출력이 달라지는가"를 ASS 문자열로 재면 그 결함을 **놓친다**. 실측했다:
결함이 있던 코드는 `background_color`를 ASS의 `BackColour` 칸에 넣고 있었고, 값이
바뀌면 ASS 문자열도 분명히 달라졌다. 다만 `BackColour`는 `BorderStyle=1`에서
그림자 색으로만 쓰이고 그림자 두께가 0으로 박혀 있어서 **화면에는 한 픽셀도
닿지 않았다**. 문자열은 달라지는데 결과는 같은 것 -- 그것이 정확히 이 결함이었다.

그래서 이 파일은 ffmpeg로 실제로 굽고 프레임을 해시해서 비교한다.

## 글꼴 이야기

제품은 컨테이너에 설치된 글꼴을 fontconfig로 찾는다. 개발 기계에는 그 글꼴들이
없을 수 있어서, 여기서는 저장소에 함께 들어 있는 파일(`assets/fonts/korean`)을
libass에 직접 가리켜 준다. 재는 대상은 글꼴 설치가 아니라 **칸이 렌더에 닿는가**
하나이고, 글꼴이 실제로 설치돼 있는지는 다른 장치가 본다.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from videobox_core_engine.ass_subtitles import render_editing_session_ass
from videobox_domain_models.caption_style import CaptionStyle


ROOT = Path(__file__).resolve().parents[1]
INSPECTOR_PATH = ROOT / "apps/web/src/features/editor/inspector/InspectorControls.tsx"
BUNDLED_FONTS = ROOT / "assets/fonts/korean"
FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None

CAPTION_STYLE_FIELDS: tuple[str, ...] = tuple(CaptionStyle.__dataclass_fields__)

# ---------------------------------------------------------------------------
# 렌더에 닿지 않아도 되는 칸 -- **여기 한 곳에만** 적는다.
#
# 이 목록이 길어지는 것이 곧 신호다. 이름을 하나 더 넣기 전에, 그 칸을 화면에서
# 없애는 쪽이 맞는지 먼저 따져라. 실제로 `shadow_blur_px`는 그렇게 처리했다.
# ---------------------------------------------------------------------------
FIELDS_EXEMPT_FROM_THE_RENDER: dict[str, str] = {
    "shadow_blur_px": (
        "ASS에는 그림자를 흐리게 하는 값이 아예 없고, CapCut으로 내보내는 길도"
        " 경고만 남긴다. 어느 길에서도 아무 일이 없는 값이라 화면의 칸을 없앴다."
        " 저장된 값은 남의 프리셋을 깨지 않으려고 그대로 들고 다닌다."
    ),
}


# ---------------------------------------------------------------------------
# 칸마다 "이 값이 보이려면 무엇이 함께 있어야 하는가".
#
# 값 두 개만 흔들면 되는 칸이 대부분이지만, 몇몇은 곁들이는 조건이 없으면
# 원래부터 화면에 안 나타난다. 그 조건을 여기 적어 둔다 -- 안 그러면 멀쩡한 칸이
# "렌더에 안 닿는다"고 잘못 잡힌다. 실제로 검은 배경에 검은 외곽선을 놓고
# 두께만 흔들었다가 `outline_width_px`를 오진할 뻔했다.
# ---------------------------------------------------------------------------
PROBES: dict[str, tuple[dict[str, Any], Any, Any]] = {
    "font_family": ({}, "Pretendard", "Gaegu"),
    "font_size_px": ({}, 40, 90),
    "text_color": ({}, "#FFFFFFFF", "#FF00FFFF"),
    # 두께가 있어야 색이 보인다.
    "outline_color": ({"outline_width_px": 6}, "#00FF00FF", "#0000FFFF"),
    # 기본 외곽선은 검은색이라 검은 바탕에서는 두께를 봐도 아무 차이가 없다.
    "outline_width_px": ({"outline_color": "#00FF00FF"}, 1, 9),
    "background_color": ({}, "#00000000", "#0000FFFF"),
    # ASS는 가운데 정렬이면 가로 위치를 무시한다. 왼쪽에 붙였을 때만 실제로 쓰인다.
    "position_x_percent": ({"horizontal_align": "left"}, 5, 55),
    "position_y_percent": ({}, 30, 80),
    "horizontal_align": ({}, "center", "left"),
    # 안전 영역은 94%를 넘을 때만 잘라낸다. 그 밑에서는 켜나 끄나 같다.
    "safe_area_enabled": ({"position_y_percent": 100}, True, False),
    "shadow_blur_px": ({}, 0, 9),
}

_FRAME_WIDTH = 640
_FRAME_HEIGHT = 360
_PROBE_TEXT = "자막 확인 ABC"

# `setCaptionStyle((current) => ({ ...current, <칸이름>: ... }))` -- 화면이 값을
# 바꾸는 자리를 그대로 읽는다. `...fromSnapshot(style)` 처럼 통째로 얹는 자리는
# 칸 이름이 없으므로 잡히지 않는다(그쪽은 아래 프리셋 대조가 본다).
_UI_SETTER = re.compile(r"setCaptionStyle\(\(current\)\s*=>\s*\(\{\s*\.\.\.current,\s*([A-Za-z0-9]+):")
# `currentStyle={{ font_family: ..., ... }}` 블록. 프리셋 저장으로 넘어가는 이름들이다.
_PRESET_HANDOFF = re.compile(r"currentStyle=\{\{(.*?)\}\}", re.DOTALL)
_PRESET_KEY = re.compile(r"([a-z0-9_]+):\s*captionStyle\.")


def _snake(camel: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", camel).lower()


def _screen_controlled_fields() -> frozenset[str]:
    source = INSPECTOR_PATH.read_text(encoding="utf-8")
    return frozenset(_snake(name) for name in _UI_SETTER.findall(source))


def _preset_handoff_fields() -> frozenset[str]:
    source = INSPECTOR_PATH.read_text(encoding="utf-8")
    block = _PRESET_HANDOFF.search(source)
    assert block is not None, "자막 모양을 프리셋으로 넘기는 자리를 못 찾았다."
    return frozenset(_PRESET_KEY.findall(block.group(1)))


def _ass_for(style: dict[str, Any]) -> str:
    return render_editing_session_ass(
        {
            "caption_style": style,
            "segments": [{"caption_text": _PROBE_TEXT, "start_sec": 0.0, "end_sec": 1.0}],
        },
        video_width=_FRAME_WIDTH,
        video_height=_FRAME_HEIGHT,
    )


def _escape_for_filter(path: Path) -> str:
    return path.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")


def _burned_frame_digest(style: dict[str, Any], tmp_path: Path, tag: str) -> str:
    """자막을 실제로 굽고 그 한 프레임을 해시한다."""
    ass_path = tmp_path / f"{tag}.ass"
    ass_path.write_text(_ass_for(style), encoding="utf-8")
    raw_path = tmp_path / f"{tag}.raw"
    subtitles = (
        f"subtitles=filename='{_escape_for_filter(ass_path)}'"
        f":fontsdir='{_escape_for_filter(BUNDLED_FONTS)}'"
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"color=c=black:s={_FRAME_WIDTH}x{_FRAME_HEIGHT}:r=5:d=1",
            "-vf", subtitles,
            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", str(raw_path),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    return hashlib.sha256(raw_path.read_bytes()).hexdigest()


def _field_changes_the_picture(field: str, tmp_path: Path) -> bool:
    context, first, second = PROBES[field]
    before = _burned_frame_digest({**context, field: first}, tmp_path, f"{field}_before")
    after = _burned_frame_digest({**context, field: second}, tmp_path, f"{field}_after")
    return before != after


# ---------------------------------------------------------------------------
# 이름 대조 -- ffmpeg 없이도 돈다.
# ---------------------------------------------------------------------------


def test_every_field_the_screen_can_change_is_a_real_caption_style_field() -> None:
    """화면이 이름을 바꾸면 저장은 조용히 그 값을 버린다. 그 전에 여기서 걸린다."""
    strays = sorted(_screen_controlled_fields() - set(CAPTION_STYLE_FIELDS))

    assert strays == [], f"화면에만 있고 CaptionStyle에는 없는 칸: {strays}"


def test_the_preset_handoff_uses_the_canonical_caption_style_names() -> None:
    """프리셋으로 넘기는 이름이 하나라도 빠지면 그 모양은 저장되지 않는다."""
    assert _preset_handoff_fields() == set(CAPTION_STYLE_FIELDS)


def test_every_caption_style_field_has_a_probe() -> None:
    """칸을 새로 만들면 재는 법도 같이 적어야 한다. 안 그러면 조용히 안 재고 넘어간다."""
    assert set(PROBES) == set(CAPTION_STYLE_FIELDS)


def test_a_field_exempt_from_the_render_has_no_control_on_the_screen() -> None:
    """렌더에 안 닿는 칸을 화면에 두는 것이 곧 owner에게 하는 거짓말이다."""
    lying = sorted(_screen_controlled_fields() & set(FIELDS_EXEMPT_FROM_THE_RENDER))

    assert lying == [], (
        f"화면에 칸은 있는데 렌더에 안 닿는다고 면제해 둔 것: {lying}."
        " 렌더에 잇든지, 화면에서 칸을 없애든지 하나를 골라라."
    )


def test_every_exemption_says_why() -> None:
    assert all(len(reason.strip()) > 20 for reason in FIELDS_EXEMPT_FROM_THE_RENDER.values())


# ---------------------------------------------------------------------------
# 픽셀 대조 -- 이 파일의 본론.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg is not installed on this machine")
@pytest.mark.parametrize(
    "field", [name for name in CAPTION_STYLE_FIELDS if name not in FIELDS_EXEMPT_FROM_THE_RENDER]
)
def test_changing_the_field_changes_the_burned_picture(field: str, tmp_path: Path) -> None:
    context, first, second = PROBES[field]

    assert _field_changes_the_picture(field, tmp_path), (
        f"`{field}` 를 {first!r} 에서 {second!r} 로 바꿔도 구운 화면이 한 픽셀도 안 달라진다."
        f" (함께 준 조건: {context or '없음'})"
        " 화면에 칸이 있다면 owner는 바뀐 줄 알고 있다."
    )


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg is not installed on this machine")
@pytest.mark.parametrize("field", sorted(FIELDS_EXEMPT_FROM_THE_RENDER))
def test_an_exempt_field_really_still_does_nothing(field: str, tmp_path: Path) -> None:
    """면제 목록이 썩지 않게 한다. 렌더에 이어 붙였으면 목록에서 빼라."""
    assert not _field_changes_the_picture(field, tmp_path), (
        f"`{field}` 는 이제 구운 화면을 바꾼다. 면제 목록에서 빼고 화면에 칸을 되살릴지 정하라."
    )
