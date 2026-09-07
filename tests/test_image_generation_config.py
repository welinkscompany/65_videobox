from __future__ import annotations

import pytest

from videobox_core_engine.settings import ImageGenerationConfig


def test_the_address_cannot_wander_off_this_machine() -> None:
    """§10.14 조항 2-C가 허용한 것은 **이 기계의 ComfyUI 하나**다.

    2-B(유진의 두뇌)가 같은 방식으로 묶여 있다. 설정 한 줄로 밖으로 나갈 수 있으면
    그 조항은 문서에만 있는 것이 된다 -- 그래서 코드가 거절한다.
    """
    assert ImageGenerationConfig(base_url="http://127.0.0.1:8188").base_url == "http://127.0.0.1:8188"
    assert ImageGenerationConfig(base_url="http://host.docker.internal:8188").base_url

    for wandered in (
        "http://127.0.0.1:8189",              # 다른 문
        "https://127.0.0.1:8188",             # 다른 scheme
        "http://127.0.0.1:8188/prompt",       # path가 붙은 것
        "http://user:pass@127.0.0.1:8188",    # 자격 증명이 붙은 것
        "http://comfy.example.com:8188",      # 남의 기계
    ):
        with pytest.raises(ValueError):
            ImageGenerationConfig(base_url=wandered)


def test_a_non_commercial_model_cannot_slip_through_quietly() -> None:
    """라이선스는 **실행 중에 눈에 보이지 않는** 제약이다. 사람이 기억하는 것에
    맡기면 반드시 새어 나간다 -- §10.14 조항 2-C가 이걸 못박은 이유다.

    owner가 2026-08-21에 `flux1-dev`로 가겠다고 결정했고 라이선스는 본인이 맡는다고
    했다. 그래서 막지 않는다. 다만 **어느 쪽을 쓰고 있는지 스스로 말하게** 한다.
    """
    schnell = ImageGenerationConfig(model_name="flux1-schnell.safetensors")
    assert schnell.commercial_use_is_unrestricted is True

    dev = ImageGenerationConfig(model_name="flux1-dev.safetensors")
    assert dev.commercial_use_is_unrestricted is False

    unknown = ImageGenerationConfig(model_name="something-new.safetensors")
    assert unknown.commercial_use_is_unrestricted is None


def test_it_refuses_settings_that_would_only_fail_later() -> None:
    with pytest.raises(ValueError):
        ImageGenerationConfig(model_name="   ")
    with pytest.raises(ValueError):
        ImageGenerationConfig(timeout_seconds=0)
    with pytest.raises(ValueError):
        ImageGenerationConfig(steps=0)


def test_it_loads_the_weights_the_way_that_actually_fits() -> None:
    """실측(2026-08-21): `flux1-dev`를 bf16으로 실으면 22GB라 여유 10.7GB에 안 들어간다.
    `fp8_e4m3fn`으로 실으면 절반이 되어 **LM Studio를 켜 둔 채로** 1920x1080이 24초다.

    기본값을 bf16으로 두면 owner의 기계에서 그냥 안 돈다. 이 기본값이 그 실측이다.
    """
    assert ImageGenerationConfig().weight_dtype == "fp8_e4m3fn"
