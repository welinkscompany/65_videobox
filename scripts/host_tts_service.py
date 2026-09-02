"""호스트에서 목소리 복제 엔진을 지키고 서서, 컨테이너의 요청을 받아 읽어 준다.

## 왜 이게 따로 있나

목소리를 복제하는 엔진은 torch와 2GB짜리 모델이 필요해서 컨테이너 이미지에
넣으면 이미지가 3GB 가까이 커진다. 그런데 **이 컴퓨터에는 이미 깔려 있다.**
그림 생성이 ComfyUI를 호스트에서 부르는 것과 같은 방식으로, 있는 것을 쓴다.
owner가 2026-09-02에 승인했다.

## 어떻게 띄우나

목소리 엔진이 깔린 파이썬으로 띄운다. **저장소 루트의 `.venv`다** --
worktree의 `.venv`가 아니다(거기엔 torch가 없다).

```
COQUI_TOS_AGREED=1 <저장소루트>/.venv/Scripts/python.exe scripts/host_tts_service.py
```

## 밖으로 안 나간다

127.0.0.1에만 묶는다. 컨테이너는 `host.docker.internal`로 이 컴퓨터에 닿고,
그건 도커가 놓아 주는 같은 경로다. 바깥에서는 못 부른다.

## 엔진은 갈아 끼울 수 있다

`VIDEOBOX_HOST_TTS_ENGINE`으로 고른다. **라이선스가 다르므로**(XTTS는 비상업용,
chatterbox는 MIT) 무엇으로 돌고 있는지 시작할 때 찍어 준다.

| 엔진 | 띄우는 파이썬 | 라이선스 |
|---|---|---|
| `local_xtts` (기본) | 저장소 루트 `.venv` | Coqui CPML (비상업용) |
| `chatterbox` | 저장소 루트 `.venv-chatterbox` | MIT |

**둘은 한 환경에 못 넣는다.** chatterbox는 torch 2.6을 요구해서 같은 venv에
넣으면 torch가 내려가고 XTTS가 깨진다(2026-09-02 실측). 그래서 venv를 나눈다.

```
python -m venv .venv-chatterbox
.venv-chatterbox/Scripts/python -m pip install chatterbox-tts "setuptools<81"
VIDEOBOX_HOST_TTS_ENGINE=chatterbox .venv-chatterbox/Scripts/python scripts/host_tts_service.py
```

`setuptools<81`이 필요한 이유가 있다. chatterbox가 쓰는 워터마커(`perth`)가
`pkg_resources`를 부르는데 setuptools 81부터 그게 빠졌다. `perth`는 그 import
실패를 조용히 삼키고 클래스를 `None`으로 두어서, 정작 터질 때는
**`'NoneType' object is not callable`**이라는 엉뚱한 말이 나온다(2026-09-02에
여기서 한참 헤맸다).
"""

from __future__ import annotations

import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading

REPO_ROOT = Path(__file__).resolve().parents[1]
for src_path in (
    REPO_ROOT / "packages" / "provider-interfaces" / "src",
    REPO_ROOT / "packages" / "domain-models" / "src",
    REPO_ROOT / "packages" / "storage-abstractions" / "src",
    REPO_ROOT / "packages" / "core-engine" / "src",
):
    sys.path.insert(0, str(src_path))

HOST = "127.0.0.1"
PORT = 8199
#: 목소리 샘플까지 실려 오므로 넉넉히. 그래도 무한은 아니다.
MAX_BODY_BYTES = 32 * 1024 * 1024


def _build_provider():
    engine = os.environ.get("VIDEOBOX_HOST_TTS_ENGINE", "local_xtts").strip() or "local_xtts"
    language = os.environ.get("VIDEOBOX_TTS_LANGUAGE", "ko").strip() or "ko"
    if engine == "chatterbox":
        from videobox_provider_interfaces.chatterbox_tts_provider import ChatterboxTTSProvider

        return ChatterboxTTSProvider(language=language), engine, "MIT"
    from videobox_provider_interfaces.local_xtts_provider import LocalXTTSProvider

    # XTTS는 Coqui CPML이라 **비상업용**이다. 상업적으로 쓰려면 chatterbox로 바꾼다.
    return LocalXTTSProvider(language=language), engine, "Coqui CPML (비상업용)"


class _Handler(BaseHTTPRequestHandler):
    provider = None
    engine_name = ""
    #: 목소리 모델은 **여러 갈래로 동시에 못 쓴다.** 요청은 각자 다른 실에서
    #: 오는데 모델은 하나뿐이라, 두 요청이 겹치면 소리가 섞이거나 죽는다
    #: (코드리뷰 2026-09-02). 읽는 일(`/health`)은 이 자물쇠를 안 지난다.
    synthesis_lock = threading.Lock()

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _fail(self, code: int, message: str) -> None:
        self._send(code, json.dumps({"detail": message}).encode("utf-8"), "application/json")

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self._fail(404, "not found")
            return
        self._send(
            200,
            json.dumps({"status": "ok", "engine": self.engine_name}).encode("utf-8"),
            "application/json",
        )

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/synthesize":
            self._fail(404, "not found")
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY_BYTES:
            self._fail(413, "request body missing or too large")
            return
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._fail(400, "body must be JSON")
            return

        text = str(payload.get("text") or "").strip()
        if not text:
            self._fail(400, "text is required")
            return
        sample_b64 = payload.get("voice_sample_base64")
        if not isinstance(sample_b64, str) or not sample_b64:
            self._fail(400, "voice_sample_base64 is required for voice cloning")
            return

        from videobox_provider_interfaces.tts import TTSRequest

        suffix = str(payload.get("voice_sample_suffix") or ".wav")
        if not suffix.startswith(".") or len(suffix) > 8:
            suffix = ".wav"
        with tempfile.TemporaryDirectory(prefix="videobox_host_tts_") as raw_dir:
            work = Path(raw_dir)
            sample_path = work / f"sample{suffix}"
            try:
                sample_path.write_bytes(base64.b64decode(sample_b64, validate=True))
            except Exception:
                self._fail(400, "voice_sample_base64 is not valid base64")
                return
            output = work / "spoken.wav"
            try:
                with self.synthesis_lock:
                    self.provider.synthesize(
                        TTSRequest(
                            text=text,
                            voice_sample_uri=str(sample_path),
                            output_path=output,
                            language=str(payload.get("language") or "") or None,
                        )
                    )
            except Exception as exc:  # noqa: BLE001 - 사유를 그대로 돌려준다
                self._fail(500, f"{type(exc).__name__}: {exc}"[:500])
                return
            self._send(200, output.read_bytes(), "audio/wav")

    def log_message(self, fmt: str, *args: object) -> None:
        # 기본 로그는 목소리 샘플이 실린 요청까지 그대로 찍는다. 짧게 줄인다.
        sys.stderr.write(f"[voice-bridge] {self.command} {self.path}\n")


def main() -> None:
    provider, engine, licence = _build_provider()
    _Handler.provider = provider
    _Handler.engine_name = engine
    print(f"[voice-bridge] 엔진: {engine} · 라이선스: {licence}")
    print(f"[voice-bridge] http://{HOST}:{PORT} 에서 기다립니다. 컨테이너에서는 host.docker.internal:{PORT}")
    ThreadingHTTPServer((HOST, PORT), _Handler).serve_forever()


if __name__ == "__main__":
    main()
