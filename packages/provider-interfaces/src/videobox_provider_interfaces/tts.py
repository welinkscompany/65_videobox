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
    #: 읽을 언어. `None`이면 엔진에 설정된 기본 언어(보통 한국어)를 쓴다.
    #:
    #: **요청마다 다를 수 있어야 한다.** 같은 프로젝트를 영어로 더빙하는 동안에도
    #: 원래 내레이션은 한국어다 -- 엔진 설정에만 언어가 있으면 하나를 고르는
    #: 순간 다른 하나를 못 만든다.
    language: str | None = None


@dataclass(slots=True, frozen=True)
class TTSResult:
    output_uri: str
    provider_name: str


class TTSProvider(Protocol):
    provider_name: str

    def synthesize(self, request: TTSRequest) -> TTSResult:
        """Generate a local-first narration replacement clip from a voice sample."""
