from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videobox_provider_interfaces.stt import STTRequest, STTResult, STTSegment


class STTTranscriptionError(RuntimeError):
    pass


def _convert_to_wav(source_path: Path, *, ffmpeg_binary: str) -> Path:
    fd, raw_output_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    output_path = Path(raw_output_path)
    command = [
        ffmpeg_binary,
        "-y",
        "-i",
        str(source_path),
        "-ar",
        "16000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except FileNotFoundError as exc:
        raise STTTranscriptionError(
            f"ffmpeg binary '{ffmpeg_binary}' was not found. Install ffmpeg to enable transcription."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise STTTranscriptionError(f"ffmpeg timed out converting '{source_path}' to wav.") from exc
    if result.returncode != 0:
        raise STTTranscriptionError(f"ffmpeg failed converting '{source_path}' to wav: {result.stderr[-500:]}")
    return output_path


@dataclass(slots=True)
class FasterWhisperSTTProvider:
    provider_name: str = "faster_whisper"
    model_size: str = "small"
    device: str = "cpu"
    compute_type: str = "int8"
    language: str | None = "ko"
    ffmpeg_binary: str = "ffmpeg"
    _model: Any = None

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise STTTranscriptionError(
                    "faster-whisper is not installed. Run `pip install faster-whisper`."
                ) from exc
            self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
        return self._model

    def transcribe(self, request: STTRequest) -> STTResult:
        wav_path = _convert_to_wav(request.source_path, ffmpeg_binary=self.ffmpeg_binary)
        try:
            model = self._get_model()
            language = request.language or self.language
            segment_iter, _info = model.transcribe(
                str(wav_path),
                language=language,
                word_timestamps=True,
                vad_filter=True,
            )
            segments = [
                STTSegment(
                    start_sec=float(segment.start),
                    end_sec=float(segment.end),
                    text=segment.text.strip(),
                    confidence=round(min(1.0, max(0.0, 1.0 - float(segment.no_speech_prob))), 4),
                )
                for segment in segment_iter
            ]
            return STTResult(
                text=" ".join(segment.text for segment in segments),
                segments=segments,
                provider_name=self.provider_name,
            )
        finally:
            wav_path.unlink(missing_ok=True)


__all__ = ["FasterWhisperSTTProvider", "STTTranscriptionError"]
