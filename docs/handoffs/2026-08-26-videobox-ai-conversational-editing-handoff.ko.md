# VideoBox 2026-08-26 자유 대화형 AI 편집 구현 인계

## 완료 범위

설계서의 고정 흐름인 `자유 대화 → 타입화된 편집안 → 미리보기 → 명시적 적용 → 공통 이력`을 구현했다. 대화 문장만으로는 저장을 바꾸지 않으며, 창작자가 **이 대화로 편집안 만들기**와 **이 편집안 적용**을 각각 눌러야 한다.

- 엄격한 7종 편집 연산 도메인 모델과 순수 검증 어댑터를 추가했다.
- 로컬 모델에는 현재 세션 revision·허용 segment ID·strict JSON Schema를 전달하고, 허용 연산만 편집안으로 수락한다.
- 후보 생성·현재성 검사·미리보기·원자 적용을 API로 연결했다. 적용은 기존 undo/redo 이력의 단일 변경이다.
- 우측 유진 패널에 후보 요약, 상세 다이얼로그, 최대 3개 후속 질문을 추가했다. 후속 질문은 입력칸만 채우며 자동 전송·적용하지 않는다.
- AI 명령 평가는 `materialize_editing_session_timeline` 결과를 사용한다.

## 구현 커밋

- `5d9d83f31` 기능: 유진 편집안 형식과 안전 검증 추가
- `c9c5521e0` 기능: 유진 편집안 생성과 후속 질문 연결
- `a62e92c9f` 기능: 유진 편집안을 한 번에 적용하고 되돌리기 연결
- `4c3a6bebd` 수정: 유진 편집안 적용 범위와 미디어 검증 보강
- `8f47d4a2` 기능: 대화에서 유진 편집안 후보 만들기
- `f1ef4d62` 기능: 유진 편집안 상세 검토와 적용 연결
- `2b45fbdd` 검증: 유진 자연어 편집 명령과 출력 시간축 확인
- `15e93fc3` 기능: 유진 편집안 로컬 모델 계약 보강

모두 `origin/codex/videobox-container-compatibility`에 푸시했다. 이 인계의 문서 커밋은 아래 최종 점검 뒤 별도로 추가한다.

## 실제 검증 증거

- 백엔드 집중 회귀: `test_yujin_editing_command_evaluation.py`, `test_yujin_editing_proposal_adapter.py`, `test_api_media_director.py`, `test_editor_timeline_mutations.py`, `test_shortform_ripple_speed.py` — **98 passed, 1 warning**.
- 프런트 정적/단위: `npx tsc --noEmit` 통과. `npx vitest run`은 **96 files, 1,286 passed**.
- 브라우저 E2E: `npx playwright test e2e/editor-workbench.spec.mjs --grep "owned conversational-editing fixture"` — **1 passed**; 파일 전체 — **12 passed**. 이 시험은 대화만으로 후보가 생기지 않음, 명시 후보 생성, 상세·미리보기·적용, 새로고침, undo/redo 지속성을 확인한다.
- 실제 런타임: `./scripts/owner-ready.ps1 -Mode Start -Rebuild -WithYujinMemory`가 재빌드·기동·준비 상태를 통과했고, 5173 포트의 컨테이너 UI를 직접 점검했다.
- 실제 로컬 모델 응답: “두 번째 장면을 두 배로 빠르게 해줘”에 대한 strict 후보는 `set_scene_speed`, rate `2`, `candidate_only`로 생성됐다.
- 실제 브라우저 역방향: 로컬 전용 QA 프로젝트 `ai-qa-20260826-8a11f547`에서 후보 `2번 장면 · 5초 → 2.5초`를 생성하고 미리본 뒤 적용했다. 총 길이는 **15.0초 → 12.5초**, 새로고침 후에도 유지됐다. undo 후 새로고침은 **15.0초** 및 redo 가능, redo 후 새로고침은 **12.5초** 및 undo 가능 상태였다.

## 알려진 경계

- QA 프로젝트는 자산 공백 placeholder 3개를 의도적으로 사용한다. 그 thumbnail 404 콘솔 오류는 편집안 생성·적용 실패가 아니라 해당 fixture의 무자산 상태다.
- 외부 provider, 게시·업로드, 실제 제작물에 대한 변경은 하지 않았다.
- 브라우저 기능 증거는 확보했지만, 승인된 5개 viewport에 대한 사람의 시각 수용 검토는 별도 게이트로 남는다.

## 2026-08-26 안전 마감 추가 상태

### Codex 실행 원장 (다음 작업의 맥락)

이 섹션은 Codex가 실제로 수행한 순서와 증거를 남긴다. 이후 작업자는 커밋 제목만 보고 이미 검증된 것과 아직 증명되지 않은 것을 혼동하지 말 것.

| 순서 | 커밋 | 실제 작업 | 확인한 증거 |
|---|---|---|---|
| 1 | `5d9d83f31` | strict 7종 typed editing operation·검증 어댑터 | adapter RED→GREEN |
| 2 | `c9c5521e0` | 후보 생성·후속 질문 API | 후보는 저장 변경이 아닌 read-only record |
| 3 | `a62e92c9f` | 원자 적용을 기존 undo/redo transaction에 연결 | AI 적용이 한 undo event |
| 4 | `4c3a6bebd` | target/media validation 보강 | 허용하지 않은 범위·미디어 거절 |
| 5 | `8f47d4a20` / `f1ef4d624` | 명시 후보 생성·상세 dialog·명시 적용 UI | 대화만으로 적용되지 않음 |
| 6 | `2b45fbdd6` | 명령 평가·materialized output time axis | speed 편집 timeline 검증 |
| 7 | `15e93fc3d` | 실제 로컬 모델 strict response schema/prompt | LM Studio가 `set_scene_speed`, rate 2 후보 반환 |
| 8 | `3441fb137` / `1cbd6f34d` | 저장 없는 proposal projection | speed 및 SFX/B-roll/reorder 복합 투영에서 source·revision·history·undo/redo 불변 |
| 9 | `79e64cf03` / `c0d939879` / `66c4f7f6d` / `a1121e8c0` | proposal 전용 MP4 artifact, stale fence, claim/GC | asset bytes 변경 시 공개 차단·409, proposal namespace만 cleanup |

#### 실제 런타임·브라우저에서 본 것

- 승인 스크립트 `./scripts/owner-ready.ps1 -Mode Start -Rebuild -WithYujinMemory`로 로컬 컨테이너를 재빌드·기동했다. 외부 provider, 게시, 업로드, production mutation은 호출하지 않았다.
- local-only QA 프로젝트 `ai-qa-20260826-8a11f547` / 세션 `editing_session_draft_d064190cda4f`에서 실제 로컬 모델로 “두 번째 장면을 두 배로 빠르게 해줘” 후보를 생성했다.
- UI에서 후보 상세 → 기존 “이 구간 미리보기” → 명시 적용을 거쳐 총 길이 15.0초→12.5초를 확인했다. 새로고침 후에도 유지됐고, undo 후 새로고침은 15.0초·redo 가능, redo 후 새로고침은 12.5초·undo 가능이었다.
- 하지만 해당 fixture는 영상 자산 공백 3개이므로 thumbnail 404가 있다. 또한 당시 “이 구간 미리보기”는 **후보 결과가 아닌 현재 저장 세션**을 보여 줬다. 따라서 이 결과는 apply/undo/redo persistence 증거일 뿐, proposal-preview 영상 증거가 아니다.
- 출력 화면은 적용 뒤 검토본 stale·검토 미승인을 표시했고 MP4/CapCut 버튼을 비활성으로 유지했다. 유효 MP4를 통한 실제 final-output 성공은 검증하지 않았다.

#### 자동 검증과 해석

- 이전 웹 전체: `npx vitest run` **96 files, 1,286 passed**; `npx tsc --noEmit` 통과.
- 브라우저: 기존 workbench/exact-preview E2E **19 passed**. 이 중 owned conversational fixture는 후보 생성·명시 apply·refresh·undo/redo를 mock API 계약으로 확인한다. 새 proposal-preview UI는 아직 없으므로 이를 증명하지 않는다.
- 백엔드 집중: proposal preview/미디어 director/exact preview/Postgres compatibility 묶음 **84 passed**. 개별 proposal-preview fence 묶음 **8 passed**, projection 묶음 **2 passed**, editing-session mutation 묶음 **25 passed**.
- 전체 pytest는 새 최종 HEAD에서 완주하지 않았다. 이 세션의 첫 전체 실행은 handoff entry 계약 실패로 중단됐고(문서 대체 표지 추가 후 개별 5 passed), 재실행은 `test_api_yujin_memory.py` 단발 실패가 보여 중단했다. 해당 파일은 단독 10회 모두 통과했다. **전체 regression PASS로 해석하면 안 된다.**

#### 독립 리뷰 결과와 판단

- 처음 독립 코드리뷰가 발견한 Critical: proposal dialog preview가 원래 session selected range를 호출해 변경 결과를 보여 주지 않았다. 이 때문에 Task 2 read-only proposal preview backend를 만들었다.
- Task 2 명세 리뷰가 발견한 P1: stale status/content가 200/404였고 publication fence가 원자적이지 않았다. `c0d939879`에서 creator-safe 409과 staged file + writer transaction fence로 보정했다.
- 다음 리뷰 P2: asset bytes mutation·성공 content endpoint 증거 부족. `66c4f7f6d`에서 asset bytes 변경 시 artifact 미발행/409, current synthetic MP4 `200 video/mp4`를 추가했다.
- 마지막 safe-close 코드리뷰의 **미해결 P1**: restart recovery가 POST에만 있어 GET polling 단독이면 pending/running이 고착될 수 있다. 이 P1은 아직 존재하며, 후속 작업의 첫 RED 대상이다. 이 사실 때문에 이번 안전 마감은 backend 완결이나 release-ready 선언이 아니다.

#### Codex가 의도적으로 하지 않은 것

- Task 3 frontend API/route/dialog 연결은 시작하지 않았다. proposal-preview endpoint가 있어도 현재 UI는 사용하지 않는다.
- approved asset catalogue를 모델 prompt에 넣기, preview/preflight/apply의 asset hash/revision 재검증, clarification `reply_text` 표시도 아직 하지 않았다.
- 사용자 기존 프로젝트를 변형하지 않았고 `output/`을 삭제·stage·commit하지 않았다.
- 최종 container rebuild, 실제 proposal-preview browser playback, owner visual acceptance, final MP4, CapCut은 다음 세션의 명시 QA 범위다.

후속 독립 리뷰에서 기존의 “이 구간 미리보기”가 **후보 결과가 아니라 현재 저장 세션**을 미리본다는 Critical을 발견했다. 이 사실은 이전 브라우저 역방향 증거를 무효화하는 것은 아니지만, 그 증거가 `적용 → 저장 → undo/redo`까지만 보장하고 **적용 전 후보 결과 확인은 보장하지 않는다**는 뜻이다.

안전 범위로 다음 백엔드 기반을 추가했다. 아직 프런트에 연결하지 않았으므로 사용자에게 이 기능이 보인다고 말하면 안 된다.

- `3441fb137` / `1cbd6f34d`: 7종 typed operation을 공통으로 수행하는 read-only `project_yujin_editing_proposal`을 추가했다. 입력 세션, revision, freshness, history, undo/redo는 불변이다.
- `79e64cf03` / `c0d939879` / `66c4f7f6d`: proposal 전용 `proposal_preview_renders`와 `derived/proposal_previews` MP4 경로를 추가했다. 후보 preview는 저장 세션 exact preview와 캐시/보존을 공유하지 않는다. 세션/자산 바이트 변경이면 공개하지 않고 status/content 모두 creator-safe 409이다.
- `a1121e8c0`: proposal preview worker 재시작 claim 회수, 900초 stale claim 회수, 동시 revision 충돌의 409 변환, proposal namespace만의 bounded retention/GC를 추가했다. exact preview와 source 파일은 정리하지 않는다.

**마감 리뷰 P1 (미해결):** recovery가 새 preview `POST`에만 있고, status `GET` polling에는 없다. 따라서 DB row를 만든 뒤 worker 시작 전에 프로세스가 종료되면 `pending`, 실행 중 종료되면 `running`이 다음 POST 전까지 고착될 수 있다. 이 인계 시점에는 수정하지 않았다. Claude는 `get_proposal_preview_status` 또는 앱 시작 복구 경로에서 이전 epoch의 running 및 orphan/aged pending을 원자적으로 terminal retry 상태로 전환하고, **API-level restart + poll** RED 시험으로 고친 뒤에만 proposal-preview backend를 완료 처리한다.

안전 범위 집중 시험 증거:

- proposal preview/미디어 director/exact preview/Postgres 호환 묶음 **84 passed**.
- proposal preview 현재성·artifact publication fence 집중 묶음 **8 passed**.
- read-only projection 집중 묶음 **2 passed**; 기존 editing-session mutation 묶음 **25 passed**.
- 각각 RED를 먼저 확인했다. worker restart, stale claim, CAS conflict 409, retention/GC의 RED→GREEN도 기록했다.

아직 하지 않은 것(Claude의 다음 작업, 순서 고정):

1. `apps/web/src/api.ts`, `EditorWorkbenchRoute.tsx`, `RightDock.tsx`를 proposal-preview status/content API에 연결한다. **적용 전에는** selected-range/exact-preview/current session mutation을 호출하지 않고 `편집안 미리보기` MP4를 표시해야 한다.
2. E2E가 proposal preview API만 호출하고 pre-apply session mutation 0을 보장하도록 바꾼다.
3. 모델 prompt에 approved asset ID/creator-visible name/type를 제공하고 preview/preflight/apply에서 asset approval/hash/revision을 모두 재검증한다.
4. clarification/rejected는 instruction echo가 아니라 `YujinEditingResponse.reply_text`를 화면에 보인다.
5. 유효 MP4가 있는 **local-only owned fixture**로 proposal-preview MP4 → apply → refresh → undo/redo → exact preview → review approval → final MP4를 실제 컨테이너에서 검증한다. CapCut은 선택 경로다.
6. UI 변경 뒤 독립 코드리뷰·갭 검증·5 viewport 사람 시각 수용 검토를 한다.

전체 pytest는 이 세션에서 두 번 중도 중단됐다. 첫 실행은 문서 handoff entry 계약 실패(수정 후 개별 5 passed), 재실행은 `test_api_yujin_memory.py` 단발 실패 뒤 단독 10회 모두 통과했다. 따라서 **새 전체 pytest 완주 PASS는 없다**. Claude는 최종 마감 전에 반드시 전체 pytest를 다시 완주해야 한다.

### Claude 시작 프롬프트

```text
VideoBox 작업을 이어서 해줘. worktree는 D:\\AI_Workspace_louis_office_50\\10_workspace\\65_videobox\\.worktrees\\videobox-container-compatibility, branch는 codex/videobox-container-compatibility야. 먼저 CLAUDE.md, docs/handoffs/2026-08-26-videobox-ai-conversational-editing-handoff.ko.md, docs/superpowers/specs/2026-08-26-ai-conversational-editing-design.ko.md, docs/superpowers/plans/2026-08-26-ai-conversational-editing-implementation.md, docs/superpowers/plans/2026-08-26-ai-conversational-editing-release-gaps.md를 읽어. git status/upstream/worktree/diff --check를 확인하고, untracked output/은 사용자 보존물이므로 절대 stage/delete하지 마.

현재 HEAD의 safe backend scope는 proposal-preview MP4 API, CAS 409, proposal-only GC까지다. **restart recovery polling P1은 아직 미해결**이며 먼저 고쳐야 한다. 이 API는 아직 UI에 연결되지 않았으며, 기존 UI의 “이 구간 미리보기”는 적용 전 후보 결과가 아닌 현재 세션을 보므로 고치지 않은 상태다. P1을 TDD로 고친 다음 apps/web API/EditorWorkbenchRoute/RightDock을 proposal preview에 연결하고, pre-apply mutation 0을 E2E로 증명하는 Task 3을 진행해. 그 다음 approved-asset prompt/currentness와 clarification reply_text, valid-local-MP4 owned fixture의 실제 output QA를 진행해. 전체 pytest는 이 세션에서 새 완주 PASS가 없으므로 최종 전에 반드시 다시 완주해. 코드리뷰·갭검증·실제 container/browser 역방향검증을 각각 분리해 기록하고, push/deploy는 별도 상태로 보고해.
```

## 보호 상태와 다음 작업

- `output/`은 사용자 보존 미추적 산출물이다. 삭제·스테이지·커밋하지 않는다.
- 컨테이너 제어는 계속 `./scripts/owner-ready.ps1 -Mode Start -Rebuild -WithYujinMemory` 경로만 사용한다.
- 다음 세션은 위 Claude 시작 프롬프트와 고정 순서를 따른다. 실제 창작자 프로젝트나 외부 provider/publish는 이 인계 범위가 아니다.
