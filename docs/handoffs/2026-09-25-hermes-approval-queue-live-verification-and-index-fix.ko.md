# AK-System Hermes 결재함 큐 실물 검증 + index 결함 수정 (2026-09-25)

**대체됨:** `2026-09-26-approval-connector-persistence-blocked-on-ak-hermes-policy.ko.md`가
이 문서를 대체한다.

**대체됨 표시 대상:** `2026-09-24-hermes-approval-queue-bridge.ko.md`가
이 문서로 이어진다.

## 무엇을 했나

`2026-09-24-hermes-approval-queue-bridge.ko.md`의 "다음 세션에 남는 것" —
실물 AK-System Hermes 결재함 서버를 띄운 상태에서 제목 후보·대본 확정·
업로드 승인 요청이 진짜로 결재함에 뜨는지 눈으로 확인하는 일 — 을 했다.

1. `scripts/new-hermes-yujin-secrets.ps1`로 유진 비밀값을 이 컴퓨터에서
   새로 만들었다(`.env.container`가 그동안 `replace-before-starting`
   자리표시자였다 — 이 컨테이너 스택이 이 환경에서 실제로 뜬 적이 없었다는
   뜻이다).
2. `.env.container`에 `VIDEOBOX_HERMES_APPROVAL_MCP_URL=http://host.docker.internal:19680`를
   채웠다(§10.14 2-D가 허용하는 두 값 중 컨테이너용 값).
3. AK-System Hermes 저장소(`100_ak-system-hermes`)의
   `scripts/videobox-mcp-connector-server.js`를 이 컴퓨터에서 직접
   `node`로 띄웠다 — 이 저장소엔 아직 전용 launcher(pm2/systemd 등)가
   없다. **owner가 재부팅하거나 이 프로세스를 닫으면 다시 수동으로 띄워야
   한다** — 다음 세션 숙제로 아래에 남긴다.
4. `.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory`로 VideoBox
   컨테이너 스택을 켰다.

## 켜고 보니 실물에서만 드러난 결함 두 개

이 검증이 "그냥 켜서 확인"으로 안 끝나고 실제 결함 두 개를 찾아 고치는
작업이 됐다 — 둘 다 **API curl 하나로는 못 잡고, 진짜 approve() 화면
흐름을 그대로 밟고서야** 드러났다.

### 1. 컨테이너가 낡은 이미지로 떠 있었다 (운영 절차 결함)

`owner-ready.ps1 -Mode Start`는 기본적으로 이미지를 다시 만들지 않는다
(`-Rebuild`를 줘도 `videobox-workspace`만 다시 만들고, `videobox-agent-gateway`는
**아예 어떤 옵션으로도 다시 만들지 않는다** — `grep -n "agent-gateway"
scripts/owner-ready.ps1` 결과 `up -d` 대상에만 있고 build 대상엔 없음).

실제로 뜬 이미지를 재보니:

- `videobox-agent-gateway`: 2026-08-27 빌드 (W1015 코드 전체가 이 날짜
  이후인 2026-09-21~24에 커밋됐다 — 즉 **이 컨테이너 안에 결재함 큐
  코드 자체가 없었다**)
- `videobox-workspace`: 2026-09-20 빌드 (`creation_briefs.py`의 백그라운드
  알림 코드가 2026-09-21 커밋이라 이것도 없었다)

그래서 `POST /internal/approvals/script-confirmation`을 직접 찔러보면
**404**가 났다 — 라우트 자체가 없었다. `docker compose ... build --pull=false
videobox-workspace videobox-agent-gateway`로 두 이미지를 현재 소스에서
다시 만들고 나서야 라우트가 생겼다.

**패턴:** 지난 세션이 "큐가 꺼져 있어요" 문구를 화면에서 정확히 봤다고
보고한 것 자체는 맞다. 하지만 이번에 실제로 큐를 켜고 다시 확인해보니
그 문구가 뜬 진짜 이유는 "큐 서버가 꺼짐"이 아니라 "그 코드가 컨테이너
안에 아예 없음"이었을 가능성이 있다 — 증상이 우연히 같아 보였을 뿐이다.
`owner-ready.ps1`이 agent-gateway를 절대 다시 만들지 않는다는 사실은
이번에 처음 확인됐다 — 앞으로 이 컨테이너의 코드를 바꾼 뒤 검증할 때는
`docker compose build videobox-agent-gateway`를 손으로 먼저 해야 한다.

### 2. 결재함 계약이 요구하는 index가 0부터였다 (진짜 코드 결함, 2026-09-21 커밋)

이미지를 다시 만들고 나니 이번엔 **502**가 났다. AK-System Hermes의
`append-videobox-approval-entry.ps1`를 직접 찔러 실제 오류 문구를 받아보니
(`docker`/`agent-gateway`를 거치면 `HermesApprovalMcpClient`가 의도적으로
오류를 뭉개서 보여준다 — 커넥터 서버에 직접 JSON-RPC를 쳐야 진짜 이유가
나온다):

```
videobox_mcp_append_candidate_index_invalid: script_candidates
```

`docs/ak-system/data/videobox-mcp-connector-config.json`의 계약(
`"index 는 1부터 시작하는 정수"`)과 달리, `services/api/src/videobox_api/routers/creation_briefs.py`가
`script_candidates=[{"index": 0, ...}]`와 `enumerate(titles)`(0부터)로
보내고 있었다. `title_candidate_writer.py`나 append 스크립트 쪽 문제가
아니라 **이 파일 두 곳**의 문제였다.

**고침:** [creation_briefs.py](../../services/api/src/videobox_api/routers/creation_briefs.py)의
`script_candidates`를 `index: 1`로, `title_candidates`는
`enumerate(titles, start=1)`로 바꿨다. [tests/test_api_creation_brief.py](../../tests/test_api_creation_brief.py)의
두 단정문도 같이 고쳤다(기존 테스트가 0-based를 정답으로 박아두고 있었다
— mock으로 도는 시험이라 진짜 계약을 밟지 않아서 못 잡았다).

## 실물로 확인한 것 (진짜 approve() 화면 흐름)

수정 뒤 curl로 직접 흉내 낸 게 아니라, 실제 화면이 부르는 것과 같은
API 순서(대본 만들기 → 건너뛰기 → 요약 입력 → 확정)를 그대로 밟았다.

1. **대본 확정**: `POST .../creation-briefs/{id}/approve` 호출 →
   `videobox-script-approval-registry.json`에 `pending_script_confirmation`
   항목이 실제로 들어감(항목 확인 후 즉시 제거).
2. **제목 후보**: 같은 승인이 백그라운드로 유진의 로컬 LLM을 불러 한글
   제목 3개를 실제로 만들고 → `videobox-title-approval-registry.json`에
   `pending_title_selection` 항목이 실제로 들어감(한글이 터미널에
   깨져 보인 건 표시 문제였고, 파일을 직접 읽어보면 정상 UTF-8이었다 —
   내용도 실제로 검증 맥락을 반영한 한글 제목이었다).
3. **업로드 승인 요청**: 기존에 이미 완성돼 있던 실제 렌더
   (`10-06-da081c96` 프로젝트의 `final_render_job_007`, 5초·1920×1080·
   소리 있음)로 `POST .../request-upload-approval`을 호출 →
   `videobox-upload-approval-registry.json`에 `pending_upload_approval`
   항목이 실제로 들어감(항목 확인 후 즉시 제거).

세 게이트 모두 레지스트리 파일에 실제로 쓰인 것을 파일을 직접 읽어
확인했다 — API 응답의 `{"queued":true}`만 보고 끝내지 않았다. 검증용으로
만든 VideoBox 테스트 프로젝트(`w1015-approval-queue-test-1584c164`)는
확인 직후 영구 삭제했다.

`founder-decision-register.ps1`이 이 세 레지스트리를 통합해 실제 결재함
화면/텔레그램/디스코드로 올리는 부분은 **이번에 건드리지 않았다** —
그건 AK-System Hermes 쪽이 이미 소유·검증한 별도 조립 단계이고,
VideoBox 쪽 계약은 "레지스트리 파일에 pending 항목이 뜨면 끝"이라고
`videobox-mcp-connector-config.json`이 명시한다.

## 검증

- `tests/test_api_creation_brief.py`: 12개 통과(수정한 두 단정 포함).
- 결재함 관련 시험 전체(`test_api_creation_brief.py`,
  `test_agent_gateway_approval_routes.py`, `test_agent_gateway_client.py`,
  `test_agent_gateway_hermes_approval_mcp_client.py`,
  `test_title_candidate_writer.py`): 72개 통과.
- 전체 backend pytest(`--ignore=tests/test_mcp_server.py`): **5143 passed ·
  56 skipped · 1 xfailed, 40분 34초.** 회귀 없음(2026-09-24 세션 종료
  시점의 기준 5143 passed와 같은 수 — 이번 수정은 assertion 두 줄만
  바꿨을 뿐 테스트를 추가하지 않았다).

## 재사용 게이트 판단 (§8.1)

- **재사용**: 기존 approve() 화면 흐름(대본 만들기→건너뛰기→요약→확정)을
  그대로 curl로 재생해 검증했다 — 새 검증 스크립트를 만들지 않았다.
  기존 succeeded 상태의 실제 렌더(`final_render_job_007`)를 재사용해
  업로드 승인 요청을 검증했다 — 새 렌더를 처음부터 만들지 않았다.
- **신규 작성**: 없음. 이번 세션은 순수 결함 수정(index 1건)과 운영
  절차 결함 문서화(이미지 재빌드 누락)뿐이다.
- **제외**: `founder-decision-register.ps1` 실행/화면 결합 검증 — AK-System
  Hermes 쪽 소유 범위라 이번 작업 경계 밖.

## 다음 세션에 남는 것

1. **AK-System Hermes 결재함 커넥터 서버에 전용 launcher가 없다.**
   지금은 이 세션이 수동으로 `node scripts/videobox-mcp-connector-server.js`를
   띄워 둔 상태다 — 터미널을 닫거나 컴퓨터를 재부팅하면 죽는다. 그러면
   `VIDEOBOX_HERMES_APPROVAL_MCP_URL`이 채워져 있어도 결재함 알림이 다시
   "최선노력 실패"로 조용히 넘어간다(대본 확정 자체는 막지 않지만, 결재함에
   안 뜬다). AK-System Hermes 쪽에 pm2/예약 작업 같은 상시 실행 방법을
   만들지, 아니면 owner가 그때그때 수동으로 띄울지는 owner 판단이 필요하다.
2. **`owner-ready.ps1`이 `videobox-agent-gateway`를 절대 다시 만들지
   않는다.** 이 컨테이너의 코드(agent-gateway 자체나 그것이 쓰는
   `hermes_approval_mcp_client.py` 등)를 바꾼 뒤에는
   `docker compose -f compose.yaml -f compose.hermes-yujin.yaml --env-file
   .env.container --profile hermes-yujin build videobox-agent-gateway`를
   손으로 먼저 돌려야 한다. `owner-ready.ps1` 자체를 고쳐 agent-gateway도
   자동으로 다시 만들게 할지는 별도 판단이 필요하다(스크립트 동작을
   바꾸는 일이라 이번 범위 밖으로 남겼다).
3. `founder-decision-register.ps1`을 실제로 돌려 이 세 게이트가 통합
   결재함 화면(텔레그램/디스코드 등)에도 뜨는지 확인하는 것은 아직
   안 했다 — AK-System Hermes 쪽 소유 범위라는 판단 아래 이번엔 건드리지
   않았지만, owner가 원하면 다음에 확인할 수 있다.
