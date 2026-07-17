from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(slots=True, frozen=True)
class TTSRequest:
    text: str
    voice_sample_uri: str
    output_path: Path
    target_duration_sec: float | None = None


@dataclass(slots=True, frozen=True)
class TTSResult:
    output_uri: str
    provider_name: str


class TTSProvider(Protocol):
    provider_name: str

    def synthesize(self, request: TTSRequest) -> TTSResult:
        """Generate a local-first narration replacement clip from a voice sample."""
