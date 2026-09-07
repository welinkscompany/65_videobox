"""캡컷 초안에서도 사진이 움직이는가 — owner 요청 2026-09-06.

> owner: "캡컷 내보내기도 사진 움직임 넣어줘"

사진 장면이 어떻게 움직일지는 `media_controls.photo_motion`이 정하고, 완성본
렌더러는 `_photo_motion_chain`으로 zoompan을 건다. **캡컷 초안을 만드는 길은 그
값을 아예 안 읽고 있었다** — 그래서 캡컷으로 넘겨 마무리하면 사진이 멈춘 그림으로
갔다.

캡컷 초안은 조각마다 키프레임을 실을 수 있다(`pycapcut`의 `add_keyframe`,
`KFTypeScaleX`/`KFTypePositionX`/`KFTypePositionY`). **정해진 움직임 하나를 양
끝 두 점으로 적는 것**이라 화면에 임의 키프레임을 여는 것과는 다르다(`§2.1`의
"임의 키프레임 범위 밖"은 우리 편집 화면 이야기다).

여기서 재는 것은 셋이다.

1. 고른 움직임이 실제로 초안 파일 안에 들어가는가.
2. `still`과 영상 장면은 **손대지 않는가**(움직이면 안 되는 것이 움직이면 결함이다).
3. 안 골랐을 때 완성본과 **같은 방향**으로 도는가 — 렌더러는 클립 이름 해시로
   정한다. 두 길이 다르면 캡컷에서 연 그림이 완성본과 다르게 움직인다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_capcut_export.pycapcut_adapter import PyCapCutRealExportAdapter
from videobox_core_engine.media_controls import PHOTO_MOTIONS
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

pytestmark = pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe가 없으면 소재를 만들 수 없다")


def _generate(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True)


def _broll_segment(
    tmp_path: Path,
    *,
    media_controls: dict | None,
    photo: bool = True,
    clip_id: str = "session-broll-seg_001-0",
) -> dict:
    """사진(또는 영상) 장면 하나짜리 초안을 실제로 만들고 그 조각을 돌려준다."""
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="사진 움직임 캡컷 초안")
    narration_path = tmp_path / "narration.wav"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4", str(narration_path)])
    narration_asset = store.register_asset(
        project_id=project.project_id, asset_type=AssetType.NARRATION_AUDIO, source_path=narration_path
    )
    if photo:
        scene_path = tmp_path / "scene.jpg"
        _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=640x480", "-frames:v", "1", str(scene_path)])
        scene_asset = store.register_asset(
            project_id=project.project_id, asset_type=AssetType.IMAGE, source_path=scene_path
        )
    else:
        scene_path = tmp_path / "scene.mp4"
        _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=6:size=640x480:rate=15", str(scene_path)])
        scene_asset = store.register_asset(
            project_id=project.project_id, asset_type=AssetType.BROLL_VIDEO, source_path=scene_path
        )

    clip: dict = {
        "clip_id": clip_id,
        "asset_uri": f"local://projects/{project.project_id}/assets/{scene_asset.asset_id}",
        "start_sec": 0.0,
        "end_sec": 4.0,
    }
    if media_controls is not None:
        clip["media_controls"] = media_controls

    result = PyCapCutRealExportAdapter(store=store, video_width=640, video_height=480, video_fps=15).export_timeline(
        project_id=project.project_id,
        timeline={
            "narration_source_uri": narration_asset.storage_uri,
            "tracks": [
                {"track_type": "narration", "clips": [{
                    "asset_uri": f"local://projects/{project.project_id}/segments/seg_001",
                    "start_sec": 0.0, "end_sec": 4.0,
                }]},
                {"track_type": "broll", "clips": [clip]},
            ],
        },
        drafts_root=tmp_path / "drafts",
        draft_name="photo-motion",
        editing_session={"caption_style": {}, "segments": []},
    )
    content = json.loads((result.draft_path / "draft_content.json").read_text(encoding="utf-8"))
    tracks = {track["name"]: track["segments"] for track in content["tracks"]}
    return tracks["broll"][0]


def _keyframes(segment: dict) -> dict[str, list[tuple[int, float]]]:
    return {
        entry["property_type"]: [
            (keyframe["time_offset"], keyframe["values"][0]) for keyframe in entry["keyframe_list"]
        ]
        for entry in segment["common_keyframes"]
    }


def test_a_photo_that_zooms_in_reaches_the_capcut_draft(tmp_path: Path) -> None:
    keyframes = _keyframes(_broll_segment(tmp_path, media_controls={"photo_motion": "zoom_in", "loop": False}))

    assert "KFTypeScaleX" in keyframes, f"확대가 초안에 안 실렸다: {keyframes}"
    first, last = keyframes["KFTypeScaleX"][0], keyframes["KFTypeScaleX"][-1]
    assert first == (0, pytest.approx(1.0))
    assert last[0] == 4_000_000, "마지막 키프레임이 장면 끝에 있어야 한다"
    assert last[1] == pytest.approx(1.12), "완성본과 같은 배율(1.12)이어야 한다"


def test_a_photo_that_zooms_out_starts_wide_and_ends_at_one(tmp_path: Path) -> None:
    keyframes = _keyframes(_broll_segment(tmp_path, media_controls={"photo_motion": "zoom_out", "loop": False}))

    assert [value for _, value in keyframes["KFTypeScaleX"]] == [pytest.approx(1.12), pytest.approx(1.0)]


def test_panning_left_slides_the_picture_left_at_a_steady_zoom(tmp_path: Path) -> None:
    """`pan_left`은 그림이 왼쪽으로 흐른다 -- 캡컷 좌표에서 position_x가 줄어든다.

    확대는 그대로 걸려 있어야 한다. 안 그러면 밀린 만큼 배경이 드러난다.
    """
    keyframes = _keyframes(_broll_segment(tmp_path, media_controls={"photo_motion": "pan_left", "loop": False}))

    assert [value for _, value in keyframes["KFTypePositionX"]] == [pytest.approx(0.12), pytest.approx(-0.12)]
    assert [value for _, value in keyframes["KFTypeScaleX"]] == [pytest.approx(1.12), pytest.approx(1.12)]
    assert "KFTypePositionY" not in keyframes


def test_panning_right_is_the_mirror_of_panning_left(tmp_path: Path) -> None:
    keyframes = _keyframes(_broll_segment(tmp_path, media_controls={"photo_motion": "pan_right", "loop": False}))

    assert [value for _, value in keyframes["KFTypePositionX"]] == [pytest.approx(-0.12), pytest.approx(0.12)]


def test_panning_up_moves_the_picture_up(tmp_path: Path) -> None:
    keyframes = _keyframes(_broll_segment(tmp_path, media_controls={"photo_motion": "pan_up", "loop": False}))

    assert [value for _, value in keyframes["KFTypePositionY"]] == [pytest.approx(-0.12), pytest.approx(0.12)]
    assert "KFTypePositionX" not in keyframes


def test_a_still_photo_is_left_alone(tmp_path: Path) -> None:
    """`still`은 "움직이지 않기"다. 여기에 키프레임을 얹으면 고른 것과 반대가 된다."""
    segment = _broll_segment(tmp_path, media_controls={"photo_motion": "still", "loop": False})

    assert segment["common_keyframes"] == []


def test_a_video_scene_never_gets_photo_motion(tmp_path: Path) -> None:
    """영상은 이미 움직인다. 완성본 렌더러도 사진에만 건다 -- 여기도 같아야 한다."""
    segment = _broll_segment(tmp_path, media_controls={"photo_motion": "zoom_in", "loop": False}, photo=False)

    assert segment["common_keyframes"] == []


def test_a_photo_with_no_chosen_motion_still_moves_the_way_the_final_render_does(tmp_path: Path) -> None:
    """안 고르면 완성본은 클립 이름으로 방향을 정한다. 초안도 같은 방향이어야 한다."""
    clip_id = "session-broll-seg_001-0"
    expected = PHOTO_MOTIONS[sum(clip_id.encode()) % len(PHOTO_MOTIONS)]
    keyframes = _keyframes(_broll_segment(tmp_path, media_controls={"loop": False}, clip_id=clip_id))

    assert keyframes, "안 골랐다고 멈춰 있으면 완성본과 다르다"
    if expected.startswith("zoom"):
        assert "KFTypePositionX" not in keyframes and "KFTypePositionY" not in keyframes
        assert keyframes["KFTypeScaleX"][0][1] != keyframes["KFTypeScaleX"][-1][1]
    else:
        axis = "KFTypePositionX" if expected in ("pan_left", "pan_right") else "KFTypePositionY"
        assert axis in keyframes, f"{expected}인데 {axis}가 없다: {keyframes}"


def test_a_photo_scene_without_media_controls_at_all_still_moves(tmp_path: Path) -> None:
    """`media_controls` 칸 자체가 없는 장면이 제품의 기본값이다."""
    assert _broll_segment(tmp_path, media_controls=None)["common_keyframes"]


def test_the_draft_uses_the_same_numbers_as_the_final_render() -> None:
    """배율과 "안 골랐을 때 방향" 두 가지가 완성본 쪽과 같은 수인가.

    두 벌을 두면 어긋난다. 렌더러 파일은 이 작업에서 손대지 않기로 한 자리라
    값을 가져다 쓸 이름이 없다 -- 그래서 **원문과 맞대어 본다**(전환·색감 표가
    이미 쓰는 방식이다).
    """
    renderer = (
        Path(__file__).resolve().parents[1]
        / "packages" / "core-engine" / "src" / "videobox_core_engine" / "ffmpeg_final_renderer.py"
    ).read_text(encoding="utf-8")
    adapter = (
        Path(__file__).resolve().parents[1]
        / "packages" / "capcut-export" / "src" / "videobox_capcut_export" / "pycapcut_adapter.py"
    ).read_text(encoding="utf-8")

    assert "ratio = 1.12" in renderer, "렌더러의 배율이 바뀌었다 -- 초안 쪽 _PHOTO_MOTION_ZOOM도 같이 옮겨라"
    assert "_PHOTO_MOTION_ZOOM = 1.12" in adapter
    assert "sum(clip_id.encode()) % len(motions)" in renderer, (
        "렌더러가 안 골랐을 때 방향을 정하는 방법이 바뀌었다 -- 초안 쪽도 같이 옮겨라"
    )
    assert "sum(clip_id.encode()) % len(PHOTO_MOTIONS)" in adapter
