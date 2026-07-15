# VideoBox Local Media Director Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 대본만 입력해도 로컬 B-roll·BGM·SFX를 자동 분석·추천하고, 사용자가 AI 디렉터 또는 수동 편집으로 미리보기·적용·10단계 복원한 결과를 SRT·MP4·real CapCut draft까지 일관되게 출력한다.

**Architecture:** 구현은 세 개의 순차 slice로 나눈다. Slice 1은 LM Studio local-only provider와 durable media analysis를, Slice 2는 immutable proposal·ranking·materialize·atomic editing transaction을, Slice 3은 대화 기록과 분리된 React Director workspace를 연결한다. Editing session은 계속 유일한 편집 truth이며, AI 응답은 명시적 apply 전에는 editing session을 변경하지 않는다.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, SQLite, FFmpeg/ffprobe, LM Studio OpenAI-compatible API, React 19, TypeScript 5.8, Vitest, pytest, PyCapCut.

---

## 0. 실행 결정

- 사용자가 말한 Codex 5.6 Sol Ultra와 실제 개발 시 Terra/Luna 선택은 개발 에이전트 실행 자원이다. VideoBox 제품 런타임 모델명이나 acceptance 조건으로 저장하지 않는다.
- 제품 AI runtime은 LM Studio loopback만 사용한다. Gemini 또는 외부 AI provider로 자동 fallback하지 않는다.
- 현재 개발 PC에서 확인한 Qwen vision/BGE embedding 모델명은 live smoke profile일 뿐이다. 실행 시 capability preflight로 loaded vision/text/embedding 모델을 고른다.
- 기존 RecommendationRecord는 자동 적용 가능 정책을 포함하므로 DirectorProposal로 재사용하지 않는다. 새 immutable aggregate를 만든다.
- 대본만 있고 나레이션이 없어도 provisional script session과 proposal을 만들 수 있어야 한다. 나레이션이 추가되면 실제 alignment가 provisional timing을 대체한다.
- global Starter Media Pack 자산은 추천에 노출할 수 있지만 apply transaction 안에서 project-local materialize가 성공해야 editing session에 들어간다.
- user-owned B-roll 권리는 unknown이 기본이다. local draft/export는 허용하되 output warning을 유지한다.
- 사용자 복원 stack은 정확히 최근 10개 transaction이다. 장기 감사 history는 별도로 최대 100개를 유지한다.
- App.tsx의 전면 리팩터링은 하지 않는다. Director와 media analysis UI만 feature 폴더로 분리하고 App은 프로젝트·세션 연결과 output freshness invalidation을 담당한다.
- 실제 CapCut Desktop 자동 실행은 이 계획 범위가 아니다. real draft JSON 생성은 자동 검증하고, Desktop open/edit/export는 기존 human acceptance로 남긴다.

## 1. 확인된 현재 갭

- packages/provider-interfaces/src/videobox_provider_interfaces/local_qwen.py는 text-only다. image, embedding, capability preflight가 없다.
- packages/core-engine/src/videobox_core_engine/local_first_runtime.py는 로컬 실패 시 Gemini로 자동 fallback한다.
- packages/core-engine/src/videobox_core_engine/settings.py는 외부 HTTP(S) host를 허용해 loopback-only 계약과 충돌한다.
- JobStatus는 pending/running/succeeded/failed뿐이고 retry attempt, next_retry, blocked, needs_review, cancelled, cancel request가 없다.
- B-roll batch directory import는 한 단계만 읽으며 등록 뒤 title/tags/thumbnail만 만든다.
- start_segment_analysis는 transcription job을 필수로 요구해 script-only flow가 없다.
- B/M/S override mutation은 일반 history만 추가하므로 현재 undo snapshot에 포함되지 않는다.
- MAX_TIMELINE_UNDO_EVENTS는 100으로 설계의 사용자 10단계 복원과 다르다.
- media library materialize가 API router 내부 단건 로직이라 proposal bundle 서비스에서 재사용할 수 없다.
- output 직전 project-local path, content SHA-256, media revision 재검증이 없다.
- apps/web/src/App.tsx는 4,396줄이고 app.test.tsx는 5,709줄이다. 새 세부 동작을 두 파일에 계속 직접 추가하면 회귀 범위가 과도하게 커진다.
- tests/conftest.py는 videobox_api.main.urlopen만 막는다. module-local urlopen이나 새 transport의 socket 연결까지 차단하지 않는다.

## 2. 파일 구조

### Slice 1 — Local media intelligence foundation

- Create: packages/domain-models/src/videobox_domain_models/media_analysis.py
- Create: packages/provider-interfaces/src/videobox_provider_interfaces/vision.py
- Create: packages/provider-interfaces/src/videobox_provider_interfaces/embeddings.py
- Create: packages/provider-interfaces/src/videobox_provider_interfaces/lm_studio.py
- Create: packages/core-engine/src/videobox_core_engine/local_only_runtime.py
- Create: packages/core-engine/src/videobox_core_engine/media_probe.py
- Create: packages/core-engine/src/videobox_core_engine/media_analysis.py
- Create: services/api/src/videobox_api/routers/media_analysis.py
- Create: apps/web/src/features/media/MediaAnalysisPanel.tsx
- Create: apps/web/src/features/media/media-analysis-panel.test.tsx
- Create: tests/test_local_media_ai_providers.py
- Create: tests/test_media_analysis_store.py
- Create: tests/test_media_analysis_jobs.py
- Create: tests/test_api_media_analysis.py
- Create: tests/test_lm_studio_media_smoke.py
- Modify: packages/domain-models/src/videobox_domain_models/jobs.py
- Modify: packages/core-engine/src/videobox_core_engine/settings.py
- Modify: packages/core-engine/src/videobox_core_engine/local_first_runtime.py
- Modify: packages/storage-abstractions/src/videobox_storage/sqlite_schema.py
- Modify: packages/storage-abstractions/src/videobox_storage/local_project_store.py
- Modify: services/api/src/videobox_api/models.py
- Modify: services/api/src/videobox_api/main.py
- Modify: services/api/src/videobox_api/orchestration.py
- Modify: services/api/src/videobox_api/routers/assets.py
- Modify: services/api/src/videobox_api/orchestration.py
- Modify: tests/conftest.py
- Modify: tests/test_test_app_factory.py
- Modify: tests/test_gemini_runtime.py
- Modify: apps/web/src/api.ts
- Modify: apps/web/src/App.tsx

### Slice 2 — Script-first proposal engine

- Create: packages/domain-models/src/videobox_domain_models/director_proposals.py
- Create: packages/core-engine/src/videobox_core_engine/script_draft_session.py
- Create: packages/core-engine/src/videobox_core_engine/media_ranking.py
- Create: packages/core-engine/src/videobox_core_engine/director_proposals.py
- Create: packages/core-engine/src/videobox_core_engine/editing_transactions.py
- Create: packages/core-engine/src/videobox_core_engine/project_asset_materializer.py
- Create: services/api/src/videobox_api/routers/director.py
- Create: tests/test_script_draft_session.py
- Create: tests/test_media_director_ranking.py
- Create: tests/test_media_director_proposals.py
- Create: tests/test_media_director_apply.py
- Create: tests/test_api_media_director.py
- Modify: packages/core-engine/src/videobox_core_engine/editing_session.py
- Modify: packages/core-engine/src/videobox_core_engine/editing_session_and_regeneration.py
- Modify: packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py
- Modify: packages/capcut-export/src/videobox_capcut_export/pycapcut_adapter.py
- Modify: packages/storage-abstractions/src/videobox_storage/media_library_store.py
- Modify: packages/storage-abstractions/src/videobox_storage/sqlite_schema.py
- Modify: packages/storage-abstractions/src/videobox_storage/local_project_store.py
- Modify: services/api/src/videobox_api/models.py
- Modify: services/api/src/videobox_api/main.py
- Modify: apps/web/src/api.ts

### Slice 3 — Director workspace

- Create: packages/domain-models/src/videobox_domain_models/director_conversation.py
- Create: packages/core-engine/src/videobox_core_engine/director_commands.py
- Create: apps/web/src/features/director/directorTypes.ts
- Create: apps/web/src/features/director/DirectorWorkspace.tsx
- Create: apps/web/src/features/director/DirectorContextBar.tsx
- Create: apps/web/src/features/director/ProposalComparisonTray.tsx
- Create: apps/web/src/features/director/ProposalCandidateCard.tsx
- Create: apps/web/src/features/director/AssetPreviewPlayer.tsx
- Create: apps/web/src/features/director/MediaReferenceBadge.tsx
- Create: apps/web/src/features/director/DirectorHistoryControls.tsx
- Create: apps/web/src/features/director/useEditingShortcuts.ts
- Create: apps/web/src/features/director/useResponsiveDirector.ts
- Create: apps/web/src/features/media/ManualMediaLibrary.tsx
- Create: apps/web/src/features/director/director-workspace.test.tsx
- Create: apps/web/src/features/director/asset-preview-player.test.tsx
- Create: apps/web/src/features/director/media-reference-badge.test.tsx
- Create: apps/web/src/features/director/director-history-controls.test.tsx
- Create: apps/web/src/features/director/editing-shortcuts.test.tsx
- Create: apps/web/src/features/director/responsive-director.test.tsx
- Create: apps/web/src/features/media/manual-media-library.test.tsx
- Create: tests/test_director_conversation.py
- Create: tests/test_director_commands.py
- Create: tests/test_real_local_media_director_e2e.py
- Modify: apps/web/src/api.ts
- Modify: apps/web/src/App.tsx
- Modify: apps/web/src/styles.css
- Modify: apps/web/src/api.test.ts
- Modify: apps/web/src/app.test.tsx
- Modify: services/api/src/videobox_api/routers/director.py
- Modify: services/api/src/videobox_api/models.py
- Modify: packages/storage-abstractions/src/videobox_storage/sqlite_schema.py
- Modify: packages/storage-abstractions/src/videobox_storage/local_project_store.py
- Modify: scripts/dev-fast-path.ps1
- Modify: docs/development-fast-path.ko.md
- Modify: docs/implementation-plan.ko.md
- Modify: docs/development-status-2026-06-29.ko.md

---

## Slice 1 — Local media intelligence foundation

### Task 1: local-only runtime 경계와 deterministic test guard

**Files:**

- Modify: packages/core-engine/src/videobox_core_engine/settings.py
- Create: packages/core-engine/src/videobox_core_engine/local_only_runtime.py
- Modify: services/api/src/videobox_api/main.py
- Modify: services/api/src/videobox_api/orchestration.py
- Modify: tests/conftest.py
- Modify: tests/test_test_app_factory.py
- Modify: tests/test_ai_provider_routing.py
- Modify: tests/test_gemini_runtime.py
- Test: tests/test_local_media_ai_providers.py

- [x] **Step 1: 외부 host와 Gemini fallback을 재현하는 RED test 작성**

~~~python
def test_local_runtime_rejects_non_lm_studio_loopback() -> None:
    with pytest.raises(ValueError, match="127.0.0.1:1234"):
        LocalOpenAICompatibleRuntimeConfig(base_url="https://example.com/v1")

def test_local_failure_never_calls_external_provider(fake_local, forbidden_external) -> None:
    runtime = LocalOnlyStructuredRuntime(local_provider=fake_local)
    with pytest.raises(LocalOnlyStructuredGenerationError):
        runtime.generate(task_type=LLMTaskType.SCENE_PLANNING, prompt="대본", response_schema=SCHEMA)
    assert forbidden_external.calls == []
~~~

- [x] **Step 2: RED 확인**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_local_media_ai_providers.py tests/test_ai_provider_routing.py tests/test_gemini_runtime.py tests/test_test_app_factory.py

Expected: 외부 URL이 허용되거나 local failure 뒤 Gemini가 호출되어 FAIL.

- [x] **Step 3: local-only runtime과 socket deny fixture 구현**

LocalOpenAICompatibleRuntimeConfig는 scheme=http, hostname=127.0.0.1, port=1234, path=/v1만 허용한다. local_only_runtime.py에 LocalOnlyStructuredRuntime을 만들고 create_app 기본 wiring은 GeminiRESTStructuredProvider를 생성하지 않고 이 runtime을 사용한다. local_first_runtime.py는 과거 저장 데이터와 직접 import 호환 테스트를 위해 유지하지만 create_app과 자동 pipeline에서 더 이상 wiring하지 않는다. 호환용 Gemini key CRUD endpoint도 즉시 삭제하지 않지만 Director와 기존 자동 pipeline에서 호출되지 않게 한다.

tests/conftest.py의 autouse fixture는 socket.socket.connect와 socket.create_connection을 실패시키고, live_lmstudio marker가 명시된 test만 127.0.0.1:1234를 허용한다.

~~~python
@pytest.fixture(autouse=True)
def deny_unexpected_network(monkeypatch, request):
    live = request.node.get_closest_marker("live_lmstudio") is not None
    original_create_connection = socket.create_connection
    original_socket_connect = socket.socket.connect
    def allowed(address):
        host, port = address[0], int(address[1])
        return live and host == "127.0.0.1" and port == 1234
    def guarded_create_connection(address, *args, **kwargs):
        if allowed(address):
            return original_create_connection(address, *args, **kwargs)
        raise AssertionError(f"Unexpected network connection: {address}")
    def guarded_socket_connect(sock, address):
        if allowed(address):
            return original_socket_connect(sock, address)
        raise AssertionError(f"Unexpected network connection: {address}")
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
    monkeypatch.setattr(socket.socket, "connect", guarded_socket_connect)
~~~

- [x] **Step 4: GREEN 확인**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_local_media_ai_providers.py tests/test_ai_provider_routing.py tests/test_gemini_runtime.py tests/test_test_app_factory.py

Expected: PASS, external provider call count 0.

- [x] **Step 5: 커밋**

~~~powershell
git add packages/core-engine/src/videobox_core_engine/settings.py packages/core-engine/src/videobox_core_engine/local_only_runtime.py packages/core-engine/src/videobox_core_engine/local_first_runtime.py services/api/src/videobox_api/main.py services/api/src/videobox_api/orchestration.py tests/conftest.py tests/test_test_app_factory.py tests/test_ai_provider_routing.py tests/test_gemini_runtime.py tests/test_local_media_ai_providers.py
git commit -m "refactor: enforce local-only ai runtime"
~~~

### Task 2: Vision, embedding, capability preflight provider

**Files:**

- Create: packages/provider-interfaces/src/videobox_provider_interfaces/vision.py
- Create: packages/provider-interfaces/src/videobox_provider_interfaces/embeddings.py
- Create: packages/provider-interfaces/src/videobox_provider_interfaces/lm_studio.py
- Modify: packages/provider-interfaces/src/videobox_provider_interfaces/__init__.py
- Modify: packages/core-engine/src/videobox_core_engine/settings.py
- Test: tests/test_local_media_ai_providers.py

- [x] **Step 1: provider protocol RED test 작성**

~~~python
def test_vision_request_is_bounded_and_structured(fake_transport) -> None:
    provider = LMStudioVisionProvider(transport=fake_transport, model_name="vision-model")
    response = provider.analyze_images(
        VisionAnalysisRequest(prompt="태그", images=(FRAME,), response_schema=TAG_SCHEMA)
    )
    request = fake_transport.requests[0]
    assert len(request["messages"][0]["content"]) == 2
    assert request["response_format"]["type"] == "json_schema"
    assert response.output_data["summary"] == "사무실 장면"

def test_embedding_uses_fifteen_second_timeout(fake_transport) -> None:
    LMStudioEmbeddingProvider(fake_transport, "embedding-model").embed(
        EmbeddingRequest(texts=("한국어 대본",))
    )
    assert fake_transport.calls[0].timeout_seconds == 15
~~~

- [x] **Step 2: RED 확인**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_local_media_ai_providers.py

Expected: vision, embeddings, lm_studio module import failure.

- [x] **Step 3: 정확한 protocol과 adapter 구현**

~~~python
class VisionProvider(Protocol):
    def analyze_images(self, request: VisionAnalysisRequest) -> VisionAnalysisResponse: ...

class EmbeddingProvider(Protocol):
    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse: ...

@dataclass(frozen=True, slots=True)
class LMStudioCapabilityProfile:
    vision_model: str
    text_model: str
    embedding_model: str
    structured_json: bool
    loaded_model_keys: tuple[str, ...]
~~~

LMStudio transport는 redirect handler를 금지하고 요청 URL을 매번 allowlist로 재검증한다. capability preflight는 loaded state와 native capability를 확인한다. Vision request는 최대 6 image, image당 long edge 768px와 encoded 1.5MiB, timeout 120초를 강제한다. Embedding timeout은 15초다.

Vision JSON schema는 place, action, time_of_day, weather, people_objects, emotion, mood, topic_links, scene, color_tone, camera, season, country_region layer와 summary, confidence, review_reasons를 고정한다. provider가 임의 필드를 추가하거나 필수 layer를 문자열 하나로 뭉개면 schema failure로 처리한다.

- [x] **Step 4: timeout, redirect, oversized image, unloaded model test GREEN**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_local_media_ai_providers.py

Expected: PASS. resource/model unavailable은 blocked code, schema/JSON 오류는 failed code.

- [x] **Step 5: 커밋**

~~~powershell
git add packages/provider-interfaces packages/core-engine/src/videobox_core_engine/settings.py tests/test_local_media_ai_providers.py
git commit -m "feat: add bounded lm studio media providers"
~~~

### Task 3: durable MEDIA_ANALYSIS schema와 state machine

**Files:**

- Create: packages/domain-models/src/videobox_domain_models/media_analysis.py
- Modify: packages/domain-models/src/videobox_domain_models/jobs.py
- Modify: packages/domain-models/src/videobox_domain_models/__init__.py
- Modify: packages/storage-abstractions/src/videobox_storage/sqlite_schema.py
- Modify: packages/storage-abstractions/src/videobox_storage/local_project_store.py
- Test: tests/test_media_analysis_store.py

- [x] **Step 1: 상태 전이와 restart recovery RED test 작성**

~~~python
def test_media_analysis_persists_retry_and_recovers_orphan(tmp_path) -> None:
    store = LocalProjectStore(tmp_path)
    job = store.create_media_analysis(
        project_id=PROJECT_ID,
        asset_id=ASSET_ID,
        idempotency_key="sha:profile",
        cache_key="cache-v1",
    )
    claimed = store.claim_media_analysis(project_id=PROJECT_ID, analysis_id=job["analysis_id"])
    assert claimed["status"] == "running"
    recovered = store.recover_orphaned_media_analysis_jobs(project_id=PROJECT_ID)
    assert recovered[0]["status"] == "queued"
    assert recovered[0]["attempt"] == 1
~~~

- [x] **Step 2: RED 확인**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_media_analysis_store.py

Expected: table 또는 create_media_analysis 부재로 FAIL.

- [x] **Step 3: domain과 SQLite migration 구현**

MediaAnalysisStatus는 queued, running, succeeded, needs_review, blocked, failed, cancelled를 가진다. media_analysis_runs는 analysis_id, asset_id, idempotency_key UNIQUE, cache_key, status, attempt, progress_percent, error_code, error_message, next_retry_at, cancel_requested, result_json, created_at, updated_at을 저장한다. media_scene_windows와 media_embeddings는 analysis_id/source_sha256/profile_hash를 연결한다.

LocalProjectStore에 create_media_analysis, claim_media_analysis, complete_media_analysis, mark_media_analysis_blocked, fail_media_analysis, request_media_analysis_cancel, recover_orphaned_media_analysis_jobs를 추가한다. 완료·cancelled record에는 늦은 result를 덮어쓰지 않는다.

- [x] **Step 4: 중복·상태 전이·restart·migration GREEN**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_media_analysis_store.py

Expected: PASS. 같은 idempotency key는 동일 analysis를 반환하며 duplicate row가 생기지 않음.

- [x] **Step 5: 커밋**

~~~powershell
git add packages/domain-models packages/storage-abstractions tests/test_media_analysis_store.py
git commit -m "feat: persist durable media analysis jobs"
~~~

### Task 4: FFmpeg probe, cache key, quality gate, deterministic dispatcher

**Files:**

- Create: packages/core-engine/src/videobox_core_engine/media_probe.py
- Create: packages/core-engine/src/videobox_core_engine/media_analysis.py
- Test: tests/test_media_analysis_jobs.py
- Modify: packages/storage-abstractions/src/videobox_storage/local_project_store.py

- [x] **Step 1: extraction budget와 cancel-late-result RED test 작성**

~~~python
def test_probe_never_emits_more_than_six_bounded_frames(fake_ffmpeg) -> None:
    result = FFmpegMediaProbe(fake_ffmpeg).probe(VIDEO)
    assert len(result.frames) <= 6
    assert all(frame.long_edge_px <= 768 for frame in result.frames)
    assert all(frame.encoded_size_bytes <= 1_500_000 for frame in result.frames)

def test_cancelled_job_discards_late_vision_result(service, blocking_vision) -> None:
    job = service.enqueue_analysis(project_id=PROJECT_ID, asset_id=ASSET_ID)
    service.cancel_analysis(project_id=PROJECT_ID, analysis_id=job.analysis_id)
    blocking_vision.release({"summary": "late"})
    assert service.get_analysis(PROJECT_ID, job.analysis_id).result is None
~~~

- [x] **Step 2: RED 확인**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_media_analysis_jobs.py

Expected: media_probe/media_analysis import failure.

- [x] **Step 3: probe와 service 구현**

FFmpegMediaProbe는 duration, codec, resolution, aspect ratio, scene boundaries와 최대 6 representative frames를 만든다. subprocess timeout은 60초다. MediaAnalysisService는 concurrency 1 dispatcher를 사용하고 stage 사이 cancel flag를 확인한다. retry는 fake clock 기준 최대 2회, 5초/30초 backoff다.

cache key는 다음 순서의 canonical JSON SHA-256이다.

~~~python
{
    "source_sha256": source_sha256,
    "extractor_version": extractor_version,
    "ffmpeg_version": ffmpeg_version,
    "model_key": profile.model_key,
    "model_variant": profile.variant,
    "quantization": profile.quantization,
    "prompt_version": TAG_PROMPT_VERSION,
    "schema_version": TAG_SCHEMA_VERSION,
}
~~~

quality gate는 JSON schema, 최소 tag layer 수, scene window bounds, confidence를 검사하고 기준 미달을 needs_review로 저장한다. source SHA 변경·삭제는 tags, embedding, preview, proposal index revision을 stale로 만든다.

asset 삭제 시 derived frame/preview cache를 즉시 삭제한다. source가 외부에서 사라지면 기존 history와 analysis provenance는 보존하되 새 proposal/apply를 막는다. 사용되지 않은 stale cache는 fake clock으로 검증 가능한 30일 retention 뒤 prune한다.

- [x] **Step 4: duplicate, retry, cancel, cache invalidation GREEN**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_media_analysis_jobs.py tests/test_media_analysis_store.py

Expected: PASS, 실제 sleep 없이 fake clock으로 완료.

- [x] **Step 5: 커밋**

~~~powershell
git add packages/core-engine/src/videobox_core_engine/media_probe.py packages/core-engine/src/videobox_core_engine/media_analysis.py packages/storage-abstractions/src/videobox_storage/local_project_store.py tests/test_media_analysis_jobs.py
git commit -m "feat: analyze local media with recoverable jobs"
~~~

### Task 5: analysis API, batch ingest 연결, 검수 UI

**Files:**

- Create: services/api/src/videobox_api/routers/media_analysis.py
- Create: apps/web/src/features/media/MediaAnalysisPanel.tsx
- Create: apps/web/src/features/media/media-analysis-panel.test.tsx
- Modify: services/api/src/videobox_api/models.py
- Modify: services/api/src/videobox_api/main.py
- Modify: services/api/src/videobox_api/routers/assets.py
- Modify: services/api/src/videobox_api/orchestration.py
- Modify: apps/web/src/api.ts
- Modify: apps/web/src/App.tsx
- Test: tests/test_api_media_analysis.py

- [x] **Step 1: fake provider API와 UI recovery RED test 작성**

~~~python
def test_broll_import_enqueues_fake_analysis_and_survives_reload(client, fake_vision) -> None:
    imported = client.post(f"/api/projects/{PROJECT_ID}/assets/broll-video/batch", json=PAYLOAD)
    assert imported.status_code == 201
    jobs = client.get(f"/api/projects/{PROJECT_ID}/media-analysis").json()["items"]
    assert jobs[0]["status"] in {"queued", "running", "succeeded", "needs_review"}
    assert fake_vision.calls

def test_recursive_folder_import_is_sorted_and_deduplicated(client, nested_media_directory) -> None:
    response = client.post(
        f"/api/projects/{PROJECT_ID}/assets/broll-video/batch",
        json={"source_directory": str(nested_media_directory), "recursive": True, "tags": []},
    )
    paths = [item["source_path"] for item in response.json()["assets"]]
    assert paths == sorted(set(paths))

def test_needs_review_manual_tags_become_searchable(client) -> None:
    response = client.patch(
        f"/api/projects/{PROJECT_ID}/media-analysis/{ANALYSIS_ID}/review",
        json={"tags": {"place": ["서울"], "action": ["걷기"]}},
    )
    assert response.json()["status"] == "succeeded"
~~~

- [x] **Step 2: RED 확인**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_api_media_analysis.py

Run: npm --prefix apps/web test -- src/features/media/media-analysis-panel.test.tsx

Expected: endpoint/component 부재로 FAIL.

- [x] **Step 3: API 구현**

다음 endpoint를 추가한다.

~~~text
POST   /api/projects/{project_id}/media-analysis
GET    /api/projects/{project_id}/media-analysis
GET    /api/projects/{project_id}/media-analysis/{analysis_id}
POST   /api/projects/{project_id}/media-analysis/{analysis_id}/cancel
POST   /api/projects/{project_id}/media-analysis/{analysis_id}/retry
PATCH  /api/projects/{project_id}/media-analysis/{analysis_id}/review
GET    /api/projects/{project_id}/assets/{asset_id}/analysis-preview
~~~

create_app은 vision_provider, embedding_provider, media_probe, analysis_dispatcher 주입점을 제공한다. tests/conftest.py의 deterministic factory가 모든 API test에서 fake provider와 synchronous deterministic queue를 사용한다. batch asset 등록 성공은 분석 실패와 분리해 유지한다.

batch directory import는 recursive=true일 때 지원 확장자를 하위 폴더까지 deterministic sort로 찾고 resolved path와 content SHA로 중복을 제거한다. recursive=false는 기존 한 단계 동작을 유지한다. response에는 등록 asset과 analysis job을 함께 반환하되 한 파일 실패가 이미 성공한 다른 등록을 롤백하지 않는다.

- [x] **Step 4: UI 구현**

MediaAnalysisPanel은 파일별 progress, queue_position, queued/running/needs_review/blocked/error, cancel/retry, preview, manual tag form을 표시한다. 분석 실패 중에도 기존 편집기는 비활성화하지 않는다. App.tsx에는 panel mount와 selected project/asset callback만 추가한다.

- [x] **Step 5: focused GREEN과 커밋**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_api_media_analysis.py tests/test_media_analysis_jobs.py

Run: npm --prefix apps/web test -- src/features/media/media-analysis-panel.test.tsx src/api.test.ts

Expected: PASS.

~~~powershell
git add services/api apps/web/src packages/storage-abstractions tests/test_api_media_analysis.py
git commit -m "feat: connect media analysis api and review ui"
~~~

### Task 6: Slice 1 live LM Studio smoke와 release gate

**Files:**

- Create: tests/test_lm_studio_media_smoke.py
- Modify: pyproject.toml
- Modify: docs/implementation-plan.ko.md
- Modify: docs/development-status-2026-06-29.ko.md

- [x] **Step 1: opt-in live smoke 작성**

~~~python
@pytest.mark.live_lmstudio
def test_live_vision_embedding_and_semantic_lookup(live_profile, sample_frame) -> None:
    tags = live_profile.vision.analyze_images(build_request(sample_frame))
    vector = live_profile.embedding.embed(EmbeddingRequest(texts=(tags.output_data["summary"],)))
    assert tags.output_data["tags"]
    assert len(vector.vectors) == 1
    assert all(math.isfinite(value) for value in vector.vectors[0])
    assert live_profile.external_provider_calls == 0
~~~

env VIDEOBOX_RUN_LM_STUDIO_MEDIA_SMOKE가 없으면 skip한다. Slice 1 release 실행에서는 env를 켜고 strict capability preflight를 통과한 실제 local profile의 PASS가 필요하다. 이 gate에서 SKIP은 성공으로 세지 않는다. 모델 이름이나 일반 `/v1/models` 항목만으로 capability를 추정하지 않는다.

- [x] **Step 2: focused와 live smoke 실행**

~~~powershell
.venv\Scripts\python.exe -m pytest -q tests/test_local_media_ai_providers.py tests/test_media_analysis_store.py tests/test_media_analysis_jobs.py tests/test_api_media_analysis.py
$env:VIDEOBOX_RUN_LM_STUDIO_MEDIA_SMOKE='1'
.venv\Scripts\python.exe -m pytest -q tests/test_lm_studio_media_smoke.py -m live_lmstudio
Remove-Item Env:VIDEOBOX_RUN_LM_STUDIO_MEDIA_SMOKE
~~~

Expected: focused PASS, live test 1 PASS, external provider call 0.

- [x] **Step 3: 전체 회귀 실행**

~~~powershell
.venv\Scripts\python.exe -m pytest -q
npm --prefix apps/web test
npm --prefix apps/web run build
git diff --check
git status --short
~~~

Expected: 전부 exit 0. intentional ErrorBoundary stderr는 기존 허용 범위를 넘지 않음.

- [x] **Step 4: SSOT에 실제 수치와 evidence 기록**

구현 완료 HEAD, test totals, live profile key/variant, 분석 sample SHA, external call 0, artifact path를 기록한다. successful opt-in run은 Git-ignored `artifacts/lm-studio-media-smoke/live-media-success.json`(또는 `VIDEOBOX_LM_STUDIO_SMOKE_ARTIFACT_ROOT`)에 exact requested endpoint/call count, profile, trace를 durable evidence로 쓴다. blocked/skip run은 이 success artifact를 쓰지 않는다. 모델명은 현재 PC smoke evidence로만 기록하고 배포 default로 고정하지 않는다.

- [x] **Step 5: Slice 1 closeout commit/push**

~~~powershell
git add pyproject.toml tests/test_lm_studio_media_smoke.py docs/implementation-plan.ko.md docs/development-status-2026-06-29.ko.md
git commit -m "test: verify local media intelligence slice"
git push
~~~

---

## Slice 2 — Script-first proposal engine

### Task 7: narration 없는 script draft session

**Files:**

- Create: packages/core-engine/src/videobox_core_engine/script_draft_session.py
- Create: tests/test_script_draft_session.py
- Modify: services/api/src/videobox_api/models.py
- Modify: services/api/src/videobox_api/routers/editing_session.py
- Modify: services/api/src/videobox_api/orchestration.py
- Modify: packages/core-engine/src/videobox_core_engine/local_pipeline.py
- Modify: packages/storage-abstractions/src/videobox_storage/local_project_store.py
- Test: tests/test_script_draft_session.py

- [x] **Step 1: script-only RED test 작성**

~~~python
def test_script_only_project_creates_provisional_session(client, script_asset_id) -> None:
    response = client.post(
        f"/api/projects/{PROJECT_ID}/editing-sessions/from-script",
        json={"script_asset_id": script_asset_id},
    )
    session = response.json()
    assert response.status_code == 201
    assert session["timing_source"] == "provisional_script"
    assert [item["caption_text"] for item in session["segments"]] == SCRIPT_SENTENCES
    assert all(item["end_sec"] > item["start_sec"] for item in session["segments"])
~~~

- [x] **Step 2: RED 확인**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_script_draft_session.py

Expected: `videobox_core_engine.script_draft_session` 부재로 FAIL. 원 계획의 `tests/test_api_media_director.py`는 저장소에 존재하지 않아 API E2E를 새 Task 7 테스트 파일에 함께 둔다.

- [x] **Step 3: deterministic provisional segmentation 구현**

빈 줄, 문장 종결부호, max character budget 순으로 구간을 나눈다. 시간은 Korean character count를 고정 speech-rate로 환산하고 최소 2초를 보장한다. session에 timing_source=provisional_script와 narration_alignment_required=true를 저장한다. 나레이션 ingest/alignment 성공 시 동일 source_script_segment_id를 사용해 실제 bounds로 교체하고 proposal을 stale 처리한다.

- [x] **Step 4: API 및 reload GREEN**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_script_draft_session.py tests/test_editing_session.py tests/test_transcript_alignment.py

Expected: PASS, restart 뒤 provisional flag와 segment IDs 유지.

- [x] **Step 5: 커밋**

~~~powershell
git add packages/core-engine/src/videobox_core_engine/script_draft_session.py packages/core-engine/src/videobox_core_engine/local_pipeline.py packages/storage-abstractions/src/videobox_storage/local_project_store.py services/api/src/videobox_api tests/test_script_draft_session.py
git commit -m "feat: create provisional sessions from scripts"
~~~

### Task 8: immutable proposal domain, persistence, ranking

**Files:**

- Create: packages/domain-models/src/videobox_domain_models/director_proposals.py
- Create: packages/core-engine/src/videobox_core_engine/media_ranking.py
- Create: packages/core-engine/src/videobox_core_engine/director_proposals.py
- Modify: packages/storage-abstractions/src/videobox_storage/sqlite_schema.py
- Modify: packages/storage-abstractions/src/videobox_storage/local_project_store.py
- Test: tests/test_media_director_ranking.py
- Test: tests/test_media_director_proposals.py

- [ ] **Step 1: ranking과 immutable proposal RED test 작성**

~~~python
def test_equal_scores_use_stable_asset_id_tie_break() -> None:
    ranked = rank_candidates(SEGMENT, [asset("z"), asset("a")], weights=WEIGHTS)
    assert [item.asset_id for item in ranked] == ["a", "z"]

def test_excluded_creator_is_ineligible_even_when_favorite() -> None:
    ranked = rank_candidates(
        SEGMENT,
        [asset("a", creator="제외 제작자", favorite=True), asset("b")],
        preferences={"exclude_creator": ["제외 제작자"]},
    )
    assert [item.asset_id for item in ranked] == ["b"]

def test_proposal_persists_revision_and_stable_reference_codes(store) -> None:
    proposal = create_proposal(base_session_revision=4, asset_index_revision=9, candidates=CANDIDATES)
    store.save_director_proposal(PROJECT_ID, proposal)
    loaded = store.get_director_proposal(PROJECT_ID, proposal.proposal_id)
    assert loaded.candidates[0].visible_reference_code == "P01-B-01"
    assert loaded.base_session_revision == 4
~~~

- [ ] **Step 2: RED 확인**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_media_director_ranking.py tests/test_media_director_proposals.py

Expected: module/table 부재로 FAIL.

- [ ] **Step 3: score와 proposal contract 구현**

Score는 semantic similarity, structured tags, duration/aspect, explicit conditions, favorite/recent, repetition/diversity, availability/license eligibility의 named components를 저장한다. embedding unavailable이면 normalized Korean tag/synonym lexical score를 사용한다. favorite는 repetition penalty를 제거하지 않는다. BGM index는 mood, energy, genre, vocal_presence, recommended_use, duration, license를, SFX index는 action_event, intensity, mood, recommended_use, duration, license를 canonical metadata로 정규화한다.

director_preferences table은 project-scoped pin_asset, exclude_asset, exclude_creator, exclude_tag를 저장한다. ranking은 exclude를 eligibility 단계에서 제거하고 pin을 explicit preference component로 반영하되 license/availability gate를 우회하지 않는다.

DirectorProposal은 proposal_id, revision_code, base_session_revision, asset_index_revision, status, target_segment_ids, candidates, diff, expires_at을 가진다. Candidate는 candidate_id, visible_reference_code, media_type, asset_id/library_asset_id, reason_chips, availability, review_status, preview_uri, controls, expected_content_sha256, media_revision을 가진다.

- [ ] **Step 4: persistence, expiry, stale, fallback GREEN**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_media_director_ranking.py tests/test_media_director_proposals.py

Expected: PASS. 같은 input/profile은 deterministic candidate order와 code를 반환.

- [ ] **Step 5: 커밋**

~~~powershell
git add packages/domain-models/src/videobox_domain_models/director_proposals.py packages/core-engine/src/videobox_core_engine/media_ranking.py packages/core-engine/src/videobox_core_engine/director_proposals.py packages/storage-abstractions tests/test_media_director_ranking.py tests/test_media_director_proposals.py
git commit -m "feat: persist ranked director proposals"
~~~

### Task 9: proposal API, numbering, preflight diff, refresh

**Files:**

- Create: services/api/src/videobox_api/routers/director.py
- Modify: services/api/src/videobox_api/models.py
- Modify: services/api/src/videobox_api/main.py
- Modify: apps/web/src/api.ts
- Test: tests/test_api_media_director.py
- Modify: apps/web/src/api.test.ts

- [ ] **Step 1: API RED test 작성**

~~~python
def test_proposal_does_not_mutate_session_until_apply(client) -> None:
    before = client.get(SESSION_URL).json()
    proposal = client.post(PROPOSALS_URL, json={"session_id": SESSION_ID}).json()
    after = client.get(SESSION_URL).json()
    assert after == before
    assert proposal["status"] == "ready"
    assert proposal["candidates"][0]["visible_reference_code"].startswith("P")
~~~

- [ ] **Step 2: RED 확인**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_api_media_director.py

Expected: 404.

- [ ] **Step 3: API 구현**

~~~text
POST /api/projects/{project_id}/director/proposals
GET  /api/projects/{project_id}/director/proposals/{proposal_id}
POST /api/projects/{project_id}/director/proposals/{proposal_id}/preflight
POST /api/projects/{project_id}/director/proposals/{proposal_id}/refresh
GET  /api/projects/{project_id}/director/preferences
PUT  /api/projects/{project_id}/director/preferences
~~~

preflight response는 add/replace/remove placement, scene controls, gain/ducking, caption 영향과 선택 scope를 반환한다. source/index/session revision 또는 expiry가 달라지면 409 stale_proposal과 refresh action을 반환한다. B-03과 P12-B-03가 동시에 가능한 자연어는 자동 적용하지 않고 disambiguation candidates를 반환한다.

- [ ] **Step 4: API client와 contract GREEN**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_api_media_director.py

Run: npm --prefix apps/web test -- src/api.test.ts

Expected: PASS, create/refresh/preflight payload가 exact revision을 전달.

- [ ] **Step 5: 커밋**

~~~powershell
git add services/api/src/videobox_api/routers/director.py services/api/src/videobox_api/models.py services/api/src/videobox_api/main.py apps/web/src/api.ts apps/web/src/api.test.ts tests/test_api_media_director.py
git commit -m "feat: expose immutable director proposals"
~~~

### Task 10: candidate preview와 project asset materializer

**Files:**

- Create: packages/core-engine/src/videobox_core_engine/project_asset_materializer.py
- Modify: services/api/src/videobox_api/routers/director.py
- Modify: services/api/src/videobox_api/routers/media_library.py
- Modify: packages/storage-abstractions/src/videobox_storage/media_library_store.py
- Test: tests/test_media_director_apply.py
- Modify: tests/test_api_media_library.py

- [ ] **Step 1: exact preview와 materialize failure RED test 작성**

~~~python
def test_preview_returns_the_proposed_scene_controls(client) -> None:
    response = client.get(f"{PROPOSAL_URL}/candidates/{CANDIDATE_ID}/preview")
    assert response.status_code == 200
    assert response.headers["X-VideoBox-In-Sec"] == "12.5"
    assert response.headers["X-VideoBox-Out-Sec"] == "17.0"

def test_bundle_preflight_fails_before_session_mutation_when_asset_missing(service) -> None:
    before = service.get_editing_session(PROJECT_ID, SESSION_ID)
    with pytest.raises(AssetMaterializationError):
        service.materialize_candidates(PROJECT_ID, [MISSING_CANDIDATE])
    assert service.get_editing_session(PROJECT_ID, SESSION_ID) == before
~~~

- [ ] **Step 2: RED 확인**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_media_director_apply.py tests/test_api_media_library.py

Expected: preview endpoint/materializer 부재로 FAIL.

- [ ] **Step 3: materialize service 추출**

기존 router의 snapshot_verified_asset, license snapshot, project register, recent usage 로직을 ProjectAssetMaterializer로 옮긴다. 모든 candidate source를 먼저 hash 검증하고 project staging에 복사한 뒤 등록한다. 실패하면 editing session은 건드리지 않는다. 이미 같은 library asset SHA가 materialize된 경우 기존 project asset을 재사용한다.

- [ ] **Step 4: preview endpoint 구현과 GREEN**

GET .../candidates/{candidate_id}/preview는 verified source snapshot 또는 project-local asset을 스트리밍하고 exact in/out/controls를 header와 proposal payload에 유지한다. audio는 서버에서 autoplay 상태를 만들지 않는다.

Run: .venv\Scripts\python.exe -m pytest -q tests/test_media_director_apply.py tests/test_api_media_library.py

Expected: PASS.

- [ ] **Step 5: 커밋**

~~~powershell
git add packages/core-engine/src/videobox_core_engine/project_asset_materializer.py packages/storage-abstractions/src/videobox_storage/media_library_store.py services/api/src/videobox_api/routers/director.py services/api/src/videobox_api/routers/media_library.py tests/test_media_director_apply.py tests/test_api_media_library.py
git commit -m "feat: materialize and preview director candidates"
~~~

### Task 11: atomic apply, named 10-step undo/redo, output freshness

**Files:**

- Create: packages/core-engine/src/videobox_core_engine/editing_transactions.py
- Modify: packages/core-engine/src/videobox_core_engine/editing_session.py
- Modify: packages/core-engine/src/videobox_core_engine/editing_session_and_regeneration.py
- Modify: services/api/src/videobox_api/routers/director.py
- Modify: services/api/src/videobox_api/models.py
- Test: tests/test_media_director_apply.py
- Modify: tests/test_editing_session.py
- Modify: tests/test_editor_timeline_mutations.py

- [ ] **Step 1: bundle apply와 10-step RED test 작성**

~~~python
def test_bundle_apply_is_one_revision_and_one_undo_action(service) -> None:
    before = service.get_editing_session(PROJECT_ID, SESSION_ID)
    applied = service.apply_proposal(PROJECT_ID, PROPOSAL_ID, CANDIDATE_IDS, before["session_revision"])
    assert applied["session_revision"] == before["session_revision"] + 1
    assert applied["undo_count"] == before["undo_count"] + 1
    restored = service.undo_editing_session(PROJECT_ID, SESSION_ID, applied["session_revision"])
    assert restored["segments"] == before["segments"]

def test_only_ten_user_actions_are_restorable(session) -> None:
    for index in range(11):
        session = apply_user_transaction(session, label=f"작업 {index}", mutations=[mutation(index)])
    assert len(session["undo_stack"]) == 10
    assert len(session["history"]) == 11
~~~

- [ ] **Step 2: RED 확인**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_media_director_apply.py tests/test_editing_session.py tests/test_editor_timeline_mutations.py

Expected: B/M/S bundle이 undo snapshot에 없거나 100개 stack 때문에 FAIL.

- [ ] **Step 3: transaction model 구현**

apply_user_transaction은 모든 mutation을 deepcopy session에 먼저 적용하고 validation이 모두 통과한 경우에만 before/after snapshot 한 건을 기록한다. action entry는 action_id, label, created_at, reversible, blocked_reason, affected_segment_ids를 가진다. 사용자 undo stack은 10개, audit history는 100개다.

proposal apply endpoint는 expected_revision, proposal base revision, asset index revision, materialized SHA를 검증하고 LocalProjectStore CAS 한 번으로 저장한다. 일부 mutation이 실패하면 session JSON/revision/history가 byte-equivalent하게 유지된다.

- [ ] **Step 4: freshness invalidation과 GREEN**

apply/undo/redo 뒤 affected timeline review approval, subtitle, preview, final render, CapCut draft의 current freshness를 false로 바꾼다. 과거 artifact row와 file은 삭제하지 않는다.

Run: .venv\Scripts\python.exe -m pytest -q tests/test_media_director_apply.py tests/test_editing_session.py tests/test_editor_timeline_mutations.py

Expected: PASS.

- [ ] **Step 5: 커밋**

~~~powershell
git add packages/core-engine/src/videobox_core_engine/editing_transactions.py packages/core-engine/src/videobox_core_engine/editing_session.py packages/core-engine/src/videobox_core_engine/editing_session_and_regeneration.py services/api/src/videobox_api tests/test_media_director_apply.py tests/test_editing_session.py tests/test_editor_timeline_mutations.py
git commit -m "feat: apply director proposals as atomic edits"
~~~

### Task 12: output hash/revision revalidation과 Slice 2 gate

**Files:**

- Modify: packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py
- Modify: packages/capcut-export/src/videobox_capcut_export/pycapcut_adapter.py
- Modify: tests/test_ffmpeg_final_renderer.py
- Modify: tests/test_pycapcut_adapter.py
- Modify: tests/test_real_starter_media_pack_e2e.py
- Modify: docs/implementation-plan.ko.md
- Modify: docs/development-status-2026-06-29.ko.md

- [ ] **Step 1: source mutation RED test 작성**

~~~python
def test_final_renderer_rejects_materialized_asset_when_content_sha256_changed(tmp_path) -> None:
    timeline = timeline_with_expected_sha(ASSET_PATH, ORIGINAL_SHA)
    ASSET_PATH.write_bytes(b"mutated")
    with pytest.raises(ValueError, match="content SHA-256"):
        renderer.render_timeline_to_mp4(timeline=timeline, output_path=tmp_path / "out.mp4")
~~~

같은 계약을 PyCapCut real adapter에 추가하고, 기존 crop/loop/pad/trim/audio controls test는 유지한다.

- [ ] **Step 2: RED 확인**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_ffmpeg_final_renderer.py tests/test_pycapcut_adapter.py

Expected: mutation을 감지하지 못해 FAIL.

- [ ] **Step 3: shared source verifier 구현**

project-local path, expected content SHA-256, media revision을 output 시작 전에 검증한다. mismatch이면 조용한 대체·재trim을 하지 않고 stale asset error를 반환한다. preview, FFmpeg, PyCapCut은 proposal apply가 저장한 동일 scene in/out/crop/loop/trim controls를 소비한다.

- [ ] **Step 4: focused/full/real pack gate**

~~~powershell
.venv\Scripts\python.exe -m pytest -q tests/test_ffmpeg_final_renderer.py tests/test_pycapcut_adapter.py tests/test_media_director_apply.py tests/test_api_media_director.py
$env:VIDEOBOX_RUN_REAL_STARTER_PACK_E2E='1'
.venv\Scripts\python.exe -m pytest -q tests/test_real_starter_media_pack_e2e.py
Remove-Item Env:VIDEOBOX_RUN_REAL_STARTER_PACK_E2E
.venv\Scripts\python.exe -m pytest -q
npm --prefix apps/web test
npm --prefix apps/web run build
~~~

Expected: 전부 PASS.

- [ ] **Step 5: SSOT, commit, push**

실제 test totals, real pack result, source mutation rejection과 commit HEAD를 기록한다.

~~~powershell
git add packages/core-engine packages/capcut-export tests docs/implementation-plan.ko.md docs/development-status-2026-06-29.ko.md
git commit -m "test: verify script-first proposal slice"
git push
~~~

---

## Slice 3 — Director workspace

### Task 13: persistent conversation과 reference command resolver

**Files:**

- Create: packages/domain-models/src/videobox_domain_models/director_conversation.py
- Create: packages/core-engine/src/videobox_core_engine/director_commands.py
- Modify: packages/storage-abstractions/src/videobox_storage/sqlite_schema.py
- Modify: packages/storage-abstractions/src/videobox_storage/local_project_store.py
- Modify: services/api/src/videobox_api/routers/director.py
- Modify: services/api/src/videobox_api/models.py
- Test: tests/test_director_conversation.py
- Test: tests/test_director_commands.py

- [ ] **Step 1: persistence와 ambiguous reference RED test 작성**

~~~python
def test_message_persists_without_editing_mutation(service) -> None:
    before = service.get_editing_session(PROJECT_ID, SESSION_ID)
    message = service.append_message(PROJECT_ID, SESSION_ID, "3번 영상 바꿔줘")
    assert message.role == "user"
    assert service.get_editing_session(PROJECT_ID, SESSION_ID) == before

def test_ambiguous_three_returns_disambiguation() -> None:
    result = resolve_director_command("3번 영상 바꿔줘", open_proposal=PROPOSAL, timeline=TIMELINE)
    assert result.status == "needs_disambiguation"
    assert {item.reference_code for item in result.options} == {"P12-B-03", "B-03"}
~~~

- [ ] **Step 2: RED 확인**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_director_conversation.py tests/test_director_commands.py

Expected: module/table 부재로 FAIL.

- [ ] **Step 3: schema와 resolver 구현**

director_conversations와 director_messages는 project_id/session_id, role, text, proposal_id, created_at을 저장한다. unsent draft는 browser local state이고 server message가 아니다. Resolver는 explicit Pxx-B/M/S candidate, B/M/S timeline placement, currently open proposal 순으로 해석하고 둘 이상이면 disambiguation을 반환한다.

- [ ] **Step 4: refresh/restart GREEN**

Run: .venv\Scripts\python.exe -m pytest -q tests/test_director_conversation.py tests/test_director_commands.py tests/test_api_media_director.py

Expected: PASS, restart 뒤 message order와 proposal link 유지.

- [ ] **Step 5: 커밋**

~~~powershell
git add packages/domain-models/src/videobox_domain_models/director_conversation.py packages/core-engine/src/videobox_core_engine/director_commands.py packages/storage-abstractions services/api/src/videobox_api tests/test_director_conversation.py tests/test_director_commands.py
git commit -m "feat: persist director conversations and commands"
~~~

### Task 14: frontend API DTO와 pure reference/history/shortcut units

**Files:**

- Modify: apps/web/src/api.ts
- Modify: apps/web/src/api.test.ts
- Create: apps/web/src/features/director/directorTypes.ts
- Create: apps/web/src/features/director/MediaReferenceBadge.tsx
- Create: apps/web/src/features/director/DirectorHistoryControls.tsx
- Create: apps/web/src/features/director/useEditingShortcuts.ts
- Create: apps/web/src/features/director/media-reference-badge.test.tsx
- Create: apps/web/src/features/director/director-history-controls.test.tsx
- Create: apps/web/src/features/director/editing-shortcuts.test.tsx

- [ ] **Step 1: component RED test 작성**

~~~tsx
it("proposal과 timeline reference를 구분한다", () => {
  render(<MediaReferenceBadge code="P12-B-03" kind="proposal" />);
  expect(screen.getByLabelText("제안 12의 비롤 후보 3번")).toBeVisible();
});

it("한글 입력 중 Ctrl+Z를 편집 undo로 가로채지 않는다", () => {
  fireEvent.compositionStart(input);
  fireEvent.keyDown(input, { key: "z", ctrlKey: true });
  expect(onUndo).not.toHaveBeenCalled();
});
~~~

- [ ] **Step 2: RED 확인**

Run: npm --prefix apps/web test -- src/features/director/media-reference-badge.test.tsx src/features/director/director-history-controls.test.tsx src/features/director/editing-shortcuts.test.tsx

Expected: component import failure.

- [ ] **Step 3: exact DTO와 pure components 구현**

DirectorProposal, DirectorCandidate, DirectorProposalDiff, DirectorApplyScope, DirectorMessage, ApplyDirectorProposalResponse를 api.ts에 정의한다. UI-only state union은 directorTypes.ts에 둔다. EditingSessionHistoryEntry에는 action_id, label, created_at, reversible, blocked_reason를 추가한다.

useEditingShortcuts는 Ctrl/Cmd+Z, Ctrl/Cmd+Shift+Z, Ctrl/Cmd+Y를 지원하고 input, textarea, contenteditable, isComposing을 무시한다.

- [ ] **Step 4: GREEN과 build**

Run: npm --prefix apps/web test -- src/features/director src/api.test.ts

Run: npm --prefix apps/web run build

Expected: PASS.

- [ ] **Step 5: 커밋**

~~~powershell
git add apps/web/src/api.ts apps/web/src/api.test.ts apps/web/src/features/director
git commit -m "feat: add director frontend contracts"
~~~

### Task 15: Director panel, context bar, cards, preview, comparison tray

**Files:**

- Create: apps/web/src/features/director/DirectorWorkspace.tsx
- Create: apps/web/src/features/director/DirectorContextBar.tsx
- Create: apps/web/src/features/director/ProposalComparisonTray.tsx
- Create: apps/web/src/features/director/ProposalCandidateCard.tsx
- Create: apps/web/src/features/director/AssetPreviewPlayer.tsx
- Create: apps/web/src/features/director/director-workspace.test.tsx
- Create: apps/web/src/features/director/asset-preview-player.test.tsx

- [ ] **Step 1: state와 explicit apply RED test 작성**

~~~tsx
it("메시지 응답만으로 편집 상태를 변경하지 않는다", async () => {
  renderDirector({ state: "proposal_ready" });
  await user.type(screen.getByRole("textbox"), "3번 영상 교체");
  await user.click(screen.getByRole("button", { name: "보내기" }));
  expect(onApplyProposal).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "변경 적용" })).toBeVisible();
});

it("새 오디오 preview가 이전 preview를 중지하며 autoplay하지 않는다", async () => {
  render(<AssetPreviewPlayer candidates={AUDIO_CANDIDATES} />);
  expect(screen.getAllByRole("audio")[0]).not.toHaveAttribute("autoplay");
  await user.click(screen.getByRole("button", { name: "M-02 미리듣기" }));
  expect(firstAudio.pause).toHaveBeenCalled();
});
~~~

- [ ] **Step 2: RED 확인**

Run: npm --prefix apps/web test -- src/features/director/director-workspace.test.tsx src/features/director/asset-preview-player.test.tsx

Expected: component import failure.

- [ ] **Step 3: workspace state machine 구현**

상태는 script_required, idle, analysis_running, proposal_ready, applying, blocked, error다. Context bar는 segment/timecode/placement/proposal revision/draft-applied를 표시한다. Card는 reason chips, availability/license/review status와 backend reference code를 표시한다.

Comparison tray는 preflight diff를 먼저 보여주고 B-roll만, 선택 reference만, 전체 적용 scope를 제공한다. primary action은 변경 적용 하나만 둔다. 후보가 부족한 경우에만 왜 이 후보뿐인가 설명을 노출하고, pin/exclude asset/creator/tag action은 project preference API에 저장한다.

- [ ] **Step 4: preview와 accessibility GREEN**

B-roll player는 proposal in/out에서 시작하고 out에서 pause/loop한다. audio는 자동 재생하지 않고 한 번에 하나만 재생하며 backend audition_gain_db를 적용한다. 현재 narration 문맥의 solo/mute를 제공하되 timeline gain 자체를 변경하지 않는다. 모든 control은 visible focus, keyboard label, live status를 가진다.

Run: npm --prefix apps/web test -- src/features/director

Expected: PASS.

- [ ] **Step 5: 커밋**

~~~powershell
git add apps/web/src/features/director
git commit -m "feat: build director proposal workspace"
~~~

### Task 16: manual media library 추출과 AI 실패 독립성

**Files:**

- Create: apps/web/src/features/media/ManualMediaLibrary.tsx
- Create: apps/web/src/features/media/manual-media-library.test.tsx
- Modify: apps/web/src/App.tsx
- Modify: apps/web/src/api.ts
- Modify: apps/web/src/styles.css

- [ ] **Step 1: 동작 보존과 filter RED test 작성**

~~~tsx
it("Director가 blocked여도 수동 배치를 허용한다", async () => {
  render(<ManualMediaLibrary directorState="blocked" assets={ASSETS} onApply={onApply} />);
  await user.click(screen.getByRole("button", { name: "B-03 선택 구간에 배치" }));
  expect(onApply).toHaveBeenCalledTimes(1);
});

it("미리보기만으로 편집 session을 변경하지 않는다", async () => {
  render(<ManualMediaLibrary assets={ASSETS} onApply={onApply} />);
  await user.click(screen.getByRole("button", { name: "효과음 미리듣기" }));
  expect(onApply).not.toHaveBeenCalled();
});
~~~

- [ ] **Step 2: RED 확인**

Run: npm --prefix apps/web test -- src/features/media/manual-media-library.test.tsx

Expected: component import failure.

- [ ] **Step 3: 기존 media library 블록을 동작 보존 상태로 추출**

App.tsx 약 2960행의 Starter Pack library UI를 ManualMediaLibrary로 이동한다. B-roll/BGM/SFX, type, aspect, duration, analyzed, review-needed, favorite, recent filter를 제공한다. drag/drop과 action button은 모두 selected segment/range를 명시한다.

- [ ] **Step 4: materialize-before-apply와 favorite GREEN**

Global pack asset은 backend proposal/manual materialize service를 통하고, project-local B-roll은 SHA/revision을 전달한다. favorite/pin/exclude는 project scope API에 저장한다.

Run: npm --prefix apps/web test -- src/features/media/manual-media-library.test.tsx src/app.test.tsx

Expected: 기존 library 테스트와 신규 test 모두 PASS.

- [ ] **Step 5: 커밋**

~~~powershell
git add apps/web/src/features/media apps/web/src/App.tsx apps/web/src/api.ts apps/web/src/styles.css
git commit -m "refactor: extract manual media library"
~~~

### Task 17: responsive bottom sheet와 focus/IME/a11y

**Files:**

- Create: apps/web/src/features/director/useResponsiveDirector.ts
- Create: apps/web/src/features/director/responsive-director.test.tsx
- Modify: apps/web/src/features/director/DirectorWorkspace.tsx
- Modify: apps/web/src/styles.css

- [ ] **Step 1: mobile interaction RED test 작성**

~~~tsx
it("모바일 sheet가 draft를 보존하고 닫은 뒤 focus를 복귀한다", async () => {
  renderResponsiveDirector({ width: 640 });
  await user.type(screen.getByRole("textbox"), "사람 없는 영상");
  await user.keyboard("{Escape}");
  expect(openButton).toHaveFocus();
  await user.click(openButton);
  expect(screen.getByRole("textbox")).toHaveValue("사람 없는 영상");
});
~~~

- [ ] **Step 2: RED 확인**

Run: npm --prefix apps/web test -- src/features/director/responsive-director.test.tsx

Expected: hook 또는 dialog behavior 부재로 FAIL.

- [ ] **Step 3: desktop/mobile layout 구현**

Desktop은 360–420px aside와 접기 기능을 사용한다. narrow viewport는 aria-modal dialog bottom sheet, focus trap, Escape/back/close, focus return을 제공한다. 기존 1100px/640px breakpoint와 겹치지 않게 Director 전환 기준 하나를 styles.css에 정의한다. candidate tray는 full-width carousel로 바뀐다.

- [ ] **Step 4: reduced motion와 keyboard GREEN**

상태를 색상만으로 전달하지 않고 live region과 text를 사용한다. prefers-reduced-motion을 존중한다.

Run: npm --prefix apps/web test -- src/features/director

Run: npm --prefix apps/web run build

Expected: PASS.

- [ ] **Step 5: 커밋**

~~~powershell
git add apps/web/src/features/director apps/web/src/styles.css
git commit -m "feat: make director workspace responsive"
~~~

### Task 18: App integration, refresh recovery, real output E2E, release closeout

**Files:**

- Modify: apps/web/src/App.tsx
- Modify: apps/web/src/app.test.tsx
- Create: tests/test_real_local_media_director_e2e.py
- Modify: tests/test_dev_fast_path.py
- Modify: scripts/dev-fast-path.ps1
- Modify: docs/development-fast-path.ko.md
- Modify: docs/implementation-plan.ko.md
- Modify: docs/development-status-2026-06-29.ko.md

- [ ] **Step 1: App integration RED scenarios 추가**

app.test.tsx에는 다음 다섯 통합 시나리오만 추가한다. 세부 component test를 이 파일에 중복하지 않는다.

1. 새로고침 뒤 conversation, proposal, numbered references 복구
2. proposal apply가 API mutation 한 번만 호출하고 output freshness를 stale 처리
3. materialize 실패 시 editing session 불변
4. “3번 영상 교체” ambiguity에서 disambiguation card 표시
5. Director blocked/error 중에도 manual mode 동작
6. 기본 Settings에 Gemini 자동 fallback/key setup이 노출되지 않고 LM Studio capability만 표시

- [ ] **Step 2: App 연결과 focused GREEN**

DirectorWorkspace props는 다음으로 고정한다.

~~~tsx
type DirectorWorkspaceProps = {
  projectId: string;
  editingSession: EditingSession;
  selectedSegment: EditingSessionSegment | null;
  isMutationBusy: boolean;
  onSelectSegment: (segmentId: string) => void;
  onApplyProposal: (
    proposalId: string,
    candidateIds: string[],
    scope: DirectorApplyScope,
  ) => Promise<void>;
  onUndo: () => Promise<void>;
  onRedo: () => Promise<void>;
};
~~~

App은 selectedSection=editing 내부에서 workspace를 mount하고 기존 applyEditingMutation flow로 성공 session을 교체한다. proposal apply 성공 때 timeline/review/subtitle/preview/final/CapCut current 상태를 한 번에 invalidation한다. 기본 Settings 화면에서는 Gemini key management block을 제거하고 LM Studio local capability만 표시한다. Gemini CRUD API와 저장 데이터는 backward compatibility를 위해 유지하지만 사용자 자동 runtime이나 Director UI에서는 사용하지 않는다.

Run: npm --prefix apps/web test -- src/app.test.tsx src/features/director src/features/media

Expected: PASS.

- [ ] **Step 3: real media director E2E 작성**

tests/test_real_local_media_director_e2e.py는 opt-in actual Starter Pack + real FFmpeg + PyCapCut을 사용하고 AI는 deterministic fake로 유지한다. 흐름은 script ingest → B-roll analysis → B/M/S proposal → preview → explicit apply/materialize → SRT → MP4 → real draft다.

Assertions:

- timeline, FFmpeg command, draft가 같은 asset SHA와 scene in/out/crop/loop/trim을 사용
- MP4 duration과 audio stream 존재
- SRT에 편집된 한국어 caption 본문 존재
- draft_content.json에 project-local material path 존재
- source mutation 뒤 final render와 CapCut draft가 둘 다 출력 전 차단
- assetless BGM/SFX candidate는 apply 불가
- rights=unknown B-roll은 local output을 막지 않지만 MP4/CapCut output metadata와 UI에 저작권 확인 warning을 남김

- [ ] **Step 4: 전체 release gate 실행**

scripts/dev-fast-path.ps1과 docs/development-fast-path.ko.md에 media-director-focused, media-director-live-smoke, media-director-release mode를 함께 추가한다. focused는 Director backend contract와 frontend feature tests, live-smoke는 127.0.0.1:1234 capability/vision/embedding, release는 full backend/frontend/build, real media director E2E, real Starter Pack, 600초 smoke, long-form CapCut QA를 순서대로 실행한다. tests/test_dev_fast_path.py는 세 mode와 실제 verifier/test 경로가 script에 존재함을 고정한다.

~~~powershell
.venv\Scripts\python.exe -m pytest -q
npm --prefix apps/web test
npm --prefix apps/web run build
$env:VIDEOBOX_RUN_REAL_MEDIA_DIRECTOR_E2E='1'
.venv\Scripts\python.exe -m pytest -q tests/test_real_local_media_director_e2e.py
Remove-Item Env:VIDEOBOX_RUN_REAL_MEDIA_DIRECTOR_E2E
$env:VIDEOBOX_RUN_REAL_STARTER_PACK_E2E='1'
.venv\Scripts\python.exe -m pytest -q tests/test_real_starter_media_pack_e2e.py
Remove-Item Env:VIDEOBOX_RUN_REAL_STARTER_PACK_E2E
.\scripts\dev-fast-path.ps1 -Mode smoke
.\scripts\dev-fast-path.ps1 -Mode long-form-capcut-qa
git diff --check
git status --short
git rev-list --left-right --count '@{upstream}...HEAD'
~~~

Expected: 모든 자동 gate PASS. CapCut Desktop을 자동으로 열지 않으며 human acceptance와 구분한다. artifacts와 local CapCut output은 evidence로 보존하고 stage하지 않는다.

- [ ] **Step 5: release audit 6개 gate와 SSOT closeout**

docs/superpowers/plans/2026-07-13-release-audit-protocol.ko.md의 코드리뷰, 계획 gap, reverse trace, 실제 동작, 문서 지침, 찌꺼기 파일 gate를 적용한다. docs/implementation-plan.ko.md와 development status에는 실제 HEAD, test totals, live smoke/e2e artifact, 자동 검증 범위, 남은 human acceptance를 기록한다.

- [ ] **Step 6: 최종 commit/push**

~~~powershell
git add apps/web packages services tests scripts/dev-fast-path.ps1 docs
git commit -m "feat: complete local media director"
git push
~~~

---

## 3. 각 Slice 완료 기준

### Slice 1

- normal pytest에서 socket/network deny가 적용된다.
- create_app contract/E2E는 deterministic fake vision/text/embedding과 fake queue/clock을 사용한다.
- live LM Studio smoke는 strict preflight를 통과한 실제 local profile에서 PASS해야 하며 Gemini/external call은 0이어야 한다.
- B-roll import 뒤 durable analysis가 reload/restart/cancel/retry를 견딘다.
- needs_review 결과는 자동 상위 추천에 사용되지 않고 수동 tag 검수 뒤 searchable하다.

### Slice 2

- script-only project가 provisional session과 proposal을 만든다.
- proposal 생성·대화만으로 editing session이 바뀌지 않는다.
- stale revision/index/source/expiry와 assetless media가 apply를 차단한다.
- bundle apply는 session revision 1회, named history 1개, undo action 1개다.
- materialize/hash 실패는 editing session을 byte-equivalent하게 유지한다.
- preview, FFmpeg, CapCut이 같은 media controls와 content SHA를 사용한다.

### Slice 3

- Desktop right panel과 mobile bottom sheet가 동일 conversation/proposal truth를 사용한다.
- AI와 manual mode가 같은 mutation model을 사용하되 서로의 실패에 종속되지 않는다.
- B/M/S candidate와 timeline reference가 화면·대화·API에서 혼동되지 않는다.
- 최근 10개 사용자 action이 restart 뒤 undo/redo되고 output freshness가 정확히 무효화된다.
- frontend 전체, backend 전체, live LM Studio, real Starter Pack, real media director E2E, 600초 Korean smoke, long-form CapCut QA가 모두 green이다.

## 4. 계획 자체 self-review

### Spec coverage

| 승인 설계 구간 | 구현 Task |
| --- | --- |
| §1 local-only 결정과 목표 | Task 1–2, 6 |
| §2 script-first/수동 제작 흐름 | Task 5, 7–12, 16 |
| §3 AI 디렉터 UX | Task 13–18 |
| §4 B-roll/BGM/SFX 자산 인텔리전스 | Task 2–6, 8–12 |
| §5 P/B/M/S 번호와 직접 편집 | Task 9, 13–16 |
| §6 persistent 10-step undo/redo | Task 11, 14, 17–18 |
| §7 local failure/cache/recovery | Task 1–6, 10–12 |
| §8 deterministic/live/real output 검증 | Task 6, 12, 18 |
| §9 비목표와 범위 제한 | §0 실행 결정, Slice 3 file boundary |
| §10 세 implementation slice | Task 1–6, Task 7–12, Task 13–18 |

- Reverse path: source asset → analysis SHA/profile → proposal candidate → materialized project asset → editing transaction → SRT/FFmpeg/CapCut까지 같은 identity와 controls를 추적한다.
- Test isolation: normal tests는 socket guard와 fake provider/queue/clock을 사용하고 live/evidence test만 opt-in이다.
- UI scope: full NLE, 새 router/state library, App 전체 rewrite를 포함하지 않는다.
- Naming consistency: backend는 DirectorProposal/DirectorCandidate/DirectorApplyScope, frontend DTO도 같은 이름을 사용한다. 파일 경로는 apps/web/src/features/director로 통일한다.
- No external fallback: Gemini key CRUD 호환성은 별도지만 자동 runtime path에서는 호출되지 않는다.
- Artifact policy: artifacts와 local CapCut output은 preserve-evidence이고 Git stage 대상이 아니다.
