# VideoBox Task 22C3 canonical output closeout handoff

## 쉬운 요약

출력 화면을 하나로 정리했다. 이제 자막, 완성본, CapCut 초안과 등록 상태는 canonical `/outputs` 화면이 맡고, 실제 영상 재생은 편집 화면의 한 플레이어에서만 한다.

예전 편집본의 승인이나 산출물이 최신처럼 보이지 않도록 프로젝트·타임라인·수정번호를 모두 확인한다. 작업 중 새로고침을 눌러도 같은 출력을 두 번 만들도록 유도하는 오래된 성공/실패 메시지가 남지 않는다.

## 이번 실제 범위

- canonical output route/component/E2E owner와 9-row parity inventory
- exact preview 상태 참조와 one-player ownership
- current session/revision에 묶인 subtitle/final/CapCut draft/handoff
- stale/historical output와 unknown project route의 fail-closed recovery
- legacy `preview_render`/`exportCapcut`의 canonical production reachability 제거
- local/test 외부 provider call 0 경계

## 음악과 효과음

- BGM library preview/materialize/apply와 BGM fade/gain/ducking 편집, SFX apply/edit/clear 및 timeline lane 자동 테스트는 이전 Task 19/22C1 범위에 있다.
- 실제 사용자 샘플 dogfood에서는 로컬 합성 BGM 220 Hz와 SFX 880 Hz를 서로 다른 구간에 적용하고 exact-preview AAC에서 주파수를 역방향 확인했다.
- 이 자동 증거는 사람이 실제로 듣고 자연스러움을 판단한 결과나 실제 CapCut Desktop 실증은 아니다.

## 검증

- focused frontend: `3 files / 90 passed`
- full frontend: `63 files / 726 passed`
- output/product-shell Playwright E2E: `14 passed`
- snapshot manifest verifier: passed
- TypeScript `tsc --noEmit`: passed
- production build: passed
- Editor UI OSS provenance verifier: passed
- Editor UI system verifier: passed
- external-runtime/network guard: `2 files / 6 passed`
- `git diff --check`: passed
- independent spec/quality/gap/reverse review: Critical/Important/Moderate 0
- 전체 Python regression은 실행하지 않았으며 통과라고 주장하지 않는다.

기존 React `act(...)`, jsdom navigation, intentional ErrorBoundary stderr와 500 kB bundle warning은 exit 0인 비실패 출력이다.

## 보호 상태

- `?? .tmp-final-fence-debug/`
- `?? .tmp-real-video-dogfood/`
- `?? apps/web/.tmp-real-video-dogfood/`
- `C:\Users\atgro\OneDrive\바탕 화면\영상샘플`

위 항목은 stage/remove/delete하지 않는다.

공식 누적은 사용자 지시대로 **9/22 (40.9%)**, 잔여 **59.1%**다. Task 9 사람/환경 acceptance와 실제 CapCut Desktop 실증은 별도다.

## 다음 goal prompt

`VideoBox만 작업해. D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility와 codex/videobox-container-compatibility만 사용해. 먼저 AGENTS.md, docs/development-fast-path.ko.md §10, docs/development-status-2026-06-29.ko.md §298, docs/superpowers/plans/2026-07-23-videobox-task22-release-parity.md, 이 handoff를 읽고 branch/HEAD/upstream/status/worktree/diff-check를 확인해. 보호된 임시 폴더 3개와 사용자 원본 샘플은 절대 stage/remove/delete하지 마. 다음은 Task 22D legacy owner removal이다. parity owner matrix를 먼저 GREEN으로 재확인하고 rg와 UI-system AST inventory로 실제 도달성을 조사한 뒤에만 legacy App.tsx, legacy CSS/components/tests, 격리 output adapter를 삭제해. canonical route와 persisted-data reader는 보존하고 package/scripts의 legacy test 참조도 TDD로 정리해. independent spec/quality/gap/reverse review 뒤 focused/full frontend, canonical E2E, build, provenance/UI/network/legacy-class 검증을 통과시키고 22E/F release audit로 이어가. 전체 Python regression은 실행하지 않았으면 통과라고 주장하지 마. Task 9 사람/환경 acceptance와 실제 CapCut Desktop 실증은 별도이며 공식 누적 9/22 (40.9%), 잔여 59.1%를 유지해.`
