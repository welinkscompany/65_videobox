"""컨테이너 안에서 **호스트에 있는 목소리 복제 엔진**을 부른다.

## 왜 다리인가

목소리를 복제하는 엔진(XTTS·chatterbox)은 torch와 2GB짜리 모델이 필요하다.
그걸 컨테이너 이미지에 넣으면 이미지가 3GB 가까이 커지고 재빌드가 매번 길어진다.
그런데 **그 엔진은 이미 이 컴퓨터에 깔려 있다**(저장소 루트 `.venv`).

그림 생성이 ComfyUI를 `host.docker.internal:8188`로 부르는 것과 **같은 방식**이다
(`docs/development-fast-path.ko.md` §10.14 조항 2-C). 컨테이너를 불리지 않고
이미 있는 것을 쓴다. owner가 2026-09-02에 이 방식을 승인했다.

## 목소리 샘플은 파일 경로가 아니라 **내용으로** 보낸다

컨테이너와 호스트가 같은 경로를 보지 않는다. 경로를 보내면 호스트에서 못 찾거나,
더 나쁘게는 **다른 파일을 찾는다.** 그래서 샘플 오디오를 실어 보낸다.

## 나가는 곳은 이 컴퓨터뿐이다

주소 검사는 ComfyUI 쪽과 같은 규칙이다 -- 정해진 호스트·정해진 포트·경로 없음.
리다이렉트도 막는다. 목소리 샘플이 실려 나가는 요청이라 더 그렇다.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from videobox_provider_interfaces.gtts_provider import TTSSynthesisError
from videobox_provider_interfaces.tts import TTSRequest, TTSResult


#: 이 컴퓨터 안에서만 부른다. 컨테이너에서는 `host.docker.internal`이 호스트다.
_ALLOWED_HOSTS = frozenset({"127.0.0.1", "host.docker.internal"})
#: 그림(8188) 옆자리. 바꾸려면 여기와 compose를 같이 바꾼다.
_BRIDGE_PORT = 8199


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        raise HTTPError(req.full_url, code, "voice bridge redirects are forbidden", headers, fp)


@dataclass(slots=True)
class HostTTSBridgeProvider:
    """호스트에서 도는 목소리 서비스를 부르는 내레이션 엔진."""

    provider_name: str = "host_bridge"
    base_url: str = "http://127.0.0.1:8199"
    language: str = "ko"
    timeout_seconds: int = 600
    http_client: Callable[..., Any] | None = None

    def _endpoint(self, path: str) -> str:
        """요청 직전에 다시 확인한다 -- 시작할 때 통과한 것과 이 요청이 거기로
        간다는 것은 다른 말이다(ComfyUI 쪽과 같은 이유)."""
        parsed = urlparse(self.base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in _ALLOWED_HOSTS
            or parsed.port != _BRIDGE_PORT
            or parsed.path
            or parsed.params
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise TTSSynthesisError(
                f"Voice bridge must be http://127.0.0.1:{_BRIDGE_PORT}, or "
                f"http://host.docker.internal:{_BRIDGE_PORT} in the container."
            )
        return f"{self.base_url}{path}"

    def synthesize(self, request: TTSRequest) -> TTSResult:
        text = request.text.strip()
        if not text:
            raise TTSSynthesisError("Cannot synthesize empty text.")
        sample = Path(request.voice_sample_uri) if request.voice_sample_uri else None
        if sample is None or not sample.exists():
            # 복제 엔진은 참조할 목소리가 있어야 한다. 없이 부르면 호스트에서
            # 실패하는데, 그때는 왜인지가 안 보인다.
            raise TTSSynthesisError(
                f"Voice sample not found: '{request.voice_sample_uri}'. "
                "Voice cloning needs a reference recording."
            )
        payload = {
            "text": text,
            "language": request.language or self.language,
            "voice_sample_base64": base64.b64encode(sample.read_bytes()).decode("ascii"),
            "voice_sample_suffix": sample.suffix.lower(),
        }
        audio = self._post("/synthesize", payload)
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        request.output_path.write_bytes(audio)
        if request.output_path.stat().st_size == 0:
            raise TTSSynthesisError("Voice bridge returned an empty file.")
        return TTSResult(output_uri=str(request.output_path), provider_name=self.provider_name)

    def _post(self, path: str, payload: dict[str, Any]) -> bytes:
        http_request = Request(
            self._endpoint(path),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            if self.http_client is not None:
                return self.http_client(http_request, timeout=self.timeout_seconds)
            with build_opener(_NoRedirect).open(http_request, timeout=self.timeout_seconds) as response:
                return response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300] if exc.fp else ""
            raise TTSSynthesisError(f"Voice bridge failed ({exc.code}): {detail}") from exc
        except URLError as exc:
            # 가장 흔한 실패다. **무엇을 켜야 하는지**까지 말해 준다.
            raise TTSSynthesisError(
                f"Voice bridge is not answering at {self.base_url}. "
                "Start it with `scripts/host_tts_service.py` on this machine."
            ) from exc
