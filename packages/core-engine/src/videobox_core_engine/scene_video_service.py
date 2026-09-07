"""장면에 **진짜 동영상**을 만드는 별도 자리. owner 결정 2026-08-29(2회차).

**`scene_image_service.py`를 건드리지 않는다.** owner가 명시적으로 "원래
만든거외에 별도로 만들자"고 했다 -- 정지 이미지+zoompan 경로(`SceneImageService`)는
그대로 두고, 진짜 동영상 생성은 여기 새 서비스가 맡는다. 둘 다 같은 장면에
쓸 수 있는 **선택지**이지 한쪽이 다른 쪽을 대체하지 않는다.

**두 가지를 만든다:**

- `broll_video` -- Wan이 만든 영상을 렌더 경로가 이미 아는 mp4로. B-roll 자리는
  `is_image=False`를 기대하므로(`scene_image_service.py`의 같은 교훈) ComfyUI가
  뱉는 webm을 h264 mp4로 다시 싼다.
- GIF 미리보기(선택) -- **새 자산 종류를 만들지 않는다.** `AssetType.IMAGE`로
  등록하면 `LibraryPreviewPane.tsx`가 이미 `<img src=...>`로 그림 자산을
  그리고 있어서(2026-08-29 확인: `isPicture` 분기), 애니메이션 GIF도 그 `<img>`가
  브라우저 기본 동작으로 그냥 재생한다 -- 화면 쪽을 하나도 안 고쳐도 된다.

**아직 실측 전이다.** owner 승인으로 ComfyUI에 텍스트 인코더·VAE를 받는 중이라
(2026-08-29), 이 서비스도 첫 실행에서 시간·자원을 재고 나서 타임아웃 같은 값을
다시 맞춰야 한다.
"""
from __future__ import annotations

import secrets
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NamedTuple

from videobox_core_engine.scene_image_prompt import SceneImagePromptUnavailable, needs_rewriting
from videobox_domain_models.assets import AssetType
from videobox_domain_models.library_assets import LibraryMediaType
from videobox_provider_interfaces.visual_generation import SceneVideoProvider, SceneVideoRequest

#: 화면·API가 고를 수 있는 화질 값 그 자체 -- 이 파일이 정본이다.
#: `services/api/.../models.py`가 이 값을 그대로 가져다 쓴다(코드리뷰
#: 2026-08-30로 잡힌 결함: 예전엔 이 문자열 목록이 여기·`models.py` 두 곳·
#: `apps/web/src/api.ts` 두 곳, 총 4곳에 손으로 각각 박혀 있어서 하나를
#: 빠뜨려도 컴파일 오류 없이 조용히 어긋날 수 있었다).
SceneVideoQuality = Literal["preview", "standard", "full"]
SCENE_VIDEO_QUALITIES: tuple[SceneVideoQuality, ...] = ("preview", "standard", "full")


class _QualityPreset(NamedTuple):
    landscape: tuple[int, int]
    portrait: tuple[int, int]
    length_frames: int
    steps: int


#: 화질별 실제 값 -- 위 문자열 목록과 짝을 이루는 표 하나. if/elif 가지 대신
#: 조회 한 번으로 고른다(코드리뷰 2026-08-30, 넷째 화질이 생겨도 이 표
#: 한 줄만 늘리면 된다).
_QUALITY_PRESETS: dict[SceneVideoQuality, _QualityPreset] = {
    # 빠른 미리보기(owner 요청 2026-08-29, 3회차). 실측(RTX 5090): 512x288·
    # 17프레임·8스텝이 약 12초 -- 프롬프트를 고르는 동안 매번 20분을 기다리게
    # 하지 않는다. 화질이 낮아 완성본에는 안 맞고, 어떤 그림이 나오는지
    # 가늠하는 용도다.
    "preview": _QualityPreset((512, 288), (288, 512), 17, 8),
    # 중간 화질(owner 요청 2026-08-30, "AI 영상 생성 단축 검토"). 미리보기
    # (12초)와 고화질(18~20분) 사이에 아무것도 없어서, 완성에 가까운 화질이
    # 필요한데 18분을 못 기다리는 경우 고를 자리가 없었다. 실측(RTX 5090,
    # 2026-08-30): 1280x720·65프레임·16스텝이 약 2분 19초(139초).
    "standard": _QualityPreset((1280, 720), (720, 1280), 65, 16),
    # Wan은 4프레임 단위로 나뉜다((length-1) % 4 == 0). 81 = 24fps에서 약
    # 3.3초 -- `_DEFAULT_SCENE_SECONDS`(scene_image_service.py의 5초)와
    # 정확히 맞추면 매 장면마다 값이 달라 그래프가 매번 다른 길이를 계산해야
    # 한다. 고정값으로 둔다. 실측(RTX 5090): 약 18~23분.
    "full": _QualityPreset((1920, 1080), (1080, 1920), 81, 20),
}

_GIF_FPS = 12
_GIF_SCALE_WIDTH = 480


@dataclass(slots=True, frozen=True)
class SceneVideoGenerationError(Exception):
    """`SceneImageGenerationError`와 같은 모양이다 -- provider 분류
    (`blocked`/`timeout`/`failed`)를 그대로 이어받고, 그 앞에서 막은 것은
    `invalid`다."""

    message: str
    code: str

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True)
class SceneVideoService:
    store: Any
    provider: SceneVideoProvider
    prompt_writer: Any | None = None
    ffmpeg_binary: str = "ffmpeg"
    #: owner 요청(2026-08-29, 3회차): "이렇게 생성된것도 우리 자산으로 들어가도록".
    #: 프로젝트 자산(위)과 별개로 자료실(여러 프로젝트가 나눠 쓰는 검색 가능한
    #: 라이브러리, `docs/development-fast-path.ko.md` §10.15)에도 등록한다 --
    #: 없으면 그림·B-roll처럼 이 장면 하나에만 갇힌다. 실패해도 20분 걸려 만든
    #: 프로젝트 자산 자체는 그대로 남아야 하므로 조용히 넘어간다.
    library_ingest: Any | None = None

    def generate_scene_video(
        self,
        *,
        project_id: str,
        prompt: str,
        segment_id: str,
        vertical: bool = False,
        gap_slot_id: str | None = None,
        make_gif: bool = False,
        quality: SceneVideoQuality = "full",
        on_prompt_submitted: Any | None = None,
        cancel_event: Any | None = None,
    ) -> dict[str, Any]:
        cleaned = (prompt or "").strip()
        if not cleaned:
            raise SceneVideoGenerationError("scene_video_prompt_empty", "invalid")
        if not (segment_id or "").strip():
            raise SceneVideoGenerationError("scene_video_segment_missing", "invalid")
        preset = _QUALITY_PRESETS.get(quality)
        if preset is None:
            raise SceneVideoGenerationError("scene_video_quality_invalid", "invalid")
        width, height = preset.portrait if vertical else preset.landscape
        length_frames, steps = preset.length_frames, preset.steps
        video_prompt = self._video_prompt(project_id=project_id, written=cleaned, vertical=vertical)
        seed = secrets.randbelow(2**31)

        generated = self._generate(
            SceneVideoRequest(
                prompt=video_prompt, width=width, height=height, seed=seed,
                length_frames=length_frames, steps=steps,
            ),
            on_prompt_submitted=on_prompt_submitted, cancel_event=cancel_event,
        )

        scene_number = _scene_number(segment_id)
        title = f"{scene_number}번째 장면 영상" if scene_number else "장면 영상"
        shared = {
            "quality": quality,
            "scene_segment_id": segment_id,
            "gap_slot_id": gap_slot_id,
            "prompt": cleaned,
            "video_prompt": video_prompt,
            "generated_by": generated.provider_name,
            "seed": seed,
            "model_name": generated.metadata.get("model_name"),
            "elapsed_sec": generated.metadata.get("elapsed_sec"),
        }

        registered: list[str] = []
        try:
            with tempfile.TemporaryDirectory(prefix="videobox-scene-video-") as folder:
                stage = Path(folder)
                webm = stage / f"scene-{scene_number or 'x'}-{seed}.webm"
                webm.write_bytes(generated.video_bytes)

                clip = stage / f"scene-{scene_number or 'x'}-{seed}.mp4"
                self._webm_to_mp4(source=webm, target=clip)
                scene_asset = self.store.register_asset(
                    project_id=project_id,
                    asset_type=AssetType.BROLL_VIDEO,
                    source_path=clip,
                    source_kind="generated_video",
                    mime_type="video/mp4",
                    metadata={**shared, "title": title},
                )
                registered.append(scene_asset.asset_id)
                library_asset_id, library_ingest_error = self._ingest_into_library(
                    media_type=LibraryMediaType.BROLL, source_path=clip,
                    project_id=project_id, segment_id=segment_id, asset_id=scene_asset.asset_id,
                    title=title,
                )

                gif_asset_id: str | None = None
                gif_library_asset_id: str | None = None
                gif_library_ingest_error: str | None = None
                if make_gif:
                    gif = stage / f"scene-{scene_number or 'x'}-{seed}.gif"
                    self._webm_to_gif(source=webm, target=gif)
                    gif_asset = self.store.register_asset(
                        project_id=project_id,
                        asset_type=AssetType.IMAGE,
                        source_path=gif,
                        source_kind="generated_video_gif",
                        mime_type="image/gif",
                        metadata={**shared, "title": f"{title} (GIF)", "source_video_asset_id": scene_asset.asset_id},
                    )
                    registered.append(gif_asset.asset_id)
                    gif_asset_id = gif_asset.asset_id
                    gif_library_asset_id, gif_library_ingest_error = self._ingest_into_library(
                        media_type=LibraryMediaType.IMAGE, source_path=gif,
                        project_id=project_id, segment_id=segment_id, asset_id=gif_asset.asset_id,
                        title=f"{title} (GIF)",
                    )

                # `list_scene_videos`(scene_videos.py)가 목록을 다시 보여 줄 때도
                # 이 값들을 알아야 한다 -- 만드는 순간의 응답에만 있으면 화면을
                # 새로고침한 뒤에는 자료실에 저장됐다는 사실이 사라져 보인다.
                # `_ingest_into_library`와 같은 이유로 이 patch 자체도 실패를
                # 삼킨다 -- 코드리뷰(2026-08-30)로 잡힌 결함: 이 호출이 실패
                # 예외를 그대로 던지면 바깥 `except Exception`이 방금 20분 걸려
                # 만든 자산까지 보상 삭제(compensate)해 버린다. 목록에서
                # `library_asset_id`가 안 보이는 것은 참을 수 있어도, 다 만든
                # 영상 자체를 지우면 안 된다.
                try:
                    self.store.update_asset_metadata(
                        project_id=project_id, asset_id=scene_asset.asset_id,
                        metadata_patch={
                            "library_asset_id": library_asset_id,
                            "gif_asset_id": gif_asset_id,
                            "gif_library_asset_id": gif_library_asset_id,
                            "library_ingest_error": library_ingest_error,
                            "gif_library_ingest_error": gif_library_ingest_error,
                        },
                    )
                except Exception:  # noqa: BLE001 -- 위 주석 참고: 방금 만든 자산을 지우면 안 된다
                    pass
        except SceneVideoGenerationError:
            self._compensate(project_id=project_id, asset_ids=registered)
            raise
        except Exception as exc:
            self._compensate(project_id=project_id, asset_ids=registered)
            raise SceneVideoGenerationError("scene_video_store_failed", "failed") from exc

        return {
            "scene_asset_id": scene_asset.asset_id,
            "gif_asset_id": gif_asset_id,
            "library_asset_id": library_asset_id,
            "gif_library_asset_id": gif_library_asset_id,
            "library_ingest_error": library_ingest_error,
            "gif_library_ingest_error": gif_library_ingest_error,
            "segment_id": segment_id,
            "title": title,
            "prompt": cleaned,
            "video_prompt": video_prompt,
            "quality": quality,
            "seed": seed,
            "elapsed_sec": generated.metadata.get("elapsed_sec"),
        }

    def _ingest_into_library(
        self, *, media_type: LibraryMediaType, source_path: Path,
        project_id: str, segment_id: str, asset_id: str, title: str,
    ) -> tuple[str | None, str | None]:
        """자료실(여러 프로젝트가 나눠 쓰는 검색 가능한 라이브러리)에도 등록한다
        -- 실패해도 20분 걸려 만든 프로젝트 자산은 그대로 둔다.

        코드리뷰(2026-08-30)로 잡힌 결함 -- 실패를 삼키기만 하고 어디에도
        남기지 않아서, 등록이 왜 안 됐는지 나중엔 알 방법이 없었다.
        `LibraryIngestService.ingest_batch`가 이미 같은 상황에서 쓰는
        `type(error).__name__` 관례를 그대로 따라 두 번째 값으로 돌려준다 --
        `generate_scene_video`가 이 값을 자산 메타데이터·응답에 같이 싣는다.
        `library_ingest`가 아예 없는 것(기능이 꺼진 정상 상태)은 오류가
        아니므로 `None`을 그대로 돌려준다."""
        if self.library_ingest is None:
            return None, None
        try:
            ingested = self.library_ingest.ingest(
                media_type=media_type,
                source=source_path,
                filename=source_path.name,
                idempotency_key=f"scene-video:{asset_id}",
                provenance={
                    "generated_by": "comfyui", "source_kind": "generated_video",
                    "project_id": project_id, "scene_segment_id": segment_id, "title": title,
                },
            )
            return str(ingested["library_asset_id"]), None
        except Exception as exc:  # noqa: BLE001 -- 자료실 등록 실패가 방금 만든 프로젝트 자산을 지우면 안 된다
            return None, type(exc).__name__

    def _video_prompt(self, *, project_id: str, written: str, vertical: bool) -> str:
        """`SceneImageService._image_prompt`와 같은 이유 -- 그림 모델과 마찬가지로
        영상 모델도 영어로만 말이 통한다(2026-08-21 실측이 그림 쪽에서 이미 확인됨)."""
        if not needs_rewriting(written):
            return written
        if self.prompt_writer is None:
            raise SceneVideoGenerationError("scene_video_prompt_needs_english", "invalid")
        try:
            return self.prompt_writer.write(project_id=project_id, line=written, vertical=vertical)
        except SceneImagePromptUnavailable as exc:
            raise SceneVideoGenerationError(str(exc), "blocked") from exc

    def _generate(
        self, request: SceneVideoRequest, *, on_prompt_submitted: Any | None = None, cancel_event: Any | None = None,
    ) -> Any:
        try:
            return self.provider.generate_video(
                request, on_submitted=on_prompt_submitted, cancel_event=cancel_event,
            )
        except SceneVideoGenerationError:
            raise
        except Exception as exc:
            code = getattr(exc, "code", None)
            # "cancelled"는 owner가 취소 버튼을 눌러 만든 결과다 -- 실패가
            # 아니라 owner의 명시적 선택이므로 `failed`로 뭉개지 않는다
            # (owner 요청 2026-08-29 3회차).
            raise SceneVideoGenerationError(
                str(exc) or "scene_video_generation_failed",
                code if code in {"blocked", "timeout", "failed", "cancelled"} else "failed",
            ) from exc

    def _webm_to_mp4(self, *, source: Path, target: Path) -> None:
        """렌더 경로가 이미 아는 모양(h264 mp4)으로 다시 싼다 --
        `scene_image_service.py`가 정지 이미지에 대해 이미 겪은 교훈과 같다:
        렌더는 B-roll을 영상으로 열고 `is_image=False`를 기대한다."""
        command = [
            self.ffmpeg_binary, "-y", "-v", "error", "-i", str(source),
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-threads", "2", "-an", str(target),
        ]
        self._run(command, target, "scene_video_mp4_failed")

    def _webm_to_gif(self, *, source: Path, target: Path) -> None:
        """팔레트 2단계 변환 -- ffmpeg 기본 GIF 변환은 색이 뭉갠다(고정 216색
        웹세이프 팔레트). 소스 영상에서 직접 팔레트를 뽑아 쓰면 훨씬 낫다."""
        palette = target.with_suffix(".palette.png")
        scale = f"fps={_GIF_FPS},scale={_GIF_SCALE_WIDTH}:-1:flags=lanczos"
        self._run([
            self.ffmpeg_binary, "-y", "-v", "error", "-i", str(source),
            "-vf", f"{scale},palettegen", str(palette),
        ], palette, "scene_video_gif_palette_failed")
        self._run([
            self.ffmpeg_binary, "-y", "-v", "error", "-i", str(source), "-i", str(palette),
            "-filter_complex", f"{scale}[x];[x][1:v]paletteuse", str(target),
        ], target, "scene_video_gif_failed")

    def _run(self, command: list[str], target: Path, error_code: str) -> None:
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=180)
        except FileNotFoundError as exc:
            raise SceneVideoGenerationError("scene_video_ffmpeg_missing", "blocked") from exc
        except subprocess.TimeoutExpired as exc:
            raise SceneVideoGenerationError("scene_video_ffmpeg_timeout", "timeout") from exc
        if result.returncode != 0 or not target.is_file():
            # stderr를 자르지 않는다 -- scene_image_service.py가 2026-08-16에
            # 잘린 stderr 때문에 며칠 헤맨 교훈을 그대로 지킨다.
            raise SceneVideoGenerationError(f"{error_code}: {result.stderr}", "failed")

    def _compensate(self, *, project_id: str, asset_ids: list[str]) -> None:
        for asset_id in reversed(asset_ids):
            try:
                self.store.delete_asset(project_id=project_id, asset_id=asset_id)
            except Exception:  # noqa: BLE001 -- 보상 삭제 실패가 원래 원인을 덮으면 안 된다
                continue


def _scene_number(segment_id: str) -> int | None:
    _, _, tail = str(segment_id).rpartition("-")
    return int(tail) if tail.isdigit() else None


__all__ = ["SCENE_VIDEO_QUALITIES", "SceneVideoGenerationError", "SceneVideoQuality", "SceneVideoService"]
