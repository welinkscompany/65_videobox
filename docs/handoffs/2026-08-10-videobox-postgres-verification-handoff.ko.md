# VideoBox 인계 — 운영 저장소 검증과 굳은 분석 (2026-08-10, 2차)

계획서: `docs/superpowers/plans/2026-08-10-videobox-consolidated-priorities.md` (새 SSOT)
앞 인계: `docs/handoffs/2026-08-10-videobox-diagnosability-handoff.ko.md`

**이 세션의 핵심은 owner의 한마디에서 나왔다** — "SQLite는 안 쓰는 걸로 아는데,
혹시 모르니까 확인해봐." 확인해 보니 맞았고, 그 확인이 훨씬 큰 것을 열었다.

## 가장 중요한 발견 — 회귀가 검증하던 저장소는 운영이 안 쓰는 쪽이었다

저장소는 **실행할 때 갈린다** (`services/api/src/videobox_api/main.py:675`).
`VIDEOBOX_DATABASE_URL`이 있으면 `PostgresProjectStore`, 없으면 `LocalProjectStore`(SQLite).
컨테이너는 앞쪽이다.

그런데 테스트는 73개 파일이 SQLite를 쓰고, Postgres 전용 52개는 통째로 건너뛰고 있었다.
**회귀 결과 맨 끝에 `52 skipped`가 매번 찍히고 있었는데 아무도 읽지 않았다.**

**왜 건너뛰었나 — 환경변수를 깜빡한 게 아니다.** `videobox-postgres`는 호스트 포트를
열지 않는다. 그리고 그것은 실수가 아니라 의도다 —
`tests/test_compose_contract.py:16`이 `"ports" not in videobox-postgres`를 못박고 있다.
**붙을 수 있는 데이터베이스가 애초에 없었다.** 그래서 아무도 그 변수를 설정할 수 없었다.

**어떻게 풀었나.** 실제 스택에 포트를 여는 것은 네트워크 경계 변경이라 `CLAUDE.md` §6
승인 대상이고, 위 계약 테스트도 깬다. 대신 **스택 밖에 일회용 PostgreSQL을 띄운다.**

```powershell
.\scripts\run-postgres-store-tests.ps1
```

**52개 통과, 건너뜀 0.** owner 데이터·스택·네트워크 경계는 건드리지 않는다.

**예상이 틀렸다.** 나는 "오래 안 돌렸으니 깨진 것이 꽤 있을 것"이라고 적었는데,
전부 통과했다. 검증이 없었다는 것과 코드가 틀렸다는 것은 다르다.

## 고친 것

### 1. 굳은 분석을 스스로 되살린다 (커밋 `483300c57`)

재시도 예산(`RETRY_BACKOFF_SECONDS = (5, 30)`)을 다 쓰면 3번째 실패에서 `next_retry_at`이
비고, claim 질의는 `failed`를 **다음 시도 시각이 적혀 있을 때만** 집어 간다. 그래서 영영
굳었다. 게다가 폴러(`main.py:361`)는 `failed`를 매 통과마다 후보에 넣어 dispatcher를
부르고 있었다 — claim이 조용히 `None`을 돌려주니 **아무 일도 안 일어나면서 로그도 없었다.**

복구 스윕이 이제 그런 것을 다시 큐에 넣는다. **재시작 한 번에 기회 한 번.**

- `attempt`를 일부러 초기화하지 않는다 → 수동 "다시 시도" 버튼과 **똑같이** 동작한다.
  예산을 통째로 돌려주면 아직 죽어 있는 공급자에 세 번 더 때린다.
- 같은 호출 안에서 `running`→`failed` 스윕보다 **먼저** 돈다. 이번 스윕에서 예산을 소진한
  건이 같은 스윕에 되살아나면 그건 복구가 아니라 무한 루프다.
- `blocked`는 건드리지 않는다. 원본 없음·파일 깨짐은 사람이 봐야 한다.

**SQLite와 Postgres 양쪽에서 검증했다.** Postgres 쪽 테스트를
`tests/test_postgres_project_store.py`에 남겼다 — 이 파일에는
"Postgres 배포에서만 터지던 버그"의 전례가 이미 있다(1237행 주석).

### 2. 저장소를 잘못 열면 로그에 남는다 (커밋 `54d14a8b6`)

주소 한 줄이 빠져도 **실패하지 않는다.** API는 멀쩡히 뜨고 빈 SQLite를 읽는데, 화면에서는
그것이 "프로젝트가 전부 사라짐"과 구별되지 않는다. 실제로 그렇게 생긴 SQLite 저장소가
런타임 폴더에 두 벌 있었다. 이제 시작할 때 어느 쪽을 열었는지 남긴다.
**비밀번호는 지운다** — 로그는 컨테이너 밖으로 나간다. 테스트로 못박았다.

### 3. 데이터베이스 로그 상한 (커밋 `54d14a8b6`)

다섯 중 `videobox-postgres`만 상한이 없었다. 계약 테스트를 **서비스 전체를 훑는 방식**으로
바꿨다 — 네 개를 나열하는 방식이었으면 새 서비스가 또 빠진 채 들어온다.

### 4. artifacts 3.6GB → 110MB

지운 것: `--work-root` 산출물과 지난 실행 결과.

**남긴 것: `task5-korean-600.wav` (110MB).** 산출물이 아니라 **입력**이다 —
`scripts/dev-fast-path.ps1:288`이 `--narration`으로 읽는다. **용량만 보고 지웠으면 검증
두 개가 깨졌다.** `CLAUDE.md` §5의 "경로로 참조되는 곳을 먼저 찾으라"가 실제로 값을 했다.

## 다음 세션이 이어서 할 것

새 계획서 `2026-08-10-videobox-consolidated-priorities.md`의 순서를 따른다.

- **P2 기록 넓히기** — 실패 이유를 버리는 곳 349, 기록하는 곳 3. 앞 세션이 owner 경로
  다섯 곳을 고쳤고 **나머지 346은 그대로다.** 값어치가 가장 크다.
- **P3 안 붙은 기능 29개** — 2026-08-09에 31개였고 5개를 붙였는데 지금 29개다.
  붙이는 속도만큼 새로 만들고 있다.
- **P4 `local_project_store.py` 분할** — 11,495줄. **선행 조건이 붙었다:** P0-1을 먼저
  끝낸 뒤에 한다. `PostgresProjectStore`가 이 파일을 상속하므로, Postgres 경로가
  검증되지 않은 상태에서 쪼개면 깨져도 모른다.

## 검증 방법

- 백엔드 전체: `.venv/Scripts/python.exe -m pytest -q` (약 23분)
- **Postgres 저장소: `.\scripts\run-postgres-store-tests.ps1`** (약 35초) — 새로 생김
- 컨테이너 반영: `docker compose --env-file .env.container build videobox-workspace` 후
  `up -d`. **rootfs가 읽기 전용이라 파일 복사로는 안 된다.**
  `owner-ready.ps1`에는 빌드 모드가 없다(Check/Start/Smoke/Open/OpenCapCut).
- 브라우저 검증 시 **창 너비 1600 이상.**

## owner가 알아야 할 것

- **새 영상 반입 목록은 비어 보인다.** 컨테이너가 보는 `drive-sync/새 영상`이 비어 있고,
  촬영본 726MB는 컨테이너가 안 보는 폴더에 있다. 이미 들어온 것은 라이브러리에 1.2GB
  있어 편집 테스트 자체는 된다.
- **LM Studio를 켜 둬야** 분석이 `blocked`로 안 떨어진다.
- 작업선이 `main`보다 **426 커밋 앞서** 있고 뒤처진 것은 0이다. 병합 결정은 owner 몫이다.
