# 2026-08-08 세션 핸드오프 — 유진이 처음으로 실제로 돌기 시작한 날

## 한 줄 요약

유진 헤르메스 컨테이너는 **오늘 아침까지 한 번도 뜬 적이 없었다.** 기동을 막던 3겹과
대화를 막던 7겹을 전부 풀었고, 두뇌를 로컬 LM Studio(qwen)에 연결했고, Mem0를
**API 키 없이 이 컴퓨터 안에서만** 도는 자체 호스팅으로 전환했다.

`codex/videobox-container-compatibility` 브랜치, 원격과 동기화 상태, worktree clean.
백엔드 회귀 **3,131개 통과 / 실패 0**.

## 커밋 (전부 푸시 완료)

| 커밋 | 내용 |
|---|---|
| `b02bba055` | fix: 유진 컨테이너가 실제로 기동하도록 (실행 파일명·프로필 설치·비밀값) |
| `409c6f095` | fix: 배포 프로필에 로컬 모델 고정 (v1.3.0) |
| `79accae72` | fix: 유진 환경변수 허용 목록에 LM_* 추가 |
| `73a8dd58a` | feat: LM Studio로 유진의 로컬 두뇌 연결 |
| `c59c9eb56` | fix: VideoBox→유진 대화 경로가 실제로 대화를 실어 나르도록 (4건) |
| `ff6b15e2c` | fix: 글자 단위로 흘려보내는 로컬 모델이 대화를 끝낼 수 있도록 |
| `14bfe8c03` | test: 올린 게이트웨이 클라이언트 제한 시간을 계약에 고정 |
| `4e6f7b67e` | fix: Hermes가 최종 텍스트의 빈 줄을 합치는 것을 견디도록 |
| `89a94d4cd` | feat: Mem0를 호스팅 키 없이 이 컴퓨터 안에서만 실행 |

## 지금 어디까지 되나 (실측)

- 컨테이너 5개 전부 healthy: postgres / workspace / hermes-yujin /
  hermes-memory-adapter / agent-gateway
- **앱 경로 대화 완주.** `POST .../hermes-runs` → SSE가 `run_completed`로 끝나고
  한국어 답변이 나온다. 게이트웨이 `/health`의 `chat_ready: true`
  (설정값이 아니라 **실제 대화가 완주했다는 증거**로만 켜지는 값)
- **자체 호스팅 Mem0 저장·검색 동작.** `MEM0_API_KEY`는 빈 값인데
  어댑터 health가 `configured: true`. 저장한 기억이 검색으로 그대로 돌아온다
- 씽킹 모드는 owner가 LM Studio에서 껐다. 답변이 첫 글자부터 한국어다

## 알아둘 것: 부하 중 흔들리는 테스트가 몇 개 있다

28분짜리 전체 회귀에서 **시간 의존 테스트 세 개가 각각 한 번씩 실패**했다가 단독
실행에서는 전부 통과했다. 오늘 하루에만 세 번이다.

- `test_api_capcut_draft_export_endpoint.py::test_capcut_draft_handoff_renews_its_durable_lease_during_a_slow_registration`
- `test_api_yujin_memory.py::test_create_rejects_noncompleted_run_sources_before_candidate_or_provider`
- `test_api_yujin_memory.py::test_delete_retries_after_local_finalize_failure`

셋 다 lease·retry 같은 **실시간 타이밍**에 걸려 있다. 전체 회귀에서 이 셋 중 하나가
빨간불이면 **먼저 단독으로 다시 돌려 본다.** 단독에서 통과하면 회귀가 아니다.
정리 대상이지만 이번 세션 범위 밖이라 남겨 둔다.

## 다음 세션에서 바로 할 일

### 1. 유진 기억 전 구간 검증 (미완, 가장 우선)

저장과 검색은 되지만 **유진이 과거 기억을 실제로 참조하는 것은 아직 확인 못 했다.**

조회는 `services/api/src/videobox_api/yujin_memory_service.py`의 **로컬 대조**를
통과해야 한다 — 게이트웨이가 돌려준 결과 중 **로컬 기록과 정확히 일치하는 것만**
채택한다. 이게 외부에서 기억을 주입하지 못하게 막는 유일한 장치다. **제거하지 말 것.**

따라서 owner가 화면에서 기억을 승인해야 로컬 기록이 생긴다. 검증 순서:

1. owner가 편집하면서 유진이 기억 후보를 제안하게 한다
2. 승인한다 (로컬 기록 + 어댑터 저장이 같이 일어나야 한다)
3. 새 대화에서 그 기억이 문맥에 실리는지 확인한다

### 2. 기억 후보 제안 흐름 자체가 동작하는지 확인

위 1번의 전제다. `POST /api/projects/{id}/director/memory-candidates`가 있고
`config/hermes/yujin/skills/videobox-memory/SKILL.md`가 규칙을 정의한다. 화면에서
후보가 실제로 뜨는지는 이번 세션에서 확인하지 못했다.

### 3. 앞선 세션에서 남은 것

- **Task 26**: owner 참관 실제 마이크 검증
- **Task 25 Step 2~6**: TTS 음성 판단 (owner가 샘플을 들어야 함)
- **Task 34**: 저장하지만 읽지 않는 데이터 정리 (`voice_samples` 죽은 테이블 등)
- **Task 35 Step 3**: 홈 대시보드 실데이터 (홈에서 fetch 허용 여부는 owner 결정 대기)
- **Task 29 남은 절반**: 버려진 요청이 LM Studio를 계속 점유하는 문제

## 진입점 문서 정리 (같은 세션, 나중에 한 것)

`CLAUDE.md`가 269줄이었고 그중 **§3 하나가 45%** 였다. 길이 자체(약 4,000 토큰)는
문제가 아니지만, 이 저장소가 가장 비싸게 배운 규칙 — **완료의 정의**와 **화면 검증** —
이 "개발 환경"이라는 제목 아래 묻혀 있었다. 훑는 사람도 훑는 도구도 건너뛴다.

- 그 규칙들을 **`## 4. 완료의 정의`** 로 끌어올려 자기 제목을 줬다
- 명령·주소·스크립트 목록은 `docs/development-fast-path.ko.md` `## 11`로 내렸다.
  `CLAUDE.md`에는 판단에 필요한 세 줄만 남겼다(venv 강제, owner-ready 강제, env 비밀)
- 219줄 / 6,960자로 줄었다. 절 번호가 밀려 §4~§8이 하나씩 이동했다
- `tests/test_handoff_entry_point.py`가 **크기 상한(260줄 / 8,000자)** 과
  **그 규칙들이 최상위 절에 있는지**를 고정한다

**알려진 낡은 참조 하나:** `docs/handoffs/2026-08-06-videobox-loop-session-handoff.ko.md:50`이
`CLAUDE.md §5`(승인 필요 항목)를 가리키는데 지금은 `§6`이다. 옛 인계 문서는 작성 시점의
기록이라 고치지 않았다. 현재 기준은 언제나 `CLAUDE.md` 본문이다.

## 이번 세션에서 실제로 고친 것 (원인별)

### 기동을 막던 3겹

1. **exit 127** — compose `command`에 실행 파일 `hermes`가 빠져 있었다. s6-overlay가
   CMD를 그대로 exec 해서 `-p`를 실행하려다 죽었다. 고정 digest와 `:latest` 둘 다
   같아서 **이미지 문제가 아니었다**
2. **프로필 미설치** — `owner-ready.ps1 -WithYujinMemory`가 `install-hermes-yujin-profile.ps1`을
   건너뛰고 바로 `up` 했다. `"Profile 'videobox-yujin' does not exist"`
3. **비밀값 8개 전부 자리표시자** — `hermes_capability_verifier_config_invalid` →
   `agent_gateway_service_token_invalid` 순으로 막혔다.
   `scripts/new-hermes-yujin-secrets.ps1`로 생성한다

### 대화를 막던 7겹 (전부 같은 화면 문구로 보였다)

1. **compose가 env 파일 값의 `$`를 변수로 먹는다.** scrypt 해시가 6칸→5칸이 돼
   로그인이 `Invalid credentials`로 실패했다. `$$` 이스케이프 필요.
   **`docker run --env-file`은 이스케이프하지 않으므로 두 경로의 동작이 다르다**
2. **`serve`에 `--isolated`가 없으면** 기계 전체 대시보드에 붙어 웹소켓 세션이
   `default` 프로필(anthropic 모델)로 열린다. `hermes -p videobox-yujin -z`는
   잘 되는데 앱만 안 되는 혼란스러운 증상
3. **게이트웨이가 `{"status":"accepted"}`만 인정했다.** Hermes 0.18.2는 `"streaming"`을
   보낸다. **테스트가 `streaming`을 오답으로 못박고 있었다**
4. 실행 서비스 `max_events` 256 → 4096 (로컬 모델은 글자 단위로 흘려보낸다)
5. 제한 시간 35초 두 겹 → 300초 (실행 서비스, 게이트웨이 클라이언트)
6. 게이트웨이 `_MAX_PUBLIC_EVENTS` 512 → 8192 (한 답변에 1000개 넘는 델타)
7. **Hermes가 최종 텍스트의 빈 줄 묶음을 합친다**(`\n\n\n`→`\n`). 엄격한
   `startswith`가 깨져 `gateway_output_unsafe`. 공백 차이만 눈감아주도록 고쳤더니
   **실패가 한 층 위로 옮겨갔다** — 작업 서비스는 최종 텍스트가 델타의 합과 **정확히
   같기**를 요구한다(`agent_gateway_client.py`의 `payload.text != assembled`).
   게이트웨이가 **자기가 흘려보낸 것**을 최종으로 내보내게 해서 끝냈다

### Mem0 자체 호스팅에서 걸린 3가지

1. **볼륨은 이미지 경로의 소유권을 물려받는다.** 어댑터는 uid 10000이고 루트가
   읽기 전용이라, Dockerfile에서 미리 만들어 두지 않으면 첫 저장이 PermissionError.
   **볼륨이 이미 있으면 지우고 다시 만들어야** 반영된다
2. **OSS는 호스팅 필터 문법(`{"AND": [...]}`)을 거절한다.** 평평한 소유자 키를 요구한다.
   `_LocalMem0Provider._split_filters`가 갈라서 **metadata 조건을 직접 다시 적용**한다 —
   빼면 승인 안 한 기억이 섞이고 되맞춤이 엉뚱한 기억을 고른다
3. **파일 기반 qdrant는 한 번에 한 프로세스만** 접근한다. 어댑터 복제본 불가,
   진단하려면 어댑터를 먼저 멈춰야 한다

## 이 세션의 두 가지 교훈 (다음에 같은 함정에 빠지지 않도록)

### 계약 테스트가 깨진 설정을 정답으로 고정하고 있었다

`tests/test_hermes_yujin_compose_contract.py`, `tests/test_hermes_yujin_profile_distribution.py`,
`tests/test_agent_gateway_hermes_rpc_client.py` 세 곳이 **동작하지 않는 값**을 pin 하고
있었다. 전부 초록불인데 컨테이너는 한 번도 뜬 적이 없었다.

**적용:** 컨테이너 관련 계약 테스트 통과를 "기동 확인"으로 적지 않는다.
`docker ps`의 healthy와 게이트웨이 `/health`의 `chat_ready`까지 본 것만 "된다"고 말한다.

### 실패 사유를 삼키면 서로 다른 원인이 같은 증상으로 보인다

두 층 모두 사유를 버리고 화면에는 "일시적으로 사용할 수 없습니다"만 띄웠다. 원인
다섯 개가 완전히 같아 보였다. 사유 기록을 넣은 뒤로는 한 줄로 위치가 잡혔다.

- 게이트웨이: `safe_block_reason()` + `hermes stream blocked: <사유>`
- 작업 서비스: `_log_block()` + `hermes run blocked: <사유>`

둘 다 **고정된 코드 문자열만** 남긴다. 예외 문구에 대화 내용이나 자격 증명이
섞일 수 있어서다.

**적용:** 유진 대화가 안 되면 **먼저 이 두 로그부터 본다.**

## 다시 켜는 방법

```powershell
# 비밀값이 자리표시자면 한 번만
.\scripts\new-hermes-yujin-secrets.ps1

# 유진 기억 스택까지 켜기 (프로필 설치가 이제 여기 포함돼 있다)
.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory
```

LM Studio가 `qwen/qwen3.6-35b-a3b`와 `text-embedding-bge-m3`를 로드한 채
1234 포트로 떠 있어야 한다. **씽킹 모드는 꺼져 있어야 한다** — 켜면 답변마다 영어
독백이 3~4천 자 붙고, 그것 때문에 위의 개수·길이 상한을 계속 건드린다.

## 확인 명령

```powershell
docker ps --filter name=videobox --format "{{.Names}}`t{{.Status}}"
docker exec 65_videobox-videobox-agent-gateway-1 python -c "import urllib.request,json;print(json.loads(urllib.request.urlopen('http://127.0.0.1:8081/health',timeout=8).read()))"
```

`chat_ready`는 대화를 한 번 해야 켜진다. 게이트웨이를 다시 만들면 초기화된다 —
`false`라고 해서 고장난 게 아니다.
