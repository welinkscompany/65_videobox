# VideoBox Hermes Yujin final technical closeout

작성일: 2026-07-30

worktree: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility`

branch: `codex/videobox-container-compatibility`

## 결론

Hermes Yujin 20-task initiative의 non-live 기술 구현과 F1 통합 검증을
완료했다. 현재 RightDock에서 지속 대화, 지원되는 typed 추천, 명시적
Apply, 단일 PreviewStage, dashboard 운영, 승인형 Hermes 보조기억을
사용할 수 있으며 각 보조 경로 장애 시 기존 대화·수동 편집 fallback을
유지한다.

## F1에서 추가로 닫은 gap

- memory candidate source는 같은 project+conversation의 completed Hermes
  run exact user/assistant message만 허용한다. 다른 상태와 legacy message는
  candidate·audit 전에 거부한다.
- 후보 생성 뒤 최신 list operation이 이전 initial list를 supersede해
  candidate/action/draft/conversation scroll을 보존한다.
- SQLite D2 migration은 exact duplicate-column 경쟁만 schema 재확인 뒤
  수용하고 다른 오류는 전파한다.
- API fixture의 synthetic pending 창을 제거해 50ms orphan recovery와의
  간헐 경쟁을 없앴다.
- 자동 create/approve/store/apply/provider write는 없고 모든 durable
  변경은 기존 명시적 사용자 경로를 따른다.

## 최종 검증

- F1 focused backend: `920 passed, 1 skipped`
- 전체 Python: `2640 passed, 47 skipped`
- memory aggregate: `81 passed`
- API file: `14 passed`를 5회 반복
- former flaky test: `20/20`
- frontend focused: `4 files / 183 passed`
- 전체 frontend: `52 files / 725 passed`
- 자동 Chromium editor E2E: `35/35`
- production frontend build: PASS
- Editor UI source provenance/UI-system: PASS
- external-runtime/network/UI: `3 files / 8 passed`
- disposable PostgreSQL 16 Yujin-memory: `6 passed, 38 deselected`
- SQLite migration: `3 passed`, D2 concurrency `10/10`
- Hermes runtime/profile/plan static verifier: PASS
- non-live Mem0 smoke: `network_calls=0 provider_calls=0`
- CycloneDX SBOM: `1.6`, `341 components`, `348 dependencies`
- independent spec/quality/gap/reverse review:
  `Critical 0 / Important 0 / Minor 0`, PASS
- `git diff --check`: PASS

기존 Starlette multipart warning 1건, React `act(...)`, jsdom navigation,
intentional ErrorBoundary stderr, E2E color warning, 500kB bundle warning,
SBOM의 documented optional-WASM npm tree 출력은 비실패 출력이다.

## 실행하지 않은 live·사람 검증

- 실제 Hermes/provider live chat
- 실제 Mem0 provider add/search/delete canary
- 브라우저 사람 E2E
- 사용자 원본 영상 재생·청취
- CapCut Desktop 사람 검증
- Task 9 사람/환경 acceptance

위 항목은 통과로 주장하지 않는다.

## 상태와 다음 goal

- Hermes Yujin initiative: `20/20 (100.0%)`, 잔여 `0.0%`
- Mem0 child: `5/5 (100.0%)`
- 기존 VideoBox 공식 누적: `9/22 (40.9%)`, 잔여 `59.1%`

다음 goal은 사용자가 데스크톱 환경으로 복귀한 뒤 owner dogfood와 Task 9
사람/환경 acceptance를 수행하는 것이다. 그 전에는 실제 live provider,
사용자 원본 영상 청취·재생, CapCut 사람 검증을 완료로 올리지 않는다.
