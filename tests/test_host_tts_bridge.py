"""호스트 목소리 다리 -- 이 컴퓨터 밖으로는 못 나간다.

목소리 샘플이 실려 나가는 요청이라 주소 검사가 특히 중요하다. 그림(ComfyUI)
다리와 **같은 규칙**을 쓴다: 정해진 호스트·정해진 포트·경로 없음·리다이렉트 금지.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from videobox_provider_interfaces.gtts_provider import TTSSynthesisError
from videobox_provider_interfaces.host_tts_bridge_provider import HostTTSBridgeProvider
from videobox_provider_interfaces.tts import TTSRequest


def _sample(tmp_path: Path) -> Path:
    path = tmp_path / "voice.wav"
    path.write_bytes(b"RIFF....WAVEfake-voice-sample")
    return path


def _request(tmp_path: Path, **overrides: Any) -> TTSRequest:
    defaults = {
        "text": "Hello there",
        "voice_sample_uri": str(_sample(tmp_path)),
        "output_path": tmp_path / "out.wav",
        "language": "en",
    }
    return TTSRequest(**{**defaults, **overrides})


def test_the_spoken_audio_is_written_where_asked(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def client(request: Any, timeout: int) -> bytes:
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data)
        return b"RIFF-spoken-audio"

    provider = HostTTSBridgeProvider(http_client=client)
    result = provider.synthesize(_request(tmp_path))

    assert (tmp_path / "out.wav").read_bytes() == b"RIFF-spoken-audio"
    assert result.provider_name == "host_bridge"
    assert seen["url"] == "http://127.0.0.1:8199/synthesize"


def test_the_voice_sample_travels_as_content_not_as_a_path(tmp_path: Path) -> None:
    """컨테이너와 호스트는 같은 경로를 안 본다.

    경로를 보내면 호스트에서 못 찾거나, 더 나쁘게는 **다른 파일을 찾는다.**
    """
    seen: dict[str, Any] = {}

    def client(request: Any, timeout: int) -> bytes:
        seen["body"] = json.loads(request.data)
        return b"RIFF-spoken"

    HostTTSBridgeProvider(http_client=client).synthesize(_request(tmp_path))

    sent = base64.b64decode(seen["body"]["voice_sample_base64"])
    assert sent == b"RIFF....WAVEfake-voice-sample"
    assert "voice_sample_uri" not in seen["body"]
    assert str(tmp_path) not in json.dumps(seen["body"])


def test_the_request_language_is_what_gets_spoken(tmp_path: Path) -> None:
    """엔진 기본이 한국어여도 **영어 자막은 영어로 읽어야 한다.**"""
    seen: dict[str, Any] = {}

    def client(request: Any, timeout: int) -> bytes:
        seen["body"] = json.loads(request.data)
        return b"RIFF-spoken"

    HostTTSBridgeProvider(http_client=client, language="ko").synthesize(_request(tmp_path))

    assert seen["body"]["language"] == "en"


@pytest.mark.parametrize(
    "base_url",
    [
        "http://evil.example.com:8199",
        "https://127.0.0.1:8199",
        "http://127.0.0.1:9999",
        "http://127.0.0.1:8199/prefix",
        "http://127.0.0.1:8199?x=1",
        "http://user:pw@127.0.0.1:8199",
    ],
)
def test_the_bridge_refuses_to_leave_this_machine(tmp_path: Path, base_url: str) -> None:
    """**목소리 샘플이 실려 나가는 요청이다.** 주소가 조금이라도 다르면 안 보낸다."""
    called = False

    def client(request: Any, timeout: int) -> bytes:
        nonlocal called
        called = True
        return b""

    provider = HostTTSBridgeProvider(base_url=base_url, http_client=client)
    with pytest.raises(TTSSynthesisError):
        provider.synthesize(_request(tmp_path))
    assert called is False


def test_the_container_address_is_allowed(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def client(request: Any, timeout: int) -> bytes:
        seen["url"] = request.full_url
        return b"RIFF-spoken"

    HostTTSBridgeProvider(
        base_url="http://host.docker.internal:8199", http_client=client
    ).synthesize(_request(tmp_path))

    assert seen["url"] == "http://host.docker.internal:8199/synthesize"


def test_a_missing_voice_sample_says_so_before_calling(tmp_path: Path) -> None:
    """복제 엔진은 참조할 목소리가 있어야 한다. 호스트까지 갔다가 실패하면
    왜인지가 안 보인다."""
    called = False

    def client(request: Any, timeout: int) -> bytes:
        nonlocal called
        called = True
        return b""

    provider = HostTTSBridgeProvider(http_client=client)
    with pytest.raises(TTSSynthesisError, match="Voice sample not found"):
        provider.synthesize(_request(tmp_path, voice_sample_uri=str(tmp_path / "nope.wav")))
    assert called is False


def test_a_sleeping_bridge_says_how_to_wake_it(tmp_path: Path) -> None:
    """가장 흔한 실패다. **무엇을 켜야 하는지**까지 말해 준다."""
    from urllib.error import URLError

    def client(request: Any, timeout: int) -> bytes:
        raise URLError("connection refused")

    provider = HostTTSBridgeProvider(http_client=client)
    with pytest.raises(TTSSynthesisError, match="host_tts_service"):
        provider.synthesize(_request(tmp_path))
