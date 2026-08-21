"""대본에 맞춘 그림을 만드는 provider. owner 승인 2026-08-20 (§10.14 조항 2-C).

**2-B(유진의 두뇌) provider를 재사용할 수 없다.** ComfyUI는 OpenAI 모양이 아니고
세 걸음으로 움직인다.

    POST /prompt        그래프 JSON을 큐에 넣고 작업 번호를 받는다
    GET  /history/{id}  끝날 때까지 물어본다
    GET  /view?...      나온 파일을 바이트로 회수한다

그래프는 `artifacts/flux-measure/try_flux_dev.py`에서 실제로 돌려 본 9노드를 그대로
옮긴 것이다. 다시 재지 않는다 -- 2026-08-21 실측으로 1920x1080·20단계가 24.1초,
1280x720이 14~16초였다(**LM Studio를 켜 둔 채**).

주소는 2-B와 같은 방식으로 묶는다. 설정 한 줄로 밖에 나갈 수 있으면 조항 2-C는
문서에만 있는 것이 된다.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from videobox_core_engine.settings import ImageGenerationConfig
from videobox_provider_interfaces.visual_generation import GeneratedSceneImage, SceneImageRequest


#: 2-C가 허용한 것은 이 기계의 ComfyUI 하나다. `host.docker.internal`은 도커 호스트,
#: 즉 같은 기계다 -- 조항 1의 provider egress와 성격이 다르다.
_ALLOWED_COMFYUI_HOSTS = frozenset({"127.0.0.1", "host.docker.internal"})
_COMFYUI_PORT = 8188
_POLL_INTERVAL_SECONDS = 2.0


@dataclass(slots=True, frozen=True)
class ComfyUIProviderError(Exception):
    """왜 끊겼는지 말한다.

    `blocked`  ComfyUI가 없거나 주소가 막혔다 -- 켜야 한다
    `timeout`  받아는 갔는데 시간 안에 안 끝났다 -- 다시 걸면 될 수 있다
    `failed`   ComfyUI가 실행 중에 거절했다 -- 프롬프트나 모델을 고쳐야 한다

    2026-08-20에 `except (KeyError, ValueError)` 하나가 원인 여덟 가지를 한 낱말로
    뭉개는 바람에 틀린 진단이 나왔다. 같은 실수를 여기서 되풀이하지 않는다.
    """

    message: str
    code: str

    def __str__(self) -> str:
        return self.message


def _is_timeout(exc: BaseException) -> bool:
    """urllib은 읽기 타임아웃을 그대로 던지기도 하고 URLError에 싸서 던지기도 한다."""
    if isinstance(exc, TimeoutError):
        return True
    return isinstance(getattr(exc, "reason", None), TimeoutError)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        raise HTTPError(req.full_url, code, "ComfyUI redirects are forbidden", headers, fp)


@dataclass(slots=True)
class ComfyUIHTTPTransport:
    base_url: str = "http://127.0.0.1:8188"
    http_client: Callable[..., Any] | None = None
    requested_endpoints: list[str] = field(default_factory=list, init=False)

    def _endpoint(self, path: str) -> str:
        """매 요청 직전에 다시 확인한다.

        시작할 때 한 번 통과한 것과 이 요청이 거기로 간다는 것은 다른 말이다.
        `base_url`은 dataclass 필드라 언제든 바뀔 수 있다.
        """
        parsed = urlparse(self.base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in _ALLOWED_COMFYUI_HOSTS
            or parsed.port != _COMFYUI_PORT
            or parsed.path
            or parsed.params
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ComfyUIProviderError(
                "ComfyUI endpoint must be http://127.0.0.1:8188, or "
                "http://host.docker.internal:8188 in the container.",
                "blocked",
            )
        if not path.startswith("/"):
            raise ComfyUIProviderError("ComfyUI request must stay on this machine.", "blocked")
        return f"{self.base_url}{path}"

    def request_json(self, path: str, payload: dict[str, Any] | None, *, timeout_seconds: int) -> dict[str, Any]:
        raw = self._request(path, payload, timeout_seconds=timeout_seconds)
        try:
            decoded = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ComfyUIProviderError("ComfyUI returned malformed JSON.", "failed") from exc
        if not isinstance(decoded, dict):
            raise ComfyUIProviderError("ComfyUI response must be a JSON object.", "failed")
        return decoded

    def request_bytes(self, path: str, *, timeout_seconds: int) -> bytes:
        raw = self._request(path, None, timeout_seconds=timeout_seconds)
        if not raw:
            raise ComfyUIProviderError("ComfyUI returned an empty image.", "failed")
        return raw

    def _request(self, path: str, payload: dict[str, Any] | None, *, timeout_seconds: int) -> bytes:
        endpoint = self._endpoint(path)
        self.requested_endpoints.append(endpoint)
        request = Request(
            endpoint,
            data=None if payload is None else json.dumps(payload).encode("utf-8"),
            headers={} if payload is None else {"Content-Type": "application/json"},
            method="GET" if payload is None else "POST",
        )
        try:
            if self.http_client is not None:
                response = self.http_client(request, timeout=timeout_seconds, allow_redirects=False)
            else:
                response = build_opener(_NoRedirect()).open(request, timeout=timeout_seconds)
            with response:
                return bytes(response.read())
        except ComfyUIProviderError:
            raise
        except HTTPError as exc:
            # 4xx는 그래프를 거절한 것이다. 켜져 있으니 `blocked`가 아니고,
            # 다시 건다고 달라지지 않으니 `timeout`도 아니다.
            try:
                detail = exc.read().decode("utf-8", "replace")[:400]
            except Exception:  # noqa: BLE001 -- 본문을 못 읽는 것이 원인을 지울 이유는 아니다
                detail = ""
            if 400 <= exc.code < 500:
                raise ComfyUIProviderError(
                    f"ComfyUI rejected the request ({exc.code}). {detail}".strip(), "failed"
                ) from exc
            raise ComfyUIProviderError(f"ComfyUI is unavailable ({exc.code}).", "blocked") from exc
        except (URLError, TimeoutError, OSError) as exc:
            if _is_timeout(exc):
                raise ComfyUIProviderError("ComfyUI timed out.", "timeout") from exc
            raise ComfyUIProviderError("ComfyUI local resource is unavailable.", "blocked") from exc


@dataclass(slots=True)
class ComfyUIImageGenerationProvider:
    """장면 하나에 그림 한 장. `SceneImageProvider`가 요구하는 모양이다."""

    transport: ComfyUIHTTPTransport
    config: ImageGenerationConfig
    provider_name: str = "comfyui"
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic

    def generate_image(self, request: SceneImageRequest) -> GeneratedSceneImage:
        started = self.monotonic()
        queued = self.transport.request_json(
            "/prompt",
            {"prompt": self._graph(request), "client_id": uuid.uuid4().hex},
            timeout_seconds=self._step_timeout(),
        )
        prompt_id = str(queued.get("prompt_id") or "")
        if not prompt_id:
            raise ComfyUIProviderError("ComfyUI accepted nothing to wait for.", "failed")
        file_name, image_bytes = self._await_image(prompt_id=prompt_id, started=started)
        return GeneratedSceneImage(
            provider_name=self.provider_name,
            image_bytes=image_bytes,
            file_name=file_name,
            metadata={
                "model_name": self.config.model_name,
                "weight_dtype": self.config.weight_dtype,
                "steps": self.config.steps,
                "guidance": self.config.guidance,
                "seed": request.seed,
                "width": request.width,
                "height": request.height,
                "prompt": request.prompt,
                "elapsed_sec": round(self.monotonic() - started, 1),
                # 라이선스는 실행 중에 눈에 보이지 않는다. 어느 쪽으로 만든 그림인지
                # 자산에 같이 남겨 둔다 -- 나중에 세면 이미 늦다 (§10.14 2-C).
                "commercial_use_is_unrestricted": self.config.commercial_use_is_unrestricted,
            },
        )

    def _step_timeout(self) -> int:
        """한 번의 HTTP 왕복 상한. 전체 대기 상한(`timeout_seconds`)과 다른 것이다."""
        return max(1, min(60, self.config.timeout_seconds))

    def _await_image(self, *, prompt_id: str, started: float) -> tuple[str, bytes]:
        while self.monotonic() - started < self.config.timeout_seconds:
            self.sleep(_POLL_INTERVAL_SECONDS)
            entry = self.transport.request_json(
                f"/history/{prompt_id}", None, timeout_seconds=self._step_timeout()
            ).get(prompt_id)
            if not isinstance(entry, dict):
                continue
            status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
            outputs = entry.get("outputs") if isinstance(entry.get("outputs"), dict) else {}
            images = [
                item
                for node in outputs.values()
                if isinstance(node, dict)
                for item in (node.get("images") or [])
                if isinstance(item, dict) and item.get("filename")
            ]
            if images:
                return self._fetch(images[0])
            if str(status.get("status_str") or "") == "error":
                raise ComfyUIProviderError(self._why(status), "failed")
        raise ComfyUIProviderError(
            f"ComfyUI did not finish within {self.config.timeout_seconds}s.", "timeout"
        )

    def _fetch(self, image: dict[str, Any]) -> tuple[str, bytes]:
        query = urlencode({
            "filename": str(image.get("filename")),
            "subfolder": str(image.get("subfolder") or ""),
            "type": str(image.get("type") or "output"),
        })
        return str(image.get("filename")), self.transport.request_bytes(
            f"/view?{query}", timeout_seconds=self._step_timeout()
        )

    @staticmethod
    def _why(status: dict[str, Any]) -> str:
        """ComfyUI가 말한 이유를 그대로 옮긴다. 요약하면 단서가 사라진다."""
        messages = status.get("messages")
        if isinstance(messages, list):
            for message in messages:
                if isinstance(message, list) and len(message) > 1 and isinstance(message[1], dict):
                    detail = message[1].get("exception_message") or message[1].get("exception_type")
                    if detail:
                        return f"ComfyUI could not finish the image: {detail}"
        return "ComfyUI could not finish the image."

    def _graph(self, request: SceneImageRequest) -> dict[str, Any]:
        """`artifacts/flux-measure/try_flux_dev.py`에서 실제로 돌아간 9노드 그대로.

        FLUX는 cfg 1.0에 `FluxGuidance`가 따로 붙는 구조라 negative 자리에 같은
        conditioning이 들어간다 -- 실측 스크립트와 같게 둔다. 임의로 바꾸면 잰 값이
        이 그래프의 값이 아니게 된다.
        """
        return {
            "1": {"class_type": "UNETLoader", "inputs": {
                "unet_name": self.config.model_name, "weight_dtype": self.config.weight_dtype,
            }},
            "2": {"class_type": "DualCLIPLoader", "inputs": {
                "clip_name1": "t5xxl_fp16.safetensors", "clip_name2": "clip_l.safetensors", "type": "flux",
            }},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": request.prompt}},
            "5": {"class_type": "FluxGuidance", "inputs": {
                "conditioning": ["4", 0], "guidance": self.config.guidance,
            }},
            "6": {"class_type": "EmptySD3LatentImage", "inputs": {
                "width": request.width, "height": request.height, "batch_size": 1,
            }},
            "7": {"class_type": "KSampler", "inputs": {
                "model": ["1", 0], "positive": ["5", 0], "negative": ["4", 0], "latent_image": ["6", 0],
                "seed": request.seed, "steps": self.config.steps, "cfg": 1.0,
                "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
            }},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
            "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "videobox-scene"}},
        }


__all__ = ["ComfyUIHTTPTransport", "ComfyUIImageGenerationProvider", "ComfyUIProviderError"]
