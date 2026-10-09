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


def test_playback_fixture_is_thirty_seconds_in_four_scenes(tmp_path: Path) -> None:
    """재생 매끄러움 시험(계획 P Task 0)은 20초 넘게 틀 수 있는 편집본이 있어야 잰다."""
    from scripts.e2e_editor_fixture import PLAYBACK_SCENES
    ids = seed_editor_fixtures(projects_root=tmp_path / "projects", media_dir=tmp_path / "media")
    store = LocalProjectStore(tmp_path / "projects")
    session = store.get_editing_session(project_id=ids["playback"]["project_id"], session_id=ids["playback"]["session_id"])
    assert [(s["segment_id"], s["start_sec"], s["end_sec"]) for s in session["segments"]] == list(PLAYBACK_SCENES)
    assert PLAYBACK_SCENES[-1][2] == 30.0


def test_shortcuts_fixture_is_a_separate_thirty_second_project(tmp_path: Path) -> None:
    """캡컷 단축키 편집 시험(계획 P2 Task 0)은 재생 측정 프로젝트와 따로 쓴다 -- 서로 밟지 않게."""
    from scripts.e2e_editor_fixture import PLAYBACK_SCENES, SHORTCUTS_PROJECT_NAME
    ids = seed_editor_fixtures(projects_root=tmp_path / "projects", media_dir=tmp_path / "media")
    assert ids["shortcuts"]["project_id"] != ids["playback"]["project_id"]
    store = LocalProjectStore(tmp_path / "projects")
    session = store.get_editing_session(project_id=ids["shortcuts"]["project_id"], session_id=ids["shortcuts"]["session_id"])
    assert [(s["segment_id"], s["start_sec"], s["end_sec"]) for s in session["segments"]] == list(PLAYBACK_SCENES)
    assert SHORTCUTS_PROJECT_NAME == "단축키 시험"
    assert store.get_project(project_id=ids["shortcuts"]["project_id"])["name"] == SHORTCUTS_PROJECT_NAME


def test_shortcuts_fixture_carries_one_broll_placement_and_playback_stays_narration_only(tmp_path: Path) -> None:
    """Q·W가 영상 배치에도 닿는지 재려고 shortcuts에만 영상 한 칸(장면 3)을 얹는다. 재생 측정 프로젝트는 그대로다."""
    from scripts.e2e_editor_fixture import SHORTCUTS_BROLL_SCENE
    ids = seed_editor_fixtures(projects_root=tmp_path / "projects", media_dir=tmp_path / "media")
    store = LocalProjectStore(tmp_path / "projects")
    shortcuts = store.get_editing_session(project_id=ids["shortcuts"]["project_id"], session_id=ids["shortcuts"]["session_id"])
    with_broll = [s["segment_id"] for s in shortcuts["segments"] if s.get("broll_override")]
    assert with_broll == [SHORTCUTS_BROLL_SCENE] == ["scene-3"]
    playback = store.get_editing_session(project_id=ids["playback"]["project_id"], session_id=ids["playback"]["session_id"])
    assert not [s for s in playback["segments"] if s.get("broll_override")]
