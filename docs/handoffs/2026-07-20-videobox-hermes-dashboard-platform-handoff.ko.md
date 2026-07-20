# VideoBox Hermes Dashboard Platform Mem0 handoff — 2026-07-20

## 현재 결과

- 작업 저장소: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility`
- 브랜치: `codex/videobox-container-compatibility`
- 공식 Hermes Dashboard는 `nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787`으로 기동한다.
- 로컬 접근 주소는 `http://127.0.0.1:9119`이며, 2026-07-20 HTTP `200`과 `HERMES_DASHBOARD_READY`를 확인했다.
- 대시보드는 `videobox-hermes-provider-egress`만 사용하며 VideoBox DB·API·media·internal/edge network 및 별도 local memory network에 연결하지 않는다.
- `a5f8fd2`에서 custom runtime/seed source와 전용 Compose 경계를 삭제했다. `b776820`에서 OAuth bootstrap verifier image를 Compose와 일치시켰다.
- 과거 종료 custom runtime 컨테이너는 source cleanup 범위 밖의 사용자 소유 runtime artefact이므로 삭제하지 않았다.
- 이후 `2096043e2`→`ffbd77be`에서 Task 11 읽기 전용 editor workbench의 기술 구현·검증은 끝냈다. Hermes 설정은 사용자가 명시적으로 재개하기 전까지 보류한다.

## Mem0 설정 경로

Hermes Dashboard에서 다음만 수행한다.

1. `Memory Provider`를 연다.
2. `mem0`을 고른다.
3. `Platform`을 고른다.
4. Mem0 Platform API key를 **대시보드에만** 입력하고 연결 상태를 확인한다.

채팅·Git·문서에 API key를 기록하지 않는다. 이 handoff 시점에는 API key 입력, memory write, GPT provider request는 아직 증빙하지 않았다.

## 검증 결과

- `.venv\Scripts\python.exe -m pytest -q tests/test_compose_contract.py tests/test_platform_only_hermes_dashboard_contract.py`: `8 passed`, 기존 multipart PendingDeprecationWarning 1건.
- dummy process environment Compose config와 실제 Dashboard의 pinned image·`/opt/data` 단일 mount·provider egress 단일 network 검증: 통과.
- `http://127.0.0.1:9119/`: HTTP `200`.
- `.venv\Scripts\python.exe -m pytest -q`: `1324 passed, 20 skipped`, 기존 multipart PendingDeprecationWarning 1건.
- `npm --prefix apps/web run build`: 통과. 기존 500 kB chunk 안내는 비차단 경고다.
- 독립 spec/quality review: Critical 0 / Important 0. `git diff --check`: 통과.

## Task 11 시각 승인 대기

- five viewport screenshot은 [1920](/D:/AI_Workspace_louis_office_50/10_workspace/65_videobox/.worktrees/videobox-container-compatibility/apps/web/e2e/snapshots/editor-workbench-1920x1080.png), [1440](/D:/AI_Workspace_louis_office_50/10_workspace/65_videobox/.worktrees/videobox-container-compatibility/apps/web/e2e/snapshots/editor-workbench-1440x900.png), [1280](/D:/AI_Workspace_louis_office_50/10_workspace/65_videobox/.worktrees/videobox-container-compatibility/apps/web/e2e/snapshots/editor-workbench-1280x800.png), [768](/D:/AI_Workspace_louis_office_50/10_workspace/65_videobox/.worktrees/videobox-container-compatibility/apps/web/e2e/snapshots/editor-workbench-768x1024.png), [390](/D:/AI_Workspace_louis_office_50/10_workspace/65_videobox/.worktrees/videobox-container-compatibility/apps/web/e2e/snapshots/editor-workbench-390x844.png)에 있다.
- 현재 상태는 `approval_required`다. 사용자의 두 번째 명시적 시각 승인 전에는 Task 11 완료 및 누적 진행률 변경을 하지 않는다. Task 9도 **9/22 (40.9%)** 그대로다.

## 다음 세션 첫 작업

1. Hermes Dashboard/provider 설정은 보류한다. 사용자가 명시적으로 재개할 때만 `docker compose -p 65_videobox ps -a`와 `http://127.0.0.1:9119`를 다시 확인한다.
2. 사용자가 다섯 Task 11 시안을 명시 승인 또는 수정 요청한다. 승인 전에는 `docs/prototypes/2026-07-20-editor-workbench/manifest.json`의 pending 상태를 바꾸지 않는다.
3. 승인 기록 뒤 공식 Task 12 revision-bound exact FFmpeg proxy preview를 새 TDD slice로 시작한다. Task 9 수동 acceptance는 실제 장면 MP4와 사람 승인 증빙 전까지 **9/22 (40.9%)**를 유지한다.
