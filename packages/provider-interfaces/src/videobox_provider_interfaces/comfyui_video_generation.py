"""ComfyUI로 장면 하나에 짧은 실제 동영상을 만드는 길. owner 결정 2026-08-29
(2회차 -- 클라우드 API가 아니라 로컬 비디오 모델).

`ComfyUIImageGenerationProvider`와 같은 세 걸음(`POST /prompt` → `/history`
폴링 → `/view` 회수)이라 `ComfyUIHTTPTransport`를 그대로 재사용한다 -- 이
파일이 새로 짜는 것은 그래프(Wan 노드 조합)와 출력 회수(webm 파일)뿐이다.

**2026-08-29 실측 완료** (owner 기계 RTX 5090) -- 텍스트 인코더·VAE를 받은 뒤
실제로 돌렸다: preview 512x288·17프레임·8스텝 약 12초, standard 1280x720·
65프레임·16스텝 약 139초, full 1920x1080·81프레임·20스텝 약 18~23분. `cfg`
등 일부 값은 여전히 커뮤니티 관행값이다(`VideoGenerationConfig`에 이유를
적어 뒀다) -- 실측은 시간·해상도만 확인했고 화질 미세조정은 아직이다.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from videobox_core_engine.settings import VideoGenerationConfig
from videobox_provider_interfaces.comfyui_image_generation import (
    ComfyUIHTTPTransport,
    ComfyUIProviderError,
)
from videobox_provider_interfaces.visual_generation import GeneratedSceneVideo, SceneVideoRequest

_POLL_INTERVAL_SECONDS = 2.0


@dataclass(slots=True)
class ComfyUIExecutionTracker:
    """ComfyUI websocket(`/ws`)의 `executing` 이벤트를 실시간으로 받아, 지금
    실제로 실행 중인 prompt_id가 무엇인지 안다.

    코드리뷰(2026-08-30)로 남겨 둔 TOCTOU 경합의 진짜 고침 -- `/queue` HTTP
    스냅샷은 요청을 보낸 그 순간의 사진일 뿐이다. 우리 작업을 취소하려고
    `/queue`로 "지금 실행 중" 확인하고 `/interrupt`를 부르는 그 사이에 우리
    작업이 자연히 끝나고 **다른** 작업이 실행을 시작하면, `/interrupt`(전역
    명령, prompt_id를 못 받는다)가 그 남의 작업을 대신 멈춘다. ComfyUI는
    실행 상태가 바뀔 때마다 연결된 모든 websocket 클라이언트에 `executing`
    이벤트를 그대로 뿌려주므로(클라이언트별 구분 없이 이 값은 서버 전역
    상태다), 이 값을 직접 받으면 스냅샷의 시차가 없다.

    `node`가 있으면 그 prompt_id가 지금 실행 중, `node`가 `null`이면 그
    prompt_id가 막 끝났다는 뜻이다(ComfyUI 프로토콜). 다음 실행이 바로
    이어지지 않는 한 그 사이엔 "확인된 실행 중인 것 없음" 상태가 된다.

    **연결 실패는 침묵한다.** 이 값은 편의 기능이지 취소의 전제조건이
    아니다 -- 연결이 안 되거나 끊기면 `has_observed_execution()`이 계속
    `False`로 남고, 호출하는 쪽(`_cancel_prompt`)이 예전 `/queue` 스냅샷
    판정으로 되돌아간다(더 racy하지만 이전과 똑같이 동작한다 -- 퇴행이
    아니다)."""

    ws_url: str
    #: 실제 연결은 `websockets.connect`(런타임 의존성, `requirements-runtime.txt`
    #: 참고)를 쓴다. 시험은 진짜 소켓을 열지 않도록 이 자리에 가짜 연결
    #: 함수를 넣는다 -- `ComfyUIHTTPTransport.http_client`와 같은 자리다.
    connect: Callable[[str], Any] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _current_prompt_id: str | None = field(default=None, init=False, repr=False)
    _observed_any_event: bool = field(default=False, init=False, repr=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def current_prompt_id(self) -> str | None:
        with self._lock:
            return self._current_prompt_id

    def has_observed_execution(self) -> bool:
        """websocket이 `executing` 이벤트를 한 번이라도 받았는가 -- 연결
        실패와 "아무것도 안 도는 중"을 구분하는 값이다."""
        with self._lock:
            return self._observed_any_event

    def _run_forever(self) -> None:
        try:
            asyncio.run(self._listen())
        except Exception:  # noqa: BLE001 -- 연결 실패는 조용히 폴백으로 넘긴다(클래스 docstring 참고)
            return

    async def _listen(self) -> None:
        connector = self.connect
        if connector is None:
            import websockets

            connector = websockets.connect
        async with connector(self.ws_url) as ws:
            while not self._stop_event.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                except Exception:  # noqa: BLE001 -- 연결이 끊기면 조용히 폴백으로 넘긴다
                    return
                self._handle_message(raw)

    def _handle_message(self, raw: Any) -> None:
        if not isinstance(raw, (str, bytes)):
            return
        try:
            message = json.loads(raw)
        except (TypeError, ValueError):
            return
        if not isinstance(message, dict) or message.get("type") != "executing":
            return
        data = message.get("data")
        if not isinstance(data, dict):
            return
        with self._lock:
            self._observed_any_event = True
            self._current_prompt_id = data.get("prompt_id") if data.get("node") is not None else None


def _output_files(entry: dict) -> list[dict]:
    """`/history/{prompt_id}` 항목 하나에서 완성된 출력 파일 목록을 뽑는다 --
    정상 폴링과 취소 경합 재확인이 같은 모양을 보므로 한 곳에 둔다."""
    outputs = entry.get("outputs") if isinstance(entry.get("outputs"), dict) else {}
    return [
        item
        for node in outputs.values()
        if isinstance(node, dict)
        for item in (node.get("images") or [])
        if isinstance(item, dict) and item.get("filename")
    ]


@dataclass(slots=True)
class ComfyUIVideoGenerationProvider:
    """장면 하나에 짧은 영상 하나. `SceneVideoProvider`가 요구하는 모양이다."""

    transport: ComfyUIHTTPTransport
    config: VideoGenerationConfig
    provider_name: str = "comfyui"
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic
    #: 켜져 있으면 websocket으로 실시간 실행 상태를 받아 취소 TOCTOU 경합을
    #: 없앤다(`ComfyUIExecutionTracker` 참고). 기본값 `None`은 예전처럼
    #: `/queue` 스냅샷만으로 판단한다 -- 단위 시험이 진짜 소켓을 열지 않는
    #: 것도 이 기본값의 역할이다. 실제 배선은 `main.py`에서 켠다.
    execution_tracker_factory: Callable[[], ComfyUIExecutionTracker] | None = None

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
        # (이 작업이 맞는지 매번 `/queue`로, 트래커가 있으면 실시간으로 확인한
        # 뒤) 맡는다.
        if on_submitted is not None:
            on_submitted(prompt_id)
        tracker = self.execution_tracker_factory() if self.execution_tracker_factory is not None else None
        if tracker is not None:
            tracker.start()
        try:
            file_name, video_bytes = self._await_video(
                prompt_id=prompt_id, started=started, cancel_event=cancel_event, tracker=tracker,
            )
        finally:
            if tracker is not None:
                tracker.stop()
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
        tracker: ComfyUIExecutionTracker | None = None,
    ) -> tuple[str, bytes]:
        # `SaveWEBM`(ComfyUI 코어, comfy_extras/nodes_video.py)은 `SaveImage`와
        # 같은 `PreviewVideo` 모양으로 결과를 돌려준다 -- history 출력이
        # `{"images": [...]}`에 파일명을 담는다. 이미지 provider의 폴링 로직과
        # 똑같이 그 키를 본다.
        while self.monotonic() - started < self.config.timeout_seconds:
            if cancel_event is not None and cancel_event.is_set():
                self._cancel_prompt(prompt_id, tracker)
                # 취소 요청 직후에도 이 작업이 실제로 끝나 있을 수 있다(취소가
                # 늦은 것뿐, 실패가 아니다) -- 그때는 결과가 실제로 나와
                # 있으면 그대로 돌려준다(버리지 않는다).
                files = self._find_finished_files(prompt_id)
                if files:
                    return self._fetch(files[0])
                raise ComfyUIProviderError("scene_video_cancelled", "cancelled")
            self.sleep(_POLL_INTERVAL_SECONDS)
            entry = self.transport.request_json(
                f"/history/{prompt_id}", None, timeout_seconds=self._step_timeout()
            ).get(prompt_id)
            if not isinstance(entry, dict):
                continue
            status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
            files = _output_files(entry)
            if files:
                return self._fetch(files[0])
            if str(status.get("status_str") or "") == "error":
                raise ComfyUIProviderError(self._why(status), "failed")
        raise ComfyUIProviderError(
            f"ComfyUI did not finish within {self.config.timeout_seconds}s.", "timeout"
        )

    def _find_finished_files(self, prompt_id: str) -> list[dict]:
        try:
            entry = self.transport.request_json(
                f"/history/{prompt_id}", None, timeout_seconds=self._step_timeout()
            ).get(prompt_id)
        except ComfyUIProviderError:
            return []
        return _output_files(entry) if isinstance(entry, dict) else []

    def _cancel_prompt(self, prompt_id: str, tracker: ComfyUIExecutionTracker | None) -> None:
        """이 작업이 아직 대기 중이면 큐에서 지우고, 지금 실행 중이면 멈춘다.

        **다른 작업은 손대지 않는다** -- ComfyUI의 `/interrupt`는 전체 실행을
        멈추는 전역 명령이다. 확인 자체가 실패하거나 이미 끝나 있으면
        조용히 넘어간다 -- 취소는 편의 기능이지, 실패해도 작업 자체(성공/실패
        판정)를 막으면 안 된다.

        **"지금 실행 중"의 판정 기준(TOCTOU 수정, 2026-08-30 코드리뷰).**
        `tracker`가 websocket으로 실제 실행 상태를 받아 본 적이 있으면
        (`has_observed_execution()`) 그 실시간 값을 그대로 믿는다 -- `/queue`
        스냅샷은 요청 시점의 사진이라, 확인과 `/interrupt` 사이에 우리 작업이
        끝나고 **다른** 작업이 막 시작해도 알 수 없다. 트래커가 없거나 한
        번도 이벤트를 못 받았으면(연결 실패 등) 예전처럼 `/queue`의
        `queue_running` 스냅샷으로 되돌아간다 -- 더 racy하지만 트래커가 있기
        전과 똑같이 동작한다(퇴행이 아니다).
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
            elif self._is_actually_running(prompt_id, running_ids, tracker):
                self.transport.request_json("/interrupt", {}, timeout_seconds=self._step_timeout())
        except ComfyUIProviderError:
            pass

    @staticmethod
    def _is_actually_running(
        prompt_id: str, running_ids: set[str], tracker: ComfyUIExecutionTracker | None,
    ) -> bool:
        if tracker is not None and tracker.has_observed_execution():
            return tracker.current_prompt_id() == prompt_id
        return prompt_id in running_ids

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
