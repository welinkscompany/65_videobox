"""ComfyUI로 그림 한 장을 받아 오는 길. §10.14 조항 2-C.

ComfyUI는 OpenAI 모양이 아니다 -- `POST /prompt`에 그래프 JSON을 넣고,
`/history/{id}`를 폴링하고, 다 되면 `/view`로 파일을 회수한다. 2-B의 provider를
재사용할 수 없어 새로 짠 이유가 그것이다.

여기서 재는 것은 **그 세 걸음이 실제로 이어지는가**와, 중간에 끊겼을 때
**왜 끊겼는지 말하는가**다. 원인을 한 낱말로 뭉개면 다음 사람이 그럴듯한
이야기를 지어낼 수밖에 없다(2026-08-20에 실제로 그랬다).
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from videobox_core_engine.settings import ImageGenerationConfig
from videobox_provider_interfaces.comfyui_image_generation import (
    ComfyUIHTTPTransport,
    ComfyUIImageGenerationProvider,
    ComfyUIProviderError,
)
from videobox_provider_interfaces.visual_generation import SceneImageRequest


class _Response:
    def __init__(self, payload: Any) -> None:
        self._body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class _Clock:
    """폴링이 얼마나 기다렸는지는 잠든 시간으로만 잰다 -- 시험은 실제로 안 잔다."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class _FakeComfyUI:
    """세 걸음을 그대로 흉내 낸다. 실제 GPU 없이 이음매만 잰다."""

    def __init__(self, *, history_rounds: int = 2, image_bytes: bytes = b"PNG-BYTES") -> None:
        self.history_rounds = history_rounds
        self.image_bytes = image_bytes
        self.calls: list[str] = []
        self.submitted: dict[str, Any] | None = None

    def __call__(self, request: Any, **_kwargs: Any) -> _Response:
        url = request.full_url
        self.calls.append(url)
        if url.endswith("/prompt"):
            self.submitted = json.loads(request.data.decode("utf-8"))
            return _Response({"prompt_id": "job-1"})
        if "/history/" in url:
            self.history_rounds -= 1
            if self.history_rounds > 0:
                return _Response({})
            return _Response({
                "job-1": {
                    "status": {"status_str": "success", "completed": True},
                    "outputs": {"9": {"images": [{"filename": "videobox_00001_.png", "subfolder": "", "type": "output"}]}},
                }
            })
        if "/view" in url:
            return _Response(self.image_bytes)
        raise AssertionError(f"unexpected call: {url}")


def _provider(comfy: _FakeComfyUI, *, clock: _Clock | None = None, **config: Any) -> ComfyUIImageGenerationProvider:
    ticking = clock or _Clock()
    return ComfyUIImageGenerationProvider(
        transport=ComfyUIHTTPTransport(http_client=comfy),
        config=ImageGenerationConfig(**config),
        sleep=ticking.sleep,
        monotonic=ticking.monotonic,
    )


def test_it_walks_prompt_then_history_then_view_and_brings_the_bytes_back() -> None:
    comfy = _FakeComfyUI()

    result = _provider(comfy).generate_image(
        SceneImageRequest(prompt="해 뜨는 바다", width=1280, height=720, seed=7)
    )

    assert result.image_bytes == b"PNG-BYTES"
    assert result.file_name.endswith(".png")
    assert comfy.calls[0].endswith("/prompt")
    assert "/history/job-1" in comfy.calls[1]
    assert "/view" in comfy.calls[-1]
    assert result.metadata["model_name"] == "flux1-dev.safetensors"
    assert result.metadata["seed"] == 7


def test_the_graph_carries_the_settings_that_were_actually_measured() -> None:
    """기본값이 곧 2026-08-21 실측이다. 그래프가 그 값을 안 실으면 설정은 장식이다.

    `fp8_e4m3fn`을 안 실으면 bf16 22GB를 부르게 되고 owner 기계에서 그냥 안 돈다.
    """
    comfy = _FakeComfyUI()

    _provider(comfy).generate_image(
        SceneImageRequest(prompt="해 뜨는 바다", width=1920, height=1080, seed=42)
    )

    graph = (comfy.submitted or {})["prompt"]
    loader = next(node for node in graph.values() if node["class_type"] == "UNETLoader")
    assert loader["inputs"] == {"unet_name": "flux1-dev.safetensors", "weight_dtype": "fp8_e4m3fn"}
    latent = next(node for node in graph.values() if node["class_type"] == "EmptySD3LatentImage")
    assert latent["inputs"]["width"] == 1920 and latent["inputs"]["height"] == 1080
    sampler = next(node for node in graph.values() if node["class_type"] == "KSampler")
    assert sampler["inputs"]["steps"] == 20 and sampler["inputs"]["seed"] == 42
    text = next(node for node in graph.values() if node["class_type"] == "CLIPTextEncode")
    assert text["inputs"]["text"] == "해 뜨는 바다"


def test_a_refusal_and_a_timeout_do_not_collapse_into_one_word() -> None:
    """원인 둘은 대응이 다르다 -- 다시 걸면 되는 것과 켜야 하는 것.
    한 낱말로 뭉개면 화면이 어느 쪽인지 말할 수 없다."""
    from urllib.error import URLError

    def refused(_request: Any, **_kwargs: Any) -> None:
        raise URLError("connection refused")

    with pytest.raises(ComfyUIProviderError) as exc:
        ComfyUIHTTPTransport(http_client=refused).request_json("/prompt", {"prompt": {}}, timeout_seconds=1)
    assert exc.value.code == "blocked"

    def timing_out(_request: Any, **_kwargs: Any) -> None:
        raise TimeoutError("timed out")

    with pytest.raises(ComfyUIProviderError) as exc:
        ComfyUIHTTPTransport(http_client=timing_out).request_json("/prompt", {"prompt": {}}, timeout_seconds=1)
    assert exc.value.code == "timeout"


def test_a_run_that_errored_reports_what_comfyui_said() -> None:
    class _Failing(_FakeComfyUI):
        def __call__(self, request: Any, **_kwargs: Any) -> _Response:
            url = request.full_url
            self.calls.append(url)
            if url.endswith("/prompt"):
                return _Response({"prompt_id": "job-1"})
            return _Response({
                "job-1": {
                    "status": {
                        "status_str": "error",
                        "completed": False,
                        "messages": [["execution_error", {"exception_message": "모델 파일이 없습니다"}]],
                    },
                    "outputs": {},
                }
            })

    with pytest.raises(ComfyUIProviderError) as exc:
        _provider(_Failing()).generate_image(SceneImageRequest(prompt="x", width=64, height=64, seed=1))

    assert exc.value.code == "failed"
    assert "모델 파일이 없습니다" in str(exc.value)


def test_the_address_is_re_checked_before_every_call_not_only_at_startup() -> None:
    """설정이 통과했다는 것과 요청이 거기로 간다는 것은 다른 말이다.
    2-B가 매 요청 직전에 다시 확인하는 것과 같은 이유다."""
    transport = ComfyUIHTTPTransport(http_client=_FakeComfyUI())
    transport.base_url = "http://comfy.example.com:8188"

    with pytest.raises(ComfyUIProviderError) as exc:
        transport.request_json("/prompt", {"prompt": {}}, timeout_seconds=1)

    assert exc.value.code == "blocked"


def test_it_gives_up_with_a_timeout_instead_of_polling_forever() -> None:
    clock = _Clock()

    with pytest.raises(ComfyUIProviderError) as exc:
        _provider(_FakeComfyUI(history_rounds=10_000), clock=clock, timeout_seconds=30).generate_image(
            SceneImageRequest(prompt="x", width=64, height=64, seed=1)
        )

    assert exc.value.code == "timeout"
    assert clock.now >= 30
