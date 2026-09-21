# 정기 자가 진단 첫 실행 결과 반영 + QA 후속 수정 (2026-09-21)

**대체됨 표시 대상:** `2026-09-20-self-diagnostics-and-transition-followups.ko.md`가
이 문서로 이어진다.

## 정기 자가 진단(`videobox-self-diagnostics`)이 어젯밤 처음 자동으로 돌았다

2026-09-20에 등록한 예약 작업(매일 새벽 4시 9분)이 처음 자동 실행됐다. 결과를
검토해 실제 결함 둘을 찾았다 — **둘 다 VideoBox 제품 버그가 아니라, 자가 진단
절차 자체의 결함**이었다.

1. **맨 `pytest -q`는 0건 실행된다** (`videobox-full-pytest-cannot-collect-test-mcp-server` 메모).
   `mcp` SDK가 uvicorn/starlette 버전 충돌로 `.venv`에 설치가 안 돼 있어서
   `test_mcp_server.py` 수집 에러로 **exit 2, 0건 실행**이 된다 — "실패"가 아니라
   "0건 실행"이라 통과처럼 착각하기 쉽다. 2026-09-08 MCP 착수 이후 계속된
   상태고 회귀가 아니다. 실측 기준선: **5108 passed·56 skipped·1 xfailed·38분
   42초** — 문서에 흔히 적힌 "약 8분"/"501건"과 다르다.
   - **원인은 내 실수였다.** 예약 작업 프롬프트(2026-09-20 작성)에
     `--ignore=tests/test_mcp_server.py`를 빼먹었다. 이번 세션 내내 다른 모든
     pytest 호출에는 이 플래그를 썼는데 예약 작업에는 안 넣었다.
   - **더 찾은 것:** 저장소의 canonical 문서(`docs/development-fast-path.ko.md`
     §11 "검증 명령")에도 **같은 실수**가 있었다 — bare
     `.venv/Scripts/python.exe -m pytest -q` 명령이 "이렇게 검증하라"는
     기준으로 박혀 있었다. 둘 다 고쳤다.
   - **owner 지적으로 마무리:** `--ignore`는 증상을 가리는 임시 우회이지 해결이
     아니다. `mcp`가 설치되기 전까지 `services/mcp/`는 시험 보호를 하나도 못
     받는다. 그래서 예약 작업과 문서 둘 다 "매번 `pip show mcp`부터 확인하고,
     설치돼 있으면 `--ignore`를 빼라"는 자기소멸 조건을 넣었다 — 우회가 영원히
     남지 않게.
2. **`editor-e2e`가 포트 점거로 거짓 실패했다** (`videobox-editor-e2e-false-fail-from-port-4173-squatter` 메모).
   Playwright 기본 포트(4173)를 **다른 프로젝트(ak-system)의 유령 node
   프로세스**가 물고 있어서 30초 타임아웃 거짓 실패가 났다.
   `PLAYWRIGHT_WEB_PORT=4199`로 재현·해소(48건 전부 통과)까지 확인했다.
   예약 작업과 `docs/development-fast-path.ko.md` §10에 "포트 점거부터 본다"는
   대응 절차를 넣었다 — `apps/web/playwright.config.mjs`가 이미
   `PLAYWRIGHT_WEB_PORT`/`PLAYWRIGHT_FAKE_API_PORT`를 읽으므로 코드 변경은
   불필요했다.

**중요 — 자가 진단이 지침대로 잘 동작했다는 뜻이다.** 두 문제 다 스스로
고치지 않고 "owner 결정 대기"로 정확히 보고했고, 근거를 실측(재실행·재현)으로
남겼다. 이 절차가 처음부터 제대로 작동한다는 증거다.

## QA(qa-testing 스킬) 결과 반영

자료실 검색 기능 QA 중 발견한 것 중 안전하게 바로 고칠 수 있는 것만 반영했다:

- `<html lang="en">` → `lang="ko"` (화면은 전부 한글인데 언어 속성이 틀려서
  스크린리더 발음 규칙이 어긋났다).
- 파비콘 없음 → 추가. **새로 디자인하지 않고** 데스크톱 앱(Tauri)이 이미 쓰는
  승인된 아이콘(`apps/desktop/src-tauri/icons/icon.ico`)을 그대로 재사용했다.
- **모바일(375px) 반응형 레이아웃은 owner 결정으로 보류.** "PC 최적화를 먼저
  한다"(2026-09-20/21) — 3단 데스크톱 그리드를 모바일용으로 다시 짜는 건 화면
  구조를 바꾸는 큰 작업이라 지금은 손대지 않는다.

## 보안 리뷰 결과 (`security-review` 스킬)

자료실 검색 fan-out + 관련도 기능 diff(`c6f07dded~1..18d00497`)에 대해 별도로
돌렸다. **높은 확신도(≥7/10)의 보안 취약점 없음.** SQL 인젝션·경로 순회·인증
우회·XSS(위험한 sink 없음)·민감정보 노출 전부 확인, 실질적인 새 공격면을
안 연다고 판단했다.

## 남겨둔 것

- 다음 자가 진단 실행(오늘 밤 새벽 4시 9분)에서 새 프롬프트(포트 지정, `pip
  show mcp` 확인)가 실제로 잘 도는지 확인해야 한다.
- "디자인 톤앤매너" 관련 남은 항목은 없다 — 이전 인계 문서의 목록은 전부
  처리 완료됐다.

## 다음 세션 시작 프롬프트

```
docs/handoffs/2026-09-21-self-diagnostics-first-run-and-fixes.ko.md를
읽고 이어서:

1. 오늘 밤 자가 진단 예약 작업이 새 프롬프트(포트 지정 + pip show mcp
   확인)로 정상적으로 도는지 다음 실행 결과를 확인해줘.
```
