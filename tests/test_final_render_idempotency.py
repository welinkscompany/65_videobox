from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from videobox_core_engine.local_pipeline import LocalPipelineRunner
from videobox_domain_models.jobs import JobStatus, JobType
from videobox_api.orchestration import ApiOrchestrator
from videobox_api.routers.outputs import build_outputs_router
from videobox_storage.local_project_store import LocalProjectStore


def _ready_timeline_job(store: LocalProjectStore, project_id: str, *, suffix: str) -> str:
    timeline = store.save_timeline_run(
        project_id=project_id,
        output_mode="review",
        source_session_revision=1,
        timeline_payload={"review_flags": [], "pending_recommendations": [], "tracks": []},
    )
    session = store.save_editing_session(
        project_id=project_id,
        timeline_id=timeline["timeline_id"],
        session_payload={"segments": [], "history": []},
    )
    store.save_review_state(
        project_id=project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
        source_session_revision=session["session_revision"],
    )
    timeline_job = store.create_job(
        project_id=project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref=suffix,
        status=JobStatus.RUNNING,
    )
    store.update_job(
        project_id=project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )
    return timeline_job["job_id"]


def test_concurrent_final_render_starts_reuse_one_active_job(tmp_path) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("final render idempotency")
    timeline_job_id = _ready_timeline_job(store, project.project_id, suffix="one")
    pipeline = LocalPipelineRunner(store)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: pipeline.start_final_render_job(
                    project_id=project.project_id, timeline_job_id=timeline_job_id
                ),
                range(2),
            )
        )

    assert len({result["job_id"] for result in results}) == 1
    assert [bool(result["should_start"]) for result in results].count(True) == 1
    assert len([
        job
        for job in store.list_jobs(project_id=project.project_id)
        if job["job_type"] == JobType.FINAL_RENDER.value and job["input_ref"] == timeline_job_id
    ]) == 1


def test_final_render_allows_a_new_job_for_a_different_timeline_or_terminal_failure(tmp_path) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("final render distinct runs")
    first_timeline_job_id = _ready_timeline_job(store, project.project_id, suffix="first")
    second_timeline_job_id = _ready_timeline_job(store, project.project_id, suffix="second")
    pipeline = LocalPipelineRunner(store)

    first = pipeline.start_final_render_job(
        project_id=project.project_id, timeline_job_id=first_timeline_job_id
    )
    second = pipeline.start_final_render_job(
        project_id=project.project_id, timeline_job_id=second_timeline_job_id
    )
    store.update_job(
        project_id=project.project_id,
        job_id=first["job_id"],
        status=JobStatus.FAILED,
        error_message="encoder failed",
    )
    retried = pipeline.start_final_render_job(
        project_id=project.project_id, timeline_job_id=first_timeline_job_id
    )

    assert second["job_id"] != first["job_id"]
    assert retried["job_id"] != first["job_id"]


def test_variant_render_route_returns_independent_itemized_statuses(monkeypatch) -> None:
    class VariantBatchOrchestrator:
        def launch_pending_variant_render_workers(self, **_kwargs) -> None:
            # 두 항목 다 `should_start`가 없으므로(고정값) 이 시험에서는
            # 아무 워커도 안 켜진다 -- 실제 켜는 것은 `ApiOrchestrator`
            # 쪽에서 별도로 검증한다.
            return None

        def start_variant_renders(self, **_kwargs):
            return {
                "project_id": "project-a",
                "items": [
                    {
                        "variant_id": "horizontal",
                        "variant_kind": "horizontal",
                        "timeline_id": "timeline-horizontal",
                        "timeline_job_id": "timeline-job-horizontal",
                        "job_id": "final-horizontal",
                        "status": "running",
                        "should_start": False,
                    },
                    {
                        "variant_id": "vertical-full",
                        "variant_kind": "vertical_full",
                        "timeline_id": "timeline-vertical",
                        "timeline_job_id": "timeline-job-vertical",
                        "job_id": "final-vertical",
                        "status": "failed",
                        "error_code": "renderer_unavailable",
                        "should_start": False,
                    },
                ],
            }

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from videobox_api.routers.outputs import build_outputs_router

    app = FastAPI()
    app.include_router(build_outputs_router(VariantBatchOrchestrator()))
    response = TestClient(app).post(
        "/api/projects/project-a/variant-renders",
        json={"session_id": "session-a", "variant_ids": ["horizontal", "vertical-full"]},
    )

    assert response.status_code == 202
    assert response.json()["items"][0]["status"] == "running"
    assert response.json()["items"][1]["status"] == "failed"


def test_pipeline_materializes_default_variants_and_reuses_their_render_jobs(tmp_path) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("variant render batch")
    timeline_job_id = _ready_timeline_job(store, project.project_id, suffix="variant-batch")
    session = store.get_latest_editing_session(project_id=project.project_id)
    store.ensure_output_variants(project_id=project.project_id, session_id=session["session_id"])
    pipeline = LocalPipelineRunner(store, final_renderer=object())

    first = pipeline.start_variant_renders(
        project_id=project.project_id,
        session_id=session["session_id"],
        variant_ids=[],
    )
    second = pipeline.start_variant_renders(
        project_id=project.project_id,
        session_id=session["session_id"],
        variant_ids=[item["variant_id"] for item in first["items"]],
    )

    assert {item.get("variant_kind") for item in first["items"]} == {"horizontal", "vertical_full"}, first
    assert {item["job_id"] for item in first["items"]} == {item["job_id"] for item in second["items"]}
    assert len([
        job for job in store.list_jobs(project_id=project.project_id)
        if job["job_type"] == JobType.TIMELINE_BUILD.value and str(job["input_ref"]).startswith("variant:")
    ]) == 2


def test_pipeline_reused_variant_materialization_inherits_newly_approved_master_review(tmp_path) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("variant review propagation")
    source = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        source_session_revision=1,
        timeline_payload={"review_flags": [], "pending_recommendations": [], "tracks": [], "segments": []},
    )
    session = store.save_editing_session(
        project_id=project.project_id,
        timeline_id=source["timeline_id"],
        session_payload={"segments": [], "history": []},
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=source["timeline_id"],
        status="draft",
        source_session_id=session["session_id"],
        source_session_revision=session["session_revision"],
    )
    variants = store.ensure_output_variants(
        project_id=project.project_id,
        session_id=session["session_id"],
    )
    pipeline = LocalPipelineRunner(store, final_renderer=object())

    first = pipeline._materialize_variant_for_output(
        project_id=project.project_id,
        session_id=session["session_id"],
        variant_id=variants[0]["variant_id"],
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=source["timeline_id"],
        status="approved",
        source_session_id=session["session_id"],
        source_session_revision=session["session_revision"],
    )

    batch = pipeline.start_variant_renders(
        project_id=project.project_id,
        session_id=session["session_id"],
        variant_ids=[variants[0]["variant_id"]],
    )

    assert batch["items"][0]["timeline_id"] == first["timeline_id"]
    review = store.get_review_state(
        project_id=project.project_id,
        timeline_id=first["timeline_id"],
    )
    assert review["status"] == "approved"
    assert review["source_variant_id"] == variants[0]["variant_id"]
    assert review["source_variant_revision"] == 1


def test_final_render_route_starts_one_worker_when_the_active_job_is_reused(monkeypatch) -> None:
    class ReusingOrchestrator:
        def __init__(self) -> None:
            self.worker_starts: list[str] = []
            self.claims = 0

        def assert_timeline_output_allowed(self, **_kwargs) -> None:
            return None

        def start_final_render_job(self, **_kwargs) -> dict[str, object]:
            self.claims += 1
            return {
                "job_id": "final_render_job_001",
                "status": "running",
                "should_start": self.claims == 1,
            }

        def run_final_render_job(self, *, job: dict[str, str], **_kwargs) -> None:
            self.worker_starts.append(job["job_id"])

    class InlineThread:
        def __init__(self, *, target, kwargs, **_kwargs) -> None:
            self.target = target
            self.kwargs = kwargs

        def start(self) -> None:
            self.target(**self.kwargs)

    import videobox_api.routers.outputs as outputs_router

    monkeypatch.setattr(outputs_router.threading, "Thread", InlineThread)
    orchestrator = ReusingOrchestrator()
    app = FastAPI()
    app.include_router(build_outputs_router(orchestrator))
    client = TestClient(app)

    first = client.post("/api/projects/project-a/jobs/final-render", json={"timeline_job_id": "timeline-job-a"})
    second = client.post("/api/projects/project-a/jobs/final-render", json={"timeline_job_id": "timeline-job-a"})

    assert first.json() == {"job_id": "final_render_job_001", "status": "running"}
    assert second.json() == {"job_id": "final_render_job_001", "status": "running"}
    assert orchestrator.worker_starts == ["final_render_job_001"]


def test_final_render_restarts_a_reused_active_job_when_the_new_runner_has_no_live_worker(
    tmp_path,
) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("final render orphan recovery")
    timeline_job_id = _ready_timeline_job(store, project.project_id, suffix="final-orphan")
    previous_process = LocalPipelineRunner(store, final_renderer=object())
    orphaned = previous_process.start_final_render_job(
        project_id=project.project_id,
        timeline_job_id=timeline_job_id,
    )

    restarted_process = LocalPipelineRunner(store, final_renderer=object())
    recovered = restarted_process.start_final_render_job(
        project_id=project.project_id,
        timeline_job_id=timeline_job_id,
    )
    concurrent = restarted_process.start_final_render_job(
        project_id=project.project_id,
        timeline_job_id=timeline_job_id,
    )

    assert recovered["job_id"] == orphaned["job_id"]
    assert recovered["should_start"] is True
    assert concurrent["job_id"] == orphaned["job_id"]
    assert concurrent["should_start"] is False


def test_final_render_releases_live_worker_ownership_when_the_worker_finishes(
    tmp_path,
) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("final render worker release")
    timeline_job_id = _ready_timeline_job(store, project.project_id, suffix="final-release")
    pipeline = LocalPipelineRunner(store, final_renderer=object())
    claimed = pipeline.start_final_render_job(
        project_id=project.project_id,
        timeline_job_id=timeline_job_id,
    )

    pipeline.run_final_render_job(
        project_id=project.project_id,
        timeline_job_id=timeline_job_id,
        job={"job_id": claimed["job_id"]},
    )
    store.update_job(
        project_id=project.project_id,
        job_id=claimed["job_id"],
        status=JobStatus.RUNNING,
    )
    restarted = pipeline.start_final_render_job(
        project_id=project.project_id,
        timeline_job_id=timeline_job_id,
    )

    assert restarted["job_id"] == claimed["job_id"]
    assert restarted["should_start"] is True


def test_final_render_route_releases_the_worker_reservation_when_thread_start_fails(
    monkeypatch,
) -> None:
    class RecoveringOrchestrator:
        def __init__(self) -> None:
            self.worker_claimed = False
            self.worker_starts: list[str] = []

        def assert_timeline_output_allowed(self, **_kwargs) -> None:
            return None

        def start_final_render_job(self, **_kwargs) -> dict[str, object]:
            should_start = not self.worker_claimed
            if should_start:
                self.worker_claimed = True
            return {
                "job_id": "final_render_job_001",
                "status": "running",
                "should_start": should_start,
            }

        def release_final_render_worker(
            self,
            *,
            project_id: str,
            job_id: str,
        ) -> None:
            assert project_id == "project-a"
            assert job_id == "final_render_job_001"
            self.worker_claimed = False

        def run_final_render_job(self, *, job: dict[str, str], **_kwargs) -> None:
            self.worker_starts.append(job["job_id"])

    class FailOnceThread:
        starts = 0

        def __init__(self, *, target, kwargs, **_kwargs) -> None:
            self.target = target
            self.kwargs = kwargs

        def start(self) -> None:
            type(self).starts += 1
            if type(self).starts == 1:
                raise RuntimeError("thread start failed")
            self.target(**self.kwargs)

    import videobox_api.routers.outputs as outputs_router

    monkeypatch.setattr(outputs_router.threading, "Thread", FailOnceThread)
    orchestrator = RecoveringOrchestrator()
    app = FastAPI()
    app.include_router(build_outputs_router(orchestrator))
    client = TestClient(app)

    with pytest.raises(RuntimeError, match="thread start failed"):
        client.post(
            "/api/projects/project-a/jobs/final-render",
            json={"timeline_job_id": "timeline-job-a"},
        )
    recovered = client.post(
        "/api/projects/project-a/jobs/final-render",
        json={"timeline_job_id": "timeline-job-a"},
    )

    assert recovered.json() == {
        "job_id": "final_render_job_001",
        "status": "running",
    }
    assert orchestrator.worker_starts == ["final_render_job_001"]


def test_launch_pending_variant_render_workers_starts_only_items_that_should_start(monkeypatch) -> None:
    """화면 단추와 유진 채팅("숏폼 내보내줘")이 공유하는 한 자리를 직접 잰다.

    `test_variant_render_route_returns_independent_itemized_statuses`는 라우터
    경유라 이 함수의 세부(어떤 항목만 켜지는지, 실패하면 반환값을 어떻게
    고치는지)까지는 안 잰다 -- 그 시험의 가짜 orchestrator는 이 함수를 아예
    안 부르게 no-op으로 세워 뒀다.
    """
    class RecordingPipeline:
        def __init__(self) -> None:
            self.started: list[str] = []
            self.released: list[tuple[str, str]] = []

        def run_final_render_job(self, *, project_id: str, timeline_job_id: str, job: dict[str, object]) -> None:
            self.started.append(str(job["job_id"]))

        def release_final_render_worker(self, *, project_id: str, job_id: str) -> None:
            self.released.append((project_id, job_id))

    class FailOnceThread:
        starts = 0

        def __init__(self, *, target, kwargs, **_kwargs) -> None:
            self.target = target
            self.kwargs = kwargs

        def start(self) -> None:
            type(self).starts += 1
            if type(self).starts == 1:
                raise RuntimeError("thread start failed")
            self.target(**self.kwargs)

    import videobox_api.orchestration as orchestration_module

    monkeypatch.setattr(orchestration_module.threading, "Thread", FailOnceThread)
    pipeline = RecordingPipeline()
    orchestrator = ApiOrchestrator(store=object(), pipeline=pipeline)  # type: ignore[arg-type]
    items = [
        {"timeline_job_id": "tj-skip", "job_id": "job-skip", "status": "failed", "should_start": True},
        {"timeline_job_id": "tj-fail", "job_id": "job-fail", "status": "running", "should_start": True},
        {"timeline_job_id": "tj-ok", "job_id": "job-ok", "status": "pending", "should_start": True},
    ]

    orchestrator.launch_pending_variant_render_workers(project_id="project-a", items=items)

    # 이미 실패로 온 항목은 워커를 켤 이유가 없다 -- `should_start`가 참이어도
    # `status`가 `running`/`pending`이 아니면 건너뛴다.
    assert pipeline.started == ["job-ok"]
    assert items[0]["status"] == "failed"
    # 첫 번째로 켜려던 항목(`job-fail`)은 스레드 시작 자체가 실패했다 --
    # 예약을 풀고 실패로 다시 적는다(화면 단추 경로와 같은 규칙).
    assert items[1]["status"] == "failed"
    assert items[1]["error_code"] == "worker_start_failed"
    assert pipeline.released == [("project-a", "job-fail")]
    assert items[2]["status"] == "pending"


def test_api_orchestrator_forwards_final_render_worker_release() -> None:
    class RecordingPipeline:
        def __init__(self) -> None:
            self.releases: list[tuple[str, str]] = []

        def release_final_render_worker(
            self,
            *,
            project_id: str,
            job_id: str,
        ) -> None:
            self.releases.append((project_id, job_id))

    pipeline = RecordingPipeline()
    orchestrator = ApiOrchestrator(store=object(), pipeline=pipeline)  # type: ignore[arg-type]

    orchestrator.release_final_render_worker(
        project_id="project-a",
        job_id="final_render_job_001",
    )

    assert pipeline.releases == [("project-a", "final_render_job_001")]


def test_concurrent_capcut_draft_starts_reuse_one_active_job(tmp_path) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("capcut draft idempotency")
    timeline_job_id = _ready_timeline_job(store, project.project_id, suffix="capcut")
    pipeline = LocalPipelineRunner(store, pycapcut_exporter=object())

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: pipeline.start_capcut_draft_export_job(
                    project_id=project.project_id, timeline_job_id=timeline_job_id
                ),
                range(2),
            )
        )

    assert len({result["job_id"] for result in results}) == 1
    assert [bool(result["should_start"]) for result in results].count(True) == 1
    assert len([
        job
        for job in store.list_jobs(project_id=project.project_id)
        if job["job_type"] == JobType.CAPCUT_DRAFT_EXPORT.value
        and job["input_ref"] == timeline_job_id
    ]) == 1


def test_capcut_draft_restarts_a_reused_active_job_when_the_new_runner_has_no_live_worker(
    tmp_path,
) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("capcut draft orphan recovery")
    timeline_job_id = _ready_timeline_job(store, project.project_id, suffix="capcut-orphan")
    previous_process = LocalPipelineRunner(store, pycapcut_exporter=object())
    orphaned = previous_process.start_capcut_draft_export_job(
        project_id=project.project_id,
        timeline_job_id=timeline_job_id,
    )

    restarted_process = LocalPipelineRunner(store, pycapcut_exporter=object())
    recovered = restarted_process.start_capcut_draft_export_job(
        project_id=project.project_id,
        timeline_job_id=timeline_job_id,
    )
    concurrent = restarted_process.start_capcut_draft_export_job(
        project_id=project.project_id,
        timeline_job_id=timeline_job_id,
    )

    assert recovered["job_id"] == orphaned["job_id"]
    assert recovered["should_start"] is True
    assert concurrent["job_id"] == orphaned["job_id"]
    assert concurrent["should_start"] is False


def test_capcut_draft_releases_live_worker_ownership_when_the_worker_finishes(
    tmp_path,
) -> None:
    store = LocalProjectStore(tmp_path / "projects")
    project = store.bootstrap_project("capcut draft worker release")
    timeline_job_id = _ready_timeline_job(store, project.project_id, suffix="capcut-release")
    pipeline = LocalPipelineRunner(store, pycapcut_exporter=object())
    claimed = pipeline.start_capcut_draft_export_job(
        project_id=project.project_id,
        timeline_job_id=timeline_job_id,
    )

    pipeline.run_capcut_draft_export_job(
        project_id=project.project_id,
        timeline_job_id=timeline_job_id,
        job={"job_id": claimed["job_id"]},
    )
    store.update_job(
        project_id=project.project_id,
        job_id=claimed["job_id"],
        status=JobStatus.RUNNING,
    )
    restarted = pipeline.start_capcut_draft_export_job(
        project_id=project.project_id,
        timeline_job_id=timeline_job_id,
    )

    assert restarted["job_id"] == claimed["job_id"]
    assert restarted["should_start"] is True


def test_capcut_draft_route_starts_one_worker_when_the_active_job_is_reused(monkeypatch) -> None:
    class ReusingOrchestrator:
        def __init__(self) -> None:
            self.worker_starts: list[str] = []
            self.claims = 0

        def assert_timeline_output_allowed(self, **_kwargs) -> None:
            return None

        def start_capcut_draft_export_job(self, **_kwargs) -> dict[str, object]:
            self.claims += 1
            return {
                "job_id": "capcut_draft_export_job_001",
                "status": "running",
                "should_start": self.claims == 1,
            }

        def run_capcut_draft_export_job(self, *, job: dict[str, str], **_kwargs) -> None:
            self.worker_starts.append(job["job_id"])

    class InlineThread:
        def __init__(self, *, target, kwargs, **_kwargs) -> None:
            self.target = target
            self.kwargs = kwargs

        def start(self) -> None:
            self.target(**self.kwargs)

    import videobox_api.routers.outputs as outputs_router

    monkeypatch.setattr(outputs_router.threading, "Thread", InlineThread)
    orchestrator = ReusingOrchestrator()
    app = FastAPI()
    app.include_router(build_outputs_router(orchestrator))
    client = TestClient(app)

    first = client.post(
        "/api/projects/project-a/jobs/capcut-draft-export",
        json={"timeline_job_id": "timeline-job-a"},
    )
    second = client.post(
        "/api/projects/project-a/jobs/capcut-draft-export",
        json={"timeline_job_id": "timeline-job-a"},
    )

    assert first.json() == {"job_id": "capcut_draft_export_job_001", "status": "running"}
    assert second.json() == {"job_id": "capcut_draft_export_job_001", "status": "running"}
    assert orchestrator.worker_starts == ["capcut_draft_export_job_001"]


def test_capcut_draft_route_releases_the_worker_reservation_when_thread_start_fails(
    monkeypatch,
) -> None:
    class RecoveringOrchestrator:
        def __init__(self) -> None:
            self.worker_claimed = False
            self.worker_starts: list[str] = []

        def assert_timeline_output_allowed(self, **_kwargs) -> None:
            return None

        def start_capcut_draft_export_job(self, **_kwargs) -> dict[str, object]:
            should_start = not self.worker_claimed
            if should_start:
                self.worker_claimed = True
            return {
                "job_id": "capcut_draft_export_job_001",
                "status": "running",
                "should_start": should_start,
            }

        def release_capcut_draft_export_worker(
            self,
            *,
            project_id: str,
            job_id: str,
        ) -> None:
            assert project_id == "project-a"
            assert job_id == "capcut_draft_export_job_001"
            self.worker_claimed = False

        def run_capcut_draft_export_job(self, *, job: dict[str, str], **_kwargs) -> None:
            self.worker_starts.append(job["job_id"])

    class FailOnceThread:
        starts = 0

        def __init__(self, *, target, kwargs, **_kwargs) -> None:
            self.target = target
            self.kwargs = kwargs

        def start(self) -> None:
            type(self).starts += 1
            if type(self).starts == 1:
                raise RuntimeError("thread start failed")
            self.target(**self.kwargs)

    import videobox_api.routers.outputs as outputs_router

    monkeypatch.setattr(outputs_router.threading, "Thread", FailOnceThread)
    orchestrator = RecoveringOrchestrator()
    app = FastAPI()
    app.include_router(build_outputs_router(orchestrator))
    client = TestClient(app)

    with pytest.raises(RuntimeError, match="thread start failed"):
        client.post(
            "/api/projects/project-a/jobs/capcut-draft-export",
            json={"timeline_job_id": "timeline-job-a"},
        )
    recovered = client.post(
        "/api/projects/project-a/jobs/capcut-draft-export",
        json={"timeline_job_id": "timeline-job-a"},
    )

    assert recovered.json() == {
        "job_id": "capcut_draft_export_job_001",
        "status": "running",
    }
    assert orchestrator.worker_starts == ["capcut_draft_export_job_001"]
