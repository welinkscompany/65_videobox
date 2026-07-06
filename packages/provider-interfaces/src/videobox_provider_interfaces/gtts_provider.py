from __future__ import annotations

from dataclasses import dataclass

from videobox_provider_interfaces.tts import TTSRequest, TTSResult


class TTSSynthesisError(RuntimeError):
    pass


@dataclass(slots=True)
class GTTSProvider:
    """Free, no-setup TTS fallback. Cannot clone a voice from voice_sample_uri —
    use LocalXTTSProvider or ElevenLabsTTSProvider for real voice cloning."""

    provider_name: str = "gtts"
    language: str = "ko"

    def synthesize(self, request: TTSRequest) -> TTSResult:
        if not request.text.strip():
            raise TTSSynthesisError("Cannot synthesize empty text.")
        try:
            from gtts import gTTS
        except ImportError as exc:
            raise TTSSynthesisError("gtts is not installed. Run `pip install gtts`.") from exc

        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            gTTS(text=request.text, lang=self.language).save(str(request.output_path))
        except Exception as exc:
            raise TTSSynthesisError(f"gTTS synthesis failed: {exc}") from exc
        return TTSResult(output_uri=str(request.output_path), provider_name=self.provider_name)


__all__ = ["GTTSProvider", "TTSSynthesisError"]
