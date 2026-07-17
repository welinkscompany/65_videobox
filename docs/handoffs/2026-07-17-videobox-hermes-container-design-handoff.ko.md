# VideoBox Hermes Container Design Handoff

**Date:** 2026-07-17
**State:** 설계·독립 리뷰·commit/push 완료. 실제 Compose/컨테이너/agent 연동 구현은 아직 시작하지 않음.

## 이번 세션에서 닫은 일

- VideoBox 내부의 루미 대화는 VideoBox 전용 Hermes profile `lumi-video-director`가 담당하고, Qwen/BGE는 로컬 미디어 분석과 제한된 저위험 보조 작업에 남기는 계층형 방향을 고정했다.
- 사용자가 의도한 것은 Hermes만의 별도 컨테이너가 아니라, **VideoBox 전체와 Hermes를 함께 실행하는 하나의 local Docker Compose 제품 스택**이라는 점을 반영했다. 단일 container process에는 섞지 않는다.
- `videobox-local` release stack은 web, API, 무네트워크 render worker, Hermes, 분리 egress, memory gateway, storage-only mem0/Postgres로 구성한다.
- Windows host에는 LM Studio와 CapCut Desktop, 그리고 native import picker·LM Studio exact loopback proxy·CapCut registration만 수행하는 최소 host bridge만 남긴다.
- Hermes는 VideoBox DB/filesystem/API를 직접 호출하지 않는다. VideoBox API의 host-mediated tool loop가 read-only tool request를 검증·실행하고, 모든 편집 변경은 proposal → deterministic preflight → 사용자 승인 → atomic mutation을 유지한다.
- mem0는 VideoBox truth/asset DB가 아니라 사용자 선호용 storage-only 보조 기억이다. model inference/embedding/external egress는 mem0에서 금지한다.
- container release profile의 file ingest와 CapCut handoff가 Windows path에 의존해 깨지는 문제를 위해 native-picker/chunk staging, project-relative URI, container/Windows typed path resolver와 opaque artifact registration 계약을 설계에 넣었다.
- architecture/security 독립 재리뷰를 두 번 수행했고 최종 미폐쇄 P0/P1은 0건이었다.

## authoritative 문서

- 설계: `docs/superpowers/specs/2026-07-17-videobox-hermes-hybrid-runtime-design.md`
- 기존 OSS dashboard/editor 실행 계획: `docs/superpowers/plans/2026-07-17-videobox-oss-dashboard-editor-adoption.md`
- 기존 OSS dashboard/editor handoff: `docs/handoffs/2026-07-17-videobox-oss-dashboard-editor-adoption-plan-closeout.ko.md`
- 현재 상태 SSOT: `docs/development-status-2026-06-29.ko.md` §252

## Git과 검증 상태

- branch: `codex/production-readiness-blocker-slice-1`
- 설계 commit: `6d9d0a5 docs: design local VideoBox Hermes stack`
- push 완료: `origin/codex/production-readiness-blocker-slice-1`가 같은 SHA를 가리킨다.
- 문서 검증: placeholder 0, referenced docs path 존재, whitespace/diff check 통과.
- 독립 architecture/security review: 최종 P0/P1 0.
- 코드·container runtime은 만들거나 실행하지 않았으므로 runtime test 결과는 없다.

## 보존해야 할 현재 worktree

현재 worktree에는 이 설계 commit에 포함되지 않은 Lumi copy UI 변경이 남아 있다. 이는 기존 OSS 계획 Slice 0 Task 1의 입력이며 되돌리거나 Hermes/container 작업과 섞으면 안 된다.

- modified: `apps/web/src/ProjectOnboarding.tsx`, `apps/web/src/features/director/*`, `apps/web/src/features/media/*`, 관련 test 파일
- untracked: `apps/web/src/features/director/DirectorContextBar.test.tsx`, `apps/web/src/user-copy-policy.test.ts`

이 변경의 이전 planning-time RED baseline은 focused 3파일 `17 passed`, production build TypeScript 오류 5건이었다. 다음 세션은 현재 tree에서 다시 재현해 사실 여부를 확인해야 하며, 이 기록을 fresh green 근거로 사용하면 안 된다.

## 아직 하지 않은 일과 순서

1. 즉시 코딩 작업은 OSS 계획 Slice 0 Task 1이다. 위 dirty Lumi copy의 RED/Green, baseline, commit/push를 먼저 닫는다.
2. 이어서 OSS Task 2–7로 visual approval, source lock, app shell과 provider-neutral creation brief/interview를 만든다.
3. 이 Hermes 설계서는 written-spec user review가 남아 있다. 설계서 승인 뒤에만 별도 implementation plan을 작성한다.
4. 그 plan의 Stage 1–3은 전체 `videobox-local` stack과 read-only Hermes chat이고, Stage 4–6은 proposal/mem0/Qwen qualification이다.
5. OSS Task 8–9 뒤에 Hermes proposal을 연결하고, OSS Task 20에서 검증한 Gateway를 editor에 통합한다.

SaaS는 이 local product stack이 안정화된 뒤 별도 fork/설계로 진행한다. owner OAuth를 고객과 공유하지 않으며 customer-owned OAuth와 tenant isolation이 전제다.

## 기록 보존 판단

- session/status/handoff: 저장 완료.
- implementation-plan: 아직 user written-spec review 전이므로 Hermes 방향으로 갱신하지 않음.
- AK-Wiki promotion: 하지 않음. VideoBox 전용 제안 설계이며 실제 운영에서 검증된 일반 규칙이 아니다.
- 삭제: 없음. 기존 Lumi UI 변경과 artifact는 preserve 대상이다.

## 다음 세션용 goal prompt

```text
goal 명령으로 다음 목표를 시작해줘.

VideoBox OSS Dashboard and Editor Adoption 계획서의 Slice 0 Task 1을 서브에이전트 드리븐 TDD로 끝까지 수행하라.

먼저 다음 handoff와 설계 문서를 읽고 현재 HEAD/upstream/worktree를 확인하라.

- docs/handoffs/2026-07-17-videobox-hermes-container-design-handoff.ko.md
- docs/handoffs/2026-07-17-videobox-oss-dashboard-editor-adoption-plan-closeout.ko.md
- docs/superpowers/plans/2026-07-17-videobox-oss-dashboard-editor-adoption.md
- docs/superpowers/specs/2026-07-17-videobox-oss-dashboard-editor-adoption-design.md
- docs/superpowers/specs/2026-07-17-videobox-hermes-hybrid-runtime-design.md

범위:
- 기존 Lumi copy dirty scope를 먼저 고정하고, focused test와 production build의 현재 RED를 재현
- user-copy policy와 Director/Lumi component test/build failure를 의미 약화 없이 GREEN으로 복구
- legacy project/select/navigation/Director/manual/preview/output/settings behavior baseline test 추가
- focused suite, full frontend suite, production build, diff/status 검사
- 코드리뷰, 계획 gap 검증, source→runtime 역방향 검증
- OSS 계획 Slice 0 Task 1 checkbox와 상태 SSOT 누적 진행률 갱신
- Lumi copy + baseline만 논리적으로 commit/push

제약:
- 기존 dirty 변경을 되돌리거나 새 shell/container/Hermes 구현과 섞지 말 것
- Tailwind/shadcn/router/OpenCut 코드는 아직 도입하지 말 것
- Hermes container 설계는 보존하되, written-spec user review와 별도 implementation plan 전에는 실제 Compose/host bridge/runtime 코드를 만들지 말 것
- external/Gemini provider call 0 유지

완료 조건:
- RED가 현재 결함을 재현하고 GREEN이 닫음
- frontend full test와 production build 통과
- Task 1만 완료 처리하고 commit/push SHA 보고
- 다음 Task 2 goal prompt와 Hermes 설계 승인 상태를 함께 보고
```
