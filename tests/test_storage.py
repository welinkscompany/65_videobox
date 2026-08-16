from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from videobox_storage.local_project_store import LocalProjectStore


def test_bootstrap_project_creates_expected_layout(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Local First Project")

    project_root = tmp_path / "projects" / project.project_id
    assert project_root.exists()
    assert (project_root / "db" / "project.sqlite").exists()
    assert (project_root / "inputs" / "narration").exists()
    assert (project_root / "inputs" / "raw_video").exists()
    assert (project_root / "inputs" / "scripts").exists()
    assert (project_root / "inputs" / "voice_samples").exists()
    assert (project_root / "assets" / "imported").exists()
    assert (project_root / "assets" / "generated").exists()
    assert (project_root / "analysis" / "transcripts").exists()
    assert (project_root / "analysis" / "segments").exists()
    assert (project_root / "analysis" / "recommendations").exists()
    assert (project_root / "timelines").exists()
    assert (project_root / "previews").exists()
    assert (project_root / "exports" / "capcut").exists()
    assert (project_root / "cache").exists()
    assert (project_root / "logs").exists()


def test_bootstrap_project_creates_sqlite_tables(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Schema Check")
    database_path = tmp_path / "projects" / project.project_id / "db" / "project.sqlite"

    connection = sqlite3.connect(database_path)
    try:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        connection.close()

    assert {
        "projects",
        "assets",
        "segments",
        "recommendations",
        "jobs",
        "timelines",
        "exports",
        "voice_samples",
    }.issubset(table_names)


def test_list_projects_skips_a_database_file_observed_before_schema_commit(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    incomplete = tmp_path / "projects" / "initializing" / "db" / "project.sqlite"
    incomplete.parent.mkdir(parents=True)
    sqlite3.connect(incomplete).close()
    project = store.bootstrap_project(name="Ready Project")

    projects = store.list_projects()

    assert [item["project_id"] for item in projects] == [project.project_id]


def test_connection_initialization_failure_closes_the_open_sqlite_handle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Connection Cleanup")
    from videobox_storage import local_project_store

    original_connect = local_project_store.sqlite3.connect

    class _FailingSetupConnection:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self.connection = connection
            self.closed = False

        def execute(self, statement: str, *args: object, **kwargs: object):
            if statement == "PRAGMA busy_timeout=5000":
                raise sqlite3.OperationalError("injected setup failure")
            return self.connection.execute(statement, *args, **kwargs)

        def close(self) -> None:
            self.closed = True
            self.connection.close()

    wrappers: list[_FailingSetupConnection] = []

    def failing_connect(*args: object, **kwargs: object) -> _FailingSetupConnection:
        connection = original_connect(*args, **kwargs)
        wrapper = _FailingSetupConnection(connection)
        wrappers.append(wrapper)
        return wrapper

    monkeypatch.setattr(local_project_store.sqlite3, "connect", failing_connect)
    with pytest.raises(sqlite3.OperationalError, match="injected setup failure"):
        store._connection(project.project_id)

    assert len(wrappers) == 1 and wrappers[0].closed is True


def test_save_timeline_run_summary_ignores_unknown_review_flag_count(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Timeline Summary Count Project")

    saved = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "version": "v001",
            "tracks": [],
            "review_flags": [
                {
                    "code": "legacy_review_required",
                    "segment_id": "seg_legacy",
                    "message": "Legacy blocker that should not count.",
                },
                {
                    "code": "segment_review_required",
                    "segment_id": "seg_001",
                    "message": "Canonical blocker that should count.",
                },
            ],
            "pending_recommendations": [],
            "applied_recommendations": [],
        },
    )

    fetched = store.get_timeline_run(
        project_id=project.project_id,
        timeline_id=saved["timeline_id"],
    )

    assert fetched["summary"]["review_flag_count"] == 1


def test_save_timeline_run_summary_ignores_unknown_pending_recommendation_count(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Timeline Pending Summary Count Project")

    saved = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "version": "v001",
            "tracks": [],
            "review_flags": [],
            "pending_recommendations": [
                {
                    "recommendation_id": "rec_unknown_pending",
                    "target_segment_id": "seg_legacy",
                    "recommendation_type": "legacy_overlay_pick",
                    "auto_apply_allowed": False,
                    "review_required": True,
                    "payload": {},
                    "created_at": "2026-07-06T00:00:00+00:00",
                }
            ],
            "applied_recommendations": [],
        },
    )

    fetched = store.get_timeline_run(
        project_id=project.project_id,
        timeline_id=saved["timeline_id"],
    )

    assert fetched["summary"]["pending_recommendation_count"] == 0


def test_save_timeline_run_summary_ignores_unknown_track_count(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Timeline Track Summary Count Project")

    saved = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "version": "v001",
            "tracks": [
                {
                    "track_id": "track_legacy",
                    "track_type": "legacy_overlay",
                    "clips": [{"clip_id": "clip_legacy_001"}],
                },
                {
                    "track_id": "track_001",
                    "track_type": "narration",
                    "clips": [{"clip_id": "clip_001"}],
                },
            ],
            "review_flags": [],
            "pending_recommendations": [],
            "applied_recommendations": [],
        },
    )

    fetched = store.get_timeline_run(
        project_id=project.project_id,
        timeline_id=saved["timeline_id"],
    )

    assert fetched["summary"]["track_count"] == 1


def test_save_timeline_run_summary_ignores_unknown_applied_recommendation_count(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Timeline Applied Summary Count Project")

    saved = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "version": "v001",
            "tracks": [],
            "review_flags": [],
            "pending_recommendations": [],
            "applied_recommendations": [
                {
                    "recommendation_id": "rec_unknown_applied",
                    "target_segment_id": "seg_legacy",
                    "recommendation_type": "legacy_overlay_pick",
                    "selected_asset_id": "asset_legacy_001",
                    "score": 0.5,
                    "reason": "Unknown applied recommendation should not count.",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "decision_state": "approved",
                    "payload": {},
                    "created_at": "2026-07-06T00:00:00+00:00",
                },
                {
                    "recommendation_id": "rec_broll_001",
                    "target_segment_id": "seg_001",
                    "recommendation_type": "broll",
                    "selected_asset_id": "asset_broll_001",
                    "score": 0.91,
                    "reason": "Canonical applied recommendation should count.",
                    "auto_apply_allowed": True,
                    "review_required": False,
                    "decision_state": "approved",
                    "payload": {},
                    "created_at": "2026-07-06T00:00:00+00:00",
                },
            ],
        },
    )

    fetched = store.get_timeline_run(
        project_id=project.project_id,
        timeline_id=saved["timeline_id"],
    )

    assert fetched["summary"]["applied_recommendation_count"] == 1


def test_save_capcut_export_metadata_ignores_unknown_track_count(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="CapCut Export Metadata Count Project")

    saved = store.save_capcut_export(
        project_id=project.project_id,
        timeline_id="timeline_001",
        export_payload={
            "adapter": "capcut",
            "tracks": [
                {
                    "track_id": "track_legacy",
                    "track_type": "legacy_overlay",
                    "clips": [{"clip_id": "clip_legacy_001"}],
                },
                {
                    "track_id": "track_001",
                    "track_type": "narration",
                    "clips": [{"clip_id": "clip_001"}],
                },
            ],
        },
    )

    fetched = store.get_export_run(
        project_id=project.project_id,
        export_id=saved["export_id"],
    )

    assert fetched["metadata"]["track_count"] == 1


def test_reading_an_export_run_refuses_a_media_artifact_instead_of_leaking_a_decode_error(
    tmp_path: Path,
) -> None:
    # `get_export_run`은 CapCut 초안처럼 JSON 매니페스트를 담은 출력만 읽는다.
    # 완성본(mp4)의 export_id가 들어오면 예전에는 그 mp4를 utf-8 텍스트로 읽으려다
    # "'utf-8' codec can't decode byte" 오류가 그대로 사용자 화면까지 나갔다.
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Final Render Export Read")
    rendered = tmp_path / "output.mp4"
    rendered.write_bytes(b"\x00\x00\x00\x20ftypisom\xd5\xd5\xd5")
    saved = store.save_final_render(
        project_id=project.project_id,
        timeline_id="timeline_001",
        source_output_path=rendered,
        source_session_absent=True,
    )

    with pytest.raises(KeyError) as caught:
        store.get_export_run(project_id=project.project_id, export_id=saved["export_id"])

    assert "codec" not in str(caught.value)


def test_a_final_render_remembers_whether_it_had_sound(tmp_path: Path) -> None:
    # 무음 완성본이 아무 말 없이 나가던 문제. 렌더가 잰 결과를 출력 행에 남겨야
    # 화면이 owner에게 알릴 수 있다.
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Silent Final Render")
    rendered = tmp_path / "output.mp4"
    rendered.write_bytes(b"rendered bytes")
    saved = store.save_final_render(
        project_id=project.project_id,
        timeline_id="timeline_001",
        source_output_path=rendered,
        source_session_absent=True,
        metadata={"has_sound": False},
    )

    fetched = store.get_final_render_export(project_id=project.project_id, export_id=saved["export_id"])

    assert fetched["has_sound"] is False


def test_a_final_render_saved_before_we_measured_sound_claims_nothing(tmp_path: Path) -> None:
    # 옛 완성본은 잰 적이 없다. 없는 것을 "소리 없음"으로 읽으면 멀쩡한 완성본에
    # 경고가 붙는다.
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Legacy Final Render")
    rendered = tmp_path / "output.mp4"
    rendered.write_bytes(b"rendered bytes")
    saved = store.save_final_render(
        project_id=project.project_id,
        timeline_id="timeline_001",
        source_output_path=rendered,
        source_session_absent=True,
    )

    fetched = store.get_final_render_export(project_id=project.project_id, export_id=saved["export_id"])

    assert fetched["has_sound"] is None


def test_save_preview_run_summary_ignores_unknown_track_clip_group_count(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Preview Summary Count Project")

    saved = store.save_preview_run(
        project_id=project.project_id,
        timeline_id="timeline_001",
        preview_payload={
            "timeline_id": "timeline_001",
            "artifact_kind": "playable_html_preview",
            "clips": [
                {
                    "track_id": "track_legacy",
                    "track_type": "legacy_overlay",
                    "clip_count": 1,
                },
                {
                    "track_id": "track_001",
                    "track_type": "narration",
                    "clip_count": 1,
                },
            ],
            "player_html": "<html></html>",
        },
    )

    fetched = store.get_preview_run(
        project_id=project.project_id,
        preview_id=saved["preview_id"],
    )

    assert fetched["summary"]["clip_group_count"] == 1
