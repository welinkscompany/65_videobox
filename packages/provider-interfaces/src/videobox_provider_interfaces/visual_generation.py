from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


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


@dataclass(slots=True, frozen=True)
class SceneVideoRequest:
    """대본의 한 장면에 얹을 짧은 영상 하나 (owner 결정 2026-08-29 2회차: 로컬
    비디오 모델). `SceneImageRequest`와 짝이지만 영상은 길이(프레임 수)가
    추가로 필요하다."""

    prompt: str
    width: int
    height: int
    seed: int
    #: Wan 계열은 4프레임 단위로 나뉜다((length-1) % 4 == 0) -- 그래프가 이 값을
    #: 그대로 못 실으면 조용히 다른 길이가 나온다.
    length_frames: int
    #: 빠른 미리보기는 스텝을 줄여서 시간을 줄인다(owner 요청 2026-08-29,
    #: 3회차). 화질(config 기본값)과 무관하게 요청마다 다르게 줄 수 있어야
    #: 해서 provider가 아니라 요청 쪽 값이다.
    steps: int


@dataclass(slots=True, frozen=True)
class GeneratedSceneVideo:
    """`GeneratedSceneImage`와 같은 이유로 바이트만 돌려준다 -- 저장·자산화는
    호출자(장면 서비스)가 맡는다."""

    provider_name: str
    video_bytes: bytes
    file_name: str
    metadata: dict[str, Any]


class SceneVideoProvider(Protocol):
    provider_name: str

    def generate_video(
        self,
        request: SceneVideoRequest,
        *,
        on_submitted: Callable[[str], None] | None = None,
        cancel_event: "threading.Event | None" = None,
    ) -> GeneratedSceneVideo:
        """Generate one short video clip for a script scene.

        코드리뷰(2026-08-30)로 잡힌 결함 -- `on_submitted`/`cancel_event`는
        취소 버튼(owner 요청 2026-08-29 3회차)을 위해 실제로 쓰이는 인자인데
        이 Protocol 선언에 빠져 있었다. `ComfyUIVideoGenerationProvider`(실제
        구현)와 `SceneVideoService._generate`(호출부)는 이미 이 모양으로
        맞춰져 있다 -- 이 선언이 그 계약을 뒤늦게 따라잡는다.
        """
