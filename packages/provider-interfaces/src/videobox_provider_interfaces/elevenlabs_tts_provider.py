from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from videobox_provider_interfaces.gtts_provider import TTSSynthesisError
from videobox_provider_interfaces.tts import TTSRequest, TTSResult


class ElevenLabsHTTPClient(Protocol):
    def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int) -> Any:
        """Execute a POST request and return a response object with .status_code/.content/.text."""


@dataclass(slots=True)
class ElevenLabsTTSProvider:
    """Real cloud voice-cloning TTS. Requires a voice already cloned on ElevenLabs
    (voice_id) — this provider does not upload voice_sample_uri to create one;
    that is a one-time setup step the operator does via the ElevenLabs dashboard/API."""

    api_key: str
    voice_id: str
    provider_name: str = "elevenlabs"
    base_url: str = "https://api.elevenlabs.io/v1/text-to-speech"
    model_id: str = "eleven_multilingual_v2"
    timeout_seconds: int = 60
    http_client: Callable[..., Any] | None = None

    def _client(self) -> Any:
        if self.http_client is not None:
            return self.http_client
        import requests

        return requests

    def synthesize(self, request: TTSRequest) -> TTSResult:
        if not request.text.strip():
            raise TTSSynthesisError("Cannot synthesize empty text.")
        if not self.api_key:
            raise TTSSynthesisError("ElevenLabs api_key is required.")
        if not self.voice_id:
            raise TTSSynthesisError("ElevenLabs voice_id is required.")

        client = self._client()
        response = client.post(
            f"{self.base_url}/{self.voice_id}",
            headers={
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": request.text,
                "model_id": self.model_id,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
            timeout=self.timeout_seconds,
        )
        if response.status_code == 429:
            raise TTSSynthesisError("ElevenLabs API quota exceeded (429).")
        if response.status_code != 200:
            raise TTSSynthesisError(f"ElevenLabs API error (status {response.status_code}): {response.text[:300]}")

        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        request.output_path.write_bytes(response.content)
        return TTSResult(output_uri=str(request.output_path), provider_name=self.provider_name)


__all__ = ["ElevenLabsTTSProvider"]
