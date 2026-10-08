"""세션 투영 클립이 박힌 편집판 수리 도구 (2026-10-08 계획 H Task 5).

전부 tmp_path 시험장이다. 대표님 실제 프로젝트 폴더는 열지 않는다.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "repair_session_projection_timelines.py"
_spec = importlib.util.spec_from_file_location("videobox_repair_projection_under_test", _PATH)
assert _spec is not None and _spec.loader is not None
repair = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(repair)

PARENT = "timeline_001:001"
DUP_ID = f"session-overlay-{PARENT}-0-0"
FIXED = datetime(2026, 10, 8, 1, 2, 3, tzinfo=timezone.utc)
STAMP = "20261008T010203Z"


def _dirty() -> dict:
    overlay = {"overlay_type": "image_overlay", "asset_id": "a", "clip_id": DUP_ID, "segment_id": PARENT, "start_sec": 0.0, "end_sec": 2.0}
    return {"timeline_id": "timeline_002", "tracks": [
        {"track_id": "narration_primary", "track_type": "narration", "clips": [
            {"clip_id": "clip_narration_001", "segment_id": PARENT, "clip_type": "narration", "start_sec": 0.0, "end_sec": 4.0}]},
        {"track_id": "track_overlay", "track_type": "overlay", "clips": [dict(overlay), dict(overlay)]},
    ]}


def _clean() -> dict:
    payload = _dirty()
    payload["tracks"] = payload["tracks"][:1]
    return payload


def _write(path: Path, payload: dict) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    path.write_bytes(data)
    return data


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def world(tmp_path):
    projects = tmp_path / "projects"
    revert = tmp_path / "revert"
    p1 = projects / "p1" / "timelines" / "timeline_002.json"
    p2 = projects / "p2" / "timelines" / "timeline_001.json"
    _write(p1, _dirty())
    _write(p2, _clean())
    return projects, revert, p1, p2


def _args(projects, revert, *extra):
    return ["--projects-dir", str(projects), "--revert-dir", str(revert), *extra]


def test_find_reports_only_the_contaminated_timeline(world) -> None:
    projects, _, _, _ = world
    found = repair.find_contaminated_timelines(projects)
    assert len(found) == 1
    assert found[0]["project_id"] == "p1"
    assert found[0]["timeline_file"] == "timeline_002.json"
    assert found[0]["projection_clip_count"] == 2
    assert found[0]["duplicate_clip_ids"] == [DUP_ID]


def test_strip_keeps_tracks_and_non_projection_clips() -> None:
    cleaned, removed = repair.strip_projection_clips(_dirty())
    assert removed == 2
    assert [t["track_id"] for t in cleaned["tracks"]] == ["narration_primary", "track_overlay"]
    assert cleaned["tracks"][1]["clips"] == []
    assert cleaned["tracks"][0]["clips"][0]["clip_id"] == "clip_narration_001"
    assert cleaned["timeline_id"] == "timeline_002"


def test_preview_is_default_and_writes_nothing(world, capsys) -> None:
    projects, revert, p1, _ = world
    before = _sha(p1)
    assert repair.main(_args(projects, revert)) == 0
    assert _sha(p1) == before
    assert not revert.exists()
    assert not list(p1.parent.glob("*.bak-h-*"))
    assert "p1" in capsys.readouterr().out


def test_apply_without_project_is_refused(world) -> None:
    projects, revert, p1, _ = world
    before = _sha(p1)
    assert repair.main(_args(projects, revert, "--apply")) == 2
    assert _sha(p1) == before and not revert.exists()


def test_apply_for_a_clean_or_unknown_project_changes_nothing(world) -> None:
    projects, revert, p1, p2 = world
    b1, b2 = _sha(p1), _sha(p2)
    assert repair.main(_args(projects, revert, "--apply", "--project", "p2"), now=FIXED) == 0
    assert repair.main(_args(projects, revert, "--apply", "--project", "nope"), now=FIXED) == 2
    assert (_sha(p1), _sha(p2)) == (b1, b2) and not revert.exists()


def test_apply_repairs_backs_up_and_writes_revert_list(world) -> None:
    projects, revert, p1, _ = world
    original = p1.read_bytes()
    before = _sha(p1)
    assert repair.main(_args(projects, revert, "--apply", "--project", "p1"), now=FIXED) == 0
    after_payload = json.loads(p1.read_text(encoding="utf-8"))
    assert after_payload["tracks"][1]["clips"] == []
    assert after_payload["tracks"][0]["clips"][0]["clip_id"] == "clip_narration_001"
    assert len(after_payload["tracks"]) == 2
    backup = p1.parent / f"timeline_002.json.bak-h-{STAMP}"
    assert backup.read_bytes() == original
    record = json.loads((revert / f"{STAMP}.json").read_text(encoding="utf-8"))
    entry = record["repaired"][0]
    assert entry["before_sha256"] == before and entry["after_sha256"] == _sha(p1)
    assert Path(entry["backup_path"]) == backup and Path(entry["timeline_path"]) == p1
    assert not list(p1.parent.glob("*.tmp*"))


def test_revert_list_is_written_before_the_timeline_is_touched(world, monkeypatch) -> None:
    projects, revert, p1, _ = world
    before = _sha(p1)

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(repair.os, "replace", boom)
    assert repair.main(_args(projects, revert, "--apply", "--project", "p1"), now=FIXED) == 1
    assert _sha(p1) == before                       # 원본은 그대로
    assert (revert / f"{STAMP}.json").exists()      # 목록은 이미 있었다
    assert not list(p1.parent.glob("*.tmp*"))       # 임시 파일 정리


def test_existing_revert_list_is_never_overwritten(world) -> None:
    projects, revert, p1, _ = world
    revert.mkdir()
    (revert / f"{STAMP}.json").write_text("keep", encoding="utf-8")
    before = _sha(p1)
    assert repair.main(_args(projects, revert, "--apply", "--project", "p1"), now=FIXED) == 2
    assert (revert / f"{STAMP}.json").read_text(encoding="utf-8") == "keep" and _sha(p1) == before


def test_undo_restores_original_bytes(world) -> None:
    projects, revert, p1, _ = world
    before = _sha(p1)
    repair.main(_args(projects, revert, "--apply", "--project", "p1"), now=FIXED)
    assert repair.main(["--undo", str(revert / f"{STAMP}.json")]) == 0
    assert _sha(p1) == before


def test_undo_refuses_a_hand_edited_file_unless_forced(world) -> None:
    projects, revert, p1, _ = world
    before = _sha(p1)
    repair.main(_args(projects, revert, "--apply", "--project", "p1"), now=FIXED)
    p1.write_text(p1.read_text(encoding="utf-8") + "\n ", encoding="utf-8")
    edited = _sha(p1)
    listing = str(revert / f"{STAMP}.json")
    assert repair.main(["--undo", listing]) != 0
    assert _sha(p1) == edited
    assert repair.main(["--undo", listing, "--force-undo"]) == 0
    assert _sha(p1) == before


def test_undo_with_bad_or_missing_list_exits_cleanly(tmp_path) -> None:
    assert repair.main(["--undo", str(tmp_path / "none.json")]) == 2
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert repair.main(["--undo", str(bad)]) == 2


def test_malformed_timeline_files_are_skipped_not_fatal(world) -> None:
    projects, revert, _, _ = world
    broken = projects / "p3" / "timelines" / "timeline_001.json"
    broken.parent.mkdir(parents=True)
    broken.write_text("{oops", encoding="utf-8")
    assert [f["project_id"] for f in repair.find_contaminated_timelines(projects)] == ["p1"]
    assert repair.main(_args(projects, revert)) == 0


def test_missing_projects_dir_exits_cleanly(tmp_path) -> None:
    assert repair.main(["--projects-dir", str(tmp_path / "nope")]) == 2


def test_apply_refuses_when_a_lock_marker_is_present(world) -> None:
    projects, revert, p1, _ = world
    (p1.parent / "timeline_002.json.lock").write_text("", encoding="utf-8")
    before = _sha(p1)
    assert repair.main(_args(projects, revert, "--apply", "--project", "p1"), now=FIXED) == 2
    assert _sha(p1) == before


def test_non_ascii_project_ids_work(tmp_path) -> None:
    projects = tmp_path / "프로젝트"
    path = projects / "한글-아이디" / "timelines" / "timeline_002.json"
    original = _write(path, _dirty())
    revert = tmp_path / "되돌림"
    assert repair.main(_args(projects, revert, "--apply", "--project", "한글-아이디"), now=FIXED) == 0
    assert path.read_bytes() != original
    assert repair.main(["--undo", str(revert / f"{STAMP}.json")]) == 0
    assert path.read_bytes() == original
