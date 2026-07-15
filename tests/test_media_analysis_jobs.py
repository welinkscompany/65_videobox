from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
import json
import subprocess
import hashlib
from threading import Event, Thread

from videobox_domain_models.assets import AssetType
from videobox_domain_models.media_analysis import MediaAnalysisStatus
from videobox_storage.local_project_store import LocalProjectStore
from videobox_provider_interfaces.lm_studio import LMStudioProviderError

from videobox_core_engine.media_analysis import AnalysisProfile, MediaAnalysisService
from videobox_core_engine.media_probe import FFmpegMediaProbe


PROJECT_ID = "project_001"
ASSET_ID = "asset_001"


@dataclass(frozen=True)
class _Frame:
    data: bytes = b"frame"
    long_edge_px: int = 768
    encoded_size_bytes: int = 1_500_000


@dataclass(frozen=True)
class _ProbeResult:
    duration_sec: float = 12.0
    codec: str = "h264"
    width: int = 1920
    height: int = 1080
    aspect_ratio: float = 16 / 9
    fps: float = 30.0
    audio_codec: str = "aac"
    scene_boundaries: tuple[float, ...] = (0.0, 6.0, 12.0)
    frames: tuple[_Frame, ...] = (_Frame(),)


class _Probe:
    ffmpeg_version = "ffmpeg-test"

    def probe(self, _path: Path) -> _ProbeResult:
        return _ProbeResult()


class _Vision:
    provider_name = "fake-vision"

    def __init__(self, *, result: dict[str, object] | None = None, error: Exception | None = None) -> None:
        self.result = result or {"layers": {name: [name] for name in ("place", "action", "time_of_day")}, "summary": "test", "confidence": 0.9, "review_reasons": []}
        self.error = error
        self.calls = 0

    def analyze_images(self, _request: object) -> object:
        self.calls += 1
        if self.error:
            raise self.error
        return type("Response", (), {"output_data": self.result, "provider_name": self.provider_name, "model_name": "local"})()


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 14, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


def _service(tmp_path: Path, vision: _Vision, clock: _Clock | None = None) -> tuple[MediaAnalysisService, LocalProjectStore, str, Path]:
    store = LocalProjectStore(tmp_path, now=(clock or _Clock()))
    project = store.bootstrap_project("analysis")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.RAW_VIDEO, source_path=source)
    return MediaAnalysisService(store=store, media_probe=_Probe(), vision_provider=vision, clock=clock or _Clock()), store, project.project_id, store.resolve_storage_uri(project_id=project.project_id, storage_uri=asset.storage_uri)


def test_probe_never_emits_more_than_six_bounded_frames() -> None:
    probe = FFmpegMediaProbe("ffmpeg", "ffprobe")
    frames = probe._bounded_frames([b"x" * 2_000_000] * 9, long_edge_px=1920)
    assert frames == ()  # Never byte-truncate an encoded JPEG: that corrupts the frame.
    assert all(frame.long_edge_px <= 768 for frame in frames)
    assert all(frame.encoded_size_bytes <= 1_500_000 for frame in frames)


def test_ffprobe_reads_video_and_audio_metadata_and_uses_60_second_timeout(monkeypatch) -> None:
    calls: list[tuple[list[str], int]] = []
    def run(command, **kwargs):
        calls.append((command, kwargs["timeout"]))
        if "-version" in command:
            return subprocess.CompletedProcess(command, 0, "ffmpeg test\n", "")
        if "-ss" in command:
            return subprocess.CompletedProcess(command, 0, b"", b"")
        return subprocess.CompletedProcess(command, 0, json.dumps({"format": {"duration": "12.5"}, "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "avg_frame_rate": "30000/1001"}, {"codec_type": "audio", "codec_name": "aac"}]}), "")
    monkeypatch.setattr(subprocess, "run", run)
    result = FFmpegMediaProbe().probe(Path("video.mp4"))
    assert (result.duration_sec, result.codec, result.width, result.height, result.fps, result.audio_codec) == (12.5, "h264", 1920, 1080, 30000 / 1001, "aac")
    assert all(timeout == 60 for _, timeout in calls)


def test_ffprobe_rejects_corrupt_media(monkeypatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: subprocess.CompletedProcess(command, 0, "ffmpeg\n" if "-version" in command else "not json", ""))
    try:
        FFmpegMediaProbe().probe(Path("broken.mp4"))
    except ValueError as exc:
        assert "ffprobe" in str(exc)
    else:
        raise AssertionError("corrupt ffprobe output must not be accepted")


def test_duplicate_enqueue_uses_canonical_cache_and_does_not_duplicate(tmp_path: Path) -> None:
    service, store, project_id, _ = _service(tmp_path, _Vision())
    asset_id = store.list_assets(project_id=project_id)[0]["asset_id"]
    first = service.enqueue_analysis(project_id=project_id, asset_id=asset_id)
    second = service.enqueue_analysis(project_id=project_id, asset_id=asset_id)
    assert first["analysis_id"] == second["analysis_id"]
    assert len(service.cache_key(source_sha256="a", profile=AnalysisProfile())) == 64


def test_quality_gate_marks_low_quality_result_needs_review(tmp_path: Path) -> None:
    vision = _Vision(result={"layers": {"place": []}, "summary": "", "confidence": 0.1, "review_reasons": []})
    service, store, project_id, _ = _service(tmp_path, vision)
    asset_id = store.list_assets(project_id=project_id)[0]["asset_id"]
    job = service.enqueue_analysis(project_id=project_id, asset_id=asset_id)
    service.dispatch_once(project_id=project_id, analysis_id=job["analysis_id"])
    assert service.get_analysis(project_id, job["analysis_id"])["status"] == MediaAnalysisStatus.NEEDS_REVIEW.value


def test_retry_uses_fake_clock_backoffs_and_stops_after_two_retries(tmp_path: Path) -> None:
    clock = _Clock()
    service, store, project_id, _ = _service(tmp_path, _Vision(error=TimeoutError("slow")), clock)
    asset_id = store.list_assets(project_id=project_id)[0]["asset_id"]
    job = service.enqueue_analysis(project_id=project_id, asset_id=asset_id)
    service.dispatch_once(project_id=project_id, analysis_id=job["analysis_id"])
    assert service.get_analysis(project_id, job["analysis_id"])["next_retry_at"] == (clock.now + timedelta(seconds=5)).isoformat()
    clock.advance(5); service.dispatch_once(project_id=project_id, analysis_id=job["analysis_id"])
    assert service.get_analysis(project_id, job["analysis_id"])["next_retry_at"] == (clock.now + timedelta(seconds=30)).isoformat()
    clock.advance(30); service.dispatch_once(project_id=project_id, analysis_id=job["analysis_id"])
    assert service.get_analysis(project_id, job["analysis_id"])["status"] == MediaAnalysisStatus.FAILED.value


def test_cancelled_job_discards_late_vision_result(tmp_path: Path) -> None:
    service, store, project_id, _ = _service(tmp_path, _Vision())
    asset_id = store.list_assets(project_id=project_id)[0]["asset_id"]
    job = service.enqueue_analysis(project_id=project_id, asset_id=asset_id)
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert claim is not None
    service.cancel_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert service.get_analysis(project_id, job["analysis_id"])["result"] is None


def test_queued_job_can_be_cancelled_before_a_worker_claims_it(tmp_path: Path) -> None:
    service, store, project_id, _ = _service(tmp_path, _Vision())
    asset_id = store.list_assets(project_id=project_id)[0]["asset_id"]
    job = service.enqueue_analysis(project_id=project_id, asset_id=asset_id)
    service.cancel_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert service.get_analysis(project_id, job["analysis_id"])["status"] == MediaAnalysisStatus.CANCELLED.value


def test_invalid_extra_vision_schema_field_requires_review(tmp_path: Path) -> None:
    result = {"layers": {name: [name] for name in ("place", "action", "time_of_day")}, "summary": "test", "confidence": 0.9, "review_reasons": [], "unexpected": True}
    service, store, project_id, _ = _service(tmp_path, _Vision(result=result))
    asset_id = store.list_assets(project_id=project_id)[0]["asset_id"]
    job = service.enqueue_analysis(project_id=project_id, asset_id=asset_id)
    service.dispatch_once(project_id=project_id, analysis_id=job["analysis_id"])
    assert service.get_analysis(project_id, job["analysis_id"])["status"] == MediaAnalysisStatus.NEEDS_REVIEW.value


def test_missing_source_blocks_instead_of_becoming_retryable_failure(tmp_path: Path) -> None:
    service, store, project_id, source = _service(tmp_path, _Vision())
    asset_id = store.list_assets(project_id=project_id)[0]["asset_id"]
    job = service.enqueue_analysis(project_id=project_id, asset_id=asset_id)
    source.unlink()
    service.dispatch_once(project_id=project_id, analysis_id=job["analysis_id"])
    persisted = service.get_analysis(project_id, job["analysis_id"])
    assert (persisted["status"], persisted["error_code"]) == (MediaAnalysisStatus.BLOCKED.value, "SOURCE_MISSING")


def test_lm_studio_blocked_error_does_not_enter_retry_queue(tmp_path: Path) -> None:
    service, store, project_id, _ = _service(tmp_path, _Vision(error=LMStudioProviderError("model missing", "blocked")))
    asset_id = store.list_assets(project_id=project_id)[0]["asset_id"]
    job = service.enqueue_analysis(project_id=project_id, asset_id=asset_id)
    service.dispatch_once(project_id=project_id, analysis_id=job["analysis_id"])
    assert service.get_analysis(project_id, job["analysis_id"])["status"] == MediaAnalysisStatus.BLOCKED.value


def test_stale_cache_lifecycle_preserves_history_then_prunes_after_30_days(tmp_path: Path) -> None:
    clock = _Clock(); store = LocalProjectStore(tmp_path, now=clock); project = store.bootstrap_project("cache")
    store.record_media_analysis_cache(project_id=project.project_id, asset_id="asset_1", source_sha256="old", cache_key="old")
    store.record_media_analysis_cache(project_id=project.project_id, asset_id="asset_1", source_sha256="new", cache_key="new")
    stale = next(item for item in store.list_media_analysis_cache(project_id=project.project_id, asset_id="asset_1") if item["source_sha256"] == "old")
    assert stale["state"] == "stale" and stale["tags_stale"] and stale["embedding_stale"] and stale["preview_stale"] and stale["proposal_index_stale"]
    assert store.prune_stale_media_analysis_cache(project_id=project.project_id, retention_days=30) == 0
    clock.advance(30 * 86400 + 1)
    assert store.prune_stale_media_analysis_cache(project_id=project.project_id, retention_days=30) == 1


def test_asset_delete_removes_derived_cache_immediately(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path); project = store.bootstrap_project("cache")
    source = tmp_path / "asset.mp4"; source.write_bytes(b"asset")
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.RAW_VIDEO, source_path=source)
    store.record_media_analysis_cache(project_id=project.project_id, asset_id=asset.asset_id, source_sha256="sha", cache_key="key")
    store.delete_asset(project_id=project.project_id, asset_id=asset.asset_id)
    assert store.list_media_analysis_cache(project_id=project.project_id, asset_id=asset.asset_id) == []


def test_same_natural_cache_key_is_unique(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path); project = store.bootstrap_project("cache")
    store.record_media_analysis_cache(project_id=project.project_id, asset_id="asset", source_sha256="sha", cache_key="key")
    store.record_media_analysis_cache(project_id=project.project_id, asset_id="asset", source_sha256="sha", cache_key="key")
    assert len(store.list_media_analysis_cache(project_id=project.project_id, asset_id="asset")) == 1


def test_asset_delete_removes_actual_derived_frame_and_preview_files(tmp_path: Path) -> None:
    store = LocalProjectStore(tmp_path); project = store.bootstrap_project("cache")
    source = tmp_path / "asset.mp4"; source.write_bytes(b"asset")
    asset = store.register_asset(project_id=project.project_id, asset_type=AssetType.RAW_VIDEO, source_path=source)
    derived = store.project_root(project.project_id) / "analysis" / "media_cache" / asset.asset_id
    derived.mkdir(parents=True); (derived / "frame.jpg").write_bytes(b"frame"); (derived / "preview.jpg").write_bytes(b"preview")
    store.delete_asset(project_id=project.project_id, asset_id=asset.asset_id)
    assert not derived.exists()


def test_blocked_analysis_is_a_durable_apply_gate(tmp_path: Path) -> None:
    service, store, project_id, source = _service(tmp_path, _Vision())
    asset_id = store.list_assets(project_id=project_id)[0]["asset_id"]
    job = service.enqueue_analysis(project_id=project_id, asset_id=asset_id); source.unlink()
    service.dispatch_once(project_id=project_id, analysis_id=job["analysis_id"])
    assert store.can_apply_media_analysis(project_id=project_id, analysis_id=job["analysis_id"]) is False


def test_post_success_source_delete_or_mutation_closes_apply_gate(tmp_path: Path) -> None:
    service, store, project_id, source = _service(tmp_path, _Vision())
    asset_id = store.list_assets(project_id=project_id)[0]["asset_id"]
    job = service.enqueue_analysis(project_id=project_id, asset_id=asset_id)
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert claim is not None
    store.complete_media_analysis(project_id=project_id, analysis_id=job["analysis_id"], expected_attempt=claim["attempt"], result={"history": "preserved"})
    assert store.can_apply_media_analysis(project_id=project_id, analysis_id=job["analysis_id"]) is True
    source.write_bytes(b"changed")
    assert store.can_apply_media_analysis(project_id=project_id, analysis_id=job["analysis_id"]) is False
    source.unlink()
    assert store.can_apply_media_analysis(project_id=project_id, analysis_id=job["analysis_id"]) is False


def test_source_delete_stales_active_cache_when_apply_gate_checks_it(tmp_path: Path) -> None:
    service, store, project_id, source = _service(tmp_path, _Vision())
    asset_id = store.list_assets(project_id=project_id)[0]["asset_id"]
    job = service.enqueue_analysis(project_id=project_id, asset_id=asset_id)
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"]); assert claim
    store.complete_media_analysis(project_id=project_id, analysis_id=job["analysis_id"], expected_attempt=claim["attempt"], result={})
    source.unlink(); assert store.can_apply_media_analysis(project_id=project_id, analysis_id=job["analysis_id"]) is False
    assert store.list_media_analysis_cache(project_id=project_id, asset_id=asset_id)[0]["state"] == "stale"


def test_corrupt_probe_is_deterministically_blocked(tmp_path: Path) -> None:
    class CorruptProbe(_Probe):
        def probe(self, _path: Path): raise ValueError("ffprobe returned corrupt metadata")
    service, store, project_id, _ = _service(tmp_path, _Vision()); service.media_probe = CorruptProbe()
    asset_id = store.list_assets(project_id=project_id)[0]["asset_id"]; job = service.enqueue_analysis(project_id=project_id, asset_id=asset_id)
    service.dispatch_once(project_id=project_id, analysis_id=job["analysis_id"])
    assert service.get_analysis(project_id, job["analysis_id"])["status"] == MediaAnalysisStatus.BLOCKED.value


def test_real_invalid_mp4_ffprobe_nonzero_is_blocked(tmp_path: Path) -> None:
    service, store, project_id, source = _service(tmp_path, _Vision())
    source.write_bytes(b"not an mp4 container")
    service.media_probe = FFmpegMediaProbe()
    asset_id = store.list_assets(project_id=project_id)[0]["asset_id"]
    job = service.enqueue_analysis(project_id=project_id, asset_id=asset_id)
    service.dispatch_once(project_id=project_id, analysis_id=job["analysis_id"])
    persisted = service.get_analysis(project_id, job["analysis_id"])
    assert (persisted["status"], persisted["error_code"]) == (MediaAnalysisStatus.BLOCKED.value, "PROBE_CORRUPT")


def test_cancel_during_actual_blocking_vision_discards_late_result(tmp_path: Path) -> None:
    entered, release = Event(), Event()
    class BlockingVision(_Vision):
        def analyze_images(self, request):
            entered.set(); release.wait(2); return super().analyze_images(request)
    service, store, project_id, _ = _service(tmp_path, BlockingVision())
    asset_id = store.list_assets(project_id=project_id)[0]["asset_id"]; job = service.enqueue_analysis(project_id=project_id, asset_id=asset_id)
    worker = Thread(target=lambda: service.dispatch_once(project_id=project_id, analysis_id=job["analysis_id"])); worker.start(); assert entered.wait(1)
    service.cancel_analysis(project_id=project_id, analysis_id=job["analysis_id"]); release.set(); worker.join(2)
    assert service.get_analysis(project_id, job["analysis_id"])["result"] is None


def test_canonical_cache_sha_changes_for_each_contract_constituent(tmp_path: Path, monkeypatch) -> None:
    service, _, _, _ = _service(tmp_path, _Vision())
    base = service.cache_key(source_sha256="source", profile=AnalysisProfile())
    assert base == hashlib.sha256(json.dumps({"source_sha256":"source","extractor_version":"v1","ffmpeg_version":"ffmpeg-test","model_key":"local-vision","model_variant":"default","quantization":"default","vision_model_name":"local","embedding_model_name":None,"prompt_version":"v1","schema_version":"v1"}, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    assert base != service.cache_key(source_sha256="changed", profile=AnalysisProfile())
    assert base != MediaAnalysisService(store=service.store, media_probe=type("P", (), {"ffmpeg_version":"changed"})(), vision_provider=_Vision()).cache_key(source_sha256="source", profile=AnalysisProfile())
    assert base != service.cache_key(source_sha256="source", profile=AnalysisProfile(model_key="changed"))
    assert base != service.cache_key(source_sha256="source", profile=AnalysisProfile(variant="changed"))
    assert base != service.cache_key(source_sha256="source", profile=AnalysisProfile(quantization="changed"))
    assert base != service.cache_key(source_sha256="source", profile=AnalysisProfile(vision_model_name="changed-model"))
    assert base != service.cache_key(source_sha256="source", profile=AnalysisProfile(embedding_model_name="changed-embed"))
    assert base != MediaAnalysisService(store=service.store, media_probe=service.media_probe, vision_provider=_Vision(), extractor_version="changed").cache_key(source_sha256="source", profile=AnalysisProfile())
    import videobox_core_engine.media_analysis as media_analysis
    monkeypatch.setattr(media_analysis, "TAG_PROMPT_VERSION", "changed")
    assert base != service.cache_key(source_sha256="source", profile=AnalysisProfile())
    monkeypatch.setattr(media_analysis, "TAG_PROMPT_VERSION", "v1")
    monkeypatch.setattr(media_analysis, "TAG_SCHEMA_VERSION", "changed")
    assert base != service.cache_key(source_sha256="source", profile=AnalysisProfile())
