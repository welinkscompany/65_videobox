# VideoBox MCP HTTP 서버 — AK-Hermes 연결 설정 (2026-09-27)

## 1. VideoBox 쪽 (이 저장소)

1. 토큰을 하나 정한다(예: `openssl rand -hex 32` 또는 아무 긴 임의 문자열).
2. 그 값을 `VIDEOBOX_MCP_HTTP_TOKEN` 환경변수로 설정한다.
3. `scripts/start-videobox-mcp-http.ps1`을 실행해 `127.0.0.1:8901`에 띄운다.
   VideoBox가 먼저 떠 있어야 한다. `VIDEOBOX_API_BASE_URL` 기본값은
   `http://127.0.0.1:5173` — 매일 쓰는 컨테이너 스택(`scripts/owner-ready.ps1`)이
   호스트에 여는 유일한 문이고, nginx가 `/api/`를 안쪽 API로 넘긴다
   (2026-09-28 정정: 예전 기본값 8000은 컨테이너 **안쪽** 포트라 호스트에서
   아무것도 안 받았다). 개발 서버(`.claude/launch.json`, api 8000)로 돌릴 때만
   `-VideoBoxApiBaseUrl http://127.0.0.1:8000`을 준다.
4. **상시 실행은 아직 없다.** 이 서버는 손으로 켜야 하고 재부팅하면 꺼진다.

## 2. AK-System Hermes 쪽 (그 저장소)

1. 같은 토큰 값을 그 세션 환경변수 `VIDEOBOX_MCP_HTTP_TOKEN`으로 설정한다.
2. 그 저장소 `.mcp.json`에 아래를 추가한다:

```json
{
  "mcpServers": {
    "videobox": {
      "type": "http",
      "url": "http://127.0.0.1:8901/mcp",
      "headers": {
        "Authorization": "Bearer ${VIDEOBOX_MCP_HTTP_TOKEN}"
      }
    }
  }
}
```

## 3. 노출된 도구

- `create_project`/`list_projects`/`get_project`/`job_status` — 조회.
- `ask_yujin(project_id, message)` — 유진에게 자연어로 편집을 요청한다.
  타임라인을 직접 조작하지 않는다. 실패하면 1회 재시도 후 오류를 낸다
  (`is_error: true`) — 그 시점에 사람에게 확인을 넘겨라, 우회하지 마라.
  반복 실패는 `services/mcp/data/ask-yujin-escalations.jsonl`에 쌓인다.

## 범위 밖

타임라인·자산·렌더를 직접 조작하는 도구는 없다(`docs/videobox-mcp-scope.ko.md`).
