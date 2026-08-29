"""ComfyUI로 장면 하나에 짧은 실제 동영상을 받아 오는 길. owner 결정 2026-08-29(2회차).

`test_comfyui_image_generation_provider.py`와 같은 방식이다 -- 세 걸음
(`POST /prompt` → `/history` 폴링 → `/view` 회수)이 실제로 이어지는지, 끊기면
왜 끊겼는지 말하는지를 가짜 HTTP 클라이언트로 잰다. 실제 GPU나 owner 기계의
ComfyUI는 필요 없다(2026-08-29 조사: 텍스트 인코더·VAE가 아직 없어서 실제로는
돌지도 않는다 -- 그래프·이음매만 여기서 확정해 둔다).
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from videobox_core_engine.settings import VideoGenerationConfig
from videobox_provider_interfaces.comfyui_image_generation import ComfyUIHTTPTransport, ComfyUIProviderError
from videobox_provider_interfaces.comfyui_video_generation import ComfyUIVideoGenerationProvider
from videobox_provider_interfaces.visual_generation import SceneVideoRequest


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
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class _FakeComfyUI:
    def __init__(self, *, history_rounds: int = 2, video_bytes: bytes = b"WEBM-BYTES") -> None:
        self.history_rounds = history_rounds
        self.video_bytes = video_bytes
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
                    "outputs": {"9": {"images": [{"filename": "videobox-scene-video_00001_.webm", "subfolder": "", "type": "output"}]}},
                }
            })
        if "/view" in url:
            return _Response(self.video_bytes)
        raise AssertionError(f"unexpected call: {url}")


def _provider(comfy: _FakeComfyUI, *, clock: _Clock | None = None, **config: Any) -> ComfyUIVideoGenerationProvider:
    ticking = clock or _Clock()
    return ComfyUIVideoGenerationProvider(
        transport=ComfyUIHTTPTransport(http_client=comfy),
        config=VideoGenerationConfig(**config),
        sleep=ticking.sleep,
        monotonic=ticking.monotonic,
    )


def test_it_walks_prompt_then_history_then_view_and_brings_the_video_bytes_back() -> None:
    comfy = _FakeComfyUI()

    result = _provider(comfy).generate_video(
        SceneVideoRequest(prompt="해 뜨는 바다", width=832, height=480, seed=7, length_frames=81)
    )

    assert result.video_bytes == b"WEBM-BYTES"
    assert result.file_name.endswith(".webm")
    assert comfy.calls[0].endswith("/prompt")
    assert "/history/job-1" in comfy.calls[1]
    assert "/view" in comfy.calls[-1]
    assert result.metadata["model_name"] == "wan2.1_t2v_1.3B_fp16.safetensors"
    assert result.metadata["seed"] == 7
    assert result.metadata["length_frames"] == 81


def test_the_graph_wires_wan_nodes_with_the_configured_settings() -> None:
    comfy = _FakeComfyUI()

    _provider(comfy).generate_video(
        SceneVideoRequest(prompt="해 뜨는 바다", width=832, height=480, seed=42, length_frames=81)
    )

    graph = (comfy.submitted or {})["prompt"]
    unet = next(node for node in graph.values() if node["class_type"] == "UNETLoader")
    assert unet["inputs"]["unet_name"] == "wan2.1_t2v_1.3B_fp16.safetensors"
    clip = next(node for node in graph.values() if node["class_type"] == "CLIPLoader")
    assert clip["inputs"] == {"clip_name": "umt5_xxl_fp16.safetensors", "type": "wan"}
    vae = next(node for node in graph.values() if node["class_type"] == "VAELoader")
    assert vae["inputs"]["vae_name"] == "wan_2.1_vae.safetensors"
    i2v = next(node for node in graph.values() if node["class_type"] == "WanImageToVideo")
    assert i2v["inputs"]["width"] == 832 and i2v["inputs"]["height"] == 480 and i2v["inputs"]["length"] == 81
    assert "start_image" not in i2v["inputs"]
    sampler = next(node for node in graph.values() if node["class_type"] == "KSampler")
    assert sampler["inputs"]["steps"] == 20 and sampler["inputs"]["seed"] == 42
    save = next(node for node in graph.values() if node["class_type"] == "SaveWEBM")
    assert save["inputs"]["codec"] == "vp9"


def test_length_must_satisfy_wans_four_frame_grouping() -> None:
    with pytest.raises(ValueError):
        VideoGenerationConfig(length_frames=80)


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
                        "messages": [["execution_error", {"exception_message": "VAE 파일이 없습니다"}]],
                    },
                    "outputs": {},
                }
            })

    with pytest.raises(ComfyUIProviderError) as exc:
        _provider(_Failing()).generate_video(
            SceneVideoRequest(prompt="x", width=64, height=64, seed=1, length_frames=9)
        )

    assert exc.value.code == "failed"
    assert "VAE 파일이 없습니다" in str(exc.value)


def test_it_gives_up_with_a_timeout_instead_of_polling_forever() -> None:
    clock = _Clock()

    with pytest.raises(ComfyUIProviderError) as exc:
        _provider(_FakeComfyUI(history_rounds=10_000), clock=clock, timeout_seconds=30).generate_video(
            SceneVideoRequest(prompt="x", width=64, height=64, seed=1, length_frames=9)
        )

    assert exc.value.code == "timeout"
    assert clock.now >= 30
