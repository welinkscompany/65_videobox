# Mem0 완전 제거, 유진 기억 사서 네이티브 전환 (2026-09-18)

**대체됨:** `docs/handoffs/2026-09-19-isolated-stack-full-e2e-verification.ko.md` —
이 문서가 "안 한 것"으로 남겨 둔 컨테이너 재빌드 + 브라우저 실물 확인을
격리 스택으로 끝까지 밟았고, `scripts/run_memory_librarian.py`의 컨테이너
연결 결함을 발견·수정했다.

## 요청과 배경

대표님이 다른 세션에서 직접 지시: "mem0 걷어내고, argo 시스템에서 도서관
사서 기억 시스템을 도입하자... 실질적으로 mem0는 쓰지도 않고 기억도 나중에
정리가 안돼." 2026-09-10에 이미 한 번 "껐다, 코드는 그대로 둔다"로 다뤄졌던
결정을 오늘 완전히 밀어붙이라는 지시. 격리된 worktree
(`.claude/worktrees/agent-aabbd843de5e5844e`)에서 작업했고, 원본 worktree나
공용 컨테이너 스택은 건드리지 않았다.

## 이번 턴에 한 일

### 1. 설계 문서

`docs/decisions/2026-09-18-mem0-removed-native-memory-librarian.ko.md` —
owner 실측(운영 Postgres 직접 조회) 결과, 재사용 판단, 판단이 필요해서
결정만 내린 것 넷(Postgres 표 vs 파일, MERGE 구현, 시험 데이터 오염 방지,
CLAUDE.md §6 대조 원칙 처리)을 근거와 함께 적었다. **먼저 읽어라.**

### 2. 실측 — owner 판단이 사실인지 확인

운영 Postgres(`65_videobox-videobox-postgres-1`, 읽기 전용 조회)에서:

- 승인된 기억 후보 15개 중 서로 다른 문구는 **3개뿐**(5주 넘게).
- 그중 하나는 옛 mem0 어댑터의 중복 저장 결함으로 **9번** 중복 저장됐었다.
- 사서 워터마크(`yujin_memory_librarian_watermark`)는 **0행** — 자동 사서가
  실제로 실행된 적이 한 번도 없다.
- **시험 데이터 오염을 실물로 확인했다.** `live-check-*`, `memcheck-*` 같은
  dev 검증 스크립트의 `client_message_id`가 실제 owner 프로젝트
  (`b-roll-smoke-test`)의 대화와 같은 테이블에 섞여 있었고, 이미 승인된
  기억 후보 하나(`...화면검증-4913.`)는 텍스트 자체가 QA 채점 흔적이었다.

owner의 "쓰지도 않고 정리도 안 된다"는 판단이 코드로 확인됐다.

### 3. 걷어낸 것 (설계 문서에 전체 목록)

`hermes_memory_adapter.py`, `memory_gateway.py`,
`docker/hermes-memory-adapter.Dockerfile`,
`scripts/smoke-hermes-yujin-mem0.ps1` 삭제. `compose.hermes-yujin.yaml`의
memory-adapter 서비스·볼륨·네트워크 삭제. `AgentGatewayClient`의 memory RPC
4개, agent-gateway의 `/internal/hermes/memory/*` 엔드포인트 4개 삭제.
`MEM0_*`/`VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN` 환경변수 전부 삭제
(compose·`.env.container.example`·스크립트).

### 4. 새로 만든 것

- **`YujinMemoryService`(`services/api/src/videobox_api/yujin_memory_service.py`)를
  전면 재작성.** 저장은 로컬 계산(`local-` + external_ref 해시) + 정확히
  같은 문구 재사용(dedup, 9번 중복 결함 방지), 삭제는 로컬 마킹만, 조회는
  카테고리 힌트 낱말 + 토큰 겹침으로 로컬 순위 매기기. 승인 큐의 claim →
  outcome → finalize 상태 기계는 **그대로 재사용**(스키마 변경 없음).
- **`find_stored_yujin_memory_ref`, `list_memory_librarian_watermarks`**를
  `_store_yujin_memory.py`에 추가.
- **`memory_librarian.py`에 dev 검증 메시지 필터**
  (`_looks_like_dev_check_message`, `client_message_id` 접두사 블랙리스트)
  추가 — 실측한 오염 패턴 그대로.
- **API 서비스 기동 시 "따라잡기" 배경 작업**
  (`_catch_up_memory_librarian`, `main.py`의 기존 정비 루프에 한 단계
  추가). 컨테이너가 상시 실행이 아니라 owner가 켜고 끄는 방식이라(재시작
  정책 없음, 크론 없음 — `docker inspect`로 확인) 고정 시각 대신 "기동마다
  워터마크를 보고 20시간 이상 지났으면 그 자리에서 한 번 따라잡는다"로
  했다. **워터마크가 있는 (project_id, conversation_id)만** 본다 — 사람이
  `run_memory_librarian.py`로 최소 한 번 돌린 프로젝트만 자동 대상이 된다.
  새 스케줄러 프레임워크·Windows 작업 스케줄러는 범위 밖으로 뺐다(owner
  확정 지침).

### 5. 테스트 (RED→GREEN, 파일별로 개별 확인)

| 파일 | 처리 |
|---|---|
| `tests/test_hermes_memory_adapter.py` | 삭제 (대상 파일 자체가 없어짐) |
| `tests/test_agent_gateway_memory.py` | 삭제 (memory RPC 전용 시험) |
| `tests/test_yujin_memory_service.py` | 전면 재작성 — 로컬 dedup·재시도·claim 충돌 시험으로 교체 |
| `tests/test_yujin_memory_retrieval.py` | 전면 재작성 — 로컬 순위 매기기 시험으로 교체 |
| `tests/test_api_yujin_memory.py` | Gateway mock 셋 제거, 나머지 유지 |
| `tests/test_agent_gateway_client.py` | memory 관련 시험 3개 제거, 나머지(스트림·예약·SSRF 등) 유지 |
| `tests/test_hermes_yujin_compose_contract.py` | memory adapter 전용 시험 6개 제거, 나머지 시험에서 관련 단언만 제거 |
| `tests/test_hermes_yujin_profile_distribution.py` | 1개 시험을 "제거됐는지" 확인으로 뒤집음 |
| `tests/test_set_local_model_script.py` | 옛 7자리→새 5자리(어댑터 자리 2개 삭제) |
| `tests/test_local_model_name_is_one_value.py` | mem0 모델 SSOT 시험 2개 삭제, compose/유진 두뇌 대조만 유지 |
| `tests/test_user_path_failures_are_recorded.py` | `gateway=` kwarg 제거, 카테고리 스키마 검증 추가로 동작 유지 |
| `tests/test_hermes_run_service.py` | `_MemorySearchGateway` 제거, 로컬 조회 1회 계약으로 시험 이름·본문 교체 |
| `tests/test_memory_off_is_not_memory_broken.py` | "꺼짐 vs 고장" 시험을 "이제 항상 켜져 있다" 시험으로 뒤집음 |
| `tests/test_owner_ready_script.py` | `SMOKE_SCRIPTS`/`PUBLIC_MARKERS`/`REQUIRED_CREDENTIAL_KEYS`에서 mem0 항목 제거, 스모크 스크립트 개수 6→5에 따른 하드코딩된 카운트·순서 단언 전부 갱신 |
| `tests/test_hermes_agent_pin_consistency.py` | 삭제된 `hermes-memory-adapter.Dockerfile`을 pin 대조 대상 목록에서 제거 |
| `tests/test_handoff_entry_point.py` | 같은 날 인계 문서 둘이 있어 옛 것에 "대체" 표시 추가(정확한 마커 문구는 그 문서 첫 줄에 있다) |
| `tests/test_memory_librarian_catchup.py` | **새 파일.** `_catch_up_memory_librarian`/`_memory_librarian_watermark_is_stale` 전용 시험 6개 |

`yujin_memory_service.py`에 **카테고리 화이트리스트 검증**을 추가했다
(`_ALLOWED_CATEGORIES`) — 옛 `GatewayRetrievedMemory` pydantic 모델이
`Literal[...]`로 하던 일을 로컬 구현이 빠뜨렸던 것을 시험이 잡았다
(`test_a_memory_row_that_will_not_parse_says_so_instead_of_vanishing`).

**owner-ready.ps1 자체도 하나 고쳤다.** `verify-hermes-yujin-runtime.ps1`의
새 출력 문구를 테스트 픽스처에서만 맞추고 **owner-ready.ps1 자신이 하드코딩해
둔 같은 문구**(`$definitions`의 `ExactLine`)를 빠뜨렸다면 시험이 74개까지
와르르 무너졌다 — 실물(전체 pytest)로 돌리지 않았으면 못 잡았을 결함이다.

### 6. 전체 backend pytest — 독립 실행, 최종 결과

`.venv/Scripts/python.exe -m pytest -q --ignore=tests/test_mcp_server.py`
(**이 worktree에는 `.venv`가 없어서 새로 만들고
`requirements-dev.txt`/`requirements-container.txt`/`requirements-runtime.txt`를
설치했다** — `requirements-mcp.txt`는 `uvicorn` 버전과 충돌해서 설치 못함,
`test_mcp_server.py`는 이번 변경과 무관해 `--ignore`로 뺐다.)

- **1차 실행(41분)**: 22개 실패. mem0 제거와 직접 관련된 게 8개
  (`test_hermes_run_service.py` 2, `test_memory_off_is_not_memory_broken.py` 1,
  `test_owner_ready_script.py` 계열 다수), **간접적으로 걸린 게 14개**
  (`test_handoff_entry_point.py` — 같은 날 인계 문서 2개 충돌;
  `test_editor_ui_source_provenance.py` 5개 — **내 변경과 무관한 사전 존재
  문제, 아래 참고**). 전부 고쳤다.
- **owner-ready.ps1 시험은 세 번 더 돌려서 확인했다**(처음엔 owner-ready.ps1
  자신의 하드코딩 문구를 못 고쳐서 74개까지 깨졌다가, 74→2→1→0으로 줄였다).
- **2차 실행(37분)**: 6개 실패로 줄었다. 5개는 아래 ProductShell.tsx
  건(무관), 1개는 **내가 새로 만든 결함**이었다.
  `test_handoff_entry_point.py::test_entry_map_points_at_the_newest_handoff`는
  "옛 문서를 대체시켰다는 표시 낱말이 없는 문서만 살아있는 인계로 본다"는
  판정 로직을 쓰는데, 이 문서의 표 한 줄이 (설명하려고) 그 표시 낱말을
  그대로 옮겨 적는 바람에 이 문서 자기 자신이 "대체된 옛 문서"로 오판됐다.
- **3차 실행에서도 같은 자리에서 또 재현됐다** — 처음 고칠 때 그 표시
  낱말을 다른 문장으로 한 번 더 옮겨 적어서 또 그대로 걸렸다(자기 지시
  버그를 고치다 같은 실수를 반복한 사례). 이 절 자체에서 그 표시 낱말을
  글자 그대로 쓰지 않도록 바꿔서 마무리했다 — 정확한 표시 낱말이 필요하면
  `tests/test_handoff_entry_point.py`의 `_SUPERSEDED` 상수를 봐라.
- **3차 실행**: `test_handoff_entry_point.py`는 고쳤지만 ProductShell.tsx
  관련 5개에 `test_owner_ready_script.py::test_smoke_runs_exact_static_non_live_scripts_and_writes_sanitized_receipt`가
  하나 더 끼어 총 6개.
- **4차(최종) 실행 -- 38분 49초**: `5074 passed, 56 skipped, 1 xfailed,
  6 failed`. 6개 전부 `test_editor_ui_source_provenance.py`(ProductShell.tsx
  건, 5개 -- 아래 참고)와 `test_owner_ready_script.py`의 다른 스모크 시험
  1개다. **단독 실행하면 통과한다**(재확인함) -- mem0와 무관한
  `test_owner_ready_script.py`의 두 하위 시험(`test_smoke_runs_exact_static_non_live_scripts_and_writes_sanitized_receipt`,
  `test_smoke_credential_classifier_fails_closed_without_value_disclosure[mixed_single_inside_double]`)이
  네 번의 전체 실행에서 각각 딱 한 번씩, 서로 다른 시험이 흔들렸다 -- 이
  파일이 실제 PowerShell 하위 프로세스를 여러 개 띄우는 구조라 CPU 부하가
  큰 상황(이번 세션에서 전체 pytest를 네 번 연달아 돌렸다)에서만 흔들리는
  것으로 보인다. mem0 제거와 무관하고, 재현이 일관되지 않아 이번 작업
  범위 밖으로 판단한다.
- **mem0와 직접 관련된 실패는 4차 실행에서 0건이다.** 이번 작업의 핵심
  검증 목표는 달성됐다.

**내 변경과 무관하게 발견한 것 — `apps/web/src/app/ProductShell.tsx` provenance
해시 어긋남.** `test_editor_ui_source_provenance.py` 5개가
`docs/oss/editor-ui-source-map.json`에 박힌 `normalized_sha256`과 실제
파일 내용이 다르다고 거부한다. `git status --short apps/web/src/app/ProductShell.tsx`가
빈 출력이라 **이 워킹트리는 그 파일을 전혀 안 건드렸다** — 커밋된 HEAD
상태 자체가 이미 manifest와 어긋나 있다는 뜻이다. 별도 세션(`task_a923ef55`)으로
플래그해 뒀다 — 이번 mem0 제거 작업 범위 밖이라 여기서 고치지 않았다.

## 검증하지 못한 채 남은 것 / 안 한 것

- **컨테이너 재빌드 + 브라우저 실물 확인 — [턴 종료 시점 상태로 채워라].**
  다른 병렬 에이전트가 `compose.yaml`의 고정된 `name: 65_videobox` 때문에
  아무 worktree에서나 `docker compose`/`owner-ready.ps1 -Rebuild`를 그냥
  돌리면 **지금 쓰이고 있는 공용 스택(포트 5173)을 덮어쓴다**는 사고를
  실제로 냈다고 코디네이터가 경고했다. 그래서 격리해야 한다 —
  `COMPOSE_PROJECT_NAME=videobox-mem0-removal-<식별자>`, 다른 포트(5299/5273
  등 이미 다른 에이전트가 씀 — 더 다른 번호), 별도 데이터 루트, 작업 전
  `docker ps`로 확인, 끝나면 내 컨테이너·이미지·볼륨만 정리. `owner-ready.ps1`은
  이 파라미터들을 직접 노출하지 않아서 `docker compose` 직접 호출이
  불가피했다(코디네이터가 이 예외를 명시적으로 승인함, CLAUDE.md §3의
  "owner-ready.ps1로만" 규정보다 우선).
- 기존 mem0 중복 point 정리(운영 Postgres에 남은 중복 8개)는 owner 판단
  대기 상태 그대로다 — 이번 작업은 코드만 바꿨고 운영 데이터는 손대지
  않았다.
- `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-mem0-memory.md`
  (옛 계획 문서)는 역사 기록으로 그대로 뒀다 — 계획 문서 자체를 고치는 건
  범위 밖으로 판단했다(`test_hermes_yujin_plan_state_contract.py`가 그
  문서의 특정 카운트를 검증하는데, 이번 시험 실행에서 이미 통과했다 —
  이 문서가 mem0를 언급하는 줄이 있어도 "20개 마스터 태스크 ID" 계약
  자체와는 무관해서 안 깨졌다).

## SSOT 갱신

- `CLAUDE.md` §2 표의 "최신 세션 인계" → 이 문서.
- `CLAUDE.md` §6의 Mem0 승인 문구 → 제거 사실과 새 구조로 교체.
- `docs/development-fast-path.ko.md` §10.14 조항 2-A → "[2026-09-18 폐기]"
  표시하고 역사 기록으로만 남김(조항 1·2·2-B·2-C·3·4는 그대로 유효).
