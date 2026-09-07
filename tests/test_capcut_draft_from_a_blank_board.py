"""빈 편집판에서 캡컷 초안이 안 나온다 — 실측 2026-09-07.

`+ 새로 만들기`로 만든 편집본에 사진을 깔고 캡컷 초안을 요청하니 실패했다:

    Timeline has no narration_source_uri to resolve narration clip
    'local://projects/.../segments/timeline_001:001'

**어젯밤 완성본 경로에서 고친 것과 같은 뿌리다.** 빈 편집판에는 목소리 원본이
없는데 `TimelineBuilder`는 장면마다 **가상** 내레이션 클립을 만든다 -- 그 클립은
소리가 아니라 편집기가 그리는 장면 막대다.

완성본 쪽은 `is_silent_narration_placeholder`로 "없는 것"과 "낡은 것"을 갈라
없는 쪽만 지나가게 했다. 캡컷 경로는 그 판단을 안 쓰고 있었다.

**fail-open이 아니다.** 한때 신원이 있었던 흔적이 남아 있으면 그대로 막힌다.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from videobox_capcut_export.pycapcut_adapter import PyCapCutRealExportAdapter
from videobox_domain_models.assets import AssetType
from videobox_storage.local_project_store import LocalProjectStore

FFMPEG = shutil.which("ffmpeg") is not None


def _photo_timeline(store: LocalProjectStore, project_id: str, tmp_path: Path) -> dict:
    photo = tmp_path / "scene.jpg"
    # **진짜 사진이어야 한다.** 흉내 낸 바이트를 넣으면 pycapcut이 "그림 트랙이
    # 없다"고 거절한다 -- 우리 결함이 아니라 시험 입력의 문제다.
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:duration=1",
         "-frames:v", "1", str(photo)],
        check=True,
    )
    asset = store.register_asset(
        project_id=project_id, asset_type=AssetType.IMAGE, source_path=photo
    )
    return {
        "project_id": project_id,
        "timeline_id": "timeline_blank",
        # 빈 편집판이 만드는 모양 그대로 -- 목소리 원본이 없다.
        "narration_source_uri": None,
        "tracks": [
            {
                "track_type": "narration",
                "clips": [{
                    "clip_id": "narration_1", "segment_id": "seg_1",
                    "asset_uri": f"local://projects/{project_id}/segments/seg_1",
                    "start_sec": 0.0, "end_sec": 4.0,
                }],
            },
            {
                "track_type": "broll",
                "clips": [{
                    "clip_id": "broll_1", "segment_id": "seg_1",
                    "asset_uri": asset.storage_uri, "asset_id": asset.asset_id,
                    "start_sec": 0.0, "end_sec": 4.0,
                    "media_controls": {"photo_motion": "pan_left"},
                }],
            },
        ],
    }


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg가 없으면 초안을 만들 수 없다")
def test_a_board_with_no_recording_still_exports(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="빈 편집판 캡컷")
    timeline = _photo_timeline(store, project.project_id, tmp_path)

    draft = PyCapCutRealExportAdapter(store=store).export_timeline(
        project_id=project.project_id, timeline=timeline,
        drafts_root=tmp_path / "drafts", draft_name="blank-board-draft",
    )

    assert draft is not None


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg가 없으면 사진을 만들 수 없다")
def test_a_lost_recording_is_still_refused(tmp_path: Path) -> None:
    """**없는 것과 잃어버린 것은 다르다.** 한때 신원이 있었으면 그대로 막힌다."""
    from videobox_core_engine.output_source_verifier import OutputSourceStaleError

    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="잃어버린 녹음")
    timeline = _photo_timeline(store, project.project_id, tmp_path)
    timeline["tracks"][0]["clips"][0]["expected_content_sha256"] = "a" * 64

    # 잡는 것은 **더 앞선 울타리**(원본 신원 검사)다. 자리표시를 걸러내는
    # 판단이 "흔적이 남아 있으면 자리표시가 아니다"로 갈라 주기 때문에, 이
    # 클립은 걸러지지 않고 그 검사에 그대로 걸린다.
    with pytest.raises(OutputSourceStaleError, match="stale_output_asset"):
        PyCapCutRealExportAdapter(store=store).export_timeline(
            project_id=project.project_id, timeline=timeline,
            drafts_root=tmp_path / "drafts", draft_name="lost-recording-draft",
        )
