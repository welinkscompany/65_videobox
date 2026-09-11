# VideoBox 진단 후속 작업서와 Claude 전달 프롬프트

작성: 2026-09-11 KST. 이번 Codex 작업은 진단만 수행했다. 아래는 후속 수정·재검증을 위한 작업서이며 기존 제품 승인·계획을 대체하지 않는다.

## 먼저 읽을 자료

- 활성 작업 트리: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility` — 다음 세션에서도 CLAUDE로 재확인.
- `docs/system-audit-2026-09-10.ko.md`: 사실·가정·과거/현재 실행·기준선 변화·한계.
- `docs/system-audit-2026-09-10-requirements.csv`: SYS-00~27, 판정·증거·다음 조치.
- `artifacts/system-audit-2026-09-09-2348/`: 원래 실패 로그·JUnit·브라우저 trace·합성 MP4·런타임 해시.
- artifact의 `closing-baseline.json`, `changes-after-tested-baseline.txt`, `reproduction-commands.md`, `generated-files.json`.

문서/운영 기준은 이번 사용자 지시 → 적용 지침/CLAUDE → development-fast-path 운영 규정 → 공식 계획과 해당 승인/명시적 대체 관계 → 최신 인계·상세 계획 순으로 적용 범위를 판단한다. 날짜만으로 기존 승인을 뒤집지 않는다.

## 증거의 유효 범위

마지막 집중 검증 소스는 D=`b590353b406f6a08d41654db679a547e527eb931`이다. 이후 E=`dc64ca7838a979c1392bfcbe54675ccbd66154aa`까지 40파일이 다른 개발 작업에서 바뀌었다. 최신 HEAD의 전체 성공 결과는 없다. 최종 관측은 closing-baseline.json 확인.

| 검사 | 실제 결과 | 한계 |
|---|---|---|
| Python 전체 | 4778 passed, 56 skipped, 1 failed | 실행 중 기준 변경. 최신 전체 통과 아님 |
| 프런트 첫 전체 | 1596 passed, 1 failed | 후보 시작값 1.5→0. 실패 보존 |
| 프런트 후속 전체 | D 소스 1605 passed | 최초 실패의 원인 해결은 입증하지 못함 |
| 타입·격리 빌드 | C/D 소스 통과 | 최신 변경분은 별도 |
| E2E | D 29 passed, 19 failed | mock API, 실제 모델/운영 DB 증거 아님 |
| Python 선별 | D 9파일 59 passed | 전체 회귀 대체 불가 |
| 실행본 대조 | D 소스 528/528 및 제공 JS/CSS 해시 일치 | 그 시점만 유효 |
| 합성 MP4 | 1920×1080, 3초, 영상+음성, 디코딩/재생/자산 역추적 성공 | legacy job + SQLite, 자막 0개, 현행 편집 세션 반영 미검증 |

## 작업 순서와 완료 조건

### FIX-00 — 변경 기준 고정 및 현재 상태 재분류 / Important / 먼저 수행

시작 Git·HEAD·dirty·upstream·worktree를 남기고 D→현재 변경을 확인한다. 기존 dirty와 보호 경로를 보존한다. 소스 해시가 변하면 결과를 분리한다. 진행 중인 다른 구현을 덮어쓰거나 오래된 실패를 현재 결함으로 단정하지 않는다. 현재 코드에 이미 해결된 항목은 재수정하지 않고 새 재현/검증으로 종결한다.

완료 조건: 대상 커밋+작업 트리 해시가 명확하고 종료까지 변하지 않았거나 변동 영향이 별도 기록되어 있을 것. 멀티트랙 render/session/transaction, 유진 overlay, UI, owner-ready 변경이 이번 검증 범위에 포함될 것.

### FIX-01 — 승인된 화면에 맞게 E2E 검증 복구 / Important / 확인된 검증 결함 D-02

근거: `e2e.log` 및 `e2e-results/**/error-context.md`, `trace.zip`.

1. `apps/web/e2e/product-shell.spec.mjs:26,36,46`: 09-04 shell, 09-05 `+ 새로 만들기` 단일 진입에 맞게 기대 동작 갱신. 사용자 이동과 실제 접근 가능한 버튼을 검증한다.
2. `apps/web/e2e/exact-preview.spec.mjs:288,297,306`: 빈 tracks/segments fixture로 실패/대기 안내를 기대하는 모순 해소. 비어 있지 않은 유효한 manifest/session을 넣고 상태·revision별 요청을 검증한다. 빈 프로젝트 안내 테스트는 유지한다.
3. `apps/web/e2e/z-script-first-vertical.spec.mjs:60`: native video.controls 속성 요구 대신 사용자 정의 재생·탐색·음소거 조작과 미디어 상태 변화를 검증한다. native controls를 다시 켜서 통과시키지 않는다.

완료 조건: 해당 테스트와 전체 E2E 통과, 잘못된 fixture/selector 수정 설명, 실사용 조작·요청·저장 검증 유지. skip/삭제/무조건 통과/문구만 맞추는 변경 금지. 7실패를 하나의 하네스 불일치 계열로 연결하되 세부 수정은 구분한다.

### FIX-02 — E2E 성능 결과 저장 격리 / Minor / 확인된 검증 결함 D-03

`apps/web/e2e/release-gates.spec.mjs`는 --output 설정과 무관하게 `apps/web/test-results/editor-workbench-performance.json`에 기록한다. testInfo.outputPath 또는 명시적 출력 루트로 바꾸고 필요한 후속 소비자도 연결한다.

완료 조건: 별도 output 지정 실행에서 결과가 지정 폴더에만 기록되고, 기존 성능 측정/판정 의미가 유지될 것. Codex 실행에서 기록된 기존 생성 파일의 이전 내용은 알 수 없으므로 임의 삭제·복구하지 않는다.

### INVEST-01 — 후보 구간 입력 손실 재현 / Important 가능 / S-01

`apps/web/src/features/creation/CreationInterview.test.tsx`의 “saves each B-roll candidate's chosen seconds with the current readiness revision”이 전체 실행에서 시작값 1.5 대신 0을 보냈다(`frontend-tests.log` 1504행 이후). 단독35개와 후속 전체1605개는 통과했다. 알려진 후속 수정은 source-video 자료실 연결이며 이 문제 해결 근거가 아니다.

`CreationInterview.tsx`의 readiness fetch/poll/update, `[readiness]` 의존 `setCandidateRanges` 초기화를 따라간다. 지연 응답, 저장 전 배경 갱신, 다른 후보 선택, 두 요청 역순 완료를 제어해 입력 덮어쓰기인지 테스트 오염인지 분리한다. 실제 입력→저장 요청 값→저장 후 재진입을 확인한다.

수정 조건: 재현 또는 확정된 호출/상태 경합 근거가 있을 때만 최소 수정. 완료 조건: 입력 보존과 서버 revision 충돌 처리를 모두 검증하고 원래 전체 실행 재검증. 예상 시작값을 0으로 바꾸거나 timeout만 늘리는 해결 금지.

### INVEST-02 — E2E 나머지 조작 실패 11건 / Important 가능 / S-03

| 파일/위치(D 당시) | 건수 | 추가 확인 |
|---|---:|---|
| editor-workbench:134,183,236,292,415 | 5 | dock 기본 desktop-both, 전화 화면 toolbar, output variant, caption/Yujin 진입·적용/undo |
| exact-preview:322 | 1 | audition 버튼 위치·선행 상태·실제 요청 |
| library-footage-crosslink:58,87 | 2 | 승인된 자료실 링크 명칭·현재 이동 경로·대상 자료 |
| library-workspace:186 | 1 | pane·선택·혼합 drop의 선행 상태 |
| media-recovery:5 | 1 | 실패 상태·숨겨진 안내·복구 버튼 노출 |
| voice-tts-settings:35 | 1 | /assets의 오래된 내레이션 tab 가정·현재 음성 화면 진입 |

trace를 먼저 읽고 현재 UI로 재현한다. locator 실패와 제품 로직 실패를 분리한다. 승인 문서에 맞게 테스트를 고쳐도 실제 기능이 실패하면 그때 별도 제품 결함을 등록한다. 소유 프로젝트/다른 프로젝트·취소·재시도·중복 요청을 검증하며 원인 같은 증상은 연결한다.

### INVEST-03 — 성능 gate 초과 원인 / Important 가능 / S-04

측정 median120.9ms, 기준92ms, 허용20%를 초과했다. `editor-workbench-performance.json`에 표본5개, Chromium149, worker1,1920×1080이 있다. 07-23 기준과 OS/브라우저/부하/측정 경계를 맞춰 기준·현재 버전을 비교한다. 렌더 횟수/이벤트 경로를 확인한 후 실제 회귀면 수정한다.

완료 조건: 비교 가능한 환경과 분산·실제 사용 영향을 설명하고 측정 기준을 보존할 것. 더 좋은 숫자를 얻을 때까지 재시도하거나 임계값만 높이지 않는다. 기준 보정이 필요하면 근거와 별도 결정으로 남긴다.

### INVEST-04 — 목록 썸네일 404 / Minor 예상 / S-02

운영 읽기 browser-readonly-B.json: 홈/프로젝트 각2회(중복 화면 관찰). 삭제/없음의 정상 fallback인지, 오래된 참조인지 데이터의 필요한 필드만 읽어 판단한다. 실제 이름·본문·키는 기록하지 않는다. 재생성·DB 수정은 하지 말고 합성 자산으로 재현한다.

### VERIFIED-01 — 인계 중복은 재수정 제외 / D-01

전체 Python의 유일 실패는 최신 인계가 2개라는 검사였다. 다른 작업 `9725b184f`에서 superseded 표시가 추가됐고 D 선별 실행에서 통과했다. 현재 다시 재현되지 않으면 닫힌 항목으로 유지한다.

## 추가로 검사할 사항

다음은 확인된 결함이 아니라 검증 공백/제안이다. 자동으로 새 기능 구현 범위를 확대하지 않는다.

| 우선 | 검사 | 필요한 조건·합격 기준 |
|---|---|---|
| Important | 최신 렌더/멀티트랙 회귀 | 변경된 clip placement, track assignment, session registry/API, render generalization, editor mutation, Yujin overlay 테스트 및 출력 합성 비교 |
| Important | 실제 브라우저 끝까지 | 격리 PostgreSQL+파일 루트+현행 빌드. 만들기→가져오기/검색→편집/자막/음성/음악→유진 직접 적용/undo→저장/새로고침/재접속→preview/MP4 |
| Important | 버전·프로젝트 경계 | 편집 중 렌더, 오래된 응답, 다른 프로젝트 열기, 재시도/중복/취소. preview/출력/session revision과 자산 추적 일치 |
| Important | 장애와 복구 | 모델/host bridge 없음, 네트워크 timeout, 작업 취소·프로세스 장애를 격리 환경에서 주입. 상태·원본 보존·재시도 일관성 |
| Important | DB+파일 전체 복구 | 운영 백업을 임의로 만들거나 변경하지 말고 합성 PostgreSQL+파일을 새 격리 경로로 복구. 참조·미디어·승인/기억 상태까지 비교 |
| Important | 보호 경계 | path traversal/다른 프로젝트 접근/링크·junction/Origin·credential·로그 비노출/승인 egress 경로. 현재 코드를 따라 조사하고 재현 가능한 경계만 확인 |
| Important | 실모델 vs mock | 실제 STT/TTS/번역/더빙은 허용된 합성 자료·외부 호출 범위/비용에서만. 연결 없음의 안내와 복구도 확인 |
| Minor 또는 선택 범위 | CapCut/Tauri | 현재 승인된 배포형태·설치/웹뷰 Origin/연결/출력 확인. MP4 우선 정책 유지 |
| 사용자 판단 | 실제 시청·청취/권리/게시 | 기술 성공과 별개로 남긴다. 자동 게시·메시지 발송 금지 |

격리 환경을 새로 구성하려면 프로젝트 운영 규정과 현재 owner-ready.ps1의 동작을 먼저 읽는다. 이번 진단은 운영 컨테이너를 재시작/재빌드하지 않았다. 이후 프롬프트도 운영 변경·배포 승인으로 해석하지 않는다. 기존 승인을 확인할 수 없는 운영 변경이 꼭 필요할 때만 필요한 작업과 이유를 구체화해 사용자 판단으로 남긴다.

## 수정 후 실행·보고 규칙

- 수정 원인에 맞는 좁은 재현 검증 후 한 고정 기준에서 전체 회귀를 순차 실행한다. 무거운 작업 동시 실행 금지.
- backend는 활성 트리 `.venv\Scripts\python.exe -m pytest`. basetemp는 충돌하지 않는 짧은 새 경로, pytest cache/bytecode·출력도 격리한다. 현재 conftest/opt-in 및 외부 호출 방지 설정을 다시 확인한다.
- 프런트 tests, tsc --noEmit, Vite 격리 outDir, E2E fake API와 실제 브라우저를 별도 판정한다. 실제 화면 조작 결과를 API 직접 호출로 대체하지 않는다.
- E2E 스냅샷 자동 덮어쓰기 금지. 기존 snapshot manifest 검사 성공은 새로운 화면 비교 성공이 아니다.
- 각 명령 cwd/start/end/commit/dirty hash/exit/pass/fail/skip/log를 보존한다. 최초 실패를 지우지 않는다.
- 전체 정상 주장 전 최신 전체 검사와 핵심 실사용/출력 근거가 필요하다. 검증 공백이 남으면 그대로 적는다.
- 결과를 새 후속 문서로 남긴다: FIX/INVEST별 재현→원인→변경→회귀→남은 제한→사용자 판단. 기존 승인/완료 체크를 임의 갱신하지 않는다.

## Claude에게 복사할 프롬프트

```text
VideoBox 시스템 진단의 후속 수정과 재검증을 진행하라.

작업 후보 경로:
D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility

먼저 적용되는 상위 지침/CLAUDE.md, development-fast-path 운영 규정, implementation-plan,
CLAUDE가 가리키는 최신 인계와 관련 승인 기록으로 활성 작업 트리·현재 범위를 확인하라.
다음 새 진단 자료를 모두 읽어라.
- docs/system-audit-2026-09-10.ko.md
- docs/system-audit-2026-09-10-requirements.csv
- docs/system-audit-2026-09-10-claude-remediation.ko.md
- artifacts/system-audit-2026-09-09-2348/closing-baseline.json
- 같은 artifact의 changes-after-tested-baseline.txt와 reproduction-commands.md

이번 요청은 위 작업서 범위의 로컬 수정·격리 검증을 승인한다.
새 기능·승인되지 않은 설계 변경·원본 변경·운영 DB 변경·서비스 중지/재시작/재빌드,
파일 정리/삭제, 커밋·푸시·병합·배포·외부 게시/메시지 발송은 포함하지 않는다.
기존 dirty와 보호 경로를 보존하고 다른 개발자의 변경을 되돌리지 마라.

FIX-00 기준 고정부터 진행하라. 마지막 검증 D 이후 코드가 바뀌었으므로
과거 실패/성공을 현재 결과로 복사하지 말고 현재 재현 여부를 확인하라.
FIX-01 E2E 승인 기준/fixture와 FIX-02 산출물 격리를 최소 범위로 수정하라.
INVEST-01~04는 원인을 먼저 조사하고 확인된 결함만 수정하라.
VERIFIED-01 인계 중복은 이미 해결 확인됐으니 현재 재발하지 않으면 재수정하지 마라.

09-01 유진 직접 적용+undo, 09-04 shell, 09-05 단일 시작 등 현행 승인을 존중하라.
실패한 테스트를 통과시키려고 승인된 UI를 되돌리거나 skip/삭제/기대값 약화/
성능 임계값 상향/스냅샷 무조건 갱신을 하지 마라.
독립적으로 가능한 조사·수정·검증을 계속하고, 막힌 항목은 조건을 기록하라.

변경 원인별 좁은 검증 후 고정된 한 기준에서 backend 전체 pytest,
frontend 전체 테스트·타입·격리 빌드·E2E를 순차 실행하라.
backend는 활성 트리 .venv\Scripts\python.exe -m pytest를 사용하라.
각 실행의 시각·cwd·commit·dirty hash·exit·pass/fail/skip·로그를 남겨라.
처음 실패 후 재실행 통과도 모두 보존하라.

격리 PostgreSQL+파일+현행 빌드가 확보되면 실제 브라우저에서
생성→자산→편집/자막/음성/음악→유진 적용/undo→저장/재진입→미리보기/MP4,
실패·취소·재시도를 확인하라. 격리할 수 없으면 운영 데이터를 대신 쓰지 마라.
최종 MP4에서 렌더 job→현재 session revision→사용 자산을 역추적하라.
legacy 합성 출력 통과를 현재 편집본·실모델·사람 승인으로 대체하지 마라.

새 날짜별 후속 보고서에 수정 완료/재현 안 됨/의심/차단/추가 승인 항목,
변경 파일·근거·재검증 결과·남은 사용자 시청/청취 판단을 구분해 남겨라.
핵심 흐름 실패나 미검증이 남으면 전체 정상이라고 보고하지 마라.
```
