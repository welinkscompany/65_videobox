# VideoBox OSS Dashboard/Editor Adoption Slice 2 Task 9 Technical Gate

**Date:** 2026-07-18
**Base commit:** `93c5b7161 feat: prepare a playable draft plan`
**Task state:** 코드·자동 검증 완료, 사람/환경 승인 대기 — **Task 9 closeout 아님**

Task 9은 사용자의 한 번의 `초안 만들기` 승인으로 실제 편집 세션과 타임라인 번들을 만들 수 있도록 구현했다. 다만 이 기록은 자동화된 기술 gate이며, 사용자가 실제 완성 미리보기를 보고 승인한 기록이나 실제 CapCut Desktop 등록 결과는 아직 없다.

## 구현 및 자동 검증된 범위

- brief/draft-plan revision, source SHA/media revision을 apply 직전에 재확인한다. idempotency와 동시 중복 요청은 같은 bundle을 재사용한다.
- 세션·placement·asset materialization은 per-SHA staging/atomic rename/rollback으로 묶었다. N번째 복사 실패, restart orphan, 부분 적용 세션을 회귀 테스트로 막는다.
- 원본 영상 소리, 완성 나레이션, 녹음 업로드, project-local 결정적 무음 narration을 실제 FFmpeg/PyCapCut으로 검증했다. `voice_sample_audio`는 완성 나레이션 선택으로 거절한다.
- 자산이 비어 있는 gap은 사용자가 `임시 장면으로 초안 만들기`를 명시적으로 선택할 때에만 결정적 placeholder로 만든다. gap 자체는 보존하고 final/CapCut 출력은 real visual asset 또는 지원되는 명시 정책 전까지 막는다.
- 새 session은 `/projects/$projectId/editor`로 연다. current revision FFmpeg render의 시작·progress·stale·retry·download·MP4 content와 in-app video playback, CapCut handoff route를 loopback browser smoke로 확인했다.

## 확인된 검증

- focused backend: atomic/API/readiness `34 passed`
- frontend full: `28 files / 281 tests passed`
- loopback-only Playwright: `13 passed`
- production build, provenance/UI-system verifier, provenance pytest `14 passed`, `git diff --check` 통과
- 독립 코드리뷰, 계획 gap, source→runtime 역방향 검증에서 발견한 P1은 TDD로 보완했다.
- external/Gemini provider call은 0이다. Hermes/container, OpenCut runtime, SaaS auth/billing은 시작하지 않았다.

## 아직 필요한 사람/환경 gate

1. 실제 current-revision 합성 MP4를 VideoBox에서 재생하고, 사용자가 영상·자막·무음/나레이션·임시 장면 표시가 의도와 맞는지 승인 또는 거부한다.
2. 대상 PC에서 실제 CapCut Desktop handoff 등록/열기와 import 결과를 확인하고 기록한다. 현재 자동 smoke는 로컬 writable fake handoff만 확인하므로 Desktop 앱 확인을 대체하지 않는다.

두 gate가 기록되기 전에는 Task 9 체크박스를 완료로 바꾸지 않고 누적은 **8/22 (36.4%)**, 잔여 **63.6%**로 유지한다. 이 상태에서는 Task 9 완료 commit/push나 다음 구현 Task로 진행하지 않는다.

## 다음 goal 프롬프트

`VideoBox OSS Dashboard/Editor Adoption Plan의 Slice 2 Task 9 사람/환경 acceptance gate를 수행하라. 현재 uncommitted Task 9 기술 구현을 보존하고, 실제 current-revision composited MP4를 VideoBox에서 재생해 사용자의 승인/거부를 기록하라. 대상 PC의 실제 CapCut Desktop handoff 등록·열기·import 결과도 기록하라. 승인된 경우에만 independent code review·계획 gap·source→runtime 역방향 검증과 focused/full tests/build를 최신 worktree에서 재확인하고, Task 9 checkbox·누적 진행률·status/handoff를 9/22로 갱신한 뒤 정확히 feat: create an edited draft from one approval 커밋과 push를 수행하라. 거부 또는 환경 불가면 Task 9을 완료로 표시하지 말고 근거와 재현 경로만 기록하라. external/Gemini call 0을 유지하고 Hermes/container, OpenCut runtime, SaaS auth/billing은 시작하지 말라.`
