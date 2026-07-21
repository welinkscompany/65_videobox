# VideoBox Task 14 written-design handoff — 2026-07-22

## 재개 위치

- worktree: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility`
- branch: `codex/videobox-container-compatibility`
- handoff HEAD: `eeca108ab` (`docs: define Task 14 timeline geometry`), origin upstream과 동기화됨.
- Task 11 사용자 시각 승인 기록: `7c06bb4c5` (`docs: record Task 11 visual approval`). 승인 manifest, decision marker, 다섯 PNG SHA, visible `편집본 미리보기` source 검증이 맞는다.
- Task 14 written design: `docs/superpowers/specs/2026-07-22-videobox-task14-timeline-geometry-design.md`.

## 확정된 Task 14 범위

- 순수 TypeScript 네 모듈만 만든다: `time-scale.ts`, `timeline-geometry.ts`, `snapping.ts`, `hit-testing.ts` 및 각각의 focused test.
- API seconds가 canonical이다. `30000/1001` rational FPS와 half-up frame quantization은 `time-scale.ts` 한 곳만 담당한다.
- Task 14는 UI navigation, pointer handler, React state, DOM/canvas, API/`EditorCommandPort`, editing-session mutation을 만들지 않는다. 이는 Task 15·16 범위다.
- output/SAR/rotation/crop은 timeline geometry input이 아니다. preview playback/caption timing도 바꾸지 않는다.
- OpenCut classic은 MIT pin `cf5e79e919144200294fb9fed22a222592a0aeea`의 실제 pure-math inspected path와 SHA를 확인해 provenance에만 기록한다. source를 복사하지 않고, EditorCore/DB/renderer/Next/IndexedDB/OPFS/browser-export import를 금지한다.

## 필수 재개 gate

사용자는 설계 대화에서 Task 14 방향을 승인했지만, skill 절차상 **committed written spec의 검토·승인**은 아직 받지 않았다. 다음 세션의 첫 사용자 입력으로 다음 한 줄 승인을 받기 전에는 implementation plan이나 production source를 만들지 않는다.

```text
Task 14 written spec 승인. 구현 계획과 TDD 개발을 시작해.
```

승인 뒤에는 `writing-plans` skill로 구체 실행 계획을 작성·self-review하고, user가 선택한 subagent-driven 방식으로 TDD를 진행한다.

## 검증과 미검증 경계

- Task 11 approval correction: `.venv\Scripts\python.exe -m pytest -q tests/test_editor_workbench_artifacts.py tests/test_editor_ui_source_provenance.py` → `16 passed`, 기존 multipart PendingDeprecationWarning 1.
- editor workbench isolated Playwright: `8 passed`.
- Task 14는 아직 source/test가 없으므로 Task 14 focused/frontend/build/provenance 검증은 아직 실행하지 않았다.
- exact-preview latest evidence: affected runtime `172 passed`, cold `387.5ms`, warm `83.2ms`, production build 및 exact-preview E2E `5 passed`였으나, 전체 Python regression은 **미검증**이다.

## 남겨 둔 상태

- `?? .tmp-final-fence-debug/`는 이전 exact-preview debugging에서 남은 untracked 잔재다. 범위 밖이며 삭제 시도는 정책상 실행 전 차단됐으므로 stage/commit하지 않는다. 따라서 worktree는 literal clean이 아니다.
- Hermes Dashboard/provider/Mem0 설정은 보류다. API key를 채팅·Git·문서에 기록하지 않으며, 사용자가 Dashboard UI에서 직접 입력하기 전에는 연결 성공·memory write·GPT request를 주장하지 않는다.
- Task 9 사람/환경 acceptance는 실제 두 번째 scene MP4, current-revision 사람 승인, 같은 revision의 CapCut Desktop 등록·열기·import 증빙 전까지 열려 있다. 공식 누적은 **9/22 (40.9%)**를 유지한다.

## 다음 세션 복붙 프롬프트

```text
VideoBox만 작업해. worktree는 D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility, branch는 codex/videobox-container-compatibility다. 다른 프로젝트는 열거나 수정하지 마.

Task 14 written spec 승인. 구현 계획과 TDD 개발을 시작해.

먼저 AGENTS.md, docs/handoffs/2026-07-22-videobox-task14-written-design-handoff.ko.md, docs/superpowers/specs/2026-07-22-videobox-task14-timeline-geometry-design.md, docs/development-fast-path.ko.md §10, docs/development-status-2026-06-29.ko.md §285, docs/implementation-plan.ko.md의 현재 next goal을 읽어.

git status --short, branch/HEAD/upstream/worktree를 확인해. ?? .tmp-final-fence-debug/는 기존 범위 밖 잔재이므로 stage/remove하지 마.

writing-plans skill로 상세 실행 계획을 만들고 self-review한 뒤, subagent-driven TDD로 pure time-scale/timeline-geometry/snapping/hit-testing만 구현해. 실제 OpenCut classic inspected path/SHA provenance를 먼저 확인하고, source copy, UI navigation, pointer handler, React/DOM/canvas, API/EditorCommandPort/mutation, Hermes/provider/Mem0 작업은 하지 마.

RED → GREEN → 독립 spec/quality/gap/source-to-runtime reverse review → focused/full frontend attempt → production build → SSOT/handoff → commit/push 순서로 진행해. 전체 Python regression은 별도 사용자 지시 없이는 실행하거나 통과로 주장하지 마. Task 9 공식 누적은 9/22 (40.9%)로 유지해.
```
