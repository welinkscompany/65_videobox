from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(slots=True, frozen=True)
class STTRequest:
    source_path: Path
    language: str | None = None


@dataclass(slots=True, frozen=True)
class STTSegment:
    start_sec: float
    end_sec: float
    text: str
    confidence: float = 1.0


@dataclass(slots=True, frozen=True)
class STTResult:
    text: str
    segments: list[STTSegment]
    provider_name: str


class STTProvider(Protocol):
    provider_name: str

    def transcribe(self, request: STTRequest) -> STTResult:
        """Transcribe a local asset into timestamped segments."""


class MockSTTProvider:
    provider_name = "mock_stt"

    def transcribe(self, request: STTRequest) -> STTResult:
        stem_text = request.source_path.stem.replace("-", " ").replace("_", " ").strip()
        normalized = stem_text or "untitled recording"
        segments = [
            STTSegment(start_sec=0.0, end_sec=1.0, text="Line one.", confidence=0.99),
            STTSegment(
                start_sec=1.0,
                end_sec=2.2,
                text=f"Line two with restart from {normalized}.",
                confidence=0.72,
            ),
        ]
        return STTResult(
            text=" ".join(segment.text for segment in segments),
            segments=segments,
            provider_name=self.provider_name,
        )
