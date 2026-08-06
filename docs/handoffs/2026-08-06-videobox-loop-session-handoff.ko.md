# 2026-08-06 무인 루프 세션 핸드오프 — Task 13/14 닫음, 모델명 설정 배선 고침

## 이 세션에서 한 일 (전부 커밋·푸시 완료, worktree clean)

`codex/videobox-container-compatibility` 브랜치, 원격과 동기화 상태.

| 커밋 | 내용 |
|---|---|
| `f26d88bf5` | feat: 유진 채팅 UI를 로컬 우선 대화 경로에 연결 (Task 13/14) |
| `9c5ffd33c` | docs: 계획서에 Task 13/14 화면 연결 closeout 기록 |
| `a3a4c201f` | fix: 로컬 런타임 model_name을 환경변수로 해석 |
| `bf4d9e6f6` | docs: 계획서에 model_name 환경변수 고침 closeout 기록 |

### Task 13/14 — 유진 채팅 UI 연결 (owner 결정: 방식 B, 로컬 전용 경로)

기존에 이미 만들어져 있었지만 프론트에 연결되지 않았던 로컬 동기 채팅 엔드포인트
(`POST .../director/conversations/{id}/messages`)를 재사용했다. 그 엔드포인트의 자유
대화 생성 로직을 일반 `OPERATOR_COPY` 호출에서 Task 13이 이미 검증한
`YujinLocalConversationService`(정책 차단 + 유진 페르소나 프롬프트)로 교체하고,
`EditorWorkbenchRoute.tsx`의 채팅 전송·취소·재시도를 Hermes SSE 스트리밍 경로에서
이 동기 경로로 전면 재배선했다. `HermesRunService`/`AgentGatewayClient`/capability-token
코드는 전혀 건드리지 않았다.

- 백엔드 전체 회귀: 3060 passed, 52 skipped, 0 failed
- 프론트 전체: 760/760 passed, `tsc --noEmit` clean
- 옛 SSE 스트리밍을 검증하던 프론트 테스트 15개를 새 동기 흐름에 맞게 재작성

### 모델명 환경변수 고침 (owner 승인 불필요 — 순수 설정 배선)

`LocalOpenAICompatibleRuntimeConfig.model_name` 기본값(`qwen3-35b`)이 실제 LM Studio에
로드된 모델(`qwen/qwen3.6-35b-a3b`)과 달랐던 문제. `resolve_whisper_stt_config()`와 같은
패턴으로 `resolve_local_runtime_config()`를 추가해 `VIDEOBOX_LOCAL_MODEL_NAME` 환경변수로
덮어쓸 수 있게 하고 `compose.yaml`에도 통과시켰다. TDD로 진행, 신규 테스트 6건 + 포커스
회귀(`test_local_runtime_config.py`+`test_stt_runtime_config.py`+`test_api.py`) 392건 전부 통과.

## 이번 루프에서 확인만 하고 손대지 않은 것

- **F-6 (테마 하드코딩 부채)**: `product-shell.css`에 하드코딩 색상 0건 확인 —
  이전 세션 Task 11/11A에서 이미 해결됨. 문서만 stale이었다.
- **F-7 (중복 액션 노출, "새 영상 만들기" 3곳)**: 어느 진입점을 남길지는 승인된
  워크스페이스 디자인 구조를 건드리는 UX 판단이라 owner 결정 없이 진행하지 않았다.

## 남은 것 — owner 확인/승인이 필요해서 자동으로 진행하지 않았다

1. **Task 18 — 구글 드라이브 실제 파일 이동.** 감시·해시검증·이동 로직은 완료했고
   owner의 실제 Drive 폴더를 읽기 전용으로 스캔해 확인까지 했다. 실제 촬영본 파일을
   옮기는 건 owner의 실제 개인 파일을 건드리는 일이라 owner가 지켜볼 수 있을 때로
   미뤄뒀다. 반복 실행되는 워처 루프와 라이브러리→project 복사 경로도 아직 없다.
2. **컨테이너→호스트 LM Studio 네트워크 경로** (`compose.yaml` `extra_hosts` 등).
   `CLAUDE.md §5`가 컨테이너 네트워크 경계 변경을 owner 승인 필요 항목으로 명시한다.
   Task 19(미디어 분석 worker)도 컨테이너 스택에선 같은 이유로 아직 못 켰다 — 호스트
   네이티브 dev 서버(`scripts/run_api.py`)에서는 이미 동작한다.

이 둘 외에는 계획서(`docs/superpowers/plans/2026-08-05-videobox-owner-usable-recovery.md`)
상 열려 있는 새 작업이 없다. `docs/handoffs/2026-08-05-videobox-owner-dogfood-findings-backlog.ko.md`의
나머지 항목들은 대부분 이미 해결됐거나(F-6처럼) owner의 결정 자체가 필요한 사안(D-1
팔레트 재승인, S-1/S-2/S-4 범위 결정 등)이라 무인 세션에서 처리할 대상이 아니었다.
