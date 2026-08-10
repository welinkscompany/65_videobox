# VideoBox 인계 — owner 음악 반입·저장소 분할 (2026-08-10, 3차)

계획서: `docs/superpowers/plans/2026-08-10-videobox-consolidated-priorities.md` (SSOT)
앞 인계: `docs/handoffs/2026-08-10-videobox-postgres-verification-handoff.ko.md`

**백엔드 3,357 통과 / 6 건너뜀. Postgres 저장소 52 통과 / 0 건너뜀.**
`main`에 병합·푸시 완료.

## owner가 요구한 것은 전부 닫혔다

| 요구 | 상태 |
|---|---|
| 데이터 폴더 3벌 → 1벌 | 완료. `20_project\65_videobox-project` 하나 |
| SQLite 안 쓰고 Postgres만 | 완료. 컨테이너 모드에서 주소 없으면 **뜨지 않는다** |
| `가져옴` → `자산화_완료` | 완료. 코드·테스트·문서·디스크 9곳 |
| **음악·효과음을 직접 넣기** | 완료. 컨테이너에서 실제 확인 |
| 시험 프로젝트 175MB 정리 | 완료. 앱의 삭제 경로로 |
| `main` 병합 | 완료 (`9a345a34a` 푸시) |

## 새로 생긴 것 — owner가 음악·효과음을 직접 넣는다

```
20_project\65_videobox-project\drive-sync\
   ├─ 새 영상      ← 촬영본
   ├─ 새 음악      ← 음악
   ├─ 새 효과음    ← 효과음
   └─ 자산화_완료  ← 셋 다 여기로 원본이 모인다
```

**폴더를 만드는 것만으로는 안 됐다.** `index_pending_library_audio`는 폴더를 훑지 않고
`list_assets_needing_audio_analysis`로 라이브러리 DB를 읽는데, 그 질의가 `media_packs`와
조인하며 `active = 1 AND verified = 1`을 요구한다. 그래서 **팩에 속하지 않은 음악은 색인
대상이 아예 아니다.**

해법은 새 등록 경로를 만드는 것이 아니라 **있는 것을 쓰는 것**이었다 —
owner 파일을 `owner-audio` 팩(버전 **고정**)으로 `index_verified_pack`에 등록한다.
버전을 고정한 이유: 그 메서드는 같은 `pack_id`의 다른 버전을 비활성화한다. 매번 버전을
올렸으면 **새로 넣을 때마다 이전에 넣은 것이 전부 사라졌을 것이다.**

**라이선스는 비워 뒀다.** owner 본인 파일이라 외부 라이선스 페이지도 증거도 없다.
없는 기록을 지어내지 않는다. `source`는 `직접 넣은 파일`.

**부하 대책:** 매 패스마다 라이브러리 전체를 해시하지 않고 색인을 한 번 읽어 새 이름만
검사한다. 이 저장소가 이미 값을 치른 실수다.

**컨테이너 실측 (에이전트):** mp3·wav를 넣으니 폴더가 비고, 원본이 `자산화_완료`로 가고,
등록·측정·임베딩까지 저절로 됐다. 검색에서 mp3가 음악 31개 중 **1위**. 스타터 팩 130개는
그대로 살아 있었다. 검증용 파일은 **파일과 색인 기록을 함께** 지웠다 — 파일만 지우면
색인이 60초마다 "없다"고 경고한다.

## 저장소 분할 1단계 — hermes 갈래

`local_project_store.py` **11,512 → 10,733줄**. 떼어낸 것은
`_store_hermes_capability.py`(814줄)의 `HermesCapabilityMixin`.

**믹스인이어야 했던 이유:** 기반 `_connection`이 `_ensure_hermes_capability_lifecycle_schema`
를 호출한다. 별도 모듈로 떼면 **실제 순환 import**가 되고, 위임으로 하면 인스턴스에
몽키패치하는 테스트와 `PostgresProjectStore._connection` 오버라이드가 조용히 깨진다.

**`postgres_project_store.py`는 한 줄도 고치지 않았다.** 공개 메서드 318개 그대로.

지뢰였던 `_validate_hermes_expected_scope`의 하드코딩 클래스 이름은 믹스인 이름으로 바꿨다
(같은 `@staticmethod`, 동작 동일).

**다음은 media(외부 의존 8개) → yujin(1,734줄, director 갈래를 부른다).**
`director_hermes` 계열 11개는 **hermes가 아니다** — director·yujin과 얽혀 있어 별도 판단.

## 침묵 7갈래 제거

가장 값어치 있는 것: **진단 화면이 못 읽은 항목을 빼고 "전부"인 척하던 것**
(`get_provider_trace_audit`, 9곳). 다른 침묵을 찾으려고 여는 바로 그 화면이 같은 방식으로
거짓말하고 있었다.

그 밖에 기억 조회 파싱 실패, 초안 없음 vs 못 읽음, 일괄 가져오기에서 분석이 안 걸린 파일,
제안이 저장되지 않은 진짜 이유, 게이트웨이 3층의 이유 없는 `False`.

**폴링 경로는 원인별로 한 번만 말하고 성공하면 초기화한다.** 한 번 말하고 영영 조용해지면
그것도 침묵이다.

## 이 세션에서 내가 틀렸던 것

- **인계 문서를 쓰고 `CLAUDE.md` 포인터를 안 고쳐** 회귀를 깨뜨렸다. 그걸 잡는 테스트가
  있었고 정확히 잡았다.
- **"172MB는 굴러다니는 SQLite"라고 보고했다.** 열어 보니 프로젝트 폴더 전체였고,
  Postgres에 등록까지 돼 있었다. 폴더만 지웠으면 깨진 항목이 남았다.
- **에이전트에게 준 설명 하나가 틀렸다.** "제안이 저장 안 됐는데 화면은 정상"이라고 했으나
  그 경로는 차단 상태로 끝나 화면에 보인다. 에이전트가 테스트를 짜다 발견해 바로잡았다.
- **`media_facts_error`를 자산 메타데이터에 넣었다가** 호스트 전체 경로가 화면 응답으로
  나가는 것을 회귀가 잡았다. 복구 조회는 그 값을 보지도 않았다.

## 다음 세션이 이어서 할 것

1. **저장소 분할 2·3단계** — media → yujin. 방식은 정해졌다(믹스인).
2. **화면이 안 부르는 API 22개** (29개 중 7개를 붙였다). DELETE 13개 판정은 조사 완료.
3. **owner 최종 인수** — 계획서가 정한 "설명 없이 대시보드를 열어 내보내기까지"는
   **아직 통과 기록이 없다.** 이건 owner만 할 수 있다.
4. 미뤄 둔 것: `progress-bar-live-test`(4MB) 정리 여부,
   `get_provider_trace_audit` 응답에 "못 읽은 것"을 실을지(계약 변경이라 결정 필요).

## 검증 방법

- 백엔드 전체: `.venv/Scripts/python.exe -m pytest -q` (약 26분)
- **Postgres 저장소: `.\scripts\run-postgres-store-tests.ps1`** (약 30초, 건너뜀 0)
- 컨테이너: `docker compose --env-file .env.container build videobox-workspace` 후 `up -d`
- 브라우저는 **창 너비 1600 이상**

## 함정 (이번에 실제로 걸린 것)

- **서브에이전트 worktree는 낡은 `main`에서 생성된다.** 셋 다 걸렸고 둘은 스스로 되돌렸다.
  나머지 하나는 낡은 트리를 보고 **자신 있게 틀린 보고**를 냈다("이 파일들은 존재하지 않는다").
  프롬프트 첫 단계에 기반 확인·재설정을 넣고, 확인 지표를 함께 줄 것
  (`wc -l apps/web/src/api.ts` == 2135).
- **에이전트 worktree에는 `.venv`가 없다.** 절대경로로 개발 worktree의 것을 준다.
- **회귀가 도는 중에 소스를 고치지 않는다.** 이번에도 두 번 겪었다.
- 다른 pytest가 동시에 돌면 시간 민감 테스트가 헛failure를 낸다. 회귀가 23분이 아니라
  67분 걸리면 그것부터 의심할 것.
