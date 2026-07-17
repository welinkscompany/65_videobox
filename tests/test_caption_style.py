from __future__ import annotations

import pytest

from videobox_domain_models.caption_style import CaptionStyle


def test_caption_style_rejects_short_rgba_hex() -> None:
    with pytest.raises(ValueError, match="text_color"):
        CaptionStyle(text_color="#fff")


def test_caption_style_rejects_unknown_style_key() -> None:
    with pytest.raises(ValueError, match="Unsupported caption style fields"):
        CaptionStyle.from_dict({"text_color": "#FFFFFFFF", "unexpected": "no-op"})


def test_caption_style_clamps_safe_area_position() -> None:
    style = CaptionStyle(position_y_percent=100, safe_area_enabled=True)

    assert style.position_y_percent < 100
    assert style.to_dict()["text_color"] == "#FFFFFFFF"
