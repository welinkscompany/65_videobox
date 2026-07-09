from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videobox_provider_interfaces.gtts_provider import TTSSynthesisError
from videobox_provider_interfaces.tts import TTSRequest, TTSResult


@dataclass(slots=True)
class LocalXTTSProvider:
    """Real local voice cloning via Coqui XTTS-v2, using voice_sample_uri as the
    speaker reference wav. Verified working end-to-end on Windows/Python 3.12 —
    see requirements-runtime.txt for the exact dependency versions this needs
    (the obvious/latest versions of torch, numpy, and transformers all break it).
    Not installed by default. Downloads the ~2GB XTTS-v2 model on first use and
    requires accepting Coqui's non-commercial CPML license (COQUI_TOS_AGREED=1
    to accept non-interactively)."""

    provider_name: str = "local_xtts"
    model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    language: str = "ko"
    use_gpu: bool = False
    _model: Any = None

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                from TTS.api import TTS
            except ImportError as exc:
                raise TTSSynthesisError(
                    "coqui-tts is not installed. Run `pip install coqui-tts` "
                    "(plus a matching PyTorch build) to enable local voice cloning."
                ) from exc
            self._model = TTS(self.model_name, gpu=self.use_gpu)
        return self._model

    def synthesize(self, request: TTSRequest) -> TTSResult:
        if not request.text.strip():
            raise TTSSynthesisError("Cannot synthesize empty text.")
        speaker_wav = Path(request.voice_sample_uri)
        if not speaker_wav.exists():
            raise TTSSynthesisError(f"Voice sample not found: '{speaker_wav}'.")

        model = self._get_model()
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            model.tts_to_file(
                text=request.text,
                speaker_wav=str(speaker_wav),
                language=self.language,
                file_path=str(request.output_path),
            )
        except Exception as exc:
            raise TTSSynthesisError(f"Local XTTS synthesis failed: {exc}") from exc
        return TTSResult(output_uri=str(request.output_path), provider_name=self.provider_name)


__all__ = ["LocalXTTSProvider"]
