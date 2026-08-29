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
from typing import Any

from videobox_core_engine.scene_image_prompt import SceneImagePromptUnavailable, needs_rewriting
from videobox_domain_models.assets import AssetType
from videobox_provider_interfaces.visual_generation import SceneVideoProvider, SceneVideoRequest

_LANDSCAPE = (1920, 1080)
_PORTRAIT = (1080, 1920)
#: Wan은 4프레임 단위로 나뉜다((length-1) % 4 == 0). 81 = 24fps에서 약 3.3초 --
#: `_DEFAULT_SCENE_SECONDS`(scene_image_service.py의 5초)와 정확히 맞추면 매
#: 장면마다 값이 달라 그래프가 매번 다른 길이를 계산해야 한다. 고정값으로 둔다.
_FULL_LENGTH_FRAMES = 81
_FULL_STEPS = 20
_GIF_FPS = 12
_GIF_SCALE_WIDTH = 480

#: 빠른 미리보기(owner 요청 2026-08-29, 3회차). 실측(RTX 5090): 512x288·17프레임·
#: 8스텝이 약 12초, 1920x1080·81프레임·20스텝(고화질)이 약 18~23분 -- 프롬프트를
#: 고르는 동안 매번 20분을 기다리게 하지 않는다. 화질이 낮아 완성본에는 안 맞고,
#: 어떤 그림이 나오는지 가늠하는 용도다.
_PREVIEW_LANDSCAPE = (512, 288)
_PREVIEW_PORTRAIT = (288, 512)
_PREVIEW_LENGTH_FRAMES = 17
_PREVIEW_STEPS = 8


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

    def generate_scene_video(
        self,
        *,
        project_id: str,
        prompt: str,
        segment_id: str,
        vertical: bool = False,
        gap_slot_id: str | None = None,
        make_gif: bool = False,
        quality: str = "full",
    ) -> dict[str, Any]:
        cleaned = (prompt or "").strip()
        if not cleaned:
            raise SceneVideoGenerationError("scene_video_prompt_empty", "invalid")
        if not (segment_id or "").strip():
            raise SceneVideoGenerationError("scene_video_segment_missing", "invalid")
        if quality not in ("preview", "full"):
            raise SceneVideoGenerationError("scene_video_quality_invalid", "invalid")
        is_preview = quality == "preview"
        if is_preview:
            width, height = _PREVIEW_PORTRAIT if vertical else _PREVIEW_LANDSCAPE
            length_frames, steps = _PREVIEW_LENGTH_FRAMES, _PREVIEW_STEPS
        else:
            width, height = _PORTRAIT if vertical else _LANDSCAPE
            length_frames, steps = _FULL_LENGTH_FRAMES, _FULL_STEPS
        video_prompt = self._video_prompt(project_id=project_id, written=cleaned, vertical=vertical)
        seed = secrets.randbelow(2**31)

        generated = self._generate(SceneVideoRequest(
            prompt=video_prompt, width=width, height=height, seed=seed,
            length_frames=length_frames, steps=steps,
        ))

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

                gif_asset_id: str | None = None
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
        except SceneVideoGenerationError:
            self._compensate(project_id=project_id, asset_ids=registered)
            raise
        except Exception as exc:
            self._compensate(project_id=project_id, asset_ids=registered)
            raise SceneVideoGenerationError("scene_video_store_failed", "failed") from exc

        return {
            "scene_asset_id": scene_asset.asset_id,
            "gif_asset_id": gif_asset_id,
            "segment_id": segment_id,
            "title": title,
            "prompt": cleaned,
            "video_prompt": video_prompt,
            "quality": quality,
            "seed": seed,
            "elapsed_sec": generated.metadata.get("elapsed_sec"),
        }

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

    def _generate(self, request: SceneVideoRequest) -> Any:
        try:
            return self.provider.generate_video(request)
        except SceneVideoGenerationError:
            raise
        except Exception as exc:
            code = getattr(exc, "code", None)
            raise SceneVideoGenerationError(
                str(exc) or "scene_video_generation_failed",
                code if code in {"blocked", "timeout", "failed"} else "failed",
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


__all__ = ["SceneVideoGenerationError", "SceneVideoService"]
