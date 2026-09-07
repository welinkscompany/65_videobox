from __future__ import annotations

import pytest

from videobox_core_engine.settings import VideoGenerationConfig


def test_the_address_cannot_wander_off_this_machine() -> None:
    """`ImageGenerationConfig`와 같은 이유(§10.14 조항 2-C 방식) -- 로컬 비디오
    모델도 이 기계의 ComfyUI 하나로만 묶는다."""
    assert VideoGenerationConfig(base_url="http://127.0.0.1:8188").base_url == "http://127.0.0.1:8188"
    assert VideoGenerationConfig(base_url="http://host.docker.internal:8188").base_url

    for wandered in (
        "http://127.0.0.1:8189",
        "https://127.0.0.1:8188",
        "http://127.0.0.1:8188/prompt",
        "http://user:pass@127.0.0.1:8188",
        "http://comfy.example.com:8188",
    ):
        with pytest.raises(ValueError):
            VideoGenerationConfig(base_url=wandered)


def test_it_refuses_settings_that_would_only_fail_later() -> None:
    with pytest.raises(ValueError):
        VideoGenerationConfig(model_name="   ")
    with pytest.raises(ValueError):
        VideoGenerationConfig(clip_name="   ")
    with pytest.raises(ValueError):
        VideoGenerationConfig(vae_name="   ")
    with pytest.raises(ValueError):
        VideoGenerationConfig(timeout_seconds=0)
    with pytest.raises(ValueError):
        VideoGenerationConfig(steps=0)


def test_length_frames_must_satisfy_wans_grouping() -> None:
    """Wan은 4프레임 단위로 나뉜다((length - 1) % 4 == 0). 안 맞으면 그래프가
    조용히 다른 길이를 만들어 낸다 -- 여기서 미리 거절한다."""
    VideoGenerationConfig(length_frames=81)  # 통과해야 한다
    with pytest.raises(ValueError):
        VideoGenerationConfig(length_frames=80)
    with pytest.raises(ValueError):
        VideoGenerationConfig(length_frames=0)


def test_default_is_off_until_the_missing_model_files_are_ready() -> None:
    """2026-08-29 조사: Wan 체크포인트는 있지만 텍스트 인코더가 중단된
    다운로드고 VAE가 없다. `enabled` 기본값이 켜져 있으면 준비 안 된 경로를
    조용히 부르게 된다."""
    assert VideoGenerationConfig().enabled is False
