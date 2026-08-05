from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from videobox_provider_interfaces.faster_whisper_stt import (
    FasterWhisperSTTProvider,
    STTTranscriptionError,
)
from videobox_provider_interfaces.stt import STTRequest


@dataclass
class _FakeWhisperSegment:
    start: float
    end: float
    text: str
    avg_logprob: float
    no_speech_prob: float = 0.0


class _FakeWhisperModel:
    def __init__(self, segments: list[_FakeWhisperSegment]) -> None:
        self._segments = segments
        self.transcribe_calls: list[dict[str, object]] = []

    def transcribe(self, wav_path: str, **kwargs: object):
        self.transcribe_calls.append({"wav_path": wav_path, **kwargs})
        return iter(self._segments), {"language": "ko"}


def _fake_ffmpeg_ok(command: list[str], **_: object):
    output_path = Path(command[command.index("-c:a") + 2])
    output_path.write_bytes(b"RIFF....WAVEfmt ")

    class _Result:
        returncode = 0
        stderr = ""

    return _Result()


def test_transcribe_maps_whisper_segments_to_stt_segments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.faster_whisper_stt.subprocess.run",
        _fake_ffmpeg_ok,
    )
    source_audio = tmp_path / "narration.wav"
    source_audio.write_bytes(b"fake audio bytes")

    fake_model = _FakeWhisperModel(
        [
            _FakeWhisperSegment(start=0.0, end=1.2, text=" Hello there. ", avg_logprob=-0.05),
            _FakeWhisperSegment(start=1.2, end=2.5, text="Second line.", avg_logprob=-0.5),
        ]
    )
    provider = FasterWhisperSTTProvider(_model=fake_model)

    result = provider.transcribe(STTRequest(source_path=source_audio))

    assert result.provider_name == "faster_whisper"
    assert [segment.text for segment in result.segments] == ["Hello there.", "Second line."]
    # confidence is exp(avg_logprob): faster-whisper's decode-quality proxy.
    assert result.segments[0].confidence == pytest.approx(0.9512, abs=1e-3)
    assert result.segments[1].confidence == pytest.approx(0.6065, abs=1e-3)
    assert result.text == "Hello there. Second line."
    assert fake_model.transcribe_calls[0]["language"] == "ko"
    assert fake_model.transcribe_calls[0]["word_timestamps"] is True


def test_confidence_is_decode_quality_not_speech_presence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression guard for the bug found via verify_owner_path.py against the
    owner's real footage: every real segment came back "low_confidence" even
    though the transcript text was accurate, because confidence was computed
    from no_speech_prob (is this speech at all?) instead of avg_logprob (how
    sure was the decoder of these exact words?). A segment that is clearly
    speech but was decoded shakily must score low; a segment the VAD flagged
    as borderline-silence but that the decoder was confident about must not be
    dragged down by that unrelated signal.
    """
    monkeypatch.setattr(
        "videobox_provider_interfaces.faster_whisper_stt.subprocess.run",
        _fake_ffmpeg_ok,
    )
    source_audio = tmp_path / "narration.wav"
    source_audio.write_bytes(b"fake audio bytes")

    fake_model = _FakeWhisperModel(
        [
            # High no_speech_prob (a noisy chunk boundary) but the decoder was
            # confident about the words it produced.
            _FakeWhisperSegment(start=0.0, end=1.0, text="Clear speech.", avg_logprob=-0.05, no_speech_prob=0.81),
            # Low no_speech_prob (definitely speech) but the decoder struggled.
            _FakeWhisperSegment(start=1.0, end=2.0, text="Garbled speech.", avg_logprob=-1.6, no_speech_prob=0.02),
        ]
    )
    provider = FasterWhisperSTTProvider(_model=fake_model)

    result = provider.transcribe(STTRequest(source_path=source_audio))

    assert result.segments[0].confidence > 0.9
    assert result.segments[1].confidence < 0.25


def test_transcribe_respects_request_language_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "videobox_provider_interfaces.faster_whisper_stt.subprocess.run",
        _fake_ffmpeg_ok,
    )
    source_audio = tmp_path / "narration.wav"
    source_audio.write_bytes(b"fake audio bytes")
    fake_model = _FakeWhisperModel([])
    provider = FasterWhisperSTTProvider(_model=fake_model, language="ko")

    provider.transcribe(STTRequest(source_path=source_audio, language="en"))

    assert fake_model.transcribe_calls[0]["language"] == "en"


def test_transcribe_raises_when_ffmpeg_binary_missing(tmp_path: Path) -> None:
    source_audio = tmp_path / "narration.wav"
    source_audio.write_bytes(b"fake audio bytes")
    provider = FasterWhisperSTTProvider(_model=_FakeWhisperModel([]), ffmpeg_binary="videobox-nonexistent-ffmpeg")

    with pytest.raises(STTTranscriptionError, match="ffmpeg binary"):
        provider.transcribe(STTRequest(source_path=source_audio))


def test_transcribe_raises_on_ffmpeg_conversion_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_ffmpeg_failure(command: list[str], **_: object):
        class _Result:
            returncode = 1
            stderr = "invalid data found when processing input"

        return _Result()

    monkeypatch.setattr(
        "videobox_provider_interfaces.faster_whisper_stt.subprocess.run",
        _fake_ffmpeg_failure,
    )
    source_audio = tmp_path / "narration.wav"
    source_audio.write_bytes(b"not really audio")
    provider = FasterWhisperSTTProvider(_model=_FakeWhisperModel([]))

    with pytest.raises(STTTranscriptionError, match="ffmpeg failed"):
        provider.transcribe(STTRequest(source_path=source_audio))
