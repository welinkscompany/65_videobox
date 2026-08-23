"""색감이 캡컷 초안까지 가는가, 그리고 **두 표가 어긋나지 않는가.**

색감은 2026-08-23까지 캡컷 초안에 전혀 실리지 않았다. 대표가 흑백을 걸어 두고
캡컷을 열면 원래 색이 그대로 나왔다.

캡컷 이름표는 캡컷 서버 자원이라 우리 ffmpeg 그림과 **같지 않다.** 그래서
`capcut_looks.py`가 "비슷한 것"을 고르고, 안내문이 그 사실을 말한다.
"""
from __future__ import annotations

import pytest

from videobox_capcut_export.capcut_looks import CAPCUT_FILTER_BY_LOOK, capcut_filter_name
from videobox_core_engine.filters import FILTER_CATALOG


def test_every_look_we_offer_has_a_capcut_counterpart() -> None:
    # 색감을 새로 만들고 이 표를 빠뜨리면, 그 색감만 캡컷에서 조용히 사라진다.
    assert set(CAPCUT_FILTER_BY_LOOK) == set(FILTER_CATALOG)


def test_every_counterpart_is_a_name_capcut_actually_knows() -> None:
    # 모르는 이름을 넣으면 초안을 만드는 순간 터진다. 여기서 먼저 잡는다.
    FilterType = pytest.importorskip("pycapcut").FilterType
    known = {member.name for member in FilterType}
    missing = sorted(name for name in CAPCUT_FILTER_BY_LOOK.values() if name not in known)
    assert missing == []


def test_a_chosen_look_becomes_a_capcut_filter_name() -> None:
    assert capcut_filter_name({"filter": {"type": "mono", "chosen_by": "owner"}}) == "BW_2"
    assert capcut_filter_name({"filter": {"type": "bright", "chosen_by": "owner"}}) == "磨砂肌"


def test_no_look_means_no_filter() -> None:
    assert capcut_filter_name(None) is None
    assert capcut_filter_name({}) is None
    assert capcut_filter_name({"filter": None}) is None


def test_every_clip_of_the_owners_footage_carries_the_look_but_the_black_pad_does_not() -> None:
    """B-roll 조각을 만드는 자리가 **셋**이다. 셋 다 같게 다루면 안 된다.

    둘은 대표의 원본 화면이고(이어 붙이는 쪽, 한 번만 놓는 쪽) 색감을 얹어야
    한다. 나머지 하나는 원본이 모자랄 때 채우는 **검은 여백**이라 얹으면 안
    된다 -- `뽀샤시하게`를 걸면 여백이 회색으로 떠오른다.

    이 저장소는 짝을 이룬 자리를 한쪽만 고쳐 같은 결함을 두 번 냈다. 원본을
    맞대어 보는 것은 이미 쓰는 방식이다(`test_capcut_export_track_states.py`).
    """
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "packages" / "capcut-export" / "src" / "videobox_capcut_export" / "pycapcut_adapter.py"
    ).read_text(encoding="utf-8")
    body = source.split("def _add_broll_segment(", 1)[1].split(chr(10) + "    def ", 1)[0]

    # 원본 화면 조각은 전부 색감을 지나간다.
    assert body.count("_with_look(VideoSegment(") == 2
    # 검은 여백은 지나가지 않는다. 그 자리에서 `material`이 아니라
    # `pad_material`을 쓰는 것으로 구별한다.
    pad = body.split("pad_material = VideoMaterial(", 1)[1]
    assert "_with_look" not in pad, "검은 여백에는 색감을 얹지 않는다"
    # 자리가 셋에서 늘면 이 시험이 붉어져 다시 판단하게 된다.
    assert body.count("VideoSegment(") == 3
