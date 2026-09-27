# VideoBox MCP HTTP 엔드포인트 — AK-Hermes 연결 설계 (2026-09-27)

## 배경

대표님이 AK-System Hermes 쪽 Claude 세션에서 VideoBox를 MCP 서버로 붙여
쓰고 싶어 하신다 — welinker/openmic이 쓰는 패턴(HTTP MCP 엔드포인트 +
Bearer 토큰 인증, `.mcp.json` 등록)과 같은 방식. 두 세션은 **같은
컴퓨터(로컬)**에서 돈다.

브레인스토밍 중 발견한 충돌: `docs/videobox-mcp-scope.ko.md`(2026-09-07,
owner 결정 다수 포함)가 이미 "타임라인 세부 편집은 MCP로 노출하지
않는다"를 명시적으로 정해뒀다 — 이유는 "그 일은 이미 유진이 프로젝트
안에서 더 잘 하기 때문, 밖에서 조각마다 지시하는 것은 유진을 우회하며
더 나쁜 결과를 얻는 길"이라서다. 대표님이 원한 "기획·편집 등등 모두"는
이 경계와 부딪히는데, **논의 결과 유진을 우회하지 않는 쪽으로 확정**했다
(아래 §3).

## 1. 그대로 두는 것 — `docs/videobox-mcp-scope.ko.md`의 경계

- MCP는 제어면이다. core engine을 직접 import하지 않고 반드시
  `VideoBoxApiClient`(HTTP)를 거친다(`tests/test_mcp_server.py`가 AST로
  강제, 이미 있음 — 손 안 댐).
- 타임라인 세부 편집, 승인, 삭제, 전면 일괄 적용 도구는 **여기서도
  만들지 않는다**(scope 문서 §1.1·§4).
- 기존 조회 도구 4개(`create_project`/`list_projects`/`get_project`/
  `job_status`)는 그대로 재사용한다 — 손 안 댐.

## 2. 새로 정하는 것 — 전송 모드

**신규 서버를 만들지 않는다.** `services/mcp/src/videobox_mcp/server.py`에
HTTP 전송 모드를 하나 더 연다(지금은 `stdio`만 있음). `mcp==2.2.0`
SDK가 이미 HTTP 전송을 담고 있고 `requirements-mcp.txt`에 그 버전이
고정돼 있다(starlette==0.38.6/uvicorn==0.30.6, FastAPI와 버전 충돌 없이
설치 확인됨) — 새 의존성 추가가 필요 없다.

**배치는 호스트 프로세스로, 컨테이너 안이 아니다.** `127.0.0.1`에만
바인딩하는 별도 파이썬 프로세스로 띄운다. 컨테이너 이미지·compose
네트워크를 손대지 않으므로 **CLAUDE.md §6의 "컨테이너 네트워크 경계
변경" 승인 조항과 무관**하다 — 로컬 호스트 프로세스 하나를 추가하는
일로 범위가 줄어든다. 같은 컴퓨터 로컬 접속이라 nginx 같은
리버스프록시도 필요 없다.

## 3. 새로 정하는 것 — 유일한 쓰기 도구: `ask_yujin`

타임라인·자산을 직접 만지는 도구 대신, **유진에게 자연어로 편집을
요청하는 도구 하나만 연다.**

```
ask_yujin(project_id: str, message: str) -> {status, reply, ...}
```

- 화면 채팅이 쓰는 것과 같은 백엔드(`yujin_editing_proposal_service`)를
  `VideoBoxApiClient`를 거쳐 호출한다 — 화면과 다른 문을 쓰지 않는다
  (scope 문서 원칙 3 "MCP → API → Core 순서를 지킨다"와 동일 정신).
- **실패 시 정확히 1회 재시도**한다. 재시도도 실패하면 성공한 척하지
  않고 이유 있는 실패(`status: "failed"`, 원인 문구)를 그대로 돌려준다.
- **VideoBox MCP는 여기서 멈춘다.** 사람에게 알리는 결정과 실행은
  AK-Hermes 쪽 몫이다 — VideoBox가 대신 우회 재시도를 하거나 다른
  도구(직접 타임라인 조작 등)로 새지 않는다. 이건 대표님이 명시적으로
  확인한 정책이다: "유진이 실패하면 재시도 1번 → 그래도 안 되면 사람에게
  에스컬레이션, 절대 우회하지 않기. 실패가 반복되면 그 기록을 근거로
  나중에 직접 도구 개방을 재검토."

## 4. 새로 정하는 것 — 실패 기록

VideoBox 안에는 대표님이 보는 범용 "확인 필요" 알림/대시보드가 없다
(실측 확인 — `review-approvals`는 렌더 승인 전용 좁은 기능, `founder-
dashboard`는 AK-System Hermes 저장소 소관). 그래서 **새 알림함을 만들지
않고, 구조화된 로그 파일에 남긴다**:

- 경로: `services/mcp/data/ask-yujin-escalations.jsonl` (append-only)
- 한 줄 = `{"timestamp", "project_id", "message", "error", "retry_count"}`
- 나중에 반복 실패가 쌓이면 이 파일이 "직접 도구 개방 재검토"의 근거
  자료가 된다(§3의 대표님 지시와 직결). 나중에 VideoBox에 통합 알림함이
  생기면 이 파일을 소스로 옮기면 된다 — 지금은 hot path에 새 인프라를
  얹지 않는다(CLAUDE.md §1.1 hot path/inspection path 분리 원칙).

## 5. 인증

- Bearer 토큰, 환경변수 하나(`VIDEOBOX_MCP_HTTP_TOKEN`)로 발급 — DB
  저장은 안 함(호출자가 AK-Hermes 하나뿐이라 openmic급 스코프 체계는
  과함, YAGNI).
- 비교는 `hmac.compare_digest`(타이밍 공격 방지). 토큰이 서버 기동 시
  없으면 HTTP 모드 자체를 거부(welinker 패턴과 동일).
- 포트는 **8901**로 정한다(기존 사용 포트 8000/8080/8081/8188/8189/8199/
  8200/9119/9120, AK-System 쪽 19680과 겹치지 않는 것을 확인함).
- AK-Hermes 쪽 `.mcp.json`에:
  ```json
  {"mcpServers":{"videobox":{"type":"http","url":"http://127.0.0.1:8901/mcp","headers":{"Authorization":"Bearer ${VIDEOBOX_MCP_HTTP_TOKEN}"}}}}
  ```
- 토큰 값은 양쪽 환경변수에 대표님이 직접 동일하게 넣는다(1회성 수동
  작업 — 대표님이 "양쪽 설정하고 바로 테스트해볼게"로 확인함).

## 6. 완료의 정의 (scope 문서 §7 그대로 적용)

- HTTP 전송 모드: 실물 HTTP 요청으로 정상 1건(올바른 토큰)·실패 1건
  (토큰 없음/틀림, 401)을 직접 호출해 확인.
- `ask_yujin`: 실물 프로젝트에 대고 정상 1건(유진이 실제로 응답), 실패
  1건(재시도까지 실패 → `ask-yujin-escalations.jsonl`에 한 줄 남는지
  파일 직접 열어 확인) — API 단건 확인이 아니라 MCP 클라이언트에서
  실제로 도구를 불러 결과를 받는 것으로 확인한다.
- 기존 조회 도구 4개는 변경 없음 — 회귀 확인만 한다.

## 7. 범위 밖 (지금 안 함)

- 타임라인/자산/렌더 도구 직접 개방 — scope 문서 경계 유지.
- 컨테이너화 배치 — 호스트 프로세스로 시작, 필요해지면 별도 결정.
- 통합 알림 대시보드 신설 — 로그 파일로 대체.
- openmic급 스코프·DB 토큰 저장 — 호출자가 하나뿐이라 불필요.
