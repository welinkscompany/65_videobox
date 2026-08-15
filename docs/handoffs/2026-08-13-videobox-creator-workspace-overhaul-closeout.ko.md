# VideoBox Creator Workspace Wave 5 QA closeout

작성일: 2026-08-13
canonical worktree: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility`
branch: `codex/videobox-container-compatibility`

## 결론

자동 회귀, isolated Chromium, production build, official runtime의 제한된 브라우저 QA와 문서/provenance 게이트를 실행했다. owner acceptance는 완료하지 않았다. 실제 Hermes live chat도 gateway stopped 상태로 확인되어 별도 미검증이다.

## 자동 검증

- frontend Vitest: `66 files, 912 passed`
- backend 전체: `3454 passed, 53 skipped, 1 warning`
- provenance/handoff 재검증: `26 passed, 1 warning`
- production build: 성공. 기존 Vite chunk-size warning만 확인
- isolated Chromium: `39 passed`, snapshot manifest verified
- editor-workbench isolated Chromium: `9 passed`, snapshot manifest verified
- `git diff --check`: 통과

첫 병렬 회귀에서 frontend 1건과 backend 1건이 실패했다. frontend 실패는 단독 재실행에서 통과해 동시 실행 경쟁으로 분류했고, backend 실패는 `WinError 10055` socket exhaustion으로 단독 재현되지 않았다. 이후 frontend 전체와 backend 전체를 직렬로 다시 실행해 위 결과를 얻었다.

## Official runtime 브라우저 QA

wrapper `owner-ready.ps1 -Mode Start -Rebuild`가 현재 worktree source로 image rebuild를 완료했다. 최초 health 502 뒤 대기 후 Check에서 VideoBox health HTTP 200을 확인했다.

Chromium headless, viewport `1280x800`, official runtime `http://127.0.0.1:5173` 결과:

| route | 결과 | 관찰 |
|---|---|---|
| `/` → `/projects` | 확인 | 프로젝트 카탈로그 렌더, document width 1280 / body width 1264 |
| `/library` | 확인 | 3-pane library, document width 1280 / body width 1264, stale marker 없음 |
| `/footage` | 확인 | source list·preview·timeline·Yujin actions 4-pane, stale marker 없음 |
| project shell `/projects/project-4967a666/plan` | 확인 | 5단계 shell과 기획 surface 렌더, width 1280 |
| existing editor session | 제한 확인 | editor surface 렌더되나 기존 exact-preview resource 404 1건 |

모든 최종 checked route에서 console error와 page error는 없었다. `/footage`에서 route 전환 중 `GET /api/library/assets?limit=500` aborted 1건은 브라우저가 취소한 요청이며 HTTP 4xx/5xx는 아니었다. 상세 산출물은 ignored QA artifact인 `artifacts/qa/creator-workspace-overhaul/wave5/official_browser_qa.json`과 PNG에 남겼다.

Yujin starter의 official runtime click-flow는 기존 session이 이미 conversation/proposal 상태여서 empty starter group을 노출하지 않아 직접 확인하지 못했다. 이 범위는 route integration test와 isolated E2E로 검증했다. 테스트 증거는 starter click이 composer value/focus만 바꾸고 create/send/proposal/apply mutation을 호출하지 않음을 확인한다.

## Hermes와 owner 경계

- `127.0.0.1:9119/api/status`: HTTP 200, dashboard ok, `gateway_state=stopped`, overall degraded
- `127.0.0.1:9130/api/status`: HTTP 200, gateway stopped, basic auth required
- owner-ready Check의 Hermes reachability는 통과했지만 이는 dashboard HTTP preflight다.
- live chat, 완전한 프로젝트 제작, 결과물 전체 시청·청취, `결과 확인 완료` human action은 수행하지 않았다.
- 따라서 owner acceptance 완료 또는 live Hermes 연동 완료로 표현하지 않는다.

## Design coverage와 reverse checks

| 설계 영역 | 자동/isolated 증거 | official browser/owner 증거 |
|---|---|---|
| 정보 구조·desktop shell | AppRouter/ProductShell/E2E | `/projects`, project shell 1280 확인 |
| 개인 library | LibraryPage, library E2E, bounded scroll | `/library` 확인 |
| 촬영본 정리 | footage API/UI/design tests, E2E | `/footage` 4-pane 확인 |
| 자체 편집기 | editor command/workbench tests, editor E2E | 기존 editor surface 확인, preview 404 blocker 기록 |
| Yujin 제안 경계 | adapter/proposal tests, starter route test | live chat 미검증 |
| 가로·세로 변형·review/output | backend/frontend/E2E 회귀 | owner 시청 미검증 |
| 실패·복구·멱등 | full backend regression 및 reverse focused tests | runtime human flow 미검증 |
| starter pack/license/provenance | provenance/handoff 26 tests | owner evidence 없음 |

Reverse/failure evidence는 stale footage proposal, preview/cancel 무변경, approval idempotency, source hash 보존, invalid/stale identity fail-closed, Yujin zero-effect starter, output sibling failure isolation 테스트를 포함한다. 사람의 실제 시청·업무 적합성은 automated evidence로 대체하지 않는다.

## 재사용·경계 보존

- 기존 ProductShell/editor/workbench, proposal preview→explicit apply, local SQLite/project store, Playwright isolation harness를 재사용했다.
- 이번 closeout에서 제품 runtime 권한, Hermes gateway, DB schema, FFmpeg, filesystem mutation 경계를 확장하지 않았다.
- `ProductShell.tsx` source-map normalized hash를 현재 파일과 맞추고 최신 handoff pointer를 갱신했다.
- 모바일 전문 편집기, CapCut 필수화, 자동 적용, owner source 변경은 수행하지 않았다.

## 남은 blocker

1. Hermes gateway가 stopped라 live chat proof가 없다.
2. owner-approved input을 사용한 새 dedicated QA project와 전체 제작·출력·시청은 owner 부재로 수행하지 않았다.
3. 기존 editor session에서 exact-preview artifact 404가 관찰되어 결과 미리보기는 해당 session 상태에서 확인이 필요하다.
4. native Python Playwright package가 없어 official QA는 설치된 Node Playwright로 대체했다. isolated Chromium 결과와 구분한다.

이 문서는 자동 검증과 확인 가능한 runtime 범위를 닫지만 owner acceptance를 대신하지 않는다.
