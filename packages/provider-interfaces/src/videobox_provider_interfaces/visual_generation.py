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


@dataclass(slots=True, frozen=True)
class SceneImageRequest:
    """대본의 한 장면에 얹을 그림 한 장. §10.14 조항 2-C."""

    prompt: str
    width: int
    height: int
    seed: int


@dataclass(slots=True, frozen=True)
class GeneratedSceneImage:
    """provider가 돌려주는 것은 **바이트지 자산이 아니다.**

    위의 `VisualGenerationProvider`는 `asset_uri`를 돌려주는 모양이라 이 자리에
    맞지 않는다 -- 그 모양대로 하면 provider가 프로젝트 저장소를 알아야 한다.
    어디에 어떻게 저장할지는 자산 쪽 규칙(내용 해시·보상 삭제·분석 걸기)이고,
    그것은 `scene_image_service`가 이미 있는 경로로 처리한다.
    """

    provider_name: str
    image_bytes: bytes
    file_name: str
    metadata: dict[str, Any]


class SceneImageProvider(Protocol):
    provider_name: str

    def generate_image(self, request: SceneImageRequest) -> GeneratedSceneImage:
        """Generate one still image for a script scene."""
