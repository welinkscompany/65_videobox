# VideoBox Task 22C1 editor commands/partial regeneration closeout

## 닫은 범위

- Inspector에서 구간 나누기/합치기, 실행 취소/다시 실행, keep/remove 컷, B-roll/BGM/SFX 제거를 현재 revision으로 저장한다.
- BGM과 효과음은 페이드 인/아웃을 편집하면서 backend가 유지하는 gain/ducking 값을 보존한다.
- 자막은 전체 style만 편집하고 독립 timing은 노출하지 않는다.
- 설명 카드, 이미지, 표 overlay만 typed payload로 편집/제거한다.
- effect, transition, keyframe, mask, backend 미지원 B-roll control, 자동 apply는 노출하지 않는다.

## 부분 재생성

- 자막, 컷 판단, B-roll, 화면 요소, 음악, 효과음, 내레이션 음성의 7개 canonical field만 선택한다.
- 영향 범위 preflight 뒤 사용자가 실행 버튼을 눌러야 run한다.
- preflight/run/result 응답은 session, job, segment, field identity가 모두 맞아야 수락한다.
- 새로고침·재진입 뒤에도 같은 editing session의 최신 성공 job을 찾고, authoritative session `updated_at`과 현재 segment membership이 맞을 때만 결과를 연다.
- 다른 편집으로 session이 실제 갱신되면 열린 결과와 아직 열지 않은 결과 capability를 함께 무효화한다. 실패한 편집 시도처럼 authoritative timestamp가 그대로면 유효한 결과를 보존한다.
- 과거 결과 조회가 일시 실패하면 manual editing을 막지 않고 오류 안내와 같은 화면의 명시적 재시도를 제공한다.
- route epoch, operation ID, mutation generation, shared mutation single-flight로 오래된 응답과 Director/editor 교차 저장을 막는다.

## BGM/SFX 검증 범위

- 자산 브라우저의 BGM/SFX 구분, preview, materialize, apply는 기존 통합 테스트와 Task 19 owner를 유지한다.
- 이번 Task 22C1은 BGM/SFX fade save, hidden authoritative control 보존, clear, 부분 재생성 field 선택을 추가 검증했다.
- §295 실제 사용자 샘플 dogfood에서 로컬 합성 BGM 220 Hz와 SFX 880 Hz를 서로 다른 구간에 적용하고 exact preview AAC의 구간별 주파수를 역방향 확인했다.
- 자동 검증은 사람이 실제로 듣고 자연스러움을 판단하는 청취 acceptance나 실제 CapCut Desktop 실증을 대신하지 않는다.

## 검증

- focused frontend: `7 files / 141 passed`.
- full frontend: `62 files / 698 passed`.
- editor Playwright E2E: `8 passed`, snapshot manifest verifier 통과.
- production build 통과. 기존 500 kB bundle warning은 비실패 출력이다.
- Editor UI OSS provenance verifier와 UI-system verifier 통과.
- external-runtime/network guard: `2 files / 6 passed`.
- `git diff --check` 통과.
- 독립 spec/quality/gap/reverse review: Critical 0, Important 0.
- 전체 Python regression은 실행하지 않았다.

## 보존 범위

- `?? .tmp-final-fence-debug/`, `?? .tmp-real-video-dogfood/`, `?? apps/web/.tmp-real-video-dogfood/`는 stage/remove/delete하지 않는다.
- 사용자 원본 `C:\Users\atgro\OneDrive\바탕 화면\영상샘플`은 read-only로 유지한다.
- Task 9 사람/환경 acceptance와 실제 CapCut Desktop 실증은 별도다.
- 공식 누적은 **9/22 (40.9%)**, 잔여 **59.1%**다.

## 다음 goal prompt

`VideoBox만 작업해. D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility와 codex/videobox-container-compatibility만 사용해. 먼저 AGENTS.md, docs/development-fast-path.ko.md §10, docs/development-status-2026-06-29.ko.md §297, docs/superpowers/plans/2026-07-23-videobox-task22-release-parity.md, 이 handoff를 읽고 branch/HEAD/upstream/status/worktree/diff-check를 확인해. 보호된 임시 폴더 3개와 사용자 원본 샘플은 절대 stage/remove/delete하지 마. 다음은 Task 22C3 superseded legacy output contracts를 RED-first로 진행해. canonical /outputs가 exact preview reference, final render, current CapCut draft/handoff, stale recovery, refresh를 소유하게 하고 legacy preview_render/exportCapcut UI reachability는 제거해. 실제 CapCut Desktop 증거라고 과장하지 말고, independent spec/quality/gap/reverse review 뒤 focused/full frontend, output E2E, build, provenance/network 검증을 통과시켜. 이어서 22D legacy owner removal을 진행하되 parity owner matrix가 모두 GREEN이기 전에는 App.tsx/legacy CSS를 삭제하지 마. 전체 Python regression은 실행하지 않았으면 통과라고 주장하지 마. Task 9 사람/환경 acceptance와 실제 CapCut Desktop 실증은 별도이며 공식 누적 9/22 (40.9%), 잔여 59.1%를 유지해.`
