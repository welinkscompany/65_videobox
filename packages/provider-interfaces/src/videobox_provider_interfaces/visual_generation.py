from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True, frozen=True)
class VisualGenerationRequest:
    prompt: str
    project_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class VisualGenerationResponse:
    provider_name: str
    asset_uri: str
    metadata: dict[str, Any]


class VisualGenerationProvider(Protocol):
    provider_name: str

    def generate(self, request: VisualGenerationRequest) -> VisualGenerationResponse:
        """Generate an operator-review visual artifact."""
