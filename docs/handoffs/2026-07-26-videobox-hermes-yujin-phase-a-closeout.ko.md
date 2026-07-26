# VideoBox Hermes Yujin A4 구현 검증 handoff

## 쉬운 말 요약

A4의 RightDock 유진 대화 구현과 비라이브 검증은 끝났다. 사용자가 보낸 말과 유진의 최종 응답은 기존 Director conversation 저장소에서 다시 불러오며, 스트리밍 중에는 하나의 임시 assistant bubble만 갱신한다. Inspector를 닫아도 대화와 실행이 끊기지 않고, project/session route가 바뀌면 이전 route의 늦은 응답은 화면과 저장 상태를 바꾸지 못한다. 유진이 unavailable이어도 입력 초안과 기존 수동 편집 기능은 유지한다.

다만 실제 인증 정보와 승인된 provider/runtime/project/session이 없어 live canary와 실제 Hermes service stop 검증은 실행하지 않았다. 따라서 이 문서는 **구현·비라이브 gate·독립 재검토 완료, owner/상위 작업 승인 대기** 상태다. A4 체크박스와 공식 진행률은 아직 변경하지 않았다.

## 작업 위치와 보호 상태

- worktree: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility`
- branch: `codex/videobox-container-compatibility`
- 검토 보완 시작 HEAD: `92fd36418015253f90137af4bb509c30572e1a54`
- 최종 품질 보완 시작 HEAD: `4dc6d8c22be9b930dd404eedc48c0c2706112e43`
- upstream: `478b0f65bdccd51d63968cd61e61e1053592baae`
- 최종 품질 보완 시작 시 ahead/behind: `2/0`
- 보호된 기존 untracked 경로는 열거나 stage/remove/delete하지 않았다.
  - `.tmp-final-fence-debug/`
  - `.tmp-real-video-dogfood/`
  - `apps/web/.tmp-real-video-dogfood/`

## 구현 범위

- `apps/web/src/api.ts`
  - conversation/run API의 typed request/response를 추가했다.
  - run 생성은 정확한 HTTP 201과 exact response shape만 허용한다.
  - SSE URL은 동일 origin의 정확한 project/conversation/run 경로만 허용하며 redirect, query, hash, 외부/upstream URL을 거부한다.
  - route abort signal을 run POST와 SSE GET 모두에 전달한다.
- `apps/web/src/features/editor/workbench/hermesSseClient.ts`
  - 자동 reconnect/retry 없는 bounded fetch stream parser를 추가했다.
  - 정확한 `text/event-stream` media type, fatal UTF-8, byte 기준 event/line/stream/text 크기 제한, 연속 ID와 허용 event allowlist를 검증한다.
  - backend의 누적 nonterminal JSON 256,000 byte 한도와 200,000 byte text 한도를 기준으로 한다.
  - frontend wire 한도는 backend JSON 누적분에 SSE framing overhead와 terminal 전문의 JSON 최악 escape 확장을 더한 값이다. backend 한도를 2 MB로 간주하지 않는다.
  - raw byte line accumulator를 사용해 1-byte fragmentation에서도 누적 문자열을 반복 인코딩하지 않고 전체 입력 크기에 선형으로 처리한다.
  - duplicate/older ID는 무시하고 `run_started → text_delta/blocked → run_completed` terminal 규약을 검증한다.
  - delta가 하나 이상이면 최종 전문과 정확히 일치해야 하고, durable replay처럼 delta 없이 `run_completed` 전문만 오는 경우도 허용한다.
  - nonterminal 256개와 terminal 1개까지 허용하고 그 이상은 거부한다.
- `EditorWorkbenchRoute`
  - draft, conversation, message history, run state, candidate ID, scroll 위치를 route가 소유한다.
  - optimistic user row와 run별 임시 assistant row를 만들고 delta는 같은 bubble에 누적한다.
  - 최종 durable row를 다시 읽어 성공/blocked 결과를 수렴하며 reload 후에도 대화를 복원한다.
  - 성공 terminal 뒤 durable 목록 재조회만 실패하면 이미 받은 assistant 전문과 complete 상태를 유지하고 저장 확인 경고만 표시한다.
  - route epoch/op fence와 abort로 이전 route의 delta, terminal, 늦은 durable reload를 차단한다.
  - run 생성 실패 전에는 draft를 보존하고, 성공한 정확한 201 뒤에도 사용자가 새로 입력한 draft는 지우지 않는다.
- `RightDock`
  - controlled view adapter로 유지했다.
  - streaming 상태에 `aria-busy`를 적용하되 token 단위 live announcement는 제거했다.
  - complete/unavailable terminal만 한 번 알리는 별도 `role=status`, polite/atomic 영역을 적용했다.
  - terminal 뒤 durable sync warning은 화면에 보이지만 성공 live status를 다시 바꾸지 않는다.
  - “Yujin 없이 계속 편집” 수동 fallback과 기존 수동 편집 control은 streaming/unavailable 중에도 유지한다.
  - dock close는 run을 중단하지 않으며 reopen 시 route-owned 대화와 scroll 상태를 다시 표시한다.
- `EditorWorkbench`
  - localStorage 읽기와 쓰기를 모두 best-effort로 처리해 SecurityError/QuotaExceededError가 나도 수동 편집을 막지 않는다.
  - workbench 내부 인스턴스를 project/session identity로 key 처리한다.
  - 같은 route의 revision 갱신은 로컬 편집 상태를 보존하고, 다른 route의 첫 render부터 이전 selection/seek/audition이 `PreviewStage`나 `TimelineDock`으로 새지 않는다.
  - 기존 `PreviewStage` 한 개의 player owner 경계를 유지한다.
- `scripts/smoke-hermes-yujin-chat.ps1`
  - 기본 실행은 network/provider/proposal/apply 호출 0을 출력하는 non-live gate다.
  - `-Live`는 BaseUri, ProjectId, SessionId를 명시해야 하며 VideoBox API의 conversation POST, run POST, SSE GET 세 호출만 수행한다.
  - harmless UTF-8 한국어 prompt를 보내고 delta와 complete를 요구하되 provider response body를 기록하지 않는다.
  - Windows PowerShell 5.1과 PowerShell 7 양쪽에서 동작하도록 구현했다.
  - redirect를 따르지 않고 각 요청에 제한 시간을 적용하며, exact SSE MIME과 선택적 UTF-8 charset만 허용한다.
  - BaseUri는 userinfo/query/fragment/path가 없는 http/https origin만 허용하고 모든 API URL을 그 origin 기준 상대 경로로 만든다.
  - 요청 실패 출력은 고정 marker로 redaction한다.

## 지킨 경계

- 브라우저는 Hermes나 provider에 직접 연결하지 않고 VideoBox API만 호출한다.
- Hermes username/password, provider body, private error는 UI·smoke 출력에 노출하지 않는다.
- Phase A에는 자동 reconnect, midstream retry, proposal 자동 생성, apply/mutation을 추가하지 않았다.
- 수동 proposal 진입은 기존 명시적 `startDirector` 경로와 분리했다.
- Gateway/Hermes DB/media mount, Mem0, OAuth 확대, SaaS/OpenCut/runtime 변경은 하지 않았다.
- 실제 service start/stop, live provider call, credential 사용은 하지 않았다.

## TDD와 검토 보완

- RED에서 SSE client/run state 부재, persistence/reload, duplicate ID, route stale completion, dock close ownership, unavailable fallback을 먼저 재현했다.
- 첫 구현 뒤 독립 code review에서 Critical은 없었고 Important 두 건을 발견했다.
  - Windows PowerShell 5.1에서 `-SkipHttpErrorCheck`를 사용할 수 있던 문제
  - `text/event-streamx`를 허용할 수 있던 MIME prefix 검사 문제
- 두 Important를 수정하고 hostile MIME, PS5.1 synthetic live harness, dock-close midstream, route-change 뒤 stale durable reload 역방향 테스트를 추가했다.
- 후속 검토에서 durable replay, byte/event cap 정합성, terminal 뒤 durable 목록 실패, localStorage 예외, live-region 소음, 새 route 첫 render의 player source 격리, canary redirect/timeout/origin/redaction 경계를 추가로 지적받았다.
- 각 항목은 실패 테스트를 먼저 확인한 뒤 최소 구현으로 통과시켰다.
- 최종 품질 검토에서는 route 변경 첫 render의 selection/seek 잔존, 1-byte SSE fragmentation의 O(n²) 재인코딩, durable warning의 두 번째 live announcement를 RED로 재현하고 보완했다.
- 보완 전 현재 HEAD의 Python 수집은 **1841 tests collected**, 보완 뒤는 **1845 tests collected**로 확인했다.

## 최신 검증

- 전체 Python (`4dc6d8c22`에서 실행): **1824 passed, 21 skipped, 1 warning**, 808.47초
- 최종 품질 보완 뒤 Python 수집: **1845 tests collected**. Python 파일과 Python 테스트는 바뀌지 않아 13분 전체 회귀는 다시 실행하지 않았다.
- A3/API/smoke 집중 Python: **133 passed, 1 warning**
- smoke script 집중 Python: **6 passed, 1 warning**
- 전체 frontend: **50 files, 622 tests passed**
- 첫 검토 보완 focused frontend: **5 files, 144 tests passed**
  - exact command: `npm exec vitest -- run src/app/AppRouter.test.tsx src/features/editor/workbench/editor-workbench-route.test.tsx src/features/editor/workbench/editor-workbench.test.tsx src/features/editor/workbench/hermesSseClient.test.ts src/features/editor/workbench/right-dock.test.tsx`
- 최종 품질 보완 focused frontend: 같은 exact command로 **5 files, 146 tests passed**
- Editor workbench E2E: **8 passed**
- frontend production build: 통과
- Hermes runtime verifier `-StaticOnly`: 통과
- Hermes profile verifier `-StaticOnly`: 통과
- Hermes plan-state verifier: 20개 master/child ID·상태·진행률 일치
- Hermes zero-tool verifier: 통과
- editor OSS provenance verifier: 통과
- non-live canary: `network_calls=0 proposal_calls=0 provider_body_recorded=false`
- `git diff --check`: 통과

Python warning 1건은 기존 Starlette `multipart` pending deprecation이다. frontend 전체 테스트에는 기존 React `act(...)` 경고가 출력되지만 실패는 없다. build에는 기존 500 kB chunk size 경고가 남는다.

## 실행하지 않은 검증

- live canary: **미실행, 통과로 간주하지 않음**
  - 이유: 승인된 인증 정보, provider/runtime, test project/session이 제공되지 않았다.
- 실제 `videobox-hermes-yujin` service stop/fallback: **미실행**
  - 이유: 이번 turn에서 실제 서비스를 시작하지 않았고 외부 runtime mutation 권한도 확대하지 않았다.
  - 대신 fake unavailable 응답과 스트리밍 중 dock close/reopen 역방향 테스트로 수동 편집 control 유지와 route ownership을 검증했다.

## 진행률과 승인 대기

- A4 master/child checkbox: **`[ ]` 유지**
- Phase A: **3/4 유지**
- Hermes Yujin initiative: **5/20 (25.0%), 잔여 75.0% 유지**
- runtime/chat child: **5/6 (83.3%), 잔여 16.7% 유지**
- 기존 VideoBox 공식 누적: **9/22 (40.9%), 잔여 59.1% 유지**

owner/상위 작업이 비라이브 증거와 live canary 미실행을 수용해 A4 closeout을 승인하면, master/child/status의 A4와 진행률을 같은 후속 commit에서 동기화해야 한다. 승인 전에는 B1을 시작하지 않는다.

## 다음 goal

**A4 closeout 승인 여부만 결정한다.** 승인 시 A4 master/child/status를 동기화하고 Phase A를 4/4, initiative를 6/20, runtime/chat child를 6/6으로 갱신한다. 승인하지 않으면 필요한 live runtime/credential/project/session을 별도 권한으로 준비해 `scripts/smoke-hermes-yujin-chat.ps1 -Live`와 실제 service-stop fallback 증거를 추가한다. 어느 경우에도 승인 전 B1이나 자동 proposal/apply를 시작하지 않는다.
