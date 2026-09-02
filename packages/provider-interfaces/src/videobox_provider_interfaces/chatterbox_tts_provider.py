"""대표님 목소리로 내레이션을 만든다 — 상업적으로 써도 되는 엔진으로.

XTTS-v2도 목소리 복제를 하지만 **Coqui CPML은 비상업용**이라, 이 제품으로 매출을 내는
순간 쓸 수 없다. Chatterbox Multilingual(Resemble AI)은 **MIT**이고 한국어를 지원해서
그 제약이 없다. 기능이 부족해서가 아니라 라이선스 때문에 바꾼 것이다.

XTTS와 마찬가지로 무거운 선택 설치이고 모델을 처음 쓸 때 내려받는다. 기본값은 꺼져 있다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videobox_provider_interfaces.gtts_provider import TTSSynthesisError
from videobox_provider_interfaces.tts import TTSRequest, TTSResult


def _import_chatterbox() -> Any:
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    return ChatterboxMultilingualTTS


def _save_wav(path: Path, wav: Any, sample_rate: int) -> None:
    import torchaudio

    torchaudio.save(str(path), wav, sample_rate)


@dataclass(slots=True)
class ChatterboxTTSProvider:
    """Chatterbox Multilingual(MIT)로 음성 샘플을 참조해 한국어 내레이션을 만든다."""

    provider_name: str = "chatterbox"
    language: str = "ko"
    device: str = "cpu"
    _model: Any = None

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                chatterbox = _import_chatterbox()
            except ImportError as exc:
                raise TTSSynthesisError(
                    "chatterbox-tts is not installed. Run `pip install chatterbox-tts` "
                    "(plus a matching PyTorch build) to enable local voice cloning."
                ) from exc
            self._model = chatterbox.from_pretrained(device=self.device)
        return self._model

    def synthesize(self, request: TTSRequest) -> TTSResult:
        if not request.text.strip():
            raise TTSSynthesisError("Cannot synthesize empty text.")
        speaker_wav = Path(request.voice_sample_uri)
        if not speaker_wav.exists():
            # 어느 파일이 없는지 말해 준다. "실패했어요"만으로는 고칠 수 없다.
            raise TTSSynthesisError(f"Voice sample not found: '{speaker_wav}'.")

        model = self._get_model()
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            wav = model.generate(
                request.text,
                audio_prompt_path=str(speaker_wav),
                language_id=request.language or self.language,
            )
            _save_wav(request.output_path, wav, getattr(model, "sr", 24000))
        except TTSSynthesisError:
            raise
        except Exception as exc:
            raise TTSSynthesisError(f"Chatterbox synthesis failed: {exc}") from exc
        return TTSResult(output_uri=str(request.output_path), provider_name=self.provider_name)


__all__ = ["ChatterboxTTSProvider"]
