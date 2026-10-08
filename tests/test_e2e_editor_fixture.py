"""e2e 고정 시험 프로젝트가 의도한 모양인지 (2026-10-08 계획 H Task 1).

깨끗한 것: 0907에서 실측한 경계(1.8990646 등)를 그대로 가진 네 장면.
오염된 것: 2026-09-20 되돌린 커밋이 남긴 모양 -- 저장된 편집판 트랙에 세션 투영
클립(`session-…`)이 박혀 있다. 이 시드가 그 모양을 잃으면 Task 4의 회귀 시험이
아무것도 지키지 않게 된다.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.e2e_editor_fixture import CLEAN_SCENE_BOUNDS, NO_NARRATION_SCENES, seed_editor_fixtures
from videobox_storage.local_project_store import LocalProjectStore

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg가 있어야 진짜 매체를 만든다")


def test_clean_fixture_has_the_0907_float_boundaries(tmp_path: Path) -> None:
    ids = seed_editor_fixtures(projects_root=tmp_path / "projects", media_dir=tmp_path / "media")
    store = LocalProjectStore(tmp_path / "projects")
    session = store.get_editing_session(project_id=ids["clean"]["project_id"], session_id=ids["clean"]["session_id"])
    assert [(s["segment_id"], s["start_sec"], s["end_sec"]) for s in session["segments"]] == list(CLEAN_SCENE_BOUNDS)
    assert CLEAN_SCENE_BOUNDS[2][1] == 1.8990646
    assert [bool(s.get("visual_overlays")) for s in session["segments"]] == [True, True, True, False]


def test_duplicated_fixture_keeps_session_projection_clips_in_its_stored_timeline(tmp_path: Path) -> None:
    ids = seed_editor_fixtures(projects_root=tmp_path / "projects", media_dir=tmp_path / "media")
    store = LocalProjectStore(tmp_path / "projects")
    fixture = ids["duplicated_overlays"]
    timeline = store.get_timeline_run(project_id=fixture["project_id"], timeline_id=fixture["timeline_id"])
    overlay_ids = [clip["clip_id"] for track in timeline["tracks"] if track["track_type"] == "overlay" for clip in track["clips"]]
    assert overlay_ids and all(clip_id.startswith("session-overlay-") for clip_id in overlay_ids)
    assert len(overlay_ids) != len(set(overlay_ids)), "0907처럼 같은 id가 두 번 있어야 한다"


def test_no_narration_fixture_has_the_742_shape_stale_caption_lineage_and_distinct_owners(tmp_path: Path) -> None:
    ids = seed_editor_fixtures(projects_root=tmp_path / "projects", media_dir=tmp_path / "media")
    store = LocalProjectStore(tmp_path / "projects")
    fixture = ids["no_narration"]
    timeline = store.get_timeline_run(project_id=fixture["project_id"], timeline_id=fixture["timeline_id"])
    assert not [clip for track in timeline["tracks"] if track["track_type"] == "narration" for clip in track["clips"]]
    session = store.get_editing_session(project_id=fixture["project_id"], session_id=fixture["session_id"])
    assert [(s["segment_id"], s["start_sec"], s["end_sec"]) for s in session["segments"]] == [(a, b, c) for a, b, c, _ in NO_NARRATION_SCENES]
    lineage = [s["content_windows"][0]["source_segment_id"] for s in session["segments"]]
    assert len(set(lineage)) < len(lineage), "자막 계보 id는 여러 장면이 같은 낡은 값을 달고 있어야 한다"
