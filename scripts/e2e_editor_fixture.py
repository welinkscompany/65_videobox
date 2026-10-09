"""e2e 고정 시험 프로젝트를 임시 폴더에 결정적으로 만든다 (2026-10-08 계획 H Task 1).

깨끗한 것: 0907에서 실측한 경계(1.8990646 등)를 그대로 가진 네 장면.
오염된 것: 2026-09-20 되돌린 커밋이 남긴 모양 -- 저장된 편집판 트랙에 세션 투영
클립(`session-…`)이 박혀 있다. 이 시드가 그 모양을 잃으면 Task 4의 회귀 시험이
아무것도 지키지 않게 된다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
for src_path in (
    REPO_ROOT / "services" / "api" / "src",
    REPO_ROOT / "packages" / "domain-models" / "src",
    REPO_ROOT / "packages" / "storage-abstractions" / "src",
    REPO_ROOT / "packages" / "provider-interfaces" / "src",
    REPO_ROOT / "packages" / "timeline-schema" / "src",
    REPO_ROOT / "packages" / "core-engine" / "src",
    REPO_ROOT / "packages" / "capcut-export" / "src",
):
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

from videobox_domain_models.assets import AssetType  # noqa: E402
from videobox_storage.local_project_store import LocalProjectStore  # noqa: E402

#: 0907-b26195af 실측 경계(2026-10-08 점검 §3-1). 셋째 장면 시작 1.8990646 -- 재생기는 1.899064를 알려 온다.
CLEAN_SCENE_BOUNDS: tuple[tuple[str, float, float], ...] = (
    ("scene-1", 0.0, 1.3324),
    ("scene-2", 1.3324, 1.8990646),
    ("scene-3", 1.8990646, 2.9281),
    ("scene-4", 2.9281, 3.7512),
)
CLEAN_PROJECT_NAME = "편집 실사용 시험"
DUPLICATED_PROJECT_NAME = "겹친 오버레이 재현"
PARENT = "timeline_001:001"
NO_NARRATION_PROJECT_NAME = "내레이션 없는 프로젝트 재현"
#: 742e1924(2026-10-09 실기 점검)의 모양: 내레이션 줄이 비어 있고, 자막의 `segment_id`(계보)는 분할 전 낡은
#: 값인데 `owning_segment_id`만 장면마다 다르다. (소유 id, 시작, 끝, 자막의 낡은 계보 id)
NO_NARRATION_SCENES: tuple[tuple[str, float, float, str], ...] = (
    (PARENT, 0.0, 2.0, PARENT),
    (f"{PARENT}__split_2", 2.0, 4.5, f"{PARENT}__split_2"),
    (f"{PARENT}__split_2__split_2", 4.5, 7.0, f"{PARENT}__split_2"),
    (f"{PARENT}__split_2__split_3", 7.0, 9.5, f"{PARENT}__split_2"),
)

#: 재생 매끄러움 시험(2026-10-09 계획 P Task 0)용 30초 네 장면. 20초 넘게 틀어야 되감기 고리가 쌓인다.
PLAYBACK_SCENES: tuple[tuple[str, float, float], ...] = (
    ("scene-1", 0.0, 7.5),
    ("scene-2", 7.5, 15.0),
    ("scene-3", 15.0, 22.5),
    ("scene-4", 22.5, 30.0),
)
PLAYBACK_PROJECT_NAME = "재생 매끄러움 시험"
#: 캡컷 단축키 편집 시험(2026-10-09 계획 P2 Task 0)용. 장면은 재생 시험과 같고, 편집 키가 재생 측정 프로젝트를 바꾸지 않게 따로 둔다.
SHORTCUTS_PROJECT_NAME = "단축키 시험"

_COLORS = ("blue", "green", "orange", "purple")
_CAPTIONS = ("첫 장면", "둘째 장면", "셋째 장면", "넷째 장면")


def _ffmpeg(*args: str) -> None:
    exe = shutil.which("ffmpeg")
    if exe is None:
        raise RuntimeError("ffmpeg가 필요합니다")
    result = subprocess.run([exe, "-y", "-v", "error", *args], capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 실패: {result.stderr}")


def _make_media(media_dir: Path) -> dict[str, Any]:
    media_dir.mkdir(parents=True, exist_ok=True)
    narration = media_dir / "narration.wav"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=330:duration=4", str(narration))
    narration_30 = media_dir / "narration-30.wav"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=330:duration=30", str(narration_30))
    brolls = []
    for index, color in enumerate(_COLORS, start=1):
        path = media_dir / f"broll-{index}.mp4"
        _ffmpeg(
            "-f", "lavfi", "-i", f"color=c={color}:s=640x360:r=30:d=2",
            "-f", "lavfi", "-i", "sine=frequency=550:duration=2",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path),
        )
        brolls.append(path)
    overlay = media_dir / "overlay.png"
    _ffmpeg("-f", "lavfi", "-i", "color=c=white:s=320x180", "-frames:v", "1", str(overlay))
    return {"narration": narration, "narration_30": narration_30, "brolls": brolls, "overlay": overlay}


def _narration_clip(clip_id: str, segment_id: str, start: float, end: float, asset: Any) -> dict[str, Any]:
    return {
        "clip_id": clip_id,
        "segment_id": segment_id,
        "start_sec": start,
        "end_sec": end,
        "source_in_sec": start,
        "source_out_sec": end,
        "asset_id": asset.asset_id,
        "asset_uri": asset.storage_uri,
    }


def _timeline_payload(clips: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "output": {"width": 1280, "height": 720},
        "fps_num": 30,
        "fps_den": 1,
        "tracks": [{"track_id": "narration_primary", "track_type": "narration", "clips": clips}],
    }


def _overlay(asset: Any) -> list[dict[str, Any]]:
    return [{"overlay_type": "image_overlay", "asset_id": asset.asset_id, "asset_uri": asset.storage_uri, "text": ""}]


def _register(store: LocalProjectStore, project_id: str, media: dict[str, Any]) -> dict[str, Any]:
    return {
        "narration": store.register_asset(project_id=project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=media["narration"]),
        "brolls": [store.register_asset(project_id=project_id, asset_type=AssetType.BROLL_VIDEO, source_path=p) for p in media["brolls"]],
        "overlay": store.register_asset(project_id=project_id, asset_type=AssetType.IMAGE, source_path=media["overlay"]),
    }


def _segment(
    segment_id: str, start: float, end: float, caption: str, broll: Any, overlays: list[dict[str, Any]], **extra: Any
) -> dict[str, Any]:
    return {
        "segment_id": segment_id,
        "start_sec": start,
        "end_sec": end,
        "caption_text": caption,
        "cut_action": "keep",
        "review_required": False,
        "broll_override": {"asset_id": broll.asset_id, "asset_uri": broll.storage_uri, "media_controls": {}},
        "visual_overlays": overlays,
        **extra,
    }


def _seed_clean(store: LocalProjectStore, media: dict[str, Any]) -> dict[str, str]:
    project = store.bootstrap_project(name=CLEAN_PROJECT_NAME)
    assets = _register(store, project.project_id, media)
    clips = [
        _narration_clip(f"clip_narration_{i:03d}", sid, start, end, assets["narration"])
        for i, (sid, start, end) in enumerate(CLEAN_SCENE_BOUNDS, start=1)
    ]
    timeline = store.save_timeline_run(
        project_id=project.project_id, output_mode="landscape", timeline_payload=_timeline_payload(clips)
    )
    segments = [
        _segment(sid, start, end, _CAPTIONS[i], assets["brolls"][i], _overlay(assets["overlay"]) if i < 3 else [])
        for i, (sid, start, end) in enumerate(CLEAN_SCENE_BOUNDS)
    ]
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={"segments": segments, "history": []},
    )
    return {"project_id": project.project_id, "session_id": session["session_id"], "timeline_id": timeline["timeline_id"]}


def _seed_duplicated(store: LocalProjectStore, media: dict[str, Any]) -> dict[str, str]:
    project = store.bootstrap_project(name=DUPLICATED_PROJECT_NAME)
    assets = _register(store, project.project_id, media)
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="landscape",
        timeline_payload=_timeline_payload([_narration_clip("clip_narration_001", PARENT, 0.0, 4.0, assets["narration"])]),
    )
    pieces = (
        (PARENT, 0.0, 1.5, 0.0, True),
        (f"{PARENT}__split_3", 1.5, 2.5, 1.5, True),
        (f"{PARENT}__split_2", 2.5, 4.0, 2.5, False),
    )
    segments = [
        _segment(
            sid, start, end, _CAPTIONS[i], assets["brolls"][i],
            _overlay(assets["overlay"]) if has_overlay else [],
            source_slices=[{"segment_id": PARENT, "source_offset_sec": offset, "duration_sec": end - start}],
        )
        for i, (sid, start, end, offset, has_overlay) in enumerate(pieces)
    ]
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={"segments": segments, "history": []},
    )
    # Task 4 이후엔 `save_timeline_run`이 이런 오버레이 트랙을 거절한다. 2026-09-20 되돌린
    # 커밋이 남긴 옛 데이터를 흉내 내려면 편집판 JSON 파일에 직접 써 넣을 수밖에 없다.
    timeline_path = store.resolve_storage_uri(
        project_id=project.project_id,
        storage_uri=store.get_timeline_run(project_id=project.project_id, timeline_id=timeline["timeline_id"])["file_uri"],
    )

    def overlay_clip(clip_id: str, segment_id: str, start: float, end: float) -> dict[str, Any]:
        return {
            "clip_id": clip_id, "segment_id": segment_id, "start_sec": start, "end_sec": end,
            "overlay_type": "image_overlay", "asset_id": assets["overlay"].asset_id, "asset_uri": assets["overlay"].storage_uri,
        }

    stored = json.loads(timeline_path.read_text(encoding="utf-8"))
    stored["tracks"].append({
        "track_id": "track_overlay",
        "track_type": "overlay",
        "clips": [
            overlay_clip(f"session-overlay-{PARENT}-0-0", PARENT, 0.0, 1.5),
            overlay_clip(f"session-overlay-{PARENT}__split_3-0-0", f"{PARENT}__split_3", 1.5, 2.5),
            overlay_clip(f"session-overlay-{PARENT}-0-0", PARENT, 0.0, 1.5),
        ],
    })
    timeline_path.write_text(json.dumps(stored, indent=2, ensure_ascii=True), encoding="utf-8")
    return {"project_id": project.project_id, "session_id": session["session_id"], "timeline_id": timeline["timeline_id"]}


def _seed_no_narration(store: LocalProjectStore, media: dict[str, Any]) -> dict[str, str]:
    project = store.bootstrap_project(name=NO_NARRATION_PROJECT_NAME)
    assets = _register(store, project.project_id, media)
    timeline = store.save_timeline_run(
        project_id=project.project_id, output_mode="landscape", timeline_payload=_timeline_payload([])
    )
    segments = []
    for i, (sid, start, end, lineage) in enumerate(NO_NARRATION_SCENES):
        segments.append(_segment(
            sid, start, end, _CAPTIONS[i], assets["brolls"][i], [],
            content_windows=[{
                "start_offset_sec": 0.0, "duration_sec": end - start, "source_segment_id": lineage,
                "caption_text": _CAPTIONS[i], "visual_overlays": [],
            }],
        ))
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={"segments": segments, "history": []},
    )
    return {"project_id": project.project_id, "session_id": session["session_id"], "timeline_id": timeline["timeline_id"]}


#: 캡컷 키 시험(Q·W)이 영상 배치에도 닿는지 재려고 `shortcuts` 프로젝트에만 영상 한 칸을 얹는 장면(15~22.5초).
SHORTCUTS_BROLL_SCENE = "scene-3"


def _seed_playback(
    store: LocalProjectStore, media: dict[str, Any], *, name: str = PLAYBACK_PROJECT_NAME, with_broll: bool = False
) -> dict[str, str]:
    project = store.bootstrap_project(name=name)
    narration = store.register_asset(project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=media["narration_30"])
    clips = [
        _narration_clip(f"clip_narration_{i:03d}", sid, start, end, narration)
        for i, (sid, start, end) in enumerate(PLAYBACK_SCENES, start=1)
    ]
    timeline = store.save_timeline_run(
        project_id=project.project_id, output_mode="landscape", timeline_payload=_timeline_payload(clips)
    )
    broll = (
        store.register_asset(project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=media["brolls"][2])
        if with_broll else None
    )
    segments = [
        {
            "segment_id": sid, "start_sec": start, "end_sec": end, "caption_text": f"재생 시험 {i}",
            "cut_action": "keep", "review_required": False, "visual_overlays": [],
            **(
                {"broll_override": {"asset_id": broll.asset_id, "asset_uri": broll.storage_uri, "media_controls": {}}}
                if broll is not None and sid == SHORTCUTS_BROLL_SCENE else {}
            ),
        }
        for i, (sid, start, end) in enumerate(PLAYBACK_SCENES, start=1)
    ]
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={"segments": segments, "history": []},
    )
    return {"project_id": project.project_id, "session_id": session["session_id"], "timeline_id": timeline["timeline_id"]}


def seed_editor_fixtures(*, projects_root: Path, media_dir: Path) -> dict[str, dict[str, str]]:
    media = _make_media(Path(media_dir))
    store = LocalProjectStore(Path(projects_root))
    return {
        "clean": _seed_clean(store, media),
        "duplicated_overlays": _seed_duplicated(store, media),
        "no_narration": _seed_no_narration(store, media),
        "playback": _seed_playback(store, media),
        "shortcuts": _seed_playback(store, media, name=SHORTCUTS_PROJECT_NAME, with_broll=True),
    }
