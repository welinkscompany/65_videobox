# VideoBox Wave2 중단 핸드오프

## 중단 기준

- 브랜치: `codex/videobox-container-compatibility`
- 구현 기준 커밋: `41f89ce44` (촬영본 UI·preview/sequence·디자인 토큰 계약 포함)
- 최신 핸드오프 커밋: 이 문서 변경을 반영할 새 커밋으로 갱신한다.
- 작업 디렉터리: clean
- 다음 세션은 반드시 이 worktree와 브랜치에서 시작한다.

## 완료된 범위

- `/api/footage` 제안 조회·편집·미리보기·승인
- proposal revision 충돌 및 승인 후 재수정 차단
- virtual sequence 생성·재정렬·승인·멱등 재시도
- preview/cancel 무변경
- 다중 구간 파생 렌더 순서 보장
- 원본 덮어쓰기 방지 및 derived asset 등록
- 승인 proposal의 source segment를 `footage_segment_index_queue`에 원자적으로 등록
- 승인된 source segment를 `footage_index`와 `/api/library/search` semantic 경로에 등록
- 부모 임베딩이 없을 때 segment 단위 pending indexer로 후속 임베딩
- managed 파일 SHA 불일치 시 색인·ack를 수행하지 않는 fail-closed 보호

## Wave2 Task4/4A 완료

- 촬영본 정리 4-pane UI: source list, preview/파형, 장면 timeline, 유진 제안/actions
- 실제 range-aware preview artifact 생성·serve, renderer 실패 시 503 fail-closed
- Shift 다중 장면 선택, virtual sequence 생성·선택 항목 reorder
- 편집 후 preview 무효화와 선택 segment remap, 재생 위치·timeline 동기화
- 촬영본 CSS를 semantic color/ring/radius 토큰으로 정리하고 editor actions 40px 계약 고정
- 관련 spec/quality review 승인: P1 없음

## 디자인 시스템 어댑터

- 명세: `docs/superpowers/specs/2026-08-13-videobox-design-system-adapter.ko.md`
- 계약 테스트: `tests/test_videobox_design_system_adapter_contract.py`
- `intranet-style` 토큰·프리미티브를 상속하되, VideoBox는 shell/editor 조작 높이와 미디어 밀도를 역할별로 오버라이드한다.
- `ui-inspector`/브라우저 시각 QA는 신규 촬영본 화면부터 적용한다.

## 검증

- `tests/test_api_footage_organizer.py`
- `tests/test_footage_organizer_store.py`
- `tests/test_footage_organizer.py`
- `tests/test_api_media_library.py`
- 결과: backend footage API `9 passed`, frontend footage/AppRouter `38 passed`, design contract `4 passed`
- production build: 통과(기존 Vite chunk-size warning만)
- `compileall`: 통과
- `git diff --check`: 통과

## Wave2 Task5 owner 브라우저 게이트 (2026-08-12)

- 기준 worktree/branch: canonical `.worktrees/videobox-container-compatibility` / `codex/videobox-container-compatibility`, `HEAD=41f89ce44`, upstream과 동기화됨.
- `scripts/owner-ready.ps1 -Mode Check -Json -TimeoutSec 8`: VideoBox health는 `HTTP 200`, local model은 pass, 외부 호출은 0건이었다. Hermes dashboard `127.0.0.1:9119`는 `connection_refused`로 blocked되어 live Hermes 승인 증거를 만들 수 없었다.
- 실제 실행 중인 `http://127.0.0.1:5173` 컨테이너를 Chromium headless, `1280x800`에서 확인했다. `/`는 프로젝트 카탈로그가 `200`으로 열렸지만 `scrollWidth=1350 > clientWidth=1280`의 가로 overflow가 있었다. `/library`와 `/footage`는 현재 source의 Wave 화면이 아닌 이전 이미지의 placeholder 문구를 `200`으로 표시했다. console/page error와 HTTP 4xx/5xx는 관찰되지 않았지만, 이는 runtime image가 `41f89ce44` source와 불일치한다는 증거이지 owner UI 합격이 아니다.
- 정확한 source를 임시 Vite `:5199`로 띄우고 API를 Playwright route-mock한 별도 검증에서는 `/footage` 네 창이 `1280x800`에 렌더링되었고 `scrollWidth=1280`, `scrollHeight=816`이었다. 촬영본 선택 → 분석 → 2개 장면 타임라인 → 제안 미리보기 흐름이 동작했고 preview URL이 `/api/footage/sources/source-1/preview?ranges=...`로 바뀌었으며 alert/console error가 없었다. 이 결과는 source-level browser evidence이며 실제 owner runtime 증거와 분리한다.
- 기존 isolated Playwright `library-workspace.spec.mjs` + `product-shell.spec.mjs`는 `16 passed`(library bounded/lifecycle/1000-row, shell viewport 포함)였다. 이는 fake/isolated API 검증이다.
- 임시 시각 산출물: `C:\Users\atgro\AppData\Local\Temp\videobox-live-library-stale.png`, `C:\Users\atgro\AppData\Local\Temp\videobox-live-footage-stale.png`, `C:\Users\atgro\AppData\Local\Temp\videobox-owner-footage.png`, `C:\Users\atgro\AppData\Local\Temp\videobox-owner-footage-after-analysis.png`, `C:\Users\atgro\AppData\Local\Temp\videobox-owner-footage-after-preview.png` (저장소에는 추가하지 않음).
- 결론: 이번 게이트에서는 owner acceptance를 주장하지 않는다. 정확한 `41f89ce44`로 컨테이너 이미지를 rebuild/restart하고, Hermes dashboard가 loopback에서 reachable해진 뒤 같은 viewport/flow를 다시 실행해야 한다.

## Wave2 Task5 owner-ready 재시도 (2026-08-12)

- `scripts/owner-ready.ps1 -Mode Start -Json -TimeoutSec 8`: exit 0 / overall pass. `videobox-postgres`와 `videobox-workspace`를 기동했고 VideoBox health는 HTTP 200이었다.
- 이어서 `scripts/owner-ready.ps1 -Mode Check -Json -TimeoutSec 8`: VideoBox, local model, Docker/compose, workspace, CapCut 검사는 통과했다. 유일한 blocker는 Hermes dashboard `127.0.0.1:9119`의 `connection_refused`였다.
- 따라서 Start 성공을 owner acceptance로 해석하지 않는다. 다음 재시도 조건은 Hermes dashboard를 명시적으로 기동한 뒤 Check를 다시 실행하는 것이다. 동일한 9119 blocker를 의미 없이 반복하지 않는다.

## Wave2 Task5 owner 브라우저 gate 상태

- source Vite + route-mocked Playwright에서는 `/footage` 1280×800 4-pane, 분석→2개 장면→range preview 흐름이 성공했다.
- isolated Playwright library/shell suite는 `16 passed`였다. 이는 fake/isolated API 증거이며 owner acceptance가 아니다.
- 실제 `127.0.0.1:5173`은 `/library`·`/footage`에 구형 placeholder를 제공해 최신 `41f89ce44` source와 runtime image가 불일치했다.
- `scripts/owner-ready.ps1 -Mode Check -Json -TimeoutSec 8`: VideoBox health 200, worktree clean, Hermes dashboard `127.0.0.1:9119`는 `connection_refused`로 blocked.
- 다음 gate는 정확한 branch 기준으로 컨테이너 image rebuild/restart 후 같은 viewport/flow를 재실행하고, Hermes dashboard가 reachable한 상태에서 owner acceptance를 확인하는 것이다.

## 아직 하지 않은 것

- 실제 owner-ready 컨테이너 브라우저 승인 및 owner 시청 확인
- `/footage` ProductShell 외부 라우팅 P2 drift의 최종 제품 결정
- Wave2 유진 제안 어댑터
- Wave3 편집기·가로/세로 변형
- Wave4 검토·독립 출력
- Wave5 최종 owner 미디어 시청 및 closeout

## 다음 세션 시작 프롬프트

```text
VideoBox Creator Workspace 작업을 이어간다. 반드시 canonical worktree
D:\\AI_Workspace_louis_office_50\\10_workspace\\65_videobox\\.worktrees\\videobox-container-compatibility
와 branch codex/videobox-container-compatibility에서 시작해라.

먼저 git status -sb와 git rev-parse HEAD를 확인하고, 이 핸드오프 문서를 읽어라. 구현 기준은 41f89ce44이며, 최신 핸드오프 커밋은 이 문서의 현재 HEAD로 확인한다.

Wave2 Task4/4A는 구현·리뷰·push까지 완료됐다. 첫 작업은 Hermes dashboard를 명시적으로 기동할 수 있는지 확인하고 owner-ready Check를 재실행하는 것이다. 9119가 reachable해지면 정확한 branch source로 runtime image를 rebuild/restart한 뒤 1280×800 이상에서 `/`, `/library`, `/footage`, project shell을 실제 브라우저로 검증해라. stale placeholder가 보이면 최신 source와 runtime image 불일치로 기록하고 owner 승인으로 표현하지 마라.

절차는 runtime preflight → 실제 브라우저/ui-inspector 검증 → console/network/overflow/focus 확인 → owner acceptance 기록이다. 자동/fake E2E 통과를 실제 owner 승인으로 표현하지 마라. owner gate가 통과되면 다음은 Wave2 유진 제안 어댑터이며, 이후 Wave3 editor로 진행한다.
```
