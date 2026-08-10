"""B-roll intake discarded everything ffprobe already knows.

Registration stored only title and tags, so the picker had no length, no
dimensions, and no audio flag to show -- which is why asset cards read
"길이 정보 없음" and "오디오 정보 확인 중".  Orientation was never derived at all,
so vertical footage could not be told apart from landscape.
"""

import subprocess
from pathlib import Path

import pytest

from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_storage.local_project_store import LocalProjectStore


def _write_video(path: Path, *, size: str, with_audio: bool, duration: int = 2) -> Path:
    command = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate=15"]
    if with_audio:
        command += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}", "-c:a", "aac", "-shortest"]
    else:
        command += ["-an"]
    command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(command, check=True, capture_output=True)
    return path


@pytest.fixture()
def runner(tmp_path: Path) -> LocalPipelineRunner:
    store = LocalProjectStore(tmp_path / "projects")
    return LocalPipelineRunner(store=store)


def _stored_metadata(runner: LocalPipelineRunner, project_id: str, asset_id: str) -> dict:
    """Registration returns an identity payload; metadata lives in the store,
    which is what the asset list endpoint reads."""
    return runner.store.get_asset(project_id=project_id, asset_id=asset_id)["metadata"]


def _register(runner: LocalPipelineRunner, tmp_path: Path, **video) -> dict:
    project = runner.store.bootstrap_project(name="Intake")
    source = _write_video(tmp_path / f"{video['size']}.mp4", **video)
    asset = runner.register_broll_asset(project_id=project.project_id, source_path=source)
    return _stored_metadata(runner, project.project_id, asset["asset_id"])


def test_landscape_intake_records_size_length_and_audio(runner, tmp_path: Path) -> None:
    metadata = _register(runner, tmp_path, size="320x180", with_audio=True)

    assert metadata["width"] == 320
    assert metadata["height"] == 180
    assert metadata["orientation"] == "가로"
    assert metadata["has_audio"] is True
    assert metadata["duration_sec"] == pytest.approx(2.0, abs=0.3)


def test_portrait_intake_is_marked_vertical(runner, tmp_path: Path) -> None:
    """Shortform work needs vertical footage to be distinguishable at intake."""
    metadata = _register(runner, tmp_path, size="180x320", with_audio=False)

    assert metadata["orientation"] == "세로"
    assert metadata["has_audio"] is False


def test_square_intake_is_marked_square(runner, tmp_path: Path) -> None:
    metadata = _register(runner, tmp_path, size="240x240", with_audio=False)

    assert metadata["orientation"] == "정사각"


def test_intake_keeps_tags_for_the_owner(runner, tmp_path: Path) -> None:
    """Derived facts must not be written into the owner's own tag list."""
    project = runner.store.bootstrap_project(name="Tags")
    source = _write_video(tmp_path / "tagged.mp4", size="320x180", with_audio=False)

    asset = runner.register_broll_asset(
        project_id=project.project_id, source_path=source, tags=["카페"]
    )

    metadata = _stored_metadata(runner, project.project_id, asset["asset_id"])

    assert metadata["tags"] == ["카페"]
    for derived in ("orientation", "duration_sec", "width", "height", "has_audio"):
        assert derived not in metadata["tags"]


def test_unreadable_media_still_registers(runner, tmp_path: Path) -> None:
    """A probe failure must not block intake, matching the thumbnail fallback."""
    project = runner.store.bootstrap_project(name="Broken")
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not a video")

    asset = runner.register_broll_asset(project_id=project.project_id, source_path=broken)
    metadata = _stored_metadata(runner, project.project_id, asset["asset_id"])

    assert asset["asset_id"]
    assert metadata.get("orientation") is None


# ---------------------------------------------------------------------------
# 실패를 삼키더라도 이유는 남기고, 나중에 다시 채울 수 있어야 한다.
#
# ffprobe가 한 번 실패하면 그 자산은 길이도 크기도 오디오도 없이 확정 등록됐다.
# 등록 시점 1회 호출뿐이라 다시 채울 경로가 없었고, 편집기에서는 "길이 정보
# 없음"으로 뜨고 세로/가로 필터에서 통째로 빠졌다 -- owner는 폰으로 찍어 롱폼과
# 숏폼을 같이 만들기 때문에 그 필터가 실제로 중요하다.
# ---------------------------------------------------------------------------


class _ExplodingProbe:
    """ffmpeg 바이너리가 없거나 ffprobe가 터진 상황."""

    def probe_metadata(self, _path):  # noqa: ANN001 - 실제 probe 시그니처를 흉내낸다
        raise RuntimeError("ffprobe binary is unavailable")


def _register_with_broken_probe(runner, tmp_path, monkeypatch, *, name: str):
    """진짜 영상을 등록하되 probe만 실패시킨다.

    파일 자체가 깨진 것과 달리, 이것은 **나중에 다시 재면 채워질 수 있는**
    실패다. 컨테이너에 ffmpeg가 아직 없을 때가 정확히 이 경우다.
    """
    project = runner.store.bootstrap_project(name=name)
    source = _write_video(tmp_path / f"{name}.mp4", size="320x180", with_audio=True)
    monkeypatch.setattr(
        "videobox_core_engine.local_pipeline.FFmpegMediaProbe", lambda *a, **k: _ExplodingProbe()
    )
    asset = runner.register_broll_asset(project_id=project.project_id, source_path=source)
    return project.project_id, asset["asset_id"]


def test_a_probe_failure_at_intake_says_why(
    runner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """지금은 완전히 조용하다. 왜 정보가 없는지 알 방법이 소스를 읽는 것뿐이었다."""
    import logging

    with caplog.at_level(logging.WARNING):
        project_id, asset_id = _register_with_broken_probe(
            runner, tmp_path, monkeypatch, name="이유"
        )

    # fail-open은 그대로다.
    assert asset_id
    assert any(
        "ffprobe binary is unavailable" in record.getMessage()
        or "ffprobe binary is unavailable" in str(record.exc_info)
        for record in caplog.records
    ), "영상 정보 수집 실패가 기록되지 않았다"
    # 로그는 흘러가지만 자산은 남는다. 이유가 자산에도 붙어 있어야 나중에 찾는다.
    assert _stored_metadata(runner, project_id, asset_id).get("media_facts_error")


def test_an_asset_without_media_facts_comes_back_for_another_pass() -> None:
    """라이브러리 색인의 `list_footage_needing_analysis`와 같은 방식 -- 따로
    표시를 만들지 않고 저장된 상태에서 "아직 안 된 것"을 유도한다. 그래야 이번
    수정 전에 이미 망가진 자산도 같이 걸린다."""
    from videobox_core_engine.local_pipeline import broll_assets_needing_media_facts
    from videobox_domain_models.assets import AssetType

    class _Store:
        @staticmethod
        def list_assets(*, project_id: str, asset_type=None):
            assert asset_type == AssetType.BROLL_VIDEO
            return [
                {"asset_id": "a-done", "storage_uri": "u1", "metadata": {"width": 320, "height": 180}},
                {"asset_id": "a-missing", "storage_uri": "u2", "metadata": {"title": "t"}},
                {
                    "asset_id": "a-failed-before",
                    "storage_uri": "u3",
                    "metadata": {"media_facts_error": "RuntimeError: 이전 실패"},
                },
            ]

    pending = broll_assets_needing_media_facts(store=_Store(), project_id="p1")

    assert [item["asset_id"] for item in pending] == ["a-missing", "a-failed-before"]
    # 다시 잴 때 필요한 것을 함께 돌려준다. 자산을 한 건씩 또 읽지 않기 위해서다.
    assert pending[0]["storage_uri"] == "u2"
    assert pending[1]["previous_error"] == "RuntimeError: 이전 실패"


def test_the_backfill_pass_is_bounded_like_the_indexers() -> None:
    """한 번에 다 걸지 않는다. 색인·재분석 패스가 batch를 두는 것과 같은 이유다."""
    from videobox_core_engine.local_pipeline import broll_assets_needing_media_facts

    class _Store:
        @staticmethod
        def list_assets(*, project_id: str, asset_type=None):
            return [{"asset_id": f"a{i}", "storage_uri": f"u{i}", "metadata": {}} for i in range(5)]

    assert len(broll_assets_needing_media_facts(store=_Store(), project_id="p1", limit=2)) == 2
    # 한도를 안 주면 전부 -- 호출부가 정한다.
    assert len(broll_assets_needing_media_facts(store=_Store(), project_id="p1")) == 5


def test_a_later_pass_fills_in_what_intake_missed(
    runner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """이것이 이 작업의 핵심이다. 등록 때 못 받은 정보를 **나중에** 채울 수
    있어야 자산이 영구히 깎인 채로 남지 않는다."""
    project_id, asset_id = _register_with_broken_probe(runner, tmp_path, monkeypatch, name="복구")

    assert _stored_metadata(runner, project_id, asset_id).get("orientation") is None

    # ffprobe가 다시 살아난 상황.
    monkeypatch.undo()

    recovered = runner.record_missing_broll_media_facts(project_id=project_id)

    assert recovered == [asset_id]
    metadata = _stored_metadata(runner, project_id, asset_id)
    assert metadata["width"] == 320
    assert metadata["height"] == 180
    assert metadata["orientation"] == "가로"
    assert metadata["has_audio"] is True
    assert metadata["duration_sec"] == pytest.approx(2.0, abs=0.3)
    # 채워졌으면 실패 흔적은 남기지 않는다. 남으면 화면이 계속 문제로 읽는다.
    assert metadata.get("media_facts_error") is None
    # 채운 뒤에는 다시 걸리지 않는다.
    assert runner.record_missing_broll_media_facts(project_id=project_id) == []


def test_the_running_app_refills_missing_media_facts_without_being_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """owner가 손으로 돌릴 일이 아니다. 라이브러리 색인과 같은 주기 패스에
    올라타야 한다."""
    import time

    from fastapi.testclient import TestClient

    from videobox_api import main as api_main

    calls: list[str] = []
    monkeypatch.setattr(
        api_main,
        "broll_assets_needing_media_facts",
        lambda **kwargs: calls.append(kwargs["project_id"]) or [],
    )

    app = api_main.create_app(
        projects_root=tmp_path / "projects", media_analysis_poll_interval_seconds=0.01
    )
    app.state.store.bootstrap_project("영상 정보")
    with TestClient(app):
        time.sleep(0.4)

    assert calls, "빠진 영상 정보를 찾는 패스가 돌지 않았다"
