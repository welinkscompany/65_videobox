# VideoBox Task 21 release-hardening closeout

## 닫은 범위

- `npm run test:e2e`와 `npm run test:e2e:editor-workbench`는 명시 override를 보존하면서 매번 독립 loopback web/fake-API port를 배정한다.
- 모든 Playwright browser spec은 navigation 전 loopback/data/blob-only network gate를 설치한다. remote origin은 browser에서 abort되고 test teardown에서 violation을 fail한다.
- 일반 검증은 화면을 캡처하지만 tracked PNG를 쓰지 않는다. `VIDEOBOX_WRITE_PLAYWRIGHT_SNAPSHOTS=1`일 때만 사람이 검토할 갱신 산출물을 쓰며, manifest는 exact PNG set/viewport/bytes/SHA-256을 검증한다.
- current Chromium `149.0.7827.55`, `chromium-headless-workers-1-1920x1080`의 right-dock drag warm-up 1회 + sample 5회 기준으로 median 92 ms/p95 108 ms baseline을 기록했다. 같은 profile에서 median 20% 회귀와 structural error는 fail한다.
- `/projects/:projectId/editing`은 canonical `/projects/:projectId/editor`로 session query를 보존해 redirect한다. 이 URL에서 legacy App은 mount하지 않는다.

## 검증

- full frontend: `52 files / 506 tests passed`.
- ordinary no-env E2E: `28 passed`, capture 뒤 manifest verifier 통과.
- focused editor E2E: `8 passed`, manifest verifier 통과.
- production build, Editor UI OSS provenance verifier, UI-system verifier, `git diff --check` 통과.
- 전체 Python regression은 실행하지 않았다. React `act(...)`, jsdom navigation, intentional ErrorBoundary stderr와 500 kB bundle warning은 exit 0의 기존 비실패 출력이다.

## 남은 Task 22 경계

legacy `App.tsx`는 job recovery, voice/TTS, subtitle/final render, CapCut output/handoff를 아직 실제로 소유한다. 새 output/voice/recovery route와 tests/E2E가 parity를 증명하기 전에는 legacy route/CSS를 삭제하지 않는다. Task 9 사람/환경 acceptance와 실제 CapCut Desktop 실증도 별도다.

`?? .tmp-final-fence-debug/`는 stage/remove/delete하지 않는다. 공식 누적은 **9/22 (40.9%)**, 잔여 **59.1%**를 유지한다.

## 다음 goal prompt

`VideoBox만 작업해. worktree D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility, branch codex/videobox-container-compatibility만 사용해. 먼저 AGENTS.md, docs/development-fast-path.ko.md §10, docs/development-status-2026-06-29.ko.md의 §294, 이 handoff와 Task 22 plan을 읽고 git status/HEAD/upstream/worktree/diff를 확인해. ?? .tmp-final-fence-debug/는 절대 stage/remove/delete하지 마. Task 22는 legacy App을 지우지 말고 output/job recovery/voice-TTS/subtitle/final/CapCut UI의 route parity와 tests를 하나씩 만든 뒤 legacy URL/CSS removal을 판단해. 일반 E2E는 npm --prefix apps/web run test:e2e를 사용해 자동 loopback port와 post-capture manifest verifier를 유지해. 전체 Python regression은 실행하거나 통과로 주장하지 마. Task 9 사람/환경 acceptance와 CapCut Desktop 실증은 별도이며 공식 누적은 9/22 (40.9%), 잔여 59.1%로 유지해.`
