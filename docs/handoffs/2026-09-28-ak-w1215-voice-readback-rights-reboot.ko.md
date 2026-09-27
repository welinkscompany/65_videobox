# AK W1215 — 목소리 기본값·결재 되읽기·ask_yujin 주소·자산 권리·재부팅 복구·시험 기록 격리 (2026-09-28)

**이어받는 문서:** `2026-09-26-approval-connector-persistence-blocked-on-ak-hermes-policy.ko.md`
(결재함 연결 서버 상시 실행 보류는 그대로다 — 이 문서가 바꾸지 않았다).

## 배경

AK-System 쪽 옆 저장소 분석(AK `docs/ak-system/closeout/2026-09-28-sibling-analysis-videobox.md`,
AK 계획 행 W1215)이 찾은 여섯 가지를 대표님 지시("나머지 다른 프로젝트 수정사항은 모두 고쳐줘")로
고쳤다. 배포·컨테이너 재시작·유튜브 업로드는 하지 않았다.

## 한 일 (커밋 순서)

| 항목 | 커밋 | 요지 |
|---|---|---|
| 6. 시험이 실제 기록 파일에 씀 | `5faaac34c` | conftest autouse 픽스처가 `VIDEOBOX_MCP_ESCALATION_LOG_PATH`를 시험마다 임시 파일로. 실제 파일의 5줄(전부 시험 데이터)은 로컬에서 지움(gitignore 파일) |
| 3. MCP API 기본 주소 | `dc7295ad6` | 8000(컨테이너 안쪽) → 5173(호스트에 열린 유일한 문). `api_client.DEFAULT_API_BASE_URL` 한 곳 |
| 1. 목소리 기본값 | `9fdf7f3b8` | 다리 기본 chatterbox(MIT). XTTS는 `VIDEOBOX_ALLOW_NON_COMMERCIAL_TTS=1` 없이는 거부, 모르는 엔진 이름은 오류, `/health`가 라이선스를 말함. `start-voice.ps1 -Engine auto`는 더 이상 XTTS로 안 넘어감 |
| 5. 재부팅 복구 | `7492ed17b` | postgres·workspace·agent-gateway·hermes-yujin = `unless-stopped`, 프로필 도구 셋은 명시적 `"no"` |
| 2. 결재 되읽기 | `98ac1af6a` | `POST/GET /api/projects/{id}/founder-approval-decisions`(결정 번호로 한 번만), 호스트 동기화 `videobox_mcp.ak_decision_sync`(AK 레지스트리 읽기만), 대본 반려면 초안 멈춤, 업로드 결정 난 완성본은 재요청 409, 결과 화면에 승인/반려 표시 |
| 4. 자산 권리 칸 | `d6a327543` | `rights_source` 기본 `unknown`, 기존 131개는 전부 `unknown`(지어내지 않음), 모르면 업로드 승인 요청 409, 자료실 미리보기에 `출처` 칸 |

## 대표님이 하실 일 / 결정할 일

1. **컨테이너 다시 만들기** — 재시작 정책·새 API·새 화면은 이미지를 다시 만들어야 적용된다:
   `.\scripts\owner-ready.ps1 -Mode Start -Rebuild -WithYujinMemory`. 이 세션은 도는 컨테이너를 건드리지 않았다.
2. **Docker Desktop 로그인 시 자동 시작**이 켜져 있어야 `unless-stopped`가 재부팅 뒤 효과가 있다(대표님 설정).
3. **자산 권리 적기** — 다시 만든 뒤에는 자료실 자산을 쓴 프로젝트의 업로드 승인 요청이 막힌다
   (의도된 안전 기본값). 자료실 미리보기의 `출처`에서 직접 촬영 / AI로 만듦 / 남의 자료(허락 내용)를 고르면 풀린다.
4. **결재 되읽기 상시 실행**은 예약 작업이 필요하다 — AK 쪽 "새 예약작업 보류" 결정과 같은 문제라 등록하지 않았다.
   지금은 손으로: `$env:VIDEOBOX_AK_APPROVAL_REGISTRY_DIR = "<AK>\docs\ak-system\data"; .\scripts\sync-ak-founder-decisions.ps1`
   (`-IntervalSeconds 60`이면 계속 돈다).
5. **MCP HTTP 서버(8901) 상시 실행**도 없다. AK `.mcp.json` 등록은 AK 저장소 쪽 일이다(`docs/videobox-mcp-http-setup.ko.md`).

## 재야 하는 것 / 못 잰 것

- **Postgres에서 새 표를 실측하지 못했다.** `founder_approval_decisions`는 SQLite 문장에서 자동 파생된 DDL을
  눈으로 확인만 했다(`VIDEOBOX_TEST_POSTGRES_URL` 없음). 다시 만든 컨테이너에서 결정 하나를 넣어 보는 것이 첫 확인이다.
- **화면을 브라우저로 밟아 보지 못했다** — 도는 컨테이너가 옛 이미지라 새 화면이 없다. vitest 화면 시험과 tsc만 통과.
- **chatterbox 한국어 품질 실측 기록은 여전히 없다**(09-02 실측은 영어 더빙).
- `editor-workbench.test.tsx`의 `gives the material dock back...` 실패는 변경 전 커밋 `a349dcc98`에서도 똑같이 난다(무관).
- `test_owner_ready_script.py`·`test_start_hermes_yujin_script.py`의 시간 제한 시험 몇 개가 실행마다 다른 이름으로 실패한다
  (부하 때 8초 벽 등). 이 시험들은 자기 compose 파일을 따로 만들어 쓰므로 이번 변경과 무관하다.
