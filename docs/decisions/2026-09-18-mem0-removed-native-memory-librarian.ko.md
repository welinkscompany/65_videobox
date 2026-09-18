# Mem0 제거, 유진 기억을 "사서" 패턴으로 네이티브 전환 (owner 지시 2026-09-18)

## 배경 — owner 지시

> "'기억은 자체 호스팅 Mem0' 이거 우리 mem0 걷어내고, argo 시스템에서 도서관 사서
> 기억 시스템을 도입하자... 실질적으로 mem0는 쓰지도 않고 기억도 나중에 정리가
> 안돼... 지금 우리 헤르메스 에이전트에서 다른 프로젝트도 모두 이 시스템으로
> 전환하고 있거든."

이 결정은 새로 시작한 게 아니다. **2026-09-10에 이미 한 번 다뤄졌다** —
`docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md`의 결론을
`bdb4bace4` 커밋이 "껐다, 코드는 그대로 둔다"로 확정했었다. 그때 완전히 걷어내지
않은 이유는 "코드까지 지우면 관련 시험 7개·스크립트 3개를 같이 고쳐야 해서
작업량이 큼"이었다. 오늘 owner가 그 작업량을 감수하고 완전히 걷어내라고
명시적으로 지시했다.

## 실측 — owner 판단이 사실인지 코드로 확인

2026-09-18, 운영 Postgres(`65_videobox-videobox-postgres-1`)를 직접 읽었다(읽기
전용).

- `yujin_memory_candidates`: 총 **15개** 행. `approved/stored` 10개,
  `approved/deleted` 4개, `approved/not_requested` 1개.
- 실제로 서로 다른 문구는 **3개뿐**이다(`docs/mem0-memory-backup-2026-09-10.ko.md`가
  이미 2026-09-10에 이 사실을 적어 뒀다) — 그중 "배경 음악..." 하나가 저장 전
  중복 확인이 없어 **9번** 중복 저장됐었다(그 결함은 `6fb13156d`로 고쳤지만
  이미 쌓인 중복은 그대로 남아 있었다).
- `yujin_memory_librarian_watermark`: **0행**. `memory_librarian.py`(사서
  증류 로직, `5e9eeab64`/`c84de46af`)가 아직 자동으로 실행된 적이 없다 — 지금
  DB의 승인된 기억 15개는 전부 사서가 아니라 더 이른 수동/개발 검증 경로로
  만들어졌다.
- **시험 데이터 오염 확인.** `director_messages.client_message_id`에
  `live-check-002`, `memcheck-1786171467-a`, `screen-1786176408-a` 같은
  dev 검증 스크립트의 사람이 읽는 이름이 실제 owner 프로젝트
  (`b-roll-smoke-test`, 2026-08-08~09)의 대화와 같은 테이블에 섞여 있었다.
  이미 승인된 기억 후보 중 하나(`컷 전환은 0.8초 간격으로 붙여 주세요.
  화면검증-4913.`)는 텍스트 자체에 QA 채점 흔적("화면검증-4913")이 남아 있어
  **owner가 실제로 한 말이 아니라는 것이 문구만으로 확인된다.**

**결론: owner 판단이 사실과 일치한다.** 5주 넘게 서로 다른 승인 기억 3개뿐이고,
그중 하나는 중복 버그로 오염됐고, 자동 사서는 한 번도 안 돌았고, 이미 있는
데이터 자체에 시험 오염이 섞여 있었다. "쓰지도 않고 정리도 안 된다"는 말 그대로다.

## 설계 — 무엇을 들고, 무엇을 버리는가

### 이미 있던 것 (재사용 게이트 — 그대로 둔다)

1. **일지(journal) = `director_conversations`/`director_messages`.** Rumi의
   `01_시스템/루미-기억/일지/`처럼 파일을 새로 만들 필요가 없다 — VideoBox는
   이미 프로젝트별 대화 원본을 append-only로 갖고 있다.
2. **사서 증류 = `memory_librarian.py` + `memory_librarian_boilerplate.py`
   (이미 구현됨, 09-08).** 대화를 훑어 LLM으로 증류하고, 결과를 **owner 승인
   큐**(`yujin_memory_candidates`)에 pending으로 올린다. Rumi와 달리 사람
   승인 없이 자동으로 저장하지 않는다 — CLAUDE.md §6이 못박은 "owner가 승인한
   것만 나간다"를 지키기 위한 의도적 차이이며, 이번 작업에서 바꾸지 않았다.
3. **승인 상태 기계 = `_store_yujin_memory.py`의 claim → outcome 기록 →
   finalize.** 원래 "믿을 수 없는 외부 provider에 멱등하게 쓴다"는 목적으로
   만들어졌지만, 상태 이름(`stored`/`event_pending`/`ambiguous`/
   `failed_retryable`)이 Mem0 전용이 아니라 일반적인 멱등-쓰기 개념이라 **그대로
   재사용한다.** 스키마 변경도, 마이그레이션도 없다.

### 새로 바꾼 것

1. **저장 = 로컬 계산.** `YujinMemoryService.store_candidate`가 더 이상
   외부 provider를 부르지 않는다. `memory_ref`를 로컬에서 결정론적으로
   계산하고(`local-` + `external_ref`의 sha256), 저장 직전에
   `find_stored_yujin_memory_ref`로 **정확히 같은 (project_id, category,
   proposed_text)**가 이미 저장돼 있는지 확인해 있으면 그 ref를 재사용한다
   — Mem0의 9번 중복 저장 결함을 로컬로 고정 방지한다.
2. **삭제 = 로컬 마킹.** 외부 확인 호출이 없어졌으니 `delete_candidate_memory`가
   `mark_yujin_memory_delete_call_started` → `mark_yujin_memory_deleted`만
   부른다.
3. **조회 = 로컬 순위 매기기.** Mem0의 뜻 기반 검색 대신, 카테고리 힌트
   낱말(예: "자막"→caption) + 질의-본문 토큰 겹침으로 점수를 매겨 정렬한다.
   임베딩·LLM 호출이 없다 — 매 채팅 턴마다 도는 hot path라 무겁게 만들지
   않는다(`development-fast-path.ko.md` §10.6).
4. **사서 자동 실행 트리거 — "기동 시 밀렸으면 따라잡기".** 컨테이너는 상시
   실행이 아니라 owner가 `owner-ready.ps1`로 켜고 끄는 온디막드 방식이다
   (`docker inspect`로 `RestartPolicy.Name` 빈 값, `compose.yaml`에 크론
   없음을 확인). "밤마다 도는 잡"을 그대로 이식하면 컨테이너가 꺼져 있는
   밤엔 절대 안 돈다. 그래서 API 서비스가 이미 갖고 있던 배경 정비 루프
   (`_media_analysis_lifespan`의 `worker()`, 라이브러리 색인과 같은 자리)에
   "워터마크를 보고 20시간 이상 지났으면 그 자리에서 한 번 따라잡는다"는
   단계 하나만 추가했다(`_catch_up_memory_librarian`, `main.py`). 새
   스케줄러 프레임워크나 Windows 작업 스케줄러는 들이지 않았다(범위 밖으로
   명시적으로 뺐다).

### 판단이 필요해서 결정만 내린 것 (근거를 남긴다)

**1. 주제 노트를 Rumi처럼 파일(`notes/*.md`)로 둘 것인가, 기존 Postgres 표로 둘
것인가 — Postgres 표를 선택했다.**

- 이미 `yujin_memory_candidates`가 "승인된 사실 하나 = 행 하나"로, 절대
  `proposed_text`를 UPDATE하지 않는 append-only 계약을 갖고 있다(스키마를
  다시 읽어도 `create_yujin_memory_candidate`는 INSERT만 한다). Rumi의
  "MERGE, 절대 REPLACE 금지"라는 원칙이 **이미 구조적으로 지켜지고 있었다.**
- VideoBox는 컨테이너 다중 서비스 구조라 파일 기반 저장은 "어느 컨테이너의
  어느 볼륨에 쓰는가"라는 새 운영 문제를 만든다. Postgres는 이미 그 문제를
  풀어 뒀다.
- 재사용 게이트(`implementation-plan.ko.md` §8.1)가 "통째 복사보다 선별
  이식"을 요구한다 — Rumi의 저장 **형태**(파일)가 아니라 저장 **원칙**(추가만,
  절대 덮어쓰지 않음)만 이식했다.

**2. "정확히 같은 문장이면 병합(MERGE)"을 무엇으로 구현했는가.**

Rumi는 같은 주제의 새 관찰을 노트 아래에 "## 날짜" 절로 추가한다. VideoBox의
승인 큐는 사실 단위가 이미 원자적(한 문장, ≤280자, 5개 고정 카테고리)이라
"같은 사실을 다시 봤다"는 **정확히 같은 (category, proposed_text)가 다시
승인**되는 것으로 나타난다. 이 경우 새 후보를 별도로 저장하지 않고
`find_stored_yujin_memory_ref`로 기존 memory_ref를 재사용한다 — 원본 텍스트는
절대 바뀌지 않고(REPLACE 없음), 재승인은 `yujin_memory_operation_audit`에
남는 감사 기록으로 "다시 관찰됨"의 흔적을 남긴다(이미 있는 감사 로그
메커니즘을 그대로 씀).

**3. 시험/합성 데이터가 저널에 섞여 들어가는 것을 어떻게 막았는가.**

두 겹으로 막는다.

- **프로젝트 겹 — 자동 실행은 사람이 이미 본 프로젝트만.** `_catch_up_memory_librarian`은
  `store.list_projects()`로 전체를 훑지 않는다. **워터마크 행이 있는
  (project_id, conversation_id)만** 다시 본다 — 즉 owner가
  `run_memory_librarian.py`로 그 프로젝트에서 사서를 최소 한 번 직접 돌린
  적이 있어야 자동 따라잡기 대상이 된다. 2026-09-18 실측 기준 워터마크는
  0행이라, 이 게이트가 켜진 순간에는 자동으로 건드릴 프로젝트가 하나도
  없다 — owner가 처음 수동으로 한 번 돌리는 순간부터 그 프로젝트만 자동
  따라잡기 대상이 된다.
- **메시지 겹 — dev 검증 호출의 사람이 읽는 이름을 막는다.**
  `memory_librarian.py`의 `_looks_like_dev_check_message`가
  `live-check-`, `final-check-`, `memcheck-`, `localcheck-`, `screen-`로
  시작하는 `client_message_id`를 가진 사용자 메시지를 증류 대상에서 뺀다.
  **UUID 형식만 허용하는 화이트리스트는 시도하지 않았다** — 실제 데이터를
  보니 가장 오래된 진짜 owner 프로젝트(`project-318cc020`)조차 예전 화면
  버전의 흔적으로 `msg-<hex>` 형식을 썼다. 형식 하나로 진짜/가짜를 가를 수
  없어서, 실제로 관측된 dev 검증 스크립트의 이름 접두사를 막는 쪽을 택했다
  — Rumi 자신도 "다음 것은 내가 예측 못 한 세 번째 모양일 것"이라고
  인정하듯, 이건 완전한 필터가 아니라 관측된 위험에 대한 방어다.

**4. CLAUDE.md §6의 "게이트웨이 응답 중 로컬 기록과 정확히 일치하는 것만
채택한다"는 대조 원칙을 어떻게 유지하는가.**

이제 외부 게이트웨이 자체가 없으니 그 대조는 **실행 가능한 코드 경로가
아니다.** 하지만 그 대조가 지키던 것(owner가 로컬에서 실제로 승인·저장한 것
말고는 절대 유진의 대화 컨텍스트에 실리지 않는다)은 사라지지 않았다 —
`YujinMemoryService._eligible_local_memories`가 반환하는 모든 항목이
`self._store.list_yujin_memory_retrieval_rows`가 돌려준 행에서만 나온다.
외부에서 주입할 자리가 구조적으로 없어졌으므로, 원래 대조가 막던 위협
자체가 없어졌다. 이 불변을 지키는 회귀 시험을
`tests/test_yujin_memory_retrieval.py`에 남겼다(로컬에 없는 항목이 조회
결과에 나오지 않는다는 것을 매 시험이 암묵적으로 검증한다 — store를
직접 스텁하므로).

## 걷어낸 것

- `services/agent-gateway/src/videobox_agent_gateway/hermes_memory_adapter.py`
  (Mem0 어댑터 FastAPI 앱 전체, `_PinnedHermesMem0Provider`/`_LocalMem0Provider`
  포함)
- `services/agent-gateway/src/videobox_agent_gateway/memory_gateway.py`
  (게이트웨이-어댑터 DTO)
- `docker/hermes-memory-adapter.Dockerfile`
- `scripts/smoke-hermes-yujin-mem0.ps1`
- `compose.hermes-yujin.yaml`의 `videobox-hermes-memory-adapter` 서비스,
  `videobox_mem0_store` 볼륨, `videobox-hermes-memory-network`
- `AgentGatewayClient`의 `add_approved_memory`/`reconcile_memory`/
  `search_memory`/`delete_memory` 4개 메서드와 그 DTO import
- agent-gateway `main.py`의 `/internal/hermes/memory/*` 엔드포인트 4개와
  `memory_gateway` 파라미터
- `MEM0_API_KEY`, `VIDEOBOX_HERMES_MEMORY_ADAPTER_TOKEN`,
  `VIDEOBOX_MEM0_MODE`, `VIDEOBOX_MEM0_LOCAL_BASE_URL`,
  `VIDEOBOX_MEM0_LLM_MODEL`, `VIDEOBOX_MEM0_EMBEDDER_MODEL`,
  `VIDEOBOX_MEM0_EMBEDDING_DIMS`, `VIDEOBOX_MEM0_STORE_PATH` 환경변수
  (compose·`.env.container.example`·스크립트 전체)

## 제외한 것(이번 범위 밖)

- **Windows 작업 스케줄러로 컨테이너를 깨우는 방식**은 복잡도가 커서 뺐다.
  지금은 owner가 VideoBox를 여는(컨테이너를 켜는) 순간이 "정리할 때"다.
- Argo(`consolidate.mjs`) 자체(Node.js 멀티에이전트 플랫폼)는 의존성으로
  들이지 않았다 — 라이선스가 source-available이고, VideoBox와 무관한 기능
  (Telegram/Slack 게이트웨이, 크루 오케스트레이션, Supabase 동기화)이 딸려
  있다. **패턴만 순수 Python으로 이미 포트돼 있던 것을 그대로 썼다.**
- 기존 mem0 중복 point 정리(운영 Postgres의 `yujin_memory_candidates`에
  남은 중복 8개 삭제 여부)는 owner 판단 대기 상태였다(2026-09-10 인계) —
  이번 작업은 코드만 바꿨고 운영 데이터는 손대지 않았다.

## 검증

- `.venv/Scripts/python.exe -m pytest -q --ignore=tests/test_mcp_server.py`
  (전체 결과는 `docs/handoffs/2026-09-18-mem0-removed-native-memory-librarian.ko.md` 참고)
- **화면에서 실물로 확인했다(2026-09-18).** 공용 컨테이너 스택을 건드리지
  않기 위해, 이 worktree 전용 로컬 개발 서버(`.claude/launch.json`의
  `api`/`web`, 파일 저장소, scratch 데이터 폴더 -- owner의 실제
  `20_project\65_videobox-project`가 아니다)를 띄워 실제 브라우저로
  진행했다.
  1. 새 프로젝트를 만들고 유진 채팅에 "저는 빠른 컷 편집을 선호합니다"를
     보냈다 -- 실제 로컬 LM Studio(`qwen/qwen3.8-27b`)가 응답했다.
  2. 화면의 "기억" 패널에서 "빠른 컷 편집을 선호함"을 후보로 만들고
     "승인하고 저장"을 눌렀다. 네트워크 탭에서 `approve`(200)·`store`(200)를
     확인했고, 외부 어댑터로 나가는 호출은 없었다(그런 서비스 자체가
     이제 없다).
  3. scratch SQLite를 직접 열어 `yujin_memory_candidates.provider_memory_ref`가
     `local-<sha256>` 형식임을 확인했다 -- Mem0 id가 아니라 로컬 계산값이다.
  4. 새 메시지로 "제 컷 편집 취향을 그대로 알려주세요"를 보내자 유진이
     "지금 저장된 컷 편집 취향은 '빠른 컷 편집을 선호함'이에요"라고
     정확히 답했다 -- 저장 → 로컬 순위 매기기 → 채팅 컨텍스트 주입 →
     실제 LLM 응답까지 전 구간이 실물로 확인됐다.
  검증 중 CSRF 신뢰 origin 목록에 dev 포트(5199)를 임시로 추가했다가
  확인 직후 되돌렸다(`git status`로 무변경 확인) -- 제품 코드에는 남지 않았다.
