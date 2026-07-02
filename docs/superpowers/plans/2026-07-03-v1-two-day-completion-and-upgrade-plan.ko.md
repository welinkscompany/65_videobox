# VideoBox V1 Two-Day Completion and Upgrade Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 2일 안에 유튜브 데모가 가능한 1차 버전을 완성하기 위해, 이미 살아 있는 엔진을 다시 넓히지 않고 demo-critical path만 정확하게 닫는다.

**Architecture:** 현재 제품의 실제 코어는 `timeline -> review snapshot -> editing session -> partial regeneration -> subtitle/preview/export` 체인이다. 이번 계획은 이 체인에서 이미 닫힌 경계를 다시 파지 않고, `approved TTS truth`, `happy-path smoke`, `evidence freeze`만 기본 실행 범위로 고정한다.

**Tech Stack:** Python, FastAPI, pytest, React, TypeScript, Vite, PowerShell helper scripts

---

## Reality Check

- 2일 안에 가능한 것은 `전체 기능 완성`이 아니라 `설명형 영상 1개를 안정적으로 데모할 수 있는 1차 버전`이다.
- 현재 기준 이미 살아 있는 축은 많다.
  - `editing session` 저장/조회/수정
  - partial regeneration request + backend job execution
  - review action family
  - subtitle / preview / CapCut export
  - `Local Qwen -> Gemini fallback`
  - provider trace audit
- 따라서 남은 일의 성격은 `큰 기능 추가`보다 `데모 직전에 깨질 수 있는 마지막 truth gap 확인`에 가깝다.

## Expert Review Summary

서브에이전트 검토와 로컬 점검을 합친 결론은 아래다.

- 유지
  - approved `tts_replacement`가 approve 이후 persisted timeline과 preview/export 소비 경로까지 같은 truth를 타는지 확인하는 slice
  - 실제 프로젝트 1개를 끝까지 돌리는 smoke
  - SSOT / closeout evidence freeze
- 기본 범위에서 삭제
  - reopen 후 residual blocker 추가 경계 태스크
  - preflight stale-shape 신규 normalization 태스크
  - thin operator UI 새 gating 규칙 태스크
- 삭제 이유
  - 이미 유사 회귀가 많고 payoff가 낮다.
  - `local_pipeline.py`를 넓게 다시 건드릴 가능성이 크다.
  - 2일 플랜에서는 demo reliability보다 내부 completeness 쪽 비중이 과해진다.

## V1 Demo Definition

이 계획에서 `1차 버전 완성`은 아래 흐름이 통과하는 상태를 뜻한다.

1. 프로젝트를 만들거나 선택한다.
2. timeline build가 성공한다.
3. review snapshot에서 pending recommendation 또는 review-required segment를 확인할 수 있다.
4. editing session으로 진입한다.
5. mutation 1회와 preflight 1회를 수행한다.
6. partial regeneration을 실행한다.
7. approve를 수행한다.
8. subtitle / preview / CapCut export가 모두 성공한다.
9. 실패 시 왜 막혔는지 blocker reason을 바로 설명할 수 있다.

이번 2일 계획에서 의도적으로 제외하는 항목은 아래다.

- 풀 편집기 UI
- 고급 멀티트랙 편집
- reopen flow polish
- 세부 stale-shape normalization 추가 확장
- 대시보드 리디자인
- 대규모 리팩터링
- OSS 편집기 셸 반입

## File Map

이번 2일 계획에서 실제로 만질 가능성이 높은 파일은 아래다.

- Backend review/output truth
  - `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\services\api\src\videobox_api\main.py`
  - `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\core-engine\src\videobox_core_engine\local_pipeline.py`
  - `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\core-engine\src\videobox_core_engine\review_action_mutations.py`
- Tests and helpers
  - `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_api.py`
  - `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_preview_export.py`
  - `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_dev_fast_path.py`
  - `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\scripts\dev-fast-path.ps1`
- Demo/operator reference only
  - `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\apps\web\src\App.tsx`
  - `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\apps\web\src\app.test.tsx`
- SSOT / closeout docs
  - `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\docs\implementation-plan.ko.md`
  - `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\docs\development-status-2026-06-29.ko.md`
  - `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\docs\session-context-*.ko.md`

## Execution Rules

- `plan reconcile -> RED -> minimal GREEN -> focused verification -> broader verification` 순서를 지킨다.
- exact failing test는 항상 1개로 시작한다.
- `editing-session SSOT`, `review/output rules`, `Gemini fallback`, `provider trace audit`, `persistence behavior`는 회귀 금지 축으로 취급한다.
- 이미 닫힌 경계를 다시 새 태스크로 올리지 않는다.
- `local_pipeline.py`는 최소 수정만 허용한다.

### Task 1: Prove The Last Approved-TTS Output Truth Gap

**Files:**
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_api.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\core-engine\src\videobox_core_engine\local_pipeline.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\packages\core-engine\src\videobox_core_engine\review_action_mutations.py`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\scripts\dev-fast-path.ps1`
- Test: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_api.py`

- [ ] **Step 1: Write the smallest failing test first**

```python
def test_review_snapshot_api_approve_tts_replacement_updates_persisted_timeline_before_output_jobs(
    tmp_path: Path,
) -> None:
    app = create_app(projects_root=tmp_path)
    client = TestClient(app)
    project_id, timeline_job_id = _create_tts_review_project(client, tmp_path)

    approve_response = client.post(
        f"/api/projects/{project_id}/review-snapshots/{timeline_job_id}/actions",
        json={
            "action": "approve_recommendation",
            "recommendation_id": "rec_tts_seg_001",
        },
    )

    assert approve_response.status_code == 200

    timeline_payload = client.get(f"/api/projects/{project_id}/timelines/{timeline_job_id}").json()
    narration_track = next(
        track for track in timeline_payload["timeline"]["tracks"] if track["track_type"] == "narration"
    )
    assert narration_track["clips"][0]["asset_uri"].endswith("asset_tts_approved_001.wav")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py -q -k "test_review_snapshot_api_approve_tts_replacement_updates_persisted_timeline_before_output_jobs"`
Expected: FAIL only if the persisted timeline truth is not actually updated after approve.

- [ ] **Step 3: Write minimal implementation**

```python
# review_action_mutations.py
for track in timeline_payload.get("tracks", []):
    if str(track.get("track_type")) != "narration":
        continue
    for clip in track.get("clips", []):
        if str(clip.get("segment_id")) != target_segment_id:
            continue
        clip["asset_uri"] = selected_asset_uri
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api.py -q -k "test_review_snapshot_api_approve_tts_replacement_updates_persisted_timeline_before_output_jobs"`
Expected: PASS

- [ ] **Step 5: Add the consumer proof only after the first test is green**

```python
def test_review_snapshot_api_approved_tts_replacement_output_jobs_consume_the_persisted_timeline_truth(
    tmp_path: Path,
) -> None:
    store = LocalProjectStore(tmp_path)
    project = store.bootstrap_project(name="Approved TTS Persisted Truth Project")
    timeline = store.save_timeline_run(
        project_id=project.project_id,
        output_mode="review",
        timeline_payload={
            "project_id": project.project_id,
            "narration_source_uri": f"local://projects/{project.project_id}/inputs/narration/source.wav",
            "tracks": [
                {
                    "track_id": "narration_primary",
                    "track_type": "narration",
                    "clips": [
                        {
                            "clip_id": "clip_narration_001",
                            "segment_id": "seg_001",
                            "asset_uri": f"local://projects/{project.project_id}/assets/generated/asset_tts_approved_001.wav",
                            "start_sec": 0.0,
                            "end_sec": 1.0,
                            "clip_type": "narration",
                        },
                        {
                            "clip_id": "clip_narration_002",
                            "segment_id": "seg_002",
                            "asset_uri": f"local://projects/{project.project_id}/inputs/narration/source.wav",
                            "start_sec": 1.0,
                            "end_sec": 2.0,
                            "clip_type": "narration",
                        },
                    ],
                }
            ],
            "review_flags": [],
            "applied_recommendations": [],
            "pending_recommendations": [],
        },
    )
    timeline_job = store.create_job(
        project_id=project.project_id,
        job_type=JobType.TIMELINE_BUILD,
        input_ref="segment_analysis_job_001",
        status=JobStatus.SUCCEEDED,
    )
    store.update_job(
        project_id=project.project_id,
        job_id=timeline_job["job_id"],
        status=JobStatus.SUCCEEDED,
        output_ref=timeline["timeline_id"],
    )
    store.save_review_state(
        project_id=project.project_id,
        timeline_id=timeline["timeline_id"],
        status="approved",
    )
    client = TestClient(create_app(projects_root=tmp_path))
    preview_job = client.post(
        f"/api/projects/{project.project_id}/jobs/preview-render",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    export_job = client.post(
        f"/api/projects/{project.project_id}/jobs/capcut-export",
        json={"timeline_job_id": timeline_job["job_id"]},
    )
    preview_payload = client.get(
        f"/api/projects/{project.project_id}/previews/{preview_job.json()['job_id']}"
    ).json()
    export_payload = client.get(
        f"/api/projects/{project.project_id}/exports/{export_job.json()['job_id']}"
    ).json()
    assert preview_payload["status"] == "succeeded"
    voiceover_track = next(
        track for track in export_payload["export"]["capcut_tracks"] if track["track_name"] == "voiceover"
    )
    assert voiceover_track["segments"][0]["source_uri"].endswith("asset_tts_approved_001.wav")
```

- [ ] **Step 6: Run the second exact test**

Run: `pytest tests/test_api.py -q -k "test_review_snapshot_api_approved_tts_replacement_output_jobs_consume_the_persisted_timeline_truth"`
Expected: PASS

- [ ] **Step 7: Close the focused lane once**

Run: `./scripts/dev-fast-path.ps1 -Mode output-gating`
Expected: PASS and no regression in approval/output hardening.

- [ ] **Step 8: Commit**

```bash
git add tests/test_api.py packages/core-engine/src/videobox_core_engine/local_pipeline.py packages/core-engine/src/videobox_core_engine/review_action_mutations.py scripts/dev-fast-path.ps1
git commit -m "test: lock approved tts persisted output truth"
```

### Task 2: Run One Real-Project Demo Smoke And Freeze Evidence

**Files:**
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\docs\implementation-plan.ko.md`
- Modify: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\docs\development-status-2026-06-29.ko.md`
- Create: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\docs\session-context-2026-07-03-v1-plan-review-closeout.ko.md`
- Test: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\tests\test_api.py`
- Test: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\apps\web\src\app.test.tsx`

- [ ] **Step 1: Use this checklist as the demo definition of done**

- [ ] project 생성 또는 선택 가능
- [ ] timeline build 성공
- [ ] review snapshot 확인 가능
- [ ] editing session 진입 가능
- [ ] mutation 1회 수행 가능
- [ ] preflight 결과 확인 가능
- [ ] partial regeneration 성공
- [ ] approve 성공
- [ ] subtitle / preview / CapCut export 3종 성공
- [ ] blocker reason 설명 가능

- [ ] **Step 2: Re-run only the confidence set before the smoke**

Run: `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
Expected:
- backend output-gating PASS
- backend preflight PASS
- frontend preflight PASS

- [ ] **Step 3: Run one real-project smoke flow manually**

- [ ] 한 프로젝트만 사용한다
- [ ] Gemini key 관리 화면은 데모 본선에서 건너뛴다
- [ ] provider trace audit은 보조 설명으로만 사용한다
- [ ] reopen flow는 기본 데모 경로에서 제외한다

- [ ] **Step 4: Run broader verification only once at the end**

Run: `./scripts/dev-fast-path.ps1 -Mode broader`
Expected:
- frontend build success
- full backend regression PASS

- [ ] **Step 5: Freeze evidence into SSOT and closeout docs**

```markdown
- approved TTS replacement now propagates through approve persistence -> persisted timeline -> preview/export consumption as one proven chain
- demo smoke path completed on one real project:
  - timeline build
  - review snapshot
  - editing session
  - preflight
  - partial regeneration
  - approve
  - subtitle / preview / export
- latest verified baseline
  - backend output-gating <updated count>
  - backend preflight <updated count>
  - frontend preflight <updated count>
  - frontend build success
  - full backend regression <updated count>
```

- [ ] **Step 6: Commit**

```bash
git add docs/implementation-plan.ko.md docs/development-status-2026-06-29.ko.md docs/session-context-2026-07-03-v1-plan-review-closeout.ko.md
git commit -m "docs: freeze v1 demo execution rail"
```

## Conditional Backlog

아래 항목은 기본 2일 계획에서 제외한다. 오직 exact failing test 1개가 실제 gap을 재현할 때만 다시 올린다.

### Conditional Slice A: Reopen + Residual Blocker

- 조건
  - demo smoke 중 reopen flow가 실제로 꼬일 것
  - 기존 `reopening_approved_review_reblocks_outputs_until_reapproved` 계열 회귀로 설명되지 않을 것

### Conditional Slice B: New Preflight Normalization Gap

- 조건
  - 기존 `predicted_review_status_after_rerun` normalization 회귀군과 중복이 아닐 것
  - stale shape가 happy path를 직접 깨뜨릴 것

### Conditional Slice C: Thin Operator UI Extra Gating

- 조건
  - 실제 데모에서 operator가 길을 잃는 것이 확인될 것
  - backend가 아니라 UI 표현/버튼 상태 때문에 오해가 생길 것

## 2-Day Schedule

### Day 1

- Task 1
- focused verification
- smoke 준비

### Day 2

- Task 2
- broader verification once
- commit / push / session-context save / SSOT update

## Post-V1 Upgrade Tracks

이 아래는 `2일 안에 무조건 끝낼 것`이 아니라, `1차 버전 후에 다시 흔들리지 않게 순서 고정`하기 위한 업그레이드 계획이다.

### Upgrade Track A: Local Pipeline Extraction

- 목적: `local_pipeline.py`의 거대한 분기와 상태 정규화를 출력, review, rerun, artifact persistence 단위로 나눈다.
- 우선 파일
  - `packages/core-engine/src/videobox_core_engine/local_pipeline.py`
  - `packages/core-engine/src/videobox_core_engine/review_action_mutations.py`
  - `packages/core-engine/src/videobox_core_engine/output_operator_copy.py`
- 완료 기준
  - output gating helper 분리
  - preflight normalization helper 분리
  - provider trace audit save path 분리

### Upgrade Track B: Thin Editor UX Completion

- 목적: 현재 이미 있는 mutation과 preflight 계약을 더 적은 클릭으로 설명 가능하게 만든다.
- 우선 파일
  - `apps/web/src/App.tsx`
  - `apps/web/src/api.ts`
  - `apps/web/src/styles.css`
  - `apps/web/src/app.test.tsx`
- 완료 기준
  - review snapshot -> editing session -> preflight -> rerun -> approve/output 흐름이 덜 헷갈리게 정리됨
  - output artifact / provider trace 링크가 더 명확해짐

### Upgrade Track C: Provider And Audit Operations

- 목적: 로컬 우선 runtime과 Gemini fallback, provider trace audit을 운영 관점에서 더 잘 설명하고 필터링한다.
- 우선 파일
  - `packages/core-engine/src/videobox_core_engine/local_first_runtime.py`
  - `packages/core-engine/src/videobox_core_engine/gemini_runtime.py`
  - `packages/core-engine/src/videobox_core_engine/provider_trace.py`
  - `tests/test_gemini_runtime.py`
  - `tests/test_api.py`

### Upgrade Track D: Demo-To-Production Packaging

- 목적: “개발용으로 돌아간다”에서 “운영자에게 반복 실행 가능하다”로 올린다.
- 완료 기준
  - 첫 실행 가이드 정리
  - 샘플 프로젝트 smoke fixture 정리
  - 오류 메시지와 artifact 경로 설명 강화

## Acceptance Checklist

- approved TTS replacement가 approve persistence 이후 persisted timeline과 preview/export 소비 경로에서 일관되게 반영된다.
- 1개 프로젝트 happy path가 끊기지 않고 실제로 끝까지 실행된다.
- subtitle / preview / CapCut export 3종이 모두 같은 approved truth를 사용한다.
- 실패 시 blocker reason을 operator가 바로 설명할 수 있다.
- `Local Qwen -> Gemini fallback`, provider trace audit, artifact persistence가 유지된다.
- broader verification이 fresh baseline으로 다시 통과한다.

## Risks

- 2일 안에 끝내려면 `새 기능 추가`를 참아야 한다.
- 이미 닫힌 경계를 다시 새 태스크로 올리면 시간만 쓰고 데모 신뢰도는 거의 오르지 않는다.
- `local_pipeline.py`가 여전히 크기 때문에, 데모 전에는 최소 수정 원칙을 지켜야 한다.
- demo smoke를 테스트만으로 대체하면 실제 설명 흐름에서 빈틈이 남을 수 있다.

## Self-Review

- Spec coverage
  - 2일 안의 1차 버전 범위, 제외 범위, expert review 반영, smoke checklist, post-v1 업그레이드 순서를 모두 포함했다.
- Placeholder scan
  - 기본 실행 태스크에는 더 이상 이미 닫힌 경계를 placeholder처럼 중복 배치하지 않았다.
- Type consistency
  - 현재 레포의 핵심 용어를 그대로 유지했다.
  - `editing session`
  - `partial regeneration`
  - `review snapshot`
  - `preview render`
  - `capcut export`

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-03-v1-two-day-completion-and-upgrade-plan.ko.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
