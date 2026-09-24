# AK-System Hermes 결재함 큐 다리 배선 (W1015, 2026-09-24)

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

## owner가 알아야 할 것 — 화면에 아직 버튼이 없다

**업로드 승인 요청은 백엔드 API만 완성됐다.** 화면(OutputsPage 등)에 "업로드
승인 요청" 버튼이 없다 — 지금은 API를 직접 호출해야만 결재함에 올라간다.
`CLAUDE.md` §4의 기준("owner가 화면에서 그 기능을 실제로 쓸 수 있는가")으로
보면 **이 조각은 완료가 아니다.** 다음 세션에서 화면에 버튼을 붙이는 작업이
남아 있다.

제목 후보/대본 확정 알림은 이미 있는 화면 흐름(대본 확정 버튼)에 얹었으므로
owner가 그 버튼을 누르는 순간 자동으로 나간다 — 새 버튼이 필요 없다.

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

## 다음 세션에 남는 것

1. **화면에 "업로드 승인 요청" 버튼 배선** — OutputsPage에서 완성본을 보고
   있을 때 누를 수 있는 자리. 없으면 이 조각은 CLAUDE.md §4 기준 미완료.
2. `.env.container`에 실제 owner가 `VIDEOBOX_HERMES_APPROVAL_MCP_URL`을
   채워서 컨테이너를 재시작하고, 실물 AK-System Hermes 서버가 떠 있는
   상태에서 실제 결재함에 항목이 뜨는지 **눈으로** 확인 — 이번 세션은
   가짜 클라이언트로만 검증했다(브라우저/컨테이너 실물 검증은 못 함).
