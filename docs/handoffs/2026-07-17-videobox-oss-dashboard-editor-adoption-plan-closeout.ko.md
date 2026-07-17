# VideoBox OSS Dashboard/Editor Adoption Plan Closeout

**Date:** 2026-07-17
**State:** research/design/implementation planning complete; production implementation not started

## 완료한 범위

- shadcn-admin, shadcn/ui, OpenCut current/classic, Opencast Editor, Supabase Studio를 공식 source와 pinned commit 기준으로 조사했다.
- `source port / adapter·rewrite / reference only / reject` 경계를 고정했다.
- 현재 VideoBox `App.tsx`, styles, editor API, preview/content 경계를 역추적했다.
- 조사 보고서, 설계서, 7-slice 22-Task 실행 계획서를 만들었다.
- 최상위 구현 계획의 OpenCut 후속 gate와 개발 상태 SSOT, OSS adoption map을 갱신했다.
- research claim ledger의 핵심 주장 6건이 schema/disposition verifier를 통과했다. 이것은 production implementation이나 법률 검토 완료를 뜻하지 않는다.
- 독립 plan-gap, UX, source→runtime 리뷰에서 실제 합성 preview, 실제 자동 편집 초안, caption timing authority, 시각 승인 순서, source lock 재현성 문제를 발견해 계획 초안의 P0/P1을 반영했다.
- 수정 뒤 세 방향 재리뷰에서 미폐쇄 P0/P1 0건을 확인했다. research evaluator는 citation 13/13, orphan 0, leak 0으로 PASS했다.

## 고정된 결정

- shadcn/ui source ownership + shadcn-admin shell partial port
- OpenCut current rewrite는 editor runtime에서 제외
- OpenCut classic은 panel/pure geometry만 selective port
- Opencast는 transcript/cue/time/cut UX를 Apache-2.0 attributed behavioral adaptation
- Supabase는 IA reference only
- editing-session/revision/FFmpeg/PyCapCut는 계속 authoritative
- Hermes와 실제 SaaS auth/team/billing은 이번 22개 Task 밖
- current revision의 exact preview는 기존 FFmpeg composition path를 재사용한 proxy artifact
- caption timing은 segment-linked이며 independent cue timing은 후속 범위
- 핵심 `대본→인터뷰→자산 점검→atomic real draft`는 advanced timeline보다 먼저 검증

## 현재 작업 트리 주의

계획 작성 시작 전부터 Lumi copy implementation 변경이 worktree에 남아 있다. 이 변경을 되돌리거나 새 shell 코드와 섞으면 안 된다. 새 계획 Task 1은 해당 변경의 focused test/build failure를 재현하고 논리적으로 closeout해 baseline commit을 만드는 작업이다. Task 2는 production shell 코드 전에 세 화면/네 viewport visual prototype의 사용자 승인을 받는 gate다.

2026-07-17 planning-time 확인 결과는 focused 3파일 `17 passed`, production build TypeScript 오류 5건이다. 오류 위치는 `director-history-controls.test.tsx`의 nullable fixture와 `user-copy-policy.test.ts`의 Node type, JSX AST name, `ImportMeta.dirname` 사용이다.

## 다음 goal prompt

```text
goal 명령으로 다음 목표를 시작해줘.

VideoBox OSS Dashboard and Editor Adoption 계획서의 Slice 0 Task 1을 서브에이전트 드리븐 TDD로 끝까지 수행하라.

기준 문서:
- docs/superpowers/plans/2026-07-17-videobox-oss-dashboard-editor-adoption.md
- docs/superpowers/specs/2026-07-17-videobox-oss-dashboard-editor-adoption-design.md
- docs/research/2026-07-17-videobox-oss-dashboard-editor-adoption.ko.md
- docs/handoffs/2026-07-17-videobox-oss-dashboard-editor-adoption-plan-closeout.ko.md

범위:
- 현재 HEAD/upstream/worktree와 기존 Lumi copy dirty scope를 먼저 고정
- 기존 focused TypeScript/test/build failure를 RED로 재현
- user-copy policy와 Director/Lumi component tests를 의미 약화 없이 GREEN으로 복구
- legacy project/select/navigation/Director/manual/preview/output/settings behavior baseline test 추가
- focused suite, full frontend suite, production build, diff/status 검사
- 독립 코드리뷰, 계획 gap 검증, source→runtime 역방향 검증
- Task 1 checkbox와 SSOT 누적 진행률 갱신
- Lumi copy + baseline만 논리적으로 commit하고 push

제약:
- 아직 Tailwind/shadcn/router/OpenCut 코드를 도입하지 말 것
- 기존 dirty 변경을 되돌리거나 새 범위와 섞지 말 것
- external/Gemini provider call은 0을 유지할 것

완료 조건:
- RED가 현재 결함을 재현하고 GREEN이 닫음
- frontend full test와 production build 통과
- Task 1만 완료 처리
- commit/push SHA와 다음 Task 2 goal prompt 보고
```
