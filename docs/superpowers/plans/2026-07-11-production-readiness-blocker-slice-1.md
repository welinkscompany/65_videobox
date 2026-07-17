# VideoBox Production-Readiness Blocker Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 첫 프로젝트 생성부터 수정 자막·길이 정규화·overlay가 포함된 SRT/MP4/실제 CapCut draft까지 여섯 production blocker를 계약 우선 TDD로 닫는다.

**Architecture:** 각 blocker는 먼저 독립 RED contract test로 고정한다. Timeline에는 output 재현에 필요한 segment snapshot과 검증된 media/overlay 정보만 저장하고, FFmpeg와 PyCapCut은 같은 canonical overlay 및 target-duration 계약을 소비한다. Frontend는 서버의 nullable output contract를 그대로 모델링하고 마지막 격리선으로 React ErrorBoundary를 둔다.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pytest, FFmpeg/ffprobe, PyCapCut, React 19, TypeScript, Vitest, Testing Library, PowerShell System.Speech

---

## 파일 책임 지도

- `tests/support/app_factory.py`: API test 전용 deterministic runtime과 `create_test_app`.
- `tests/conftest.py`: test support import path와 실제 HTTP transport 금지 guard.
- `apps/web/src/ProjectOnboarding.tsx`: 프로젝트 생성 및 server-local narration/script 경로 ingest 상태 머신.
- `apps/web/src/DashboardErrorBoundary.tsx`: 예상하지 못한 React render/lifecycle 오류 격리.
- `apps/web/src/api.ts`: onboarding 및 nullable output TypeScript contract.
- `apps/web/src/App.tsx`: 새 프로젝트 선택, output 실패/재시도 surface 연결.
- `packages/timeline-schema/src/videobox_timeline_schema/models.py`: timeline-local effective segment snapshot.
- `packages/core-engine/src/videobox_core_engine/timeline_builder.py`: 실제 asset 없는 BGM clip 금지와 segment snapshot 생성.
- `packages/core-engine/src/videobox_core_engine/_pipeline_private_helpers.py`: partial regeneration candidate에 effective segments 영속화 및 legacy fallback.
- `packages/storage-abstractions/src/videobox_storage/timeline_clip_source_resolution.py`: source trim과 timeline target duration 분리.
- `packages/core-engine/src/videobox_core_engine/export_overlays.py`: FFmpeg/CapCut 공통 overlay validation/canonicalization.
- `packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py`: video loop, audio pad/trim, overlay burn-in.
- `packages/capcut-export/src/videobox_capcut_export/pycapcut_adapter.py`: target window 및 real text/image overlay material.
- `services/api/src/videobox_api/main.py`: smoke용 deterministic STT/TTS/final-renderer injection.
- `scripts/New-ProductionReadinessKoreanSample.ps1`: 600초 실제 한국어 narration fixture 생성.
- `scripts/verify-production-readiness-smoke.py`: production API/storage/FFmpeg 10분 smoke.

### Task 1: API tests를 deterministic fake runtime으로 격리

**Files:**
- Create: `tests/support/__init__.py`
- Create: `tests/support/app_factory.py`
- Create: `tests/test_test_app_factory.py`
- Modify: `tests/conftest.py`
- Modify imports: `tests/test_api.py`, `tests/test_api_final_render_endpoint.py`, `tests/test_job_retry.py`, `tests/test_cross_project_job_dashboard.py`, `tests/test_api_capcut_draft_export_endpoint.py`, `tests/test_api_stt_provider_wiring.py`, `tests/test_broll_thumbnail_generation.py`, `tests/test_api_auto_cut_detect_endpoint.py`, `tests/test_api_tts_candidate_endpoint.py`

- [ ] **Step 1: 실제 transport를 호출하면 실패하는 RED test 작성**

```python
def test_create_test_app_uses_deterministic_runtime_without_http(tmp_path: Path) -> None:
    client = TestClient(create_test_app(projects_root=tmp_path))
    project_id = client.post("/api/projects", json={"name": "Offline Runtime"}).json()["project_id"]
    narration = tmp_path / "offline.wav"
    narration.write_bytes(b"deterministic test bytes")
    asset_id = client.post(
        f"/api/projects/{project_id}/assets/narration-audio",
        json={"source_path": str(narration)},
    ).json()["asset_id"]
    transcription_id = client.post(
        f"/api/projects/{project_id}/jobs/transcription",
        json={"narration_asset_id": asset_id},
    ).json()["job_id"]
    response = client.post(
        f"/api/projects/{project_id}/jobs/segment-analysis",
        json={"transcription_job_id": transcription_id, "script_asset_id": None},
    )
    assert response.status_code == 202
```

- [ ] **Step 2: RED 확인**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_test_app_factory.py -q -p no:cacheprovider`

Expected: `support.app_factory`가 없거나 기본 runtime이 forbidden transport까지 도달해 FAIL.

- [ ] **Step 3: deterministic fake factory와 transport guard 구현**

```python
class DeterministicOfflineRuntime:
    def generate_structured(self, **_: object) -> StructuredLLMResponse:
        raise LLMProviderError(
            provider_name="deterministic_test",
            message="Deterministic test runtime uses heuristic fallbacks.",
            retryable=False,
            error_code="DETERMINISTIC_TEST_FALLBACK",
        )


def create_test_app(**kwargs: object) -> FastAPI:
    kwargs.setdefault(
        "local_first_runtime_service_factory",
        lambda _store: DeterministicOfflineRuntime(),
    )
    return production_create_app(**kwargs)
```

`tests/conftest.py`에는 `ROOT / "tests"`를 import path에 추가하고 아래 autouse guard를 둔다.

```python
@pytest.fixture(autouse=True)
def forbid_live_llm_http(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_urlopen(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("API tests must not call a live LLM HTTP endpoint.")

    monkeypatch.setattr("videobox_api.main.urlopen", forbidden_urlopen)
```

아홉 test module은 `from support.app_factory import create_test_app as create_app`을 사용한다. 이미 `local_first_runtime_service_factory`를 넘기는 73개 호출은 wrapper가 그 값을 보존한다.

- [ ] **Step 4: GREEN 및 수집 수 확인**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_test_app_factory.py tests/test_api.py -q -p no:cacheprovider`

Expected: localhost 접속 없이 PASS.

Run: `& .\.venv\Scripts\python.exe -m pytest --collect-only -q -p no:cacheprovider`

Expected: 기존 605개보다 신규 test 수만큼 증가하고 collection error 없음.

- [ ] **Step 5: Commit**

```powershell
git add tests
git commit -m "test: isolate API suite from live LLM runtime"
```

### Task 2: nullable final/CapCut artifact와 UI ErrorBoundary

**Files:**
- Create: `apps/web/src/DashboardErrorBoundary.tsx`
- Create: `apps/web/src/DashboardErrorBoundary.test.tsx`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/main.tsx`
- Modify: `apps/web/src/app.test.tsx`
- Modify: `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `services/api/src/videobox_api/routers/outputs.py`

- [ ] **Step 1: nullable failure/retry와 boundary RED tests 작성**

```tsx
it("renders a final-render failure with a null artifact without unmounting the dashboard", async () => {
  vi.stubGlobal("fetch", createFetchMock({
    finalRenderResult: {
      job_id: "final_render_job_failed",
      status: "failed",
      render: null,
      error_message: "ffmpeg could not resolve the B-roll source",
    },
  }));
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "완성본 렌더" }));
  expect(await screen.findByText("완성본 렌더 실패")).toBeInTheDocument();
  expect(screen.getByText(/B-roll source/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "완성본 다시 렌더" })).toBeInTheDocument();
});
```

같은 형태로 CapCut null artifact, 두 retry, remount 복구를 추가한다. Boundary test는 의도적으로 throw하는 child와 주입한 reload spy를 사용한다.

```tsx
function BrokenDashboard(): never {
  throw new Error("unexpected dashboard render");
}
```

- [ ] **Step 2: RED 확인**

Run: `Push-Location apps\web; npm test -- src/app.test.tsx -t "null artifact|다시 렌더|다시 내보내기"; npm test -- src/DashboardErrorBoundary.test.tsx; Pop-Location`

Expected: 현 UI는 `null.file_uri`에서 crash하고 recovery control이 없어 FAIL.

- [ ] **Step 3: backend와 frontend nullable contract 구현**

Backend response에는 failure detail을 함께 보존한다.

```python
class FinalRenderJobResponse(StartJobResponse):
    render: FinalRenderArtifactResponse | None = None
    error_message: str | None = None


class CapCutDraftExportJobResponse(StartJobResponse):
    export: CapCutDraftExportArtifactResponse | None = None
    error_message: str | None = None
```

`get_final_render_result()`과 `get_capcut_draft_export_result()`은 `job["error_message"]`를 반환하고 router가 response에 전달한다.

Frontend는 canonical job status를 사용한다.

```ts
type OutputJobStatus = "pending" | "running" | "succeeded" | "failed";

export type FinalRenderJob = {
  job_id: string;
  status: OutputJobStatus;
  render: FinalRenderArtifact | null;
  error_message: string | null;
};
```

`App`은 `status === "succeeded" && render !== null`일 때만 file URI를 읽고 failed/null이면 오류 카드와 기존 start handler를 호출하는 retry button을 표시한다.

- [ ] **Step 4: ErrorBoundary 구현 및 root 연결**

```tsx
export class DashboardErrorBoundary extends Component<PropsWithChildren<Props>, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("VideoBox dashboard render failed", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <main role="alert" className="shell">
          <h1>대시보드를 표시하지 못했습니다</h1>
          <p>{this.state.error.message}</p>
          <button type="button" onClick={this.props.reloadDashboard ?? (() => window.location.reload())}>
            대시보드 다시 불러오기
          </button>
        </main>
      );
    }
    return this.props.children;
  }
}
```

- [ ] **Step 5: GREEN 및 frontend 전체 회귀**

Run: `Push-Location apps\web; npm test; npm run build; Pop-Location`

Expected: 기존 75개와 신규 nullable/retry/boundary tests 전체 PASS, TypeScript build PASS.

- [ ] **Step 6: Commit**

```powershell
git add apps/web/src packages/core-engine/src/videobox_core_engine/local_pipeline.py services/api/src
git commit -m "fix: handle nullable output artifacts safely"
```

### Task 3: 첫 프로젝트 생성과 narration/script ingest UI

**Files:**
- Create: `apps/web/src/ProjectOnboarding.tsx`
- Create: `apps/web/src/project-onboarding.test.tsx`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/App.tsx`

- [ ] **Step 1: create/ingest/failure/retry/remount RED tests 작성**

```tsx
it("registers optional narration and script paths for the created project", async () => {
  const harness = createEmptyProjectFetchHarness();
  vi.stubGlobal("fetch", harness.fetchMock);
  render(<App />);
  fireEvent.change(await screen.findByLabelText("프로젝트 이름"), { target: { value: "첫 영상" } });
  fireEvent.change(screen.getByLabelText("나레이션 로컬 경로"), { target: { value: "D:\\media\\narration.wav" } });
  fireEvent.change(screen.getByLabelText("스크립트 로컬 경로"), { target: { value: "D:\\media\\script.txt" } });
  fireEvent.click(screen.getByRole("button", { name: "프로젝트 만들기" }));
  expect(await screen.findByText("첫 영상")).toBeInTheDocument();
  expect(harness.narrationRequests).toEqual(["D:\\media\\narration.wav"]);
  expect(harness.scriptRequests).toEqual(["D:\\media\\script.txt"]);
});
```

별도 tests는 빈 dashboard create/select, 한 ingest만 실패 후 해당 항목 retry, unmount/remount 뒤 GET project 복구를 검증한다.

- [ ] **Step 2: RED 확인**

Run: `Push-Location apps\web; npm test -- src/project-onboarding.test.tsx; Pop-Location`

Expected: create form과 API client methods가 없어 FAIL.

- [ ] **Step 3: API client와 onboarding 상태 머신 구현**

```ts
createProject: (payload: { name: string }) =>
  request<Project>("/api/projects", jsonRequest("POST", payload)),
registerNarrationAudio: (projectId: string, payload: AssetRegistrationRequest) =>
  request<AssetResponse>(`/api/projects/${projectId}/assets/narration-audio`, jsonRequest("POST", payload)),
registerScriptDocument: (projectId: string, payload: AssetRegistrationRequest) =>
  request<AssetResponse>(`/api/projects/${projectId}/assets/script-document`, jsonRequest("POST", payload)),
```

`ProjectOnboarding`은 `idle | creating | ingesting | partial-error | ready`와 narration/script별 status를 유지한다. 입력은 browser upload가 아니라 서버가 접근 가능한 로컬 경로임을 label/help text에 명시한다. 프로젝트 POST 성공 즉시 `onProjectCreated(project)`를 호출하며 optional ingest 실패는 프로젝트 선택을 되돌리지 않는다.

`App` callback:

```tsx
function handleProjectCreated(project: Project) {
  setProjects((current) =>
    current.some((item) => item.project_id === project.project_id)
      ? current
      : [...current, project],
  );
  setSelectedProjectId(project.project_id);
}
```

Component는 생성 직후 ingest가 끝날 때까지 mount를 유지해 partial failure retry surface를 잃지 않는다.

- [ ] **Step 4: GREEN 및 frontend 전체 회귀**

Run: `Push-Location apps\web; npm test -- src/project-onboarding.test.tsx; npm test; npm run build; Pop-Location`

Expected: 신규 4개 이상과 기존 75개 모두 PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/web/src
git commit -m "feat: onboard the first local project"
```

### Task 4: 실제 music asset 없는 추천의 BGM clip 금지

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/timeline_builder.py`
- Modify: `tests/test_timeline_builder.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: mood-only 추천과 mixed recommendation RED tests 작성**

```python
def test_timeline_builder_does_not_create_bgm_track_without_selected_asset() -> None:
    timeline = TimelineBuilder().build(
        project_id="project_001",
        segments=[{"segment_id": "seg_001", "text": "소개", "start_sec": 0.0, "end_sec": 4.0}],
        recommendations=[{
            "recommendation_id": "rec_bgm_mood",
            "target_segment_id": "seg_001",
            "recommendation_type": "bgm",
            "selected_asset_id": None,
            "score": 0.8,
            "reason": "차분한 분위기",
            "auto_apply_allowed": True,
            "review_required": False,
            "payload": {"music_mood": "calm"},
        }],
    )
    assert all(track.track_type != "bgm" for track in timeline.tracks)
    assert timeline.applied_recommendations[0]["recommendation_id"] == "rec_bgm_mood"
```

API contract test는 실제 music recommendation job을 timeline build에 포함하고도 `music/suggested` URI와 BGM track이 없음을 검사한다.

- [ ] **Step 2: RED 확인**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_timeline_builder.py::test_timeline_builder_does_not_create_bgm_track_without_selected_asset tests/test_api.py -q -k "music_recommendation_local_first_path_preserves_downstream_timeline_behavior" -p no:cacheprovider`

Expected: 현재 builder가 `music/suggested` clip을 생성해 FAIL.

- [ ] **Step 3: playable asset이 있는 경우에만 BGM clip 생성**

```python
if rec_type == "bgm" and recommendation.get("selected_asset_id"):
    music_clips.append(
        TimelineClip(
            clip_id=f"clip_bgm_{len(music_clips) + 1:03d}",
            segment_id=segment_id,
            asset_uri=f"local://projects/{project_id}/assets/{recommendation['selected_asset_id']}",
            start_sec=float(segment["start_sec"]),
            end_sec=float(segment["end_sec"]),
            clip_type="bgm",
            recommendation_id=str(recommendation["recommendation_id"]),
        )
    )
```

Mood recommendation metadata는 `applied_recommendations`에 남기되 media track에는 넣지 않는다. Synthetic `music/suggested` 생성은 삭제한다.

- [ ] **Step 4: GREEN**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_timeline_builder.py tests/test_recommendations.py tests/test_api.py -q -k "timeline_builder or music_recommendation" -p no:cacheprovider`

Expected: 관련 tests PASS, `rg -n "music/suggested" packages tests`에서 production 생성 코드 0건.

- [ ] **Step 5: Commit**

```powershell
git add packages/core-engine/src/videobox_core_engine/timeline_builder.py tests
git commit -m "fix: skip assetless BGM timeline clips"
```

### Task 5: caption partial regeneration을 timeline-local SRT/final SSOT로 유지

**Files:**
- Modify: `packages/timeline-schema/src/videobox_timeline_schema/models.py`
- Modify: `packages/core-engine/src/videobox_core_engine/timeline_builder.py`
- Modify: `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
- Modify: `packages/core-engine/src/videobox_core_engine/_pipeline_private_helpers.py`
- Modify: `services/api/src/videobox_api/models.py`
- Modify: `apps/web/src/api.ts`
- Modify: `tests/test_editing_session.py`
- Modify: `tests/test_local_pipeline_final_render.py`

- [ ] **Step 1: caption→SRT, final subtitle input, legacy fallback RED tests 작성**

```python
def test_partial_regeneration_caption_flows_into_subtitle_render(pipeline_fixture) -> None:
    result = pipeline_fixture.regenerate_caption("수정된 최종 자막")
    pipeline_fixture.approve(result["job_id"])
    subtitle = pipeline_fixture.render_subtitle(result["job_id"])
    srt_text = pipeline_fixture.read_uri(subtitle["subtitle"]["file_uri"])
    assert "수정된 최종 자막" in srt_text
    assert "원본 자막" not in srt_text
```

Final renderer fake는 전달된 `subtitle_file_path.read_text(encoding="utf-8")`를 기록하고 수정 문구를 검사한다. Legacy timeline test는 `segments` key가 없는 저장 payload에서 기존 DB segment가 계속 나오는지 확인한다.

- [ ] **Step 2: RED 확인**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_editing_session.py::test_partial_regeneration_caption_flows_into_subtitle_render tests/test_local_pipeline_final_render.py::test_partial_regeneration_caption_flows_into_final_render_subtitle_input -q -p no:cacheprovider`

Expected: SRT/final input이 원본 caption을 포함해 FAIL.

- [ ] **Step 3: timeline-local segment snapshot 구현**

```python
@dataclass(slots=True, frozen=True)
class TimelineRecord:
    timeline_id: str
    project_id: str
    version: str
    output_mode: str
    tracks: list[TimelineTrack]
    review_flags: list[TimelineReviewFlag]
    segments: list[dict[str, object]] = field(default_factory=list)
```

`TimelineBuilder.build()`은 normalized segments를 `TimelineRecord.segments`에 넣고 최초/partial timeline payload 둘 다 `"segments": timeline.segments`를 저장한다.

```python
def _segments_for_timeline(self, *, project_id: str, timeline: dict[str, Any]) -> list[dict[str, Any]]:
    if "segments" in timeline:
        snapshot = timeline["segments"]
        if not isinstance(snapshot, list):
            return []
        return [deepcopy(item) for item in snapshot if isinstance(item, dict)]
    return self.store.list_segments(project_id=project_id)
```

실제 구현은 clip order와 removed segment filtering을 기존 helper 규칙대로 적용한다. `TimelinePayloadResponse`와 frontend `TimelinePayload`에는 optional segment/export overlay surface를 추가한다.

- [ ] **Step 4: GREEN 및 저장 재조회 회귀**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_editing_session.py tests/test_local_pipeline_final_render.py tests/test_preview_export.py -q -p no:cacheprovider`

Expected: 수정 caption이 저장 재조회, SRT, final renderer input에서 동일하고 legacy test PASS.

- [ ] **Step 5: Commit**

```powershell
git add packages/timeline-schema packages/core-engine services/api apps/web/src/api.ts tests
git commit -m "fix: persist regenerated captions into output timelines"
```

### Task 6: 짧은 B-roll/TTS를 target duration에 맞게 loop/pad/trim

**Files:**
- Modify: `packages/storage-abstractions/src/videobox_storage/timeline_clip_source_resolution.py`
- Modify: `packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py`
- Modify: `packages/capcut-export/src/videobox_capcut_export/pycapcut_adapter.py`
- Modify: `tests/test_ffmpeg_final_renderer.py`
- Modify: `tests/test_pycapcut_adapter.py`

- [ ] **Step 1: target duration 및 실제 ffprobe RED tests 작성**

```python
def test_resolve_tts_narration_clip_source_exposes_timeline_target_duration(tmp_path: Path) -> None:
    resolved = resolve_narration_clip_source(
        store=store,
        project_id=project.project_id,
        timeline={},
        clip={"asset_uri": tts_asset.storage_uri, "start_sec": 0.0, "end_sec": 4.0},
    )
    assert resolved.trim_duration_sec is None
    assert resolved.target_duration_sec == 4.0
```

FFmpeg tests는 4초 narration + 1초 B-roll, 1초 TTS + 4초 clip을 각각 실제 render하고 `ffprobe` duration이 `pytest.approx(4.0, abs=0.25)`인지 검사한다. 긴 TTS도 4초 clip에서 4초로 trim되는 test를 추가한다.

- [ ] **Step 2: RED 확인**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_ffmpeg_final_renderer.py -q -k "short_broll or short_tts or target_duration" -p no:cacheprovider`

Expected: 현재 4초 timeline이 약 1초 output으로 끝나거나 target field가 없어 FAIL.

- [ ] **Step 3: source trim과 target duration 분리**

```python
@dataclass(slots=True, frozen=True)
class ResolvedClipSource:
    path: Path
    trim_start_sec: float
    trim_duration_sec: float | None
    target_duration_sec: float
```

Original narration은 source trim/target 모두 clip window, TTS는 source natural/target clip window, B-roll은 target clip window로 해석한다.

- [ ] **Step 4: FFmpeg loop/pad/trim 구현**

Video extraction은 input 앞에 `-stream_loop -1`, output에 정확한 `-t target_duration`을 적용한다. Audio extraction은 다음 filter를 적용한다.

```python
audio_filter = (
    f"apad=whole_dur={source.target_duration_sec},"
    f"atrim=duration={source.target_duration_sec},asetpts=PTS-STARTPTS"
)
```

Final mux는 짧은 보조 track에 의해 조기 종료되지 않도록 계산한 timeline duration을 `-t`로 지정한다. B-roll concat과 narration concat이 같은 target duration 합을 갖는지 검사한다.

- [ ] **Step 5: PyCapCut target window 구현**

Narration/TTS `target_timerange.duration`은 항상 clip window를 사용한다. B-roll source가 짧으면 material duration 단위로 여러 `VideoSegment`를 이어 붙여 target window를 채우고 마지막 반복만 trim한다. 긴 source는 target window에서 trim한다.

- [ ] **Step 6: GREEN**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_ffmpeg_final_renderer.py tests/test_pycapcut_adapter.py -q -p no:cacheprovider`

Expected: short/long media duration tests와 기존 real MP4/CapCut draft tests PASS.

- [ ] **Step 7: Commit**

```powershell
git add packages/storage-abstractions packages/core-engine packages/capcut-export tests
git commit -m "fix: normalize media clips to timeline duration"
```

### Task 7: export_overlays를 FFmpeg와 real CapCut draft에 반영

**Files:**
- Create: `packages/core-engine/src/videobox_core_engine/export_overlays.py`
- Modify: `packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py`
- Modify: `packages/capcut-export/src/videobox_capcut_export/pycapcut_adapter.py`
- Modify: `tests/test_ffmpeg_final_renderer.py`
- Modify: `tests/test_pycapcut_adapter.py`

- [ ] **Step 1: text/image overlay RED tests 작성**

FFmpeg text test는 단색 B-roll로 render한 뒤 overlay 전/중 frame을 PNG로 추출해 SHA-256 또는 non-background pixel 수가 달라지는지 검사한다. Image test는 등록한 PNG의 고유 색상이 지정 window frame에 존재하는지 검사한다.

```python
def test_export_timeline_materializes_text_overlay_in_real_capcut_draft(tmp_path: Path) -> None:
    draft_path = adapter.export_timeline(
        project_id=project.project_id,
        timeline={**timeline, "export_overlays": [{
            "overlay_type": "explanation_card",
            "segment_id": "seg_001",
            "text": "핵심 설명 카드",
            "start_sec": 1.0,
            "end_sec": 3.0,
        }]},
        drafts_root=tmp_path / "drafts",
        draft_name="overlay_contract",
    )
    content = json.loads((draft_path / "draft_content.json").read_text(encoding="utf-8"))
    assert "핵심 설명 카드" in json.dumps(content, ensure_ascii=False)
```

- [ ] **Step 2: RED 확인**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_ffmpeg_final_renderer.py tests/test_pycapcut_adapter.py -q -k "export_overlay" -p no:cacheprovider`

Expected: renderer/draft가 overlay를 무시해 FAIL.

- [ ] **Step 3: 공통 canonicalizer 구현**

```python
@dataclass(slots=True, frozen=True)
class CanonicalExportOverlay:
    overlay_type: str
    segment_id: str
    start_sec: float
    end_sec: float
    text: str | None
    asset_id: str | None


def canonical_export_overlays(timeline: dict[str, Any]) -> list[CanonicalExportOverlay]:
    overlays = timeline.get("export_overlays", [])
    if not isinstance(overlays, list):
        raise ExportOverlayError("export_overlays must be a list.")
    return [_canonical_overlay(item) for item in overlays]
```

Aliases `image/image_card/image_overlay`, `table_card/table_overlay`, `hook_title/visual_overlay`를 canonical family로 묶는다. 잘못된 type, 음수/역전 timing, text/asset 필수값 누락은 ID/type을 포함한 `ExportOverlayError`로 실패시켜 조용한 누락을 금지한다.

- [ ] **Step 4: FFmpeg overlay 합성 구현**

Text/card/table은 UTF-8 ASS event를 임시 파일로 생성해 지정 window에 burn-in한다. Image overlay는 `resolve_generic_asset_uri()`로 실제 asset을 찾고 looped image input과 `overlay=enable='between(t,start,end)'` filter를 사용한다. Overlay가 없을 때만 기존 video-copy fast path를 유지하고, 하나라도 있으면 `libx264`로 재인코딩한다.

- [ ] **Step 5: PyCapCut real material 구현**

`TrackType.text`의 `TextSegment`와 `TextBackground`로 text/card/table을 만들고, image는 상위 video track에 `VideoMaterial`/`VideoSegment`로 추가한다. `Timerange`는 canonical start/duration을 사용하며 `ClipSettings`에 position/scale 기본값을 명시한다.

- [ ] **Step 6: GREEN**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_ffmpeg_final_renderer.py tests/test_pycapcut_adapter.py tests/test_preview_export.py -q -p no:cacheprovider`

Expected: frame/draft JSON에서 overlay가 실제 확인되고 malformed overlay error test도 PASS.

- [ ] **Step 7: Commit**

```powershell
git add packages/core-engine packages/capcut-export tests
git commit -m "feat: render export overlays in final outputs"
```

### Task 8: 실제 600초 한국어 ingest→edit→SRT→MP4 smoke

**Files:**
- Create: `scripts/New-ProductionReadinessKoreanSample.ps1`
- Create: `scripts/verify-production-readiness-smoke.py`
- Modify: `services/api/src/videobox_api/main.py`
- Modify: `tests/test_api_stt_provider_wiring.py`

- [ ] **Step 1: app assembly injection RED test 작성**

```python
def test_create_app_accepts_explicit_stt_tts_and_final_renderer_factories(tmp_path: Path) -> None:
    stt = DeterministicKoreanSTTProvider(duration_sec=600.0)
    tts = DeterministicWaveTTSProvider()
    app = create_app(
        projects_root=tmp_path,
        stt_provider=stt,
        tts_provider=tts,
        final_renderer_factory=lambda store: FfmpegFinalRenderer(
            store=store,
            video_width=320,
            video_height=180,
            video_fps=12,
        ),
    )
    assert app.state.stt_provider is stt
    assert app.state.tts_provider is tts
```

- [ ] **Step 2: RED 확인**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/test_api_stt_provider_wiring.py -q -p no:cacheprovider`

Expected: `create_app`에 injection parameters가 없어 FAIL.

- [ ] **Step 3: production assembly injection 구현**

`create_app()`에 optional `stt_provider`, `tts_provider`, `final_renderer_factory`를 추가한다. 값이 없으면 기존 config factory를 그대로 사용하고, 값이 있으면 pipeline에 명시적으로 전달한다. Resolved instances는 smoke assertion을 위해 `app.state`에 둔다.

- [ ] **Step 4: 600초 실제 한국어 fixture generator 구현**

PowerShell script는 설치된 `Microsoft Heami Desktop` ko-KR voice로 번호와 주제가 다른 한국어 문장 묶음을 충분히 길게 합성한다. Raw synthesis가 600초보다 짧으면 실패하고, 길면 FFmpeg로 정확히 600초 WAV를 만든다. 15초 음성 반복이나 silence padding은 성공으로 인정하지 않는다.

Run: `powershell -ExecutionPolicy Bypass -File scripts/New-ProductionReadinessKoreanSample.ps1 -OutputPath "D:\AI_Workspace_louis_office_50\20_project\65_videobox-project\smoke_sources\production-readiness-korean-10m.wav"`

Expected: `ffprobe` duration `600.0 ± 0.1`, 파일 SHA-256 출력.

- [ ] **Step 5: smoke harness 구현**

Harness는 deterministic offline structured runtime, 600초 Korean STT segment, valid WAV TTS provider를 주입하고 다음 production API 순서를 실행한다.

1. project create
2. narration/script/B-roll ingest
3. transcription and segment analysis
4. B-roll and assetless music recommendation
5. timeline build and review approval
6. editing session caption/overlay update
7. partial regeneration and candidate approval
8. subtitle render
9. final MP4 render/poll

검증은 수정 한국어 SRT 포함, `music/suggested` 부재, 3초 B-roll의 600초 loop, overlay window frame 변화, MP4 `600.0 ± 0.5`, artifact SHA-256를 포함한다.

- [ ] **Step 6: 실제 smoke 실행**

Run: `& .\.venv\Scripts\python.exe scripts/verify-production-readiness-smoke.py --narration "D:\AI_Workspace_louis_office_50\20_project\65_videobox-project\smoke_sources\production-readiness-korean-10m.wav" --work-root "tmp\production-readiness-smoke"`

Expected: exit 0과 JSON summary에 ingest/edit/SRT/MP4 checks 모두 `true`.

- [ ] **Step 7: Commit**

```powershell
git add services/api/src/videobox_api/main.py tests/test_api_stt_provider_wiring.py scripts
git commit -m "test: add ten minute production readiness smoke"
```

### Task 9: 전체 회귀, 코드리뷰, SSOT와 누적 진행률 closeout

**Files:**
- Modify: `scripts/dev-fast-path.ps1`
- Modify: `docs/development-fast-path.ko.md`
- Modify: `docs/implementation-plan.ko.md`
- Modify: `docs/development-status-2026-06-29.ko.md`

- [ ] **Step 1: 표준 verifier가 venv Python 3.12를 강제하는 RED 확인**

Run: `rg -n 'Command = "pytest|Command "pytest' scripts/dev-fast-path.ps1`

Expected: bare `pytest` 호출이 존재.

- [ ] **Step 2: verifier interpreter pin 구현**

```powershell
$backendPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $backendPython)) {
    throw "VideoBox backend venv Python not found: $backendPython"
}
$pytestCommand = "& `"$backendPython`" -m pytest"
```

모든 backend command는 `$pytestCommand`를 prefix로 사용한다. `docs/development-fast-path.ko.md` §10.3에 동일한 영구 규칙을 기록한다.

- [ ] **Step 3: frontend 전체와 build 실행**

Run: `Push-Location apps\web; npm test; npm run build; Pop-Location`

Expected: 기존 75개 + 신규 tests 전체 PASS, warning/error 별도 기록, build PASS.

- [ ] **Step 4: backend 전체를 venv Python 3.12로 실행**

Run: `& .\.venv\Scripts\python.exe --version`

Expected: `Python 3.12.x`.

Run: `& .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`

Expected: 기존 605개 + 신규 tests 전체 PASS, skip이 있으면 이유를 기록.

- [ ] **Step 5: 독립 code review와 finding 수정**

Review는 여섯 계약 각각의 test coverage, nullable 상태 분기, legacy timeline fallback, FFmpeg command safety, PyCapCut draft JSON, smoke artifact를 확인한다. Blocker finding은 RED test 추가 후 수정하고 focused/full suites를 재실행한다.

- [ ] **Step 6: SSOT와 누적 진행률 갱신**

`docs/implementation-plan.ko.md` §§12–13을 현재 HEAD, blocker matrix, 실제 test 수, smoke evidence, 설계/계획 링크로 갱신한다. `docs/development-status-2026-06-29.ko.md` 상단에 새 authoritative §217을 추가하고 §§1–216은 historical로 명시한다.

39개 milestone bullet을 다시 판정해 완료/부분/미구현 수, strict 완료율, 부분 0.5 가중 진행률과 잔여율을 계산한다. 근거 없이 기존 79%를 재사용하지 않는다.

- [ ] **Step 7: diff/status와 최종 검증**

Run: `git diff --check`

Run: `git status --short --branch`

Run: `git diff --stat dd03143..HEAD`

Run: `git log --oneline dd03143..HEAD`

Expected: whitespace error 없음, 의도한 source/test/docs만 존재, smoke 대용량 media는 Git에 포함되지 않음.

- [ ] **Step 8: closeout commit**

```powershell
git add scripts/dev-fast-path.ps1 docs
git commit -m "docs: close production readiness blocker slice 1"
```

- [ ] **Step 9: completion audit**

여섯 범위와 모든 검증 명령에 대해 current-state 증거를 다시 대조한다. 하나라도 실패·미실행·간접 증거이면 goal을 complete로 표시하지 않는다. 전부 충족됐을 때만 goal status를 complete로 갱신한다.
