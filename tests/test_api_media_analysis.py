from pathlib import Path
from datetime import UTC, datetime, timedelta
import time

from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.media_analysis import MediaAnalysisStatus
from videobox_core_engine.media_probe import MediaProbeResult, RepresentativeFrame
from videobox_provider_interfaces.vision import FIXED_VISION_LAYERS, VisionAnalysisResponse


class FakeProbe:
    ffmpeg_version = "fake"
    def probe(self, path: Path) -> MediaProbeResult:
        del path
        return MediaProbeResult(1.0, "fake", 1, 1, 1.0, 1.0, None, (0.0, 1.0), (RepresentativeFrame(b"frame", 1, 5),))


class FakeVision:
    provider_name = "fake"
    def __init__(self) -> None: self.calls: list[object] = []
    def analyze_images(self, request: object) -> VisionAnalysisResponse:
        self.calls.append(request)
        layers = {layer: [] for layer in FIXED_VISION_LAYERS}
        layers.update({"place": ["local"], "action": ["analyze"], "scene": ["media"]})
        return VisionAnalysisResponse("fake", "fake", {"layers": layers, "summary": "fake", "confidence": 0.9, "review_reasons": []})


class FakeClock:
    def __init__(self) -> None: self.value = datetime.now(UTC)
    def __call__(self) -> datetime: return self.value
    def advance(self, seconds: float) -> None: self.value += timedelta(seconds=seconds)


class FlakyVision(FakeVision):
    def __init__(self) -> None:
        super().__init__()
        self.fail_once = True
    def analyze_images(self, request: object) -> VisionAnalysisResponse:
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("temporary vision failure")
        return super().analyze_images(request)


def wait_for(predicate) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if predicate(): return
        time.sleep(0.02)
    assert predicate()


def test_default_app_does_not_fabricate_media_analysis_provider(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path / "projects")
    assert app.state.media_analysis_vision_provider is None


def test_no_provider_retry_stays_visibly_blocked(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "blocked"}).json()["project_id"]
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    asset = client.post(f"/api/projects/{project_id}/assets/broll-video", json={"source_path": str(source), "tags": []}).json()
    analysis = client.post(f"/api/projects/{project_id}/media-analysis", json={"asset_id": asset["asset_id"]}).json()
    retry = client.post(f"/api/projects/{project_id}/media-analysis/{analysis['analysis_id']}/retry")
    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == "blocked"
    assert retry.json()["error_code"] == "MEDIA_ANALYSIS_WORKER_UNAVAILABLE"


def test_startup_recovers_orphaned_analysis_and_dispatches_injected_worker(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    first_vision = FakeVision()
    first = create_app(projects_root=projects_root, vision_provider=first_vision, media_probe=FakeProbe())
    client = TestClient(first)
    project_id = client.post("/api/projects", json={"name": "restart"}).json()["project_id"]
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    asset = client.post(f"/api/projects/{project_id}/assets/broll-video", json={"source_path": str(source), "tags": []}).json()
    job = first.state.media_analysis_service.enqueue_analysis(project_id=project_id, asset_id=asset["asset_id"])
    assert first.state.store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])["status"] == "running"

    restarted_vision = FakeVision()
    restarted = create_app(projects_root=projects_root, vision_provider=restarted_vision, media_probe=FakeProbe())
    with TestClient(restarted):
        wait_for(lambda: restarted.state.store.get_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])["status"] == "succeeded")
        recovered = restarted.state.store.get_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert recovered["status"] == "succeeded"
    assert restarted_vision.calls


def test_poller_retries_due_analysis_after_fake_clock_advances(tmp_path: Path) -> None:
    clock = FakeClock()
    vision = FlakyVision()
    app = create_app(projects_root=tmp_path / "projects", vision_provider=vision, media_probe=FakeProbe(), analysis_clock=clock, media_analysis_poll_interval_seconds=0.01)
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "retry"}).json()["project_id"]
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    asset = client.post(f"/api/projects/{project_id}/assets/broll-video", json={"source_path": str(source), "tags": []}).json()
    job = app.state.media_analysis_service.enqueue_analysis(project_id=project_id, asset_id=asset["asset_id"])
    with TestClient(app):
        wait_for(lambda: app.state.store.get_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])["status"] == "failed")
        clock.advance(6)
        wait_for(lambda: app.state.store.get_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])["status"] == "succeeded")


def test_recursive_broll_import_is_sorted_and_returns_analysis_jobs(tmp_path: Path) -> None:
    media = tmp_path / "media"
    (media / "nested").mkdir(parents=True)
    (media / "z.mp4").write_bytes(b"same")
    (media / "nested" / "a.mp4").write_bytes(b"different")
    fake_vision = FakeVision()
    client = TestClient(create_app(projects_root=tmp_path / "projects", vision_provider=fake_vision, media_probe=FakeProbe()))
    assert client.app.state.media_analysis_vision_provider is fake_vision
    project_id = client.post("/api/projects", json={"name": "analysis"}).json()["project_id"]

    response = client.post(
        f"/api/projects/{project_id}/assets/broll-video/batch",
        json={"source_directory": str(media), "recursive": True, "tags": []},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert len(payload["assets"]) == 2
    assert len(payload["analysis_jobs"]) == 2
    assert [item["source_path"] for item in payload["assets"]] == sorted(
        item["source_path"] for item in payload["assets"]
    )
    listed = client.get(f"/api/projects/{project_id}/media-analysis")
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 2
    assert fake_vision.calls


def test_manual_review_preserves_fixed_layers_and_updates_asset_tags(tmp_path: Path) -> None:
    app = create_app(projects_root=tmp_path / "projects")
    client = TestClient(app)
    project_id = client.post("/api/projects", json={"name": "review"}).json()["project_id"]
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    asset = client.post(f"/api/projects/{project_id}/assets/broll-video", json={"source_path": str(source), "tags": ["기존 메타"]}).json()
    store = app.state.store
    job = store.create_media_analysis(project_id=project_id, asset_id=asset["asset_id"], idempotency_key="manual", cache_key="manual")
    claimed = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    layers = {name: [] for name in ("place", "action", "time_of_day", "weather", "people_objects", "emotion", "mood", "topic_links", "scene", "color_tone", "camera", "season", "country_region")}
    layers["place"] = ["기존"]
    store.complete_media_analysis(project_id=project_id, analysis_id=job["analysis_id"], expected_attempt=claimed["attempt"], status=MediaAnalysisStatus.NEEDS_REVIEW, result={"tags": {"layers": layers}})

    response = client.patch(f"/api/projects/{project_id}/media-analysis/{job['analysis_id']}/review", json={"tags": {"place": ["서울"], "action": ["걷기"]}})

    assert response.status_code == 200, response.text
    result_layers = response.json()["result"]["tags"]["layers"]
    assert set(result_layers) == set(layers)
    assert result_layers["place"] == ["기존", "서울"]
    assert store.get_asset(project_id=project_id, asset_id=asset["asset_id"])["metadata"]["tags"] == ["기존 메타", "기존", "서울", "걷기"]


def test_batch_keeps_successful_assets_and_returns_per_file_failures(tmp_path: Path) -> None:
    source = tmp_path / "good.mp4"
    source.write_bytes(b"good")
    client = TestClient(create_app(projects_root=tmp_path / "projects", vision_provider=FakeVision(), media_probe=FakeProbe()))
    project_id = client.post("/api/projects", json={"name": "partial"}).json()["project_id"]
    response = client.post(f"/api/projects/{project_id}/assets/broll-video/batch", json={"source_paths": [str(source), str(tmp_path / "missing.mp4")], "tags": []})
    assert response.status_code == 201, response.text
    assert len(response.json()["assets"]) == 1
    assert response.json()["failures"] == [{"source_path": str((tmp_path / "missing.mp4").resolve()), "reason": "source file does not exist"}]
