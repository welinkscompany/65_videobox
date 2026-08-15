# VideoBox 전체 시스템 점검 계획서 (2026-08-16)

> **For agentic workers:** 이 문서는 점검 계획과 그 실측 결과를 함께 담는다. 코드 수정은 이 점검의 범위가 아니다.
> 재실행할 때의 고정 규칙 — 전체 pytest는 **다른 무거운 작업과 절대 동시에 돌리지 않는다**(2026-08-15에 두 번,
> 2026-08-16에 한 번, 시간에 민감한 테스트가 부하로 오탐 실패했다). `owner-ready.ps1 -Mode Start`의 준비 확인은
> `-TimeoutSec 30` 이상으로 준다. 실패가 나오면 그 테스트 파일만 격리 재실행해 진짜 결함인지 먼저 판단한다.

**Goal:** 2026-08-15 UX 개편(Task 1~7)과 스냅샷 재승인이 끝난 시점의 시스템 전체 상태를 실측으로 확정한다 —
코드-문서 정합성, 테스트 실제 통과 수, owner-ready Start, 실제 브라우저 6경로, 스냅샷-승인 일치, 미해결 항목.

**Method:** 문서를 근거로 쓰지 않고 전부 직접 잰다(§10.5, "짐작하지 말고 재라"). 자동 검증·owner-ready·실제
브라우저·owner acceptance는 서로 다른 것이며 어느 것도 다른 것을 대신하지 않는다(CLAUDE.md §4).

---

## 0. 점검 기준선 (2026-08-16 실측)

- HEAD `453553c9c`, branch `codex/videobox-container-compatibility`, 원격과 **0/0 완전 동기화**
- working tree 깨끗, `git diff --check` 통과 (점검 시작 시점과 종료 시점 모두)
- 컨테이너 5개 전부 healthy: workspace(Up 5h) · postgres · agent-gateway · hermes-memory-adapter · yujin
- 마지막 앱 코드 커밋은 `8e99a308e`. 그 이후 커밋 4개(`aa1b0f38a`~`453553c9c`)는 전부 docs+스냅샷이므로
  **컨테이너가 서빙 중인 번들은 현재 HEAD의 앱 소스와 일치한다** (근거는 git 이력이다 — 로컬 `npm run build`의
  번들 해시는 컨테이너 빌드 환경과 달라 해시 비교로는 판정하지 않았다)

---

### Task 1: 코드-문서 정합성

- [x] CLAUDE.md §2 `최신 세션 인계` 포인터 → `2026-08-14-videobox-claude-resume-handoff.ko.md` — **일치**
- [x] main 루트 안내판(CLAUDE.md)이 가리키는 worktree·branch — 실제와 일치
- [x] main 루트의 `projects/` 잔여 데이터 — **삭제 완료 확인** (2026-08-11 세션이 owner 몫으로 남겼던 항목, 이제 없음)
- [x] UX 개편 계획서(`2026-08-15-videobox-dashboard-ux-recovery.md`) Task 1~7 체크 상태와 실제 화면 대조 — Task 4(홈
  문구 1회)·Task 5(사이드바 구획)·Task 1~3(편집기 20.8%)이 배포본에서 전부 유지됨 (Task 4의 브라우저 실측 참고)
- [x] `api.ts` 미사용 메서드 재측정: `export const api` 메서드 **175개 중 18개**가 api.ts 밖 어디서도(화면·테스트
  포함) 참조되지 않음. 2026-08-09의 147개 중 31개에서 **개선**. §4의 요점("새 백엔드마다 부르는 화면을 같이
  만들지 않으면 목록이 늘어난다")은 이번엔 지켜지고 있다.

**발견한 문서 낡음 2건 (경미, 판단을 틀리게 할 수준은 아님):**

1. UX 개편 계획서 Task 7의 스냅샷 재승인 체크박스가 `- [ ]`로 남아 있으나, 실제로는 `b4910f738`로 재생성·재승인
   완료됐다(`docs/decisions/2026-07-20-editor-workbench-visual-approval.ko.md` 두 번째 재승인 절). 문서가 코드보다
   한 발 늦다.
2. 핸드오프 `다음 세션 시작점` 절이 HEAD를 `382abe3b5`로 적었으나 실제 HEAD는 `453553c9c`다 — 그 절을 추가한
   커밋 자체라서 생긴 자기참조 지연이다. 핸드오프 스스로 "수치와 HEAD가 다르면 직접 잰 값이 우선"이라 명시하므로
   실해는 없다.

이 2건은 이 점검의 범위(계획서만, 코드·문서 수정 없음)에 따라 **고치지 않고 기록만 남긴다.** 다음에 그 문서들을
어차피 만질 세션이 함께 정리하면 된다.

### Task 2: 테스트 실제 통과 수 — 전부 단독 실행

- [x] Python 전체: `.venv\Scripts\python.exe -m pytest -q` **단독** 실행 (35분 57초)
- [x] 실패 1건 격리 재실행으로 오탐 판정
- [x] frontend Vitest · production build · Chromium E2E 2종 · `git diff --check`

| 검증 | 결과 |
|---|---|
| Python 전체 (단독) | `3521 passed, 53 skipped, 1 failed` → 실패 1건은 아래 판정 |
| 실패 격리 재실행 | `tests/test_maintenance_loop_cadence.py` 단독 `5 passed` (3.1초) — **부하 오탐, 결함 아님** |
| frontend Vitest | `76 files / 973 passed` |
| production build | 통과 (기존 500kB chunk 경고만) |
| Chromium E2E | `42 passed`, snapshot manifest verified |
| editor-workbench E2E | `10 passed`, snapshot manifest verified |
| `git diff --check` | 통과 |

전체 실행에서 실패한 `test_the_analysis_cache_is_actually_pruned`는 0.4초 sleep 안에 유지보수 루프가 돌기를
기대하는 시간 민감 테스트다. 단독 실행조차 35분 57초가 걸리는 전체 스위트 안에서 부하를 탔고, 격리 재실행에서
바로 통과했다. 2026-08-15에 두 번 겪은 것과 같은 패턴이며, **오탐이 나는 테스트 자체를 고치는 일은 이 점검
범위 밖이라 손대지 않았다.**

### Task 3: owner-ready Start 실측

- [x] `-Mode Check -Json -TimeoutSec 8`: **16개 항목 전부 pass** — 로컬 모델(`qwen/qwen3.6-35b-a3b`) 로드·설정
  일치, VideoBox 5173 HTTP 200, Hermes 대시보드 HTTP 200(launcher 재실행 없이 확인, 핸드오프 지시 준수),
  CapCut 9.1.0.3879 설치 확인
- [x] `-Mode Start -TimeoutSec 30`: **한 번에 통과** — "바로 사용할 준비가 됐습니다 … 화면 연결 준비가 끝났습니다"

2026-08-15의 판정("짧은 타임아웃 FAIL은 실제 실패가 아니다, 30초면 통과한다")이 재현됐다. Start는 이미 떠 있는
스택을 재확인하는 경로였고 아무것도 재시작하지 않았다.

### Task 4: 실제 브라우저 6경로 (1920×1080, 컨테이너 배포본 127.0.0.1:5173)

- [x] `/`(→`/projects/my-project/home`) · `/library` · `/footage` · `/projects/my-project/plan` ·
  `/projects/my-project/home` · `/projects/my-project/editor?session_id=editing_session_draft_5ee4d7c4b924`

전 경로 공통: **HTTP 200/206만, console error 0건, 실패 요청 0건, 가로 overflow 0건**(`scrollWidth ==
clientWidth` 전부 일치), `TODO`/`Coming soon`/`준비 중`/`placeholder` 잔여 문구 **0건**.

| 경로 | 확인한 것 |
|---|---|
| 홈 | "초안 있음" **1회**, "편집 계속하기" **1회** — Task 4 결과 유지 |
| `/library` | 자산 138(영상 8·음악 30·효과음 100). 옛 wave2 자산 4개는 "**길이 정보 없음**"으로 정직하게 표시("길이 확인 중" 거짓 문구 0건) |
| `/footage` | 머리말 `VideoBox` — `Wave-2`/`VIDEObox` 내부 용어 0건 |
| `/plan` | 사이드바 구획 라벨(전체 메뉴 → 현재 프로젝트 → 단계) 유지 |
| 편집기 | 그림 **876×492 = 화면의 20.8%** (UX 개편 계획서 실측값과 정확히 일치), `readyState 4`, duration 20.00초, 상태 한 줄 병합 유지 |

편집기 심층:

- playback manifest: `session_revision 10` = `source_session_revision 10` = `artifact_revision 10`, exact preview
  `succeeded` — 삼중 일치
- exact preview content `Range: bytes=0-1023` → **HTTP 206**, `Content-Range: bytes 0-1023/257944`,
  `Accept-Ranges: bytes`
- 재생: 직접 `play()`로 1.78초 진행 후 pause 정상. **재생 버튼 클릭은 이번에도 pane이 `visibilityState:
  hidden`일 때 시작되지 않았다** — 2026-08-15 핸드오프가 이미 판정한 브라우저 autoplay 차단이며 제품 결함이
  아니다. 화면이 보이는 상태의 버튼 재생은 E2E(`exact-preview.spec.mjs`)가 실제 user gesture로 고정하고 있고
  이번 42 passed에 포함돼 통과했다.
- 네트워크에 exact-preview `ERR_ABORTED` 2건 — Chromium이 버퍼링 중 Range 요청을 교체하며 이전 요청을 취소하는
  정상 패턴(UX 개편 계획서 Task 7 판정과 동일). 재생·duration 정상으로 재확인.

### Task 5: 스냅샷-승인 일치

- [x] `verify-snapshot-manifest.mjs` → `verified` (10장 PNG sha256이 manifest와 일치)
- [x] 재승인 커밋 `b4910f738` 이후 `apps/web` 변경 이력 → **0건**
- [x] 결정적 확인: `VIDEOBOX_WRITE_PLAYWRIGHT_SNAPSHOTS=1`로 E2E 2종을 다시 돌려 10장 전부 재생성 →
  `git status` **변경 0건, 바이트 단위 동일.** 원복할 것도 없었다.

**판정: 승인된 스냅샷 10장(편집기 5 + 대시보드 5)은 현재 코드가 렌더하는 것과 정확히 일치한다.** 2026-08-15에
두 번 반복됐던 "스냅샷이 코드보다 낡음" 문제는 현재 없다. 단, 이 스냅샷은 E2E fixture 상태를 담은 무결성
기록이지 실제 편집 결과물의 화질·타이밍 승인이 아니다 — owner의 실제 시청 승인과는 별개다(재승인 기록의 범위
문구 그대로).

---

## 미해결 항목 — 전부 사람(owner) 몫이며, 자동화로 닫을 수 있는 것은 남아 있지 않다

1. **owner acceptance (최우선).** owner가 실제 긴 원본으로 만든 완성본을 처음부터 끝까지 직접 시청·청취하고,
   자막 타이밍·음량·B-roll 선택·화면 밀도를 승인한 적이 없다. 이 점검을 포함한 어떤 자동·브라우저 검증도 이것을
   대신하지 못한다.
2. **Hermes live chat.** Hermes gateway/provider가 실제 활성 상태일 때 유진 라이브 대화 확인. 9119/9130의 HTTP
   200은 reachability일 뿐 live provider/chat 성공 증거가 아니다.
3. **UX 개편 보류 2건 (owner가 Task 1~6을 써본 뒤 결정).** 재료 전면 통합(라이브러리+촬영본+프로젝트 자산),
   5단계 단일 작업판 — 계획서 "하지 않을 것" 절에 근거와 함께 기록돼 있다.
4. **옛 자산 4개의 길이 데이터.** `wave2-long-qa.mp4`, `wave2-short-a/b/c.mp4`는 여전히 duration 데이터가 없다.
   화면 문구는 "길이 정보 없음"으로 정직해졌고 현재 ingest 경로는 정상이므로, 이 4개를 재분석(backfill)할지
   그대로 둘지는 owner 결정이다.
5. **(경미) 문서 낡음 2건** — Task 1의 발견 1·2. 다음 관련 세션에서 함께 정리.

## 이 점검에서 하지 않은 것

- **코드·문서 수정 일절 없음** (점검 범위 규정). 발견 사항은 위에 기록만 했다.
- **owner acceptance 대행 없음.** 시청·청취·취향 판단은 사람만 할 수 있다.
- **Hermes provider 로그인 없음** (CLAUDE.md §6 승인 필요 항목).
- **오탐 테스트 수선 없음.** `test_maintenance_loop_cadence.py`의 시간 민감성은 알려진 패턴으로 기록만.

## 종합 판정

자동으로 검증 가능한 전 영역이 초록불이다: 테스트(3521+973+42+10, 오탐 1건 격리 판정), 빌드, owner-ready
Check/Start, 실제 브라우저 6경로, 스냅샷-승인 바이트 일치, 저장소-원격 동기화, 배포본-소스 일치. **시스템은
owner가 실사용 검증을 시작하기에 준비된 상태이며, 남은 것은 전부 사람의 판단이다.**
