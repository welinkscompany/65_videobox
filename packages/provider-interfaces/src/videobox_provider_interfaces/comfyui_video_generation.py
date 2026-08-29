"""ComfyUI로 장면 하나에 짧은 실제 동영상을 만드는 길. owner 결정 2026-08-29
(2회차 -- 클라우드 API가 아니라 로컬 비디오 모델).

`ComfyUIImageGenerationProvider`와 같은 세 걸음(`POST /prompt` → `/history`
폴링 → `/view` 회수)이라 `ComfyUIHTTPTransport`를 그대로 재사용한다 -- 이
파일이 새로 짜는 것은 그래프(Wan 노드 조합)와 출력 회수(webm 파일)뿐이다.

**아직 실측하지 않았다.** 2026-08-29 조사로 owner 기계의 ComfyUI에 Wan 체크포인트는
있지만 텍스트 인코더가 중단된 다운로드이고 VAE가 없다 -- 그래서 `KSampler`의
`cfg` 등 일부 값은 커뮤니티 관행값이지 이 프로젝트가 잰 값이 아니다
(`VideoGenerationConfig`에 이유를 적어 뒀다). 파일이 갖춰진 뒤 첫 실행에서
반드시 재조정한다.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from videobox_core_engine.settings import VideoGenerationConfig
from videobox_provider_interfaces.comfyui_image_generation import (
    ComfyUIHTTPTransport,
    ComfyUIProviderError,
)
from videobox_provider_interfaces.visual_generation import GeneratedSceneVideo, SceneVideoRequest

_POLL_INTERVAL_SECONDS = 2.0


@dataclass(slots=True)
class ComfyUIVideoGenerationProvider:
    """장면 하나에 짧은 영상 하나. `SceneVideoProvider`가 요구하는 모양이다."""

    transport: ComfyUIHTTPTransport
    config: VideoGenerationConfig
    provider_name: str = "comfyui"
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic

    def generate_video(
        self,
        request: SceneVideoRequest,
        *,
        on_submitted: Callable[[str], None] | None = None,
        cancel_event: "threading.Event | None" = None,
    ) -> GeneratedSceneVideo:
        started = self.monotonic()
        queued = self.transport.request_json(
            "/prompt",
            {"prompt": self._graph(request), "client_id": uuid.uuid4().hex},
            timeout_seconds=self._step_timeout(),
        )
        prompt_id = str(queued.get("prompt_id") or "")
        if not prompt_id:
            raise ComfyUIProviderError("ComfyUI accepted nothing to wait for.", "failed")
        # owner 요청(2026-08-29 3회차, 취소 버튼) -- 취소를 실제로 걸려면
        # ComfyUI가 이 작업을 어떤 prompt_id로 부르는지 호출한 쪽이 알아야
        # 한다. 여기서 알려 주고 나면, 실제로 멈추는 일은 아래 폴링 루프가
        # (이 작업이 맞는지 매번 `/queue`로 확인한 뒤) 맡는다.
        if on_submitted is not None:
            on_submitted(prompt_id)
        file_name, video_bytes = self._await_video(
            prompt_id=prompt_id, started=started, cancel_event=cancel_event,
        )
        return GeneratedSceneVideo(
            provider_name=self.provider_name,
            video_bytes=video_bytes,
            file_name=file_name,
            metadata={
                "model_name": self.config.model_name,
                "steps": request.steps,
                "cfg": self.config.cfg,
                "length_frames": request.length_frames,
                "fps": self.config.fps,
                "seed": request.seed,
                "width": request.width,
                "height": request.height,
                "prompt": request.prompt,
                "elapsed_sec": round(self.monotonic() - started, 1),
            },
        )

    def _step_timeout(self) -> int:
        return max(1, min(60, self.config.timeout_seconds))

    def _await_video(
        self, *, prompt_id: str, started: float, cancel_event: "threading.Event | None" = None,
    ) -> tuple[str, bytes]:
        # `SaveWEBM`(ComfyUI 코어, comfy_extras/nodes_video.py)은 `SaveImage`와
        # 같은 `PreviewVideo` 모양으로 결과를 돌려준다 -- history 출력이
        # `{"images": [...]}`에 파일명을 담는다. 이미지 provider의 폴링 로직과
        # 똑같이 그 키를 본다.
        while self.monotonic() - started < self.config.timeout_seconds:
            if cancel_event is not None and cancel_event.is_set():
                self._cancel_prompt(prompt_id)
                raise ComfyUIProviderError("scene_video_cancelled", "cancelled")
            self.sleep(_POLL_INTERVAL_SECONDS)
            entry = self.transport.request_json(
                f"/history/{prompt_id}", None, timeout_seconds=self._step_timeout()
            ).get(prompt_id)
            if not isinstance(entry, dict):
                continue
            status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
            outputs = entry.get("outputs") if isinstance(entry.get("outputs"), dict) else {}
            files = [
                item
                for node in outputs.values()
                if isinstance(node, dict)
                for item in (node.get("images") or [])
                if isinstance(item, dict) and item.get("filename")
            ]
            if files:
                return self._fetch(files[0])
            if str(status.get("status_str") or "") == "error":
                raise ComfyUIProviderError(self._why(status), "failed")
        raise ComfyUIProviderError(
            f"ComfyUI did not finish within {self.config.timeout_seconds}s.", "timeout"
        )

    def _cancel_prompt(self, prompt_id: str) -> None:
        """이 작업이 아직 대기 중이면 큐에서 지우고, 지금 실행 중이면 멈춘다.

        **다른 작업은 손대지 않는다** -- ComfyUI의 `/interrupt`는 전체 실행을
        멈추는 전역 명령이라, 지금 도는 것이 정말 이 prompt_id인지 `/queue`로
        먼저 확인한 뒤에만 부른다. 확인 자체가 실패하거나 이미 끝나 있으면
        조용히 넘어간다 -- 취소는 편의 기능이지, 실패해도 작업 자체(성공/실패
        판정)를 막으면 안 된다.
        """
        try:
            queue = self.transport.request_json("/queue", None, timeout_seconds=self._step_timeout())
        except ComfyUIProviderError:
            return
        pending_ids = {
            str(entry[1]) for entry in queue.get("queue_pending", [])
            if isinstance(entry, list) and len(entry) > 1
        }
        running_ids = {
            str(entry[1]) for entry in queue.get("queue_running", [])
            if isinstance(entry, list) and len(entry) > 1
        }
        try:
            if prompt_id in pending_ids:
                self.transport.request_json(
                    "/queue", {"delete": [prompt_id]}, timeout_seconds=self._step_timeout(),
                )
            elif prompt_id in running_ids:
                self.transport.request_json("/interrupt", {}, timeout_seconds=self._step_timeout())
        except ComfyUIProviderError:
            pass

    def _fetch(self, item: dict) -> tuple[str, bytes]:
        from urllib.parse import urlencode
        query = urlencode({
            "filename": str(item.get("filename")),
            "subfolder": str(item.get("subfolder") or ""),
            "type": str(item.get("type") or "output"),
        })
        return str(item.get("filename")), self.transport.request_bytes(
            f"/view?{query}", timeout_seconds=self._step_timeout()
        )

    @staticmethod
    def _why(status: dict) -> str:
        messages = status.get("messages")
        if isinstance(messages, list):
            for message in messages:
                if isinstance(message, list) and len(message) > 1 and isinstance(message[1], dict):
                    detail = message[1].get("exception_message") or message[1].get("exception_type")
                    if detail:
                        return f"ComfyUI could not finish the video: {detail}"
        return "ComfyUI could not finish the video."

    def _graph(self, request: SceneVideoRequest) -> dict:
        """Wan 텍스트→영상 워크플로. 노드 번호는 순서를 의미하지 않는다 -- ComfyUI가
        의존성 그래프로 실행 순서를 정한다.

        `WanImageToVideo`는 `start_image`가 optional이라 여기선 비워 텍스트만으로
        만든다(순수 t2v) -- `scene_image_service`가 이미 만든 정지 그림을 영상
        시작 프레임으로 쓰는 이미지→영상 경로는 별도 확장이다(`start_image`에
        업로드한 이미지를 `LoadImage`로 물리면 된다), 지금은 다루지 않는다.
        """
        return {
            "1": {"class_type": "UNETLoader", "inputs": {
                "unet_name": self.config.model_name, "weight_dtype": self.config.weight_dtype,
            }},
            "2": {"class_type": "CLIPLoader", "inputs": {
                "clip_name": self.config.clip_name, "type": "wan",
            }},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": self.config.vae_name}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": request.prompt}},
            "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": ""}},
            "6": {"class_type": "WanImageToVideo", "inputs": {
                "positive": ["4", 0], "negative": ["5", 0], "vae": ["3", 0],
                "width": request.width, "height": request.height,
                "length": request.length_frames, "batch_size": 1,
            }},
            "7": {"class_type": "KSampler", "inputs": {
                "model": ["1", 0], "positive": ["6", 0], "negative": ["6", 1], "latent_image": ["6", 2],
                "seed": request.seed, "steps": request.steps, "cfg": self.config.cfg,
                "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1.0,
            }},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
            "9": {"class_type": "SaveWEBM", "inputs": {
                "images": ["8", 0], "filename_prefix": "videobox-scene-video",
                "codec": "vp9", "fps": self.config.fps, "crf": 32.0,
            }},
        }


__all__ = ["ComfyUIVideoGenerationProvider"]
