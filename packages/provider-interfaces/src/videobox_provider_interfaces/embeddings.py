from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True, frozen=True)
class EmbeddingRequest:
    model_name: str
    inputs: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class EmbeddingResponse:
    provider_name: str
    model_name: str
    vectors: tuple[tuple[float, ...], ...]


class EmbeddingProvider(Protocol):
    provider_name: str

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Return one local embedding vector per input."""
