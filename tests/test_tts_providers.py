from __future__ import annotations

from pathlib import Path

import pytest

from videobox_provider_interfaces.elevenlabs_tts_provider import ElevenLabsTTSProvider
from videobox_provider_interfaces.gtts_provider import GTTSProvider, TTSSynthesisError
from videobox_provider_interfaces.local_xtts_provider import LocalXTTSProvider
from videobox_provider_interfaces.tts import TTSRequest


def test_gtts_provider_synthesizes_a_real_playable_mp3(tmp_path: Path) -> None:
    provider = GTTSProvider(language="en")
    output_path = tmp_path / "narration.mp3"

    result = provider.synthesize(
        TTSRequest(text="Hello from VideoBox.", voice_sample_uri="", output_path=output_path)
    )

    assert result.provider_name == "gtts"
    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_gtts_provider_rejects_empty_text(tmp_path: Path) -> None:
    provider = GTTSProvider()

    with pytest.raises(TTSSynthesisError, match="empty"):
        provider.synthesize(TTSRequest(text="   ", voice_sample_uri="", output_path=tmp_path / "out.mp3"))


class _FakeResponse:
    def __init__(self, *, status_code: int, content: bytes = b"", text: str = "") -> None:
        self.status_code = status_code
        self.content = content
        self.text = text


class _FakeElevenLabsClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.received_calls: list[dict[str, object]] = []

    def post(self, url, *, headers, json, timeout):  # noqa: ANN001
        self.received_calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return self.response


def test_elevenlabs_provider_writes_audio_bytes_on_success(tmp_path: Path) -> None:
    fake_client = _FakeElevenLabsClient(_FakeResponse(status_code=200, content=b"fake mp3 bytes"))
    provider = ElevenLabsTTSProvider(api_key="key123", voice_id="voice456", http_client=fake_client)
    output_path = tmp_path / "narration.mp3"

    result = provider.synthesize(
        TTSRequest(text="Hello.", voice_sample_uri="", output_path=output_path)
    )

    assert result.provider_name == "elevenlabs"
    assert output_path.read_bytes() == b"fake mp3 bytes"
    assert fake_client.received_calls[0]["url"].endswith("/voice456")
    assert fake_client.received_calls[0]["headers"]["xi-api-key"] == "key123"


def test_elevenlabs_provider_raises_on_quota_exceeded(tmp_path: Path) -> None:
    fake_client = _FakeElevenLabsClient(_FakeResponse(status_code=429))
    provider = ElevenLabsTTSProvider(api_key="key123", voice_id="voice456", http_client=fake_client)

    with pytest.raises(Exception, match="quota"):
        provider.synthesize(TTSRequest(text="Hello.", voice_sample_uri="", output_path=tmp_path / "out.mp3"))


def test_elevenlabs_provider_requires_voice_id(tmp_path: Path) -> None:
    provider = ElevenLabsTTSProvider(api_key="key123", voice_id="", http_client=_FakeElevenLabsClient(_FakeResponse(status_code=200)))

    with pytest.raises(Exception, match="voice_id"):
        provider.synthesize(TTSRequest(text="Hello.", voice_sample_uri="", output_path=tmp_path / "out.mp3"))


class _FakeXTTSModel:
    def __init__(self) -> None:
        self.received_calls: list[dict[str, object]] = []

    def tts_to_file(self, *, text, speaker_wav, language, file_path):  # noqa: ANN001
        self.received_calls.append(
            {"text": text, "speaker_wav": speaker_wav, "language": language, "file_path": file_path}
        )
        Path(file_path).write_bytes(b"fake cloned voice wav")


def test_local_xtts_provider_uses_voice_sample_as_speaker_reference(tmp_path: Path) -> None:
    speaker_wav = tmp_path / "voice_sample.wav"
    speaker_wav.write_bytes(b"fake speaker sample")
    fake_model = _FakeXTTSModel()
    provider = LocalXTTSProvider(_model=fake_model, language="ko")
    output_path = tmp_path / "narration.wav"

    result = provider.synthesize(
        TTSRequest(text="안녕하세요.", voice_sample_uri=str(speaker_wav), output_path=output_path)
    )

    assert result.provider_name == "local_xtts"
    assert output_path.read_bytes() == b"fake cloned voice wav"
    assert fake_model.received_calls[0]["speaker_wav"] == str(speaker_wav)
    assert fake_model.received_calls[0]["language"] == "ko"


def test_local_xtts_provider_raises_when_voice_sample_missing(tmp_path: Path) -> None:
    provider = LocalXTTSProvider(_model=_FakeXTTSModel())

    with pytest.raises(Exception, match="Voice sample not found"):
        provider.synthesize(
            TTSRequest(
                text="Hello.",
                voice_sample_uri=str(tmp_path / "missing.wav"),
                output_path=tmp_path / "out.wav",
            )
        )
