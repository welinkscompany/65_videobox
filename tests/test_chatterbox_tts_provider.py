from __future__ import annotations

from pathlib import Path

import pytest

from videobox_provider_interfaces.chatterbox_tts_provider import ChatterboxTTSProvider
from videobox_provider_interfaces.gtts_provider import TTSSynthesisError
from videobox_provider_interfaces.tts import TTSRequest


class _FakeModel:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.sr = 24000

    def generate(self, text: str, **kwargs: object) -> str:
        self.calls.append({"text": text, **kwargs})
        return "waveform"


def _request(tmp_path: Path, *, text: str = "안녕하세요") -> TTSRequest:
    sample = tmp_path / "my-voice.wav"
    sample.write_bytes(b"RIFF....WAVE")
    return TTSRequest(text=text, voice_sample_uri=str(sample), output_path=tmp_path / "out" / "narration.wav")


def test_it_clones_from_the_voice_sample_in_korean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 대표님 목소리를 그대로 쓰는 것이 목적이다. 샘플을 넘기지 않으면 남의
    # 목소리가 나온다.
    model = _FakeModel()
    saved: dict = {}
    provider = ChatterboxTTSProvider()
    monkeypatch.setattr(ChatterboxTTSProvider, "_get_model", lambda _self: model)
    monkeypatch.setattr(
        "videobox_provider_interfaces.chatterbox_tts_provider._save_wav",
        lambda path, wav, sample_rate: saved.update({"path": path, "sample_rate": sample_rate}),
    )

    result = provider.synthesize(_request(tmp_path))

    assert model.calls[0]["audio_prompt_path"].endswith("my-voice.wav")
    assert model.calls[0]["language_id"] == "ko"
    assert result.provider_name == "chatterbox"
    assert saved["sample_rate"] == 24000


def test_it_refuses_to_synthesize_nothing(tmp_path: Path) -> None:
    with pytest.raises(TTSSynthesisError):
        ChatterboxTTSProvider().synthesize(_request(tmp_path, text="   "))


def test_it_says_which_voice_sample_is_missing(tmp_path: Path) -> None:
    # "실패했어요"만 나오면 owner가 무엇을 고쳐야 할지 모른다.
    request = TTSRequest(
        text="안녕하세요",
        voice_sample_uri=str(tmp_path / "gone.wav"),
        output_path=tmp_path / "out.wav",
    )

    with pytest.raises(TTSSynthesisError, match="gone.wav"):
        ChatterboxTTSProvider().synthesize(request)


def test_a_missing_install_explains_how_to_fix_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 무거운 선택 설치라 안 깔려 있을 수 있다. 그때 import 오류만 던지면
    # 무엇을 깔아야 하는지 알 수 없다.
    provider = ChatterboxTTSProvider()
    monkeypatch.setattr(
        "videobox_provider_interfaces.chatterbox_tts_provider._import_chatterbox",
        lambda: (_ for _ in ()).throw(ImportError("no module named chatterbox")),
    )

    with pytest.raises(TTSSynthesisError, match="chatterbox-tts"):
        provider.synthesize(_request(tmp_path))
