# VideoBox Hermes Dashboard Platform Mem0 handoff — 2026-07-20

## 현재 결과

- 작업 저장소: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility`
- 브랜치: `codex/videobox-container-compatibility`
- 공식 Hermes Dashboard는 `nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787`으로 기동한다.
- 로컬 접근 주소는 `http://127.0.0.1:9119`이며, 2026-07-20 HTTP `200`과 `HERMES_DASHBOARD_READY`를 확인했다.
- 대시보드는 `videobox-hermes-provider-egress`만 사용하며 VideoBox DB·API·media·internal/edge network 및 별도 local memory network에 연결하지 않는다.
- `a5f8fd2`에서 custom runtime/seed source와 전용 Compose 경계를 삭제했다. `b776820`에서 OAuth bootstrap verifier image를 Compose와 일치시켰다.
- 과거 종료 custom runtime 컨테이너는 source cleanup 범위 밖의 사용자 소유 runtime artefact이므로 삭제하지 않았다.
- 이후 `2096043e2`→`ffbd77be`에서 Task 11 읽기 전용 editor workbench의 기술 구현·검증은 끝냈고, `c6890becd`→`82f11e106`/`dd570bbea`에서 Task 12·13 exact FFmpeg preview와 PreviewStage의 기술 구현을 완료했다. Hermes 설정은 사용자가 명시적으로 재개하기 전까지 보류한다.

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

## Task 12·13 exact preview 기술 검증 기록

- exact preview는 current editing-session revision에 fenced 된 FFmpeg H.264/AAC faststart MP4이며, source/revision 변화 뒤 stale artifact는 재생 URL을 잃고 Range delivery도 거부한다. full/selected-range proxy는 같은 composition plan을 사용하고 captions는 burned ASS만 사용한다. preview 생성은 review approval, final output, CapCut handoff를 바꾸지 않는다.
- 브라우저 PreviewStage는 current artifact 하나만 mount한다. pending/failed/stale에는 재생 대신 refresh recovery를 보이고, source audition은 exact player를 대체하지만 합성 편집본이라고 주장하거나 autoplay하지 않는다. `apps/web/e2e/exact-preview.spec.mjs`가 current seek mapping, pending, stale revision, failed retry, audition/exact 전환을 `5 passed`로 확인했다.
- fresh verification: actual 10초 1280×720 local fixture cold `472.5ms`(≤20초), warm `84.3ms`(≤500ms); focused backend/API/real FFmpeg/edit-session `102 passed`(기존 multipart warning 1); frontend full `37 files / 335 tests passed`; production build; isolated editor workbench Playwright `8 passed`; provenance verifier와 `git diff --check` 통과. build의 500 kB chunk 안내와 기존 React `act(...)`/JSDOM stderr는 비차단 경고다.
- 이번 slice의 전체 Python regression은 실행하지 않았다. 이전 사용자 중단 상태를 존중해 full-pass를 주장하지 않으며 **미검증**으로 남긴다. Task 9 사람/환경 acceptance와 Task 11 사용자 시각 승인은 그대로 pending이고, 공식 checkbox/누적은 **9/22 (40.9%)**를 유지한다.

### 2026-07-21 final publish-fence 보강

- `b781540ca`→`e27049fba`와 후속 bounded fence는 final renderer/exact preview가 base/override B-roll·BGM·SFX, export overlay와 virtual narration segment가 읽는 `narration_source_uri`의 모든 실제 project asset을 capture/revalidate하도록 확장했다. 기존 SHA/revision field가 없는 legacy clip도 현재 digest/revision을 snapshot한다. `/segments/` URI는 narration track에서만 허용하며, 논리 asset URI는 asset ID/project로, direct storage URI는 등록된 project asset 역매핑으로 검증하고 어느 쪽도 아니면 fail-closed다.
- full SHA 재검증과 completed MP4 copy/staging은 writer lock 전에 한 번만 수행한다. durable publish는 precomputed revalidation·session CAS·size/mtime quick check·atomic rename·DB pointer만 하므로, controlled slow rehash/copy 중 concurrent editing-session mutation이 완료되고 old preview가 obsolete 되는 회귀를 보장한다.
- fresh affected runtime `172 passed`(기존 multipart warning 1), 10초·1280×720 local fixture cold `387.5ms`(≤20초), warm `83.2ms`(≤500ms). 이번 최종 verification에서는 frontend production build와 exact-preview E2E `5 passed`를 다시 실행했지만, 전체 Python regression은 **미검증**이다. Task 9은 실제 MP4/사람 승인/CapCut Desktop 증빙 전까지, Task 11은 두 번째 사용자 시각 승인 전까지 계속 열려 있으며 누적은 **9/22 (40.9%)**다.

## 2026-07-22 Task 11 사용자 승인 기록

- 사용자가 Task 11 편집기 UI를 명시 승인했다. 다섯 deterministic screenshot의 manifest와 연결 승인 기록은 `approved` 상태로 동기화된다.
- Task 11은 완료로 기록하며, 독립 Task 9 사람/환경 acceptance는 그대로 열려 있다. 사용자가 고정한 공식 누적은 **9/22 (40.9%)**, 잔여 **59.1%**를 유지한다.
- Task 14는 UI mutation이나 provider 설정 없이 pure timeline geometry/frame-safe scaling 계약만 TDD로 시작한다.

## 다음 세션 첫 작업

1. Hermes Dashboard/provider 설정은 보류한다. 사용자가 명시적으로 재개할 때만 `docker compose -p 65_videobox ps -a`와 `http://127.0.0.1:9119`를 다시 확인한다.
2. Task 14의 pure time-scale/geometry/snapping/hit-test 설계를 사용자 승인받은 뒤 TDD로 구현한다. UI interaction/navigation/mutation은 Task 15·16 범위로 남긴다.
3. Task 9 수동 acceptance는 실제 장면 MP4와 사람 승인 증빙 전까지 계속 별도 gate다.
