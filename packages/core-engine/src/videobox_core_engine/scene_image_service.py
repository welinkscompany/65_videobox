"""만든 그림을 **그 장면의 자산**으로 앉히는 자리. §10.14 조항 2-C.

provider는 바이트만 돌려준다. 제품이 되려면 그 다음이 있어야 한다 --
프로젝트 자산이 되고, 어느 장면 것인지 자기가 말하고, 초안 준비가 그 장면을
더 이상 공백으로 세지 않아야 한다. 부품과 제품의 차이가 그것이다(`CLAUDE.md` §4).

**그림 한 장이 자산 두 개가 된다.**

- `image` -- 겹치기·썸네일·라이브러리가 이미 읽는 종류다(2026-08-20에 화면까지 붙었다)
- `broll_video` -- 그 그림을 정지 화면으로 담은 짧은 클립

두 번째가 왜 필요한지가 이 파일의 핵심이다. 렌더 경로는 B-roll 입력을 **영상으로**
연다(`ffmpeg_final_renderer.py`에서 broll 소스는 `is_image=False`로 들어가고
`_probe_media_duration`이 길이를 요구한다). PNG를 B-roll 자리에 그냥 꽂으면 초안
화면까지는 멀쩡하고 **완성본에서 터진다.** 렌더 경로는 둘이라 한 곳만 고치면 같은
함정에 두 번 걸리므로(2026-08-11), 렌더를 건드리는 대신 그림을 그 경로가 이미 아는
모양으로 바꿔 넣는다.

**분석은 걸지 않는다.** 촬영본은 무엇이 찍혔는지 몰라서 화면 분석으로 설명을 얻지만,
만든 그림은 **우리가 쓴 프롬프트가 곧 설명**이다. 같은 그림을 다시 보고 더 나쁜
설명을 만들 이유가 없어서, 프롬프트를 제목·설명으로 그대로 적어 둔다.
"""
from __future__ import annotations

import secrets
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videobox_domain_models.assets import AssetType
from videobox_provider_interfaces.visual_generation import SceneImageProvider, SceneImageRequest


#: 가로는 owner가 찍는 크기, 세로는 숏폼. F-9가 재발하는 자리라 기본값을 못박는다 --
#: 세로가 기본이 되어 롱폼까지 전부 세로로 렌더된 적이 있다.
_LANDSCAPE = (1920, 1080)
_PORTRAIT = (1080, 1920)
_DEFAULT_SCENE_SECONDS = 5.0
#: 대본이 바뀌면 장면 길이가 조금씩 움직인다. 딱 맞게 만들어 두면 그때마다
#: "B-roll이 화면 시간보다 짧다"로 렌더가 멈춘다. 여유를 앞에 붙여 둔다.
_SCENE_HEADROOM_SECONDS = 2.0
_SCENE_FPS = 30


@dataclass(slots=True, frozen=True)
class SceneImageGenerationError(Exception):
    """왜 안 됐는지 코드로 말한다. provider의 분류(`blocked`/`timeout`/`failed`)를
    그대로 이어받고, 그 앞에서 우리가 막은 것은 `invalid`다.

    영어 문장을 화면까지 흘려보내지 않는다 -- 문장은 creator 문구로 옮길 방법이
    없어서 2026-08-20에 게이트 하나를 코드로 바꿨다.
    """

    message: str
    code: str

    def __str__(self) -> str:
        return self.message


@dataclass(slots=True)
class SceneImageService:
    store: Any
    provider: SceneImageProvider
    ffmpeg_binary: str = "ffmpeg"

    def generate_scene_image(
        self,
        *,
        project_id: str,
        prompt: str,
        segment_id: str,
        vertical: bool = False,
        duration_sec: float = _DEFAULT_SCENE_SECONDS,
        gap_slot_id: str | None = None,
    ) -> dict[str, Any]:
        cleaned = (prompt or "").strip()
        if not cleaned:
            raise SceneImageGenerationError("scene_image_prompt_empty", "invalid")
        if not (segment_id or "").strip():
            raise SceneImageGenerationError("scene_image_segment_missing", "invalid")
        width, height = _PORTRAIT if vertical else _LANDSCAPE
        # 씨앗을 고정하면 "다시 만들기"가 같은 그림을 돌려주는 -- 아무것도 안 하는
        # 버튼이 된다. 매번 새로 뽑고, 어느 씨앗이었는지는 자산에 적어 둔다.
        seed = secrets.randbelow(2**31)

        generated = self._generate(
            SceneImageRequest(prompt=cleaned, width=width, height=height, seed=seed)
        )

        scene_number = _scene_number(segment_id)
        title = f"{scene_number}번째 장면 그림" if scene_number else "장면 그림"
        shared = {
            "scene_segment_id": segment_id,
            "gap_slot_id": gap_slot_id,
            "prompt": cleaned,
            "generated_by": generated.provider_name,
            "seed": seed,
            "model_name": generated.metadata.get("model_name"),
            "elapsed_sec": generated.metadata.get("elapsed_sec"),
            # 라이선스는 실행 중에 눈에 보이지 않는 제약이다. 사람이 기억하는 것에
            # 맡기면 반드시 새어 나간다 -- 자산마다 스스로 말하게 둔다 (§10.14 2-C).
            "commercial_use_is_unrestricted": generated.metadata.get("commercial_use_is_unrestricted"),
        }

        registered: list[str] = []
        try:
            with tempfile.TemporaryDirectory(prefix="videobox-scene-image-") as folder:
                stage = Path(folder)
                still = stage / f"scene-{scene_number or 'x'}-{seed}.png"
                still.write_bytes(generated.image_bytes)
                image_asset = self.store.register_asset(
                    project_id=project_id,
                    asset_type=AssetType.IMAGE,
                    source_path=still,
                    source_kind="generated_image",
                    mime_type="image/png",
                    metadata={**shared, "title": title, "width": width, "height": height},
                )
                registered.append(image_asset.asset_id)

                clip = stage / f"scene-{scene_number or 'x'}-{seed}.mp4"
                self._still_to_clip(
                    still=still, target=clip, width=width, height=height,
                    duration_sec=max(float(duration_sec), 0.5) + _SCENE_HEADROOM_SECONDS,
                )
                scene_asset = self.store.register_asset(
                    project_id=project_id,
                    asset_type=AssetType.BROLL_VIDEO,
                    source_path=clip,
                    source_kind="generated_image",
                    mime_type="video/mp4",
                    metadata={**shared, "title": title, "source_image_asset_id": image_asset.asset_id},
                )
                registered.append(scene_asset.asset_id)
        except SceneImageGenerationError:
            self._compensate(project_id=project_id, asset_ids=registered)
            raise
        except Exception as exc:
            self._compensate(project_id=project_id, asset_ids=registered)
            raise SceneImageGenerationError("scene_image_store_failed", "failed") from exc

        return {
            "image_asset_id": image_asset.asset_id,
            "scene_asset_id": scene_asset.asset_id,
            "segment_id": segment_id,
            "title": title,
            "prompt": cleaned,
            "seed": seed,
            "elapsed_sec": generated.metadata.get("elapsed_sec"),
            "commercial_use_is_unrestricted": generated.metadata.get("commercial_use_is_unrestricted"),
        }

    def _generate(self, request: SceneImageRequest) -> Any:
        try:
            return self.provider.generate_image(request)
        except SceneImageGenerationError:
            raise
        except Exception as exc:
            # provider가 분류해 준 원인을 그대로 이어받는다. 여기서 한 낱말로
            # 뭉개면 화면이 "켜야 한다"와 "다시 걸면 된다"를 구분할 수 없다.
            code = getattr(exc, "code", None)
            raise SceneImageGenerationError(
                str(exc) or "scene_image_generation_failed",
                code if code in {"blocked", "timeout", "failed"} else "failed",
            ) from exc

    def _still_to_clip(self, *, still: Path, target: Path, width: int, height: int, duration_sec: float) -> None:
        """정지 화면을 그 길이만큼의 mp4로. 소리 트랙은 만들지 않는다 --
        무음 B-roll은 이미 다루고 있고, 빈 소리를 실으면 섞을 때 한 겹이 는다."""
        command = [
            self.ffmpeg_binary, "-y", "-v", "error",
            "-loop", "1", "-framerate", str(_SCENE_FPS), "-i", str(still),
            "-t", f"{duration_sec:.3f}",
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                   f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-r", str(_SCENE_FPS), "-an", str(target),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=180)
        except FileNotFoundError as exc:
            raise SceneImageGenerationError("scene_image_ffmpeg_missing", "blocked") from exc
        except subprocess.TimeoutExpired as exc:
            raise SceneImageGenerationError("scene_image_ffmpeg_timeout", "timeout") from exc
        if result.returncode != 0 or not target.is_file():
            # stderr를 자르지 않는다 -- 2026-08-16에 잘린 stderr 때문에 렌더 실패
            # 원인을 며칠 못 찾았다.
            raise SceneImageGenerationError(f"scene_image_clip_failed: {result.stderr}", "failed")

    def _compensate(self, *, project_id: str, asset_ids: list[str]) -> None:
        """반쯤 등록된 자산을 남기지 않는다. 그림만 남고 클립이 없으면 초안 준비가
        그 장면을 여전히 공백으로 세고, owner는 왜 안 채워졌는지 알 수 없다."""
        for asset_id in reversed(asset_ids):
            try:
                self.store.delete_asset(project_id=project_id, asset_id=asset_id)
            except Exception:  # noqa: BLE001 -- 보상 삭제 실패가 원래 원인을 덮으면 안 된다
                continue


def _scene_number(segment_id: str) -> int | None:
    """`script-3` -> 3. 초안 준비가 붙이는 이름이라 형식이 이것 하나다.

    화면의 `sceneNames.ts`와 같은 말로 부른다 -- 세는 자리가 두 벌이 되면 같은
    장면이 화면마다 다른 번호가 된다.
    """
    _, _, tail = str(segment_id).rpartition("-")
    return int(tail) if tail.isdigit() else None


__all__ = ["SceneImageGenerationError", "SceneImageService"]
