# AK-System Hermes 결재함 큐 다리 배선 (W1015, 2026-09-24)

**대체됨:** `2026-09-25-hermes-approval-queue-live-verification-and-index-fix.ko.md`가
이 문서를 대체한다.

**대체됨 표시 대상:** `2026-09-21-self-diagnostics-first-run-and-fixes.ko.md`가
이 문서로 이어진다.

## 무엇을 했나

AK-System Hermes 저장소에 이미 만들어져 있던 결재함 큐 MCP 서버
(`scripts/videobox-mcp-connector-server.js`, `127.0.0.1:19680/mcp`, 로컬 전용,
도구 3개: `submit_title_candidates`·`submit_script_confirmation`·
`submit_upload_request`)에 VideoBox를 실제로 연결했다. 이 서버는 **대표님
결재함에 대기 항목을 넣기만 한다** — 실제 실행(제목 확정·업로드 등)은 이
서버가 절대 하지 않고, 승인 이후에도 VideoBox 쪽 책임이다.

세 가지를 순서대로 했다.

1. **`services/agent-gateway/src/videobox_agent_gateway/hermes_approval_mcp_client.py`
   신설** — `127.0.0.1:19680/mcp`로 HTTP MCP(JSON-RPC 2.0) 요청을 보내는 새
   클라이언트. 기존 `hermes_rpc_client.py`(WebSocket,
   `videobox-hermes-yujin:9120`)는 프로토콜이 달라 재사용할 수 없어 새로
   만들었다. `base_url`이 `127.0.0.1`/`host.docker.internal`의 정확히 포트
   `19680`, 경로 없음이 아니면 생성 자체를 거부한다(사용자·비밀번호·쿼리도
   금지).
2. **오케스트레이션 배선** — 사람 게이트 셋 중 코드로 이미 존재하던 자리
   (대본 확정: `/creation-briefs/{id}/approve`)에 걸었고, 존재하지 않던 둘
   (제목 후보 생성, 업로드 승인 요청)은 이번에 새로 만들었다.
   - **대본 확정** (`creation_briefs.py`의 `approve()`): 승인 직후
     `submit_script_confirmation`을 호출한다. **같은 순간에 제목 후보도
     새로 뽑아 함께 올린다**(`title_candidate_writer.py` 신설,
     `script_draft_writer.py`와 같은 구조 — 구조화 출력만, 한국어 검증,
     실패 시 예외). 이 알림은 **최선노력**이다 — 승인 자체는 큐 전송 실패와
     무관하게 이미 끝난 뒤라, 실패해도 화면에는 안 알린다.
   - **업로드 승인 요청** (`outputs.py`의 새 엔드포인트
     `POST /api/projects/{project_id}/final-renders/{job_id}/request-upload-approval`):
     완성본이 있어야만(`render` 존재) 호출을 받는다. 이건 **owner가 지금 막
     누른 요청**이라 대본 확정과 다르게 **실패를 화면에 그대로 알린다**
     (`upload_approval_queue_unavailable`) — 삼키면 결재함에 아무것도 안
     올라간 걸 owner가 모른 채 기다리게 된다.
3. **컨테이너 네트워크 경계 변경(owner 승인, AskUserQuestion)** —
   `videobox-agent-gateway`는 이전까지 host로 가는 경로가 전혀 없었다.
   기존에 `videobox-hermes-yujin`이 LM Studio(`host.docker.internal:1234`)에
   닿을 때 쓰던 공유망 `videobox-hermes-provider-egress`를 gateway에도
   열었다 — 새 망을 만들지 않고 기존 선례를 재사용했다.
   `docs/development-fast-path.ko.md` §10.14에 새 조항
   **"2-D. VideoBox → AK-System Hermes 결재함 큐 경로"**로 남겼다.

`project_id`/`cycle_id`는 VideoBox DB의 실제 값을 그대로 넘긴다 — Hermes
쪽은 그 값의 의미를 모른다. 결제·정산·PII·실제 업로드 실행 도구는 만들지
않았다(요청받은 범위 밖이라 만들지 말라고 명시됐던 부분).

## 화면 배선 (같은 날 이어서 완료)

**업로드 승인 요청 버튼을 화면에 붙였다.** `OutputsPage.tsx`의 완성본 카드에
"이 완성본 좋아요/아쉬워요" 판단 블록 바로 아래, "이 영상처럼 만들고 싶으면
포맷으로 저장" 블록 바로 위에 새 블록을 넣었다 — 완성본이 있을 때만 보인다
(`currentFinal`). 요약 한 줄을 입력하고 누르면 `request-upload-approval`을
호출하고, 결과에 따라 세 가지 문구 중 하나를 보여준다: 결재함에 올림/큐가
안 켜져 있음/요청 자체가 실패함(이건 화면에 그대로 알린다 — owner가 방금
누른 것이므로 최선노력이 아니다).

`api.ts`에 `requestUploadApproval` 신설, CSS는 기존
`.vb-final-verdict, .vb-final-format` 규칙에 `.vb-upload-approval`을 얹었다
(`videobox-unstyled-classname-detection-method` 메모의 함정 — 클래스만
붙이고 스타일 규칙을 안 챙기면 간격 0px로 붙어버린다).

제목 후보/대본 확정 알림은 이미 있는 화면 흐름(대본 확정 버튼)에 얹었으므로
owner가 그 버튼을 누르는 순간 자동으로 나간다 — 새 버튼이 필요 없다.

### 실물 확인 (브라우저, 진짜 완성본 기준)

owner 요청으로 스모크가 아니라 **실제 화면**에서 밟았다.

1. Windows TTS(`System.Speech`)로 실제 사람 말소리 wav를 만들어 — 합성
   사인파가 아니라 진짜 음성이라야 STT가 뭔가를 알아듣는다 — API를 직접
   호출해 자산 등록→전사→구간분석→B-roll추천→타임라인까지 만들고, 그 뒤부터는
   **에디터 화면을 실제로 열어** 검토 승인 → 완성본 만들기를 버튼으로 눌렀다.
2. 진짜 완성본(mp4, 3.06초, 1920×1080, 소리 있음)이 나온 뒤 새 블록에 요약을
   입력하고 "업로드 승인 요청"을 눌렀다 — 서버 로그에 실제
   `POST .../request-upload-approval → 200 OK`가 찍혔고, 화면에는 "결재함
   큐가 아직 안 켜져 있어요..." 문구가 정확히 떴다(이 dev 환경에는
   `VIDEOBOX_HERMES_APPROVAL_MCP_URL`을 안 채웠으므로 `queued:false`가 맞는
   동작이다).
3. **덤으로 잡은 것:** 이 저장소의 CSRF 가드(`csrf_guard.py`)가 `Origin`을
   `http://localhost:5173`/`127.0.0.1:5173`만 허용하는데, `.claude/launch.json`의
   `web` 설정은 포트 `5199`를 쓴다 — 그래서 5199에서는 검토 승인·촬영본 승인
   같은 버튼이 **조용히 실패**한다(화면엔 "승인하지 못했어요"만 뜨고 원인은
   안 보임). 이번 검증은 5173으로 직접 띄워 우회했다. 코드 결함이 아니라
   dev 설정과 보안 화이트리스트가 어긋난 것이라 고치지 않았다 — 어느 쪽을
   맞출지는 owner 판단이 필요하다(포트를 5173으로 되돌리거나, 화이트리스트에
   5199를 추가하거나).

검증 중 만든 임시 프로젝트 2개와 `_verify_scratch` 폴더는 확인 직후 지웠다.

## 검증한 것

- 새 클라이언트 단위 테스트 8개, agent-gateway 라우트 테스트 7개,
  `title_candidate_writer` 테스트 8개, `agent_gateway_client` 확장 테스트
  4개, `creation_briefs` 알림 테스트 3개, 새 업로드 승인 엔드포인트 테스트
  4개(`tests/test_upload_approval_request.py`, ffmpeg로 만든 **진짜 완성본**
  기준 — 손으로 만든 job 행이 아니다) — 전부 통과.
- `docker compose ... config --env-file .env.container` 정상 렌더 확인.
- **정기 자가 진단 가드(`hermes-yujin-scripts` 훅)가 이 세션에서 실제로
  결함을 잡았다** — 아래 절 참조.
- 전체 backend pytest(`--ignore=tests/test_mcp_server.py`, `mcp` SDK 미설치
  때문 — `videobox-full-pytest-cannot-collect-test-mcp-server` 메모 참고):
  **5142 passed · 56 skipped · 1 xfailed, 38분 33초.** 회귀 없음.

## 이번 세션에서 잡은 절차 결함 — "같은 계약이 두 자리에 박혀 있었다"

compose 파일(`compose.hermes-yujin.yaml`)에 새 환경변수와 새 네트워크를
추가했더니, **그 값을 검증하는 하네스가 세 군데에 따로 하드코딩**돼
있었다 — 하나만 고치고 넘어갔으면 나머지가 거짓 FAIL로 남거나(반대로 거짓
PASS로 새는) 상황이었다.

1. `scripts/start-hermes-yujin.ps1` — 실행 시 gateway 환경변수 이름을
   정확히 대조하는 `$expectedGatewayEnvironmentNames` 배열. 안 고치면 매번
   시작이 "Agent gateway environment contract is invalid."로 막힌다.
2. `scripts/verify-hermes-yujin-runtime.ps1` — **완전히 별도 스크립트**에
   같은 계약이 **환경변수 이름 목록과 네트워크 목록 둘 다** 다시
   박혀 있었다(`Assert-Networks $gateway`, `$gatewayEnvironmentNames`).
   이것도 안 고치면 "A1 정적 검증"이 통과하지 않는다.
3. `tests/test_hermes_yujin_compose_contract.py` — 원본 yaml을 직접
   파싱해서 gateway의 네트워크/환경변수를 **문자 그대로** 비교하는 테스트.
   그중 하나는 이름 자체가
   `test_gateway_bridges_api_hermes_and_memory_without_provider_egress`였다
   — "gateway는 provider egress로 못 나간다"는 예전 보안 가정을 이름에 박아
   둔 것. 이번 승인(§10.14 2-D)으로 그 가정이 끝났으므로, 테스트를 지우지
   않고 **이름과 주석을 바꿔서 새 계약을 설명하도록** 다시 썼다
   (`test_gateway_bridges_api_hermes_and_the_hermes_approval_queue_bridge`).
4. `tests/test_start_hermes_yujin_script.py`의 `_rendered_model()` — 실제
   docker를 안 부르고 **가짜 config JSON**을 만들어 스크립트에 먹이는
   fixture. 여기도 새 환경변수 키를 안 넣으면 스크립트의 새 기대치와
   안 맞아 20여 개 무관한 테스트가 한꺼번에 빨개진다(실제로 그랬다).

**패턴 이름을 붙이면:** "네트워크/환경변수 계약을 넓힐 때는 실제 compose
파일 하나만 보지 말고, 그 계약을 하드코딩한 검증 스크립트·시험 파일을 모두
찾아서 같이 고쳐야 한다" — `videobox-required-compose-var-breaks-every-renderer`
메모와 같은 계열의 함정이지만, 이번엔 "필수 값 하나"가 아니라 "정확히 이
목록과 일치해야 한다"는 화이트리스트 계약이라 실수하면 **거짓 FAIL**로
나타났다(거짓 PASS가 아니라서 다행히 숨지는 않았다).

## 재사용 게이트 판단 (§8.1)

- **재사용**: `videobox-hermes-provider-egress` 네트워크(신규 생성 안 함),
  `title_candidate_writer.py`는 `script_draft_writer.py`의 구조를 그대로
  따름, 결제/승인 라우트 패턴은 `creation_briefs.py`의 기존 approve 흐름에
  얹음.
- **신규 작성**: `hermes_approval_mcp_client.py`(프로토콜이 달라 기존
  `hermes_rpc_client.py` 재사용 불가), `title_candidate_writer.py`(제목
  후보라는 새 산출물), 업로드 승인 라우트(기존에 없던 사람 게이트).
- **제외**: 결제·정산·PII·업로드 실행 도구 — 요청 자체가 명시적으로 배제.

## CSRF 포트 불일치 — 5199를 5173으로 되돌리는 대신 화이트리스트를 넓혔다

owner에게 "5199를 5173으로 되돌릴까, 화이트리스트에 5199를 추가할까"를
물었다. **화이트리스트 추가를 골랐다** — `docs/development-fast-path.ko.md`
"데이터 폴더가 두 벌이다" 절이 5199/5173을 의도적으로 분리해 둔 이유(같은
포트를 쓰면 로컬 파일 저장소와 컨테이너 Postgres 저장소가 섞여 보이는
사고가 2026-08-08에 실제로 났다)를 되돌리면 다시 살아나기 때문이다.
`services/api/src/videobox_api/csrf_guard.py`의 `TRUSTED_ORIGINS`에
`http://127.0.0.1:5199`/`http://localhost:5199`를 추가하고,
`tests/test_approval_routes_reject_untrusted_origin.py`에 회귀 테스트를
더했다(실물로도 재확인 — 아래 절).

## 코드리뷰 (8각도, 이번 세션 커밋 4개 + 이 CSRF 수정)

`git diff 34852456c...HEAD` + working tree를 8개 독립 각도로 리뷰했다.
확정 결함 3개, 정확한 지적 1개는 **바로 고쳤다**:

1. **[correctness, 고침]** `creation_briefs.py`의 `approve()`가
   `async def`였는데, 그 안에서 로컬 LLM을 동기 호출하는
   `title_candidate_writer.write()`를 직접 `await`했다 -- GPU 경합 시
   수십 초까지 걸리는 이 호출이 그동안 **같은 프로세스의 다른 모든 요청**을
   막았다. `BackgroundTasks`로 응답과 분리하고, `write()` 자체도
   `asyncio.to_thread`로 스레드에 넘겼다. `approve()`는 더는 async가 아니어도
   돼서 일반 `def`로 되돌렸다(FastAPI가 자동으로 스레드풀에 태운다 --
   `script_drafts.py`가 이미 쓰는 방식과 같아졌다).
2. **[conventions, 고침]** 업로드 승인 화면 문구에 내부 용어 "큐"가 그대로
   노출됐다(CLAUDE.md §8). "결재함이 아직 연결돼 있지 않아요"로 고쳤다.
3. **[correctness, 고침]** 업로드 승인 큐 연결 실패가 400(Bad Request)으로
   나가 owner 입력이 잘못됐다는 뜻처럼 보였다 -- 실제로는 상류(Hermes 다리)
   문제라 502로 고쳤다.
4. **[conventions, 고침]** `compose.hermes-yujin.yaml`의 network 주석이
   "이 컴퓨터 밖으로 안 나간다"고 **망 자체의 속성**인 것처럼 적혀 있었다.
   실제로는 이 망(`videobox-hermes-provider-egress`)이 `internal: true`가
   **아니고** 유진 컨테이너의 외부 provider egress에도 쓰이는 진짜 망이며,
   보장은 `HermesApprovalMcpClient` 하나의 앱 레벨 URL 잠금에서만 나온다는
   걸 주석에 명시했다 -- 나중에 이 gateway 프로세스에 다른 아웃바운드
   호출이 생기면 이 망으로 실제 인터넷에 나갈 수 있다는 경고도 남겼다.

**의도적으로 안 고친 것 3개** (모두 순수 리팩터, CLAUDE.md "관련 없는 코드와
구조는 건드리지 않는다"에 따라 이번 범위 밖으로 남김 -- `ReportFindings`에
`skipped`로 기록):
- 한글 검증 정규식이 `title_candidate_writer.py`/`script_draft_writer.py`
  둘에 복제됨.
- HTTP 클라이언트 팩토리 + "loopback만 허용" URL 검증 패턴이
  `hermes_approval_mcp_client.py`/`hermes_rpc_client.py` 둘에 복제됨.
- agent-gateway의 승인 엔드포인트 3개가 거의 동일한 보일러플레이트를 반복.

## 갭검증 (원래 요청 대조)

owner의 원래 지시(3가지: 새 MCP 클라이언트, 세 도구 배선, project_id/cycle_id
그대로 전달 + 결제·PII·업로드실행 도구 금지)를 다시 한 줄씩 대조했다 -- 셋 다
됐고, 금지 항목은 안 만들었다. `docs/implementation-plan.ko.md`에는 이
작업이 번호 붙은 Task로 없다(owner가 대화로 직접 지시한 범위 밖 요청이라
공식 계획서 항목이 아니다) -- 그래서 갭검증은 계획서 대조가 아니라 원래
지시문 대조로 했다.

## 역방향 동작검증 (코드리뷰 수정 반영 후)

- CSRF 수정: 브라우저(포트 5199)에서 실제 `fetch`로 존재하지 않는
  프로젝트의 검토 승인을 호출 -- 이전엔 403(untrusted_origin)이었는데
  지금은 500(내부 오류, 프로젝트가 없어서 정상)으로 나왔다. 즉 CSRF는
  통과하고 실제 핸들러까지 도달한다.
- `approve()` 백그라운드 태스크 전환: `tests/test_api_creation_brief.py`
  12개 전부 그대로 통과 -- `TestClient`는 응답을 돌려주기 전에 백그라운드
  태스크를 실제로 실행하므로, 알림이 여전히 나가는지는 시험이 계속 지킨다.
- 502 상태코드 변경: `tests/test_upload_approval_request.py`의 실패 시험을
  `>= 400`에서 **정확히 502**로 좁혀 재확인.
- 전체 backend pytest(`--ignore=tests/test_mcp_server.py`) 재실행:
  **5143 passed · 56 skipped · 1 xfailed, 37분 38초.** 회귀 없음(이번
  코드리뷰 수정 다섯 개를 반영한 새 실행 기준).
- 프론트 `OutputsPage.test.tsx` 123개 전부 통과, `tsc --noEmit` 클린.

## 다음 세션에 남는 것

1. `.env.container`에 실제 owner가 `VIDEOBOX_HERMES_APPROVAL_MCP_URL`을
   채워서 컨테이너를 재시작하고, 실물 AK-System Hermes 서버가 떠 있는
   상태에서 실제 결재함에 항목이 뜨는지 **눈으로** 확인 — 이번 세션은
   화면·백엔드 배선은 실물로 확인했지만(위 절), 큐 자체가 켜진 상태의
   확인은 아직 못 했다(그 서버가 지금 안 떠 있음).
