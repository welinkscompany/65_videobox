# VideoBox 시스템 진단 — 2026-09-09~11

상태: 수행한 진단의 기록·인계 정리 완료. 전체 시스템 정상 판정은 불가하다. 기능별 미검증·차단 및 최신 코드 변경분은 남아 있다. 종료 확인일은 2026-09-11 KST다.

이 문서는 사용자 요청으로 새로 작성한 진단 기록이다. 기존 지침·승인·계획을 변경하지 않는다. 기능 구현 완료율에 합산하지 않는다. 코드 수정·정리·삭제·커밋·푸시·배포는 이 점검에서 수행하지 않는다.

## 1. 기준선과 증거 위치

- 작업 트리: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility`
- 브랜치: `codex/videobox-container-compatibility`
- 시작 A: 2026-09-09 23:48 KST, `9e836cc02be22f35d53c74fe910cbae6c0093081` + 기존 미커밋 변경 2개.
- 보호한 기존 변경: `packages/storage-abstractions/src/videobox_storage/_store_yujin_memory.py`, `sqlite_schema.py`. 두 파일은 기억 사서 워터마크 구현이었다. 점검자가 수정하지 않았다.
- 중간 B: 2026-09-10 14:11 KST, `ea26b76c9e50a74ac2cb894269ef9be48da0bc80`, 기존 변경은 다른 개발 작업에서 커밋되어 작업 트리가 깨끗해졌다.
- 후속 C: 2026-09-10 20:31 KST, `dbf7e20b2cfa18ed289bb5da334f9d4eb23f1265`.
- 검증 D: `b590353b406f6a08d41654db679a547e527eb931`. C→D는 인계 문서만 변경되어 소스는 같다. 전체 프런트·E2E·선별 Python·실행본 대조의 기준이다.
- 마감 관측 E: 2026-09-11 00:39 KST, `dc64ca7838a979c1392bfcbe54675ccbd66154aa`. D→E에서 40개 파일이 변경됐다. 렌더러·멀티트랙·편집 트랜잭션·유진·화면·owner-ready 변경은 D 검증으로 승인하지 않는다. 이후 최종 Git 스냅샷은 `closing-baseline.json`을 따른다.
- 점검 도중 다른 개발 작업의 커밋·런타임 변경이 있었다. 서로 다른 기준의 결과를 단일 커밋의 전체 통과로 합치지 않는다.
- 증거 디렉터리: 작업 트리의 `artifacts/system-audit-2026-09-09-2348/`.
- 짧은 합성 테스트 데이터: `%TEMP%\vb-audit-0910-probe`, `%TEMP%\vb-audit-0910-full`. 사용자 원본 데이터가 아니다.

`baseline.json`에 시작 Git 상태·원격 추적 상태·작업 트리 목록, `source-hashes-start.json`에 추적 파일 1,749개의 시작 해시를 보관했다. 원격 조회는 로컬 remote-tracking ref 기준이며 fetch하지 않았다. 시작 main/개발선 차이는 `0 0`이었다.

### 점검 도구 자체에서 발생한 오류

처음에 작업 트리 하위의 긴 경로를 pytest `--basetemp`로 지정했다. 약 7%까지 진행 중 연속 실패가 나타나 실행을 중단했다. 대표 1건을 같은 긴 경로에서 다시 실행하여 `WinError 206`을 확인했다. 동일 테스트와 초기 실패 표본을 짧은 경로에서 실행한 결과 2개가 통과했다.

- `pytest-full.log`: 중단된 최초 실행. 완결된 집계·JUnit이 없어 통과율 근거로 사용하지 않는다.
- `path-probe-long.log`: 긴 경로에서 1 failed, 경로 길이 오류 재현.
- `path-probe-short.log`: 짧은 경로에서 2 passed.
- 긴 경로 실패 전체의 원인이 전부 같다고 입증한 것은 아니다. 이 실행의 실패 수를 제품 결함 수에 포함하지 않는다.

## 2. 문서 체계와 적용 기준

| 문서 | 역할·적용 | 판단 |
|---|---|---|
| 사용자 이번 지시 | 진단 범위·변경 금지 | 기존 커밋 기본값보다 이번 지시 우선 |
| `CLAUDE.md` | 저장소 진입점, 활성 작업 트리, 제품 경계, 보호 경로 | 현재 범위 확인의 출발점 |
| `docs/development-fast-path.ko.md` §10·§11 | 운영 규정·검증 도구·데이터 위치 | 명령과 실제 사용 완료의 기준 |
| `docs/implementation-plan.ko.md` | 제품 목표·MVP·최상위 계획 | 머리말·§12·§13의 과거 실적은 현재 근거로 사용하지 않음 |
| `docs/decisions/` | 승인된 제품·UI 결정 | 승인 범위와 명시적 대체 관계를 적용 |
| `docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md` | 진입점이 가리키는 최신 인계 | 점검 중 §6~§8이 추가됨. 앞의 계획과 뒤의 실제 상태를 구분 |
| `docs/handoffs/2026-09-08-owner-decided-followups-csrf-async-captions.ko.md` | 앞선 CSRF·비동기화 작업의 기록 | A/B에는 대체 표시 누락. C에서는 명시적 대체 표시로 해소 |
| `docs/superpowers/plans/2026-08-16-videobox-full-system-inspection.md` | 과거 전체 점검 방법·실적 | 당시 수치·경로·오탐 판정을 현재 결과로 사용하지 않음 |
| `docs/superpowers/plans/2026-07-13-release-audit-protocol.ko.md` | 6개 출시 검증 관점 | 과거 diff 기준 커밋·CapCut 필수 경로는 현재 요구로 복사하지 않음 |

### 대체 관계와 오진 방지

1. 유진 편집: 2026-09-01 `yujin-chat-applies-edits-directly` 승인이 예전 모든 편집안의 수동 적용 요구를 대체한다. 직접 적용과 되돌리기를 검증해야 하며, 예전 설계로 자동 적용을 버그라 판정하지 않는다.
2. 시작 화면: `/` → `/projects`; 2026-09-05의 `+ 새로 만들기` 단일 진입 기준을 사용한다.
3. 다크 테마·CapCut 버튼 배치는 승인된 방향이다. 진단을 이유로 재디자인하지 않는다.
4. 자유 멀티트랙·Hermes egress: 승인된 방향, 구현 단계, 미결정 세부 사항을 분리한다. 인계의 서로 다른 트랙 enum을 일괄 통합해야 한다는 주장은 같은 문서 뒤에서 철회됐다.
5. 최신 인계 §7.2~7.3은 의도적으로 UI 없는 자동화·감사·레거시 API와 다른 UI 경로로 이미 연결된 기능을 설명한다. 단순 미참조 검색으로 모두 결함 처리하지 않는다.
6. `docs/local-storage-strategy.ko.md`는 스스로 낡은 SQLite 설계라고 표시한다. 현재 컨테이너는 PostgreSQL이고, 로컬 테스트의 SQLite와 구분한다.
7. 설치형 문서·개별 인계에 서로 다른 과거 상태가 남아 있다. Tauri의 현재 서명·설치·실행은 이번에 검증하지 않았다.

## 3. 구조와 점검 목록

현재 주요 연결은 `AppRouter/각 화면 → api.ts → FastAPI routers → core-engine → storage-abstractions → PostgreSQL 또는 로컬 파일·SQLite`다. 미리보기·최종 출력은 FFmpeg와 파일, 이미지·음성·AI는 개별 호스트/모델 어댑터에 의존한다. MCP는 별도 stdio 진입점을 가진다.

아래는 사용자 흐름 기준 점검 단위다. API·함수·모든 경계조건을 전수 리뷰했다는 뜻은 아니다. 정상 입력의 자동 검증과 실운영 환경의 실제 사용은 분리한다. 세부 증거와 후속 조치는 뒤의 실행표·발견사항을 함께 본다.

| ID | 기능·기준 | 구현 진입점 | 기대 조건·검증 방법 | 현재 실사용 판정 |
|---|---|---|---|---|
| SYS-00 | 기준선 / CLAUDE §0·§3 | Git·런타임 | 커밋·변경·실행본 출처 추적 | 기준선 변경 이력 기록, 단일 기준 전체 통과 아님 |
| SYS-01 | 문서 진입점 / 운영 §10.9 | CLAUDE·handoff test | 현재 인계 1개, 대체 관계 명시 | A/B 실패, 다른 작업 수정 후 D 선별 테스트 통과 |
| SYS-02 | 승인 범위 / 구현계획 §4·승인 기록 | decisions·계획 | 보류·제외·구현 완료 구분 | 문서 기준 정리, 일부 상태는 추가 확인 필요 |
| SYS-03 | 프로젝트 / 구현계획 §4 | ProjectsPage·routers/projects.py | 만들기·열기·새로고침 | 운영 목록 조회만 확인, 쓰기 미검증 |
| SYS-04 | 입력·촬영본 / 최신 인계 §8 | SourceVideoStart·routers/draft_readiness.py | 업로드·받아쓰기·자료실 연결 유지 | D source-video API 시험 통과, 운영 업로드 미실행 |
| SYS-05 | 자산 검색·선택 / 운영 §10.15 | LibraryPage·EditorAssetBrowser·LibraryPickerDialog | 종류 구분·검색·삽입 | 운영 자료실 조회 확인, 쓰기 미검증 |
| SYS-06 | STT·분석 / 구현계획 §4 | assets/jobs·media_analysis | 진짜 음성 인식·재분석·장애 안내 | 단위/모의 검증과 실제 모델 분리, 실제 STT 미검증 |
| SYS-07 | 대본·기획 / 구현계획 §4 | CreationInterview·creation_briefs/script_drafts | 저장·확정·재진입 | 프런트 자동 검증, 운영 상태 변경 미실행 |
| SYS-08 | 추천·사용 구간 / 구현계획 §4 | CreationInterview·draft_readiness | 선택한 시작/끝 저장·버전 보호 | 앞선 1회 실패 원인 미확정, 후속 통과도 보존 |
| SYS-09 | 초안 / 운영 §10.5 | atomic_draft_bundles·draft_readiness | 같은 버전의 원자적 생성·실패 복구 | 자동 근거와 운영 실사용 구분 |
| SYS-10 | 타임라인 / 구현계획 §8.4 | EditorWorkbenchRoute·editing_session | 편집·저장·새로고침·undo/redo | 모의 API E2E에 실패 있음, 운영 편집 미실행 |
| SYS-11 | 자막 / 번역 승인 | transcript·caption controls | 내용·스타일·타이밍 유지 | 자동 근거, 실제 시청 승인 없음 |
| SYS-12 | 음성·음악·효과음 / 구현계획 §4 | audio controls·TTS/host bridge | 선택·음량·재생·출력 반영 | 실제 음성 생성·청취 미검증 |
| SYS-13 | 번역·더빙 / 09-02~03 승인 | orchestration·progress polling | 비동기 접수·상태·실패·재시도 | 자동 근거, 실모델·긴 영상 미검증 |
| SYS-14 | 유진 편집 / 09-01 승인 | director_proposals·editing proposal adapter | 직접 적용·범위 제한·버전·되돌리기 | 모델 통합 실사용 미검증 |
| SYS-15 | 기억·사서 / 인계 §6 | yujin_memory·memory_librarian | 후보만 생성·승인 경계·중복·워터마크 | D 선별 시험 통과, 운영 기억 변경 없음 |
| SYS-16 | 미리보기·최종 MP4 / 운영 §10.0 | outputs·FfmpegFinalRenderer | 현재 편집 반영·파일·재생·원본 추적 | 합성 legacy 출력 재생·역추적 통과, 현재 편집 세션 반영 미검증 |
| SYS-17 | 가로·세로 변형 / 구현계획 §8.4 | output_variants | 같은 원본·변형 상태·출력 유지 | 자동 근거, 실영상 변형 미검증 |
| SYS-18 | CapCut / 운영 §10.0 | capcut-export·host bridge | 선택적 호환 결과·실제 Desktop | 설치 탐지만 확인, Desktop 편집·출력 미검증 |
| SYS-19 | 공유·회수 / 최신 인계 §7 | OutputsPage·preview_shares | 새로고침 후 목록·회수 | 프런트 자동 검증, 실제 링크 생성/회수 안 함 |
| SYS-20 | MCP / 최신 인계 §1 | services/mcp | stdio 도구·오류·범위 제한 | 자동 근거, 현재 컨테이너 stdio 통합 미검증 |
| SYS-21 | 저장·원본 보호 / 운영 §10.14·§11 | local_project_store/postgres·asset paths | 경로 경계·일관성·재접속·원본 보존 | 운영 읽기만, 복구·마이그레이션 실증 없음 |
| SYS-22 | 보호 경계 / CSRF 인계·운영 §10.14 | csrf_guard·gateway·network config | 승인 Origin·credential 비노출·외부 전송 제한 | 지정 경계 코드·구성 표본, 종합 보안 인증 아님 |
| SYS-23 | 기동·장애 진단 / 운영 §11 | owner-ready·health | 준비 상태를 기능 성공과 구분 | 시작 시 blocked 2항목, 런타임 변동 있음 |
| SYS-24 | 백업·복구 / 운영 데이터 보존 | 저장 전략·백업 문서 | DB+파일+승인/기억의 일관 복구 | 전체 복구 실증 미검증 |
| SYS-25 | 설치형 / 08-30 승인·운영 §10.19 | apps/desktop | 설치·서명·웹뷰 Origin·기능 사용 | 미검증 |
| SYS-26 | 외부 게시 / 승인 게이트 | YouTube·Telegram 연결 | 실제 전송 전 승인·실패 복구 | 이번 진단에서 실제 전송 제외 |
| SYS-27 | 확장 계획 / 인계 §2·§3 | track_registry·egress allowlist | 계획·부분 구현·실행 배선 분리 | 미구현을 기존 제품 회귀로 집계하지 않음 |

개별 자동 테스트의 전체 결과는 로그와 JUnit에 보존한다. 이 목록을 공식 제품 기능 통과율의 모수로 사용하지 않는다.

요청한 모든 필드(계획 상태·기준 조항·진입점·검증 방법·증거·판정·심각도·다음 조치)는 같은 디렉터리의 `system-audit-2026-09-10-requirements.csv`에 28행으로 정리했다. 계획 상태는 문서상의 기능 제공 주장과 진행 상태이며 실사용 완료 승인을 뜻하지 않는다. 기준의 정확한 승인/완료 수준을 확정하지 못한 세부 조건은 표 안에 명시했다.

## 4. 실행 증거

| 실행 | 기준·결과 | 증거 |
|---|---|---|
| 시작 Git 검사 | A, 기존 변경 2개, main/개발선 0/0, diff whitespace 오류 없음 | baseline.json |
| owner-ready Check | 16항목 중 14 pass·2 blocked: 기존 변경, Hermes dashboard 연결 거부 | owner-ready-check.json, owner-ready-run.json |
| 런타임 소스 비교 | A: API/packages/frontend 소스 524개 중 522 일치, 2개는 기존 미커밋 파일 | container-source-hashes.json, runtime-source-comparison.json |
| 전체 Python | 4,778 passed·56 skipped·1 failed, 46분12초. 실행 중 커밋 변경 | pytest-short-full.log, pytest-short-results.xml, pytest-short-run.json |
| 프런트 전체 B | 1,596 passed·1 failed / 130 files | frontend-tests.log, frontend-run.json |
| 프런트 단독 C | CreationInterview 35 passed | frontend-creation-focused.log |
| 프런트 전체 D(C와 동일 소스) | 1,605 passed / 130 files | frontend-current.log, frontend-current-run.json |
| 타입 검사·빌드 C | tsc --noEmit 및 별도 디렉터리 Vite build 통과, JS 918.34 kB 경고 | typecheck.log, build.log, build-run.json |
| 실제 브라우저 1차 | 6개 주소 모두 연결 거부. 앱을 켜거나 재시작하지 않음 | browser-readonly.json |
| 실제 브라우저 B | 6개 경로 HTTP 200, JS page error·가로 넘침 없음. 홈/프로젝트 썸네일 404 존재 | browser-readonly-B.json |
| 기존 모의 API E2E D | 29 passed·19 failed / 48, 단일 worker, 5.8분 | e2e.log, e2e-run.json, e2e-results/ |
| 선별 Python D | 9파일 59 passed·1 warning, 24.54초 | current-backend.log, current-backend.xml, current-backend-run.json |
| 런타임 대조 D | 5개 컨테이너 healthy. 비교 대상 소스 528/528 일치. 실제 제공 JS/CSS와 별도 빌드 SHA256 일치 | runtime-current.json |
| 합성 출력 D | 실제 FFmpeg·ffprobe·전체 디코딩·Chromium 재생 및 자산 해시 대조 통과 | reverse-output.json, synthetic-playback.json |
| 스냅샷 manifest E | 기존 PNG 메타데이터·해시 검증 통과. 새로운 화면 비교 통과를 의미하지 않음 | snapshot-manifest-check.log, snapshot-manifest-run.json |

브라우저 운영 점검은 읽기 전용 요청만 허용했다. POST/PATCH/PUT/DELETE와 다른 origin을 차단하는 점검 스크립트를 사용했다. 실제 자료를 편집하거나 외부로 전송하지 않았다. 응답 본문·프로젝트 이름·개인 자료 내용은 보고서에 수집하지 않았다.

단위 테스트는 기본적으로 실제 LLM 연결을 막고 결정적 대체 구현을 사용한다(`tests/conftest.py`). 프런트 테스트는 jsdom 재생을 대체하고, 기존 E2E는 fake API 및 route mock을 쓴다. 이들 성공은 실제 모델 품질·PostgreSQL 통합·사용자 영상 품질을 입증하지 않는다.

## 5. 발견·정정·추가 확인

### D-01 인계 진입점 중복 — B에서 확인, 후속 수정됨

- 분류: 문서 불일치 / Important(점검·개발의 기준 선택 오류 가능).
- 재현: `tests/test_handoff_entry_point.py::test_entry_map_points_at_the_newest_handoff`.
- 기대: 가장 최신 날짜에 대체되지 않은 인계가 하나.
- 실제 B: 2026-09-08 두 문서가 남아 `assert 2 == 1` 실패.
- 후속: 다른 개발 작업의 `9725b184f`가 옛 인계에 대체 표시 추가. D 선별 테스트에서 통과했다. 당시 결함은 해결 확인이며 다시 수정 대상으로 넘기지 않는다.

### S-01 촬영본 후보 구간 저장 시 시작값 손실 — 원인 미확정

- 분류: 의심 사항 / Important 가능(선택 구간이 달라질 수 있음).
- B 전체 프런트 실행: 요청 인수의 시작값 1.5 예상, 실제 0, 끝값 4·revision 3은 일치. 로그 1504행 이후.
- C 단독 파일 35개와 전체 1,605개는 통과했다. 이를 최초 실패의 오탐 확정 또는 수정 완료로 해석하지 않는다.
- C의 CreationInterview 변경은 source-video와 자료실 링크 관련이며, 후보 구간 초기화의 원인을 고친 변경이라고 확인하지 않았다.
- 조사 지점: `CreationInterview.tsx`의 readiness 변경 시 `setCandidateRanges` 초기화와 비동기 복구. 초기 로드/갱신/다른 후보 조작이 미저장 입력을 덮는지 지연 응답을 제어하여 재현한다.
- 실제 사용자 화면의 같은 증상 재현은 아직 없다. 타임아웃만 늘리거나 테스트 기대값을 0으로 바꾸지 않는다.

### S-02 프로젝트 썸네일 404 — 영향·원인 미확정

- 분류: 의심 사항 / Minor 예상.
- B 운영 브라우저 홈과 프로젝트 목록에서 각각 2회 thumbnail 404. 페이지 자체는 정상 표시되고 오류 문구·JS 예외 없음.
- 썸네일 부재의 정상 대체 표시인지, 삭제된 자산 참조인지 현재 데이터와 렌더링 경로를 추가 확인해야 한다. 목록 오류 4건을 독립 결함 4개로 세지 않는다.
- 운영 자산 삭제·재생성·DB 수정은 하지 않았다.

### G-01 전체 검증 기준선의 변동 — 검증 공백

- 분류: 미검증 / Important.
- 전체 Python 실행 중 `fb2b06155` 이후 `5e9eeab64`·`c84de46af`·`ea26b76c9`가 들어왔다. 이후 C에서도 23파일이 바뀌었다.
- 4,778 passed 결과를 C의 전체 회귀 통과로 옮겨 적지 않는다. 현재 변경분 시험을 추가해도 현재 HEAD 전체 스위트와는 다르다.
- 다음 종료 검증 때 구현 변경을 닫은 한 커밋에서 전체 실행하고 시작/종료 해시를 대조해야 한다.

### G-02 실제 통합·복구·사람 승인 — 검증 공백

- 운영 PostgreSQL 환경에서 쓰기가 필요한 전체 사용자 흐름, 실제 AI/STT/TTS/번역·더빙, 실제 Desktop CapCut/Tauri, DB+파일 일관 복구는 통과 판정하지 않았다.
- 운영 원본을 쓰기 테스트에 사용하지 않는다. 별도 PostgreSQL 데이터·파일 루트와 현재 빌드를 가진 격리 실행 환경으로 이어서 검증한다.
- 기존 mem0 백업이 있다는 사실과 VideoBox 전체 데이터 복구 가능 여부는 다르다.
- 최종 영상·음향 품질, 권리·게시 승인은 사용자 몫으로 남긴다.

### D-02 E2E 기준·fixture가 승인된 화면과 불일치 — 확인된 검증 결함

- 분류: 확인된 결함(검증 하네스) / Important. 핵심 사용 흐름을 검증하지 못한 채 실패하여 출시 판단을 방해한다. 제품 결함 19개로 집계하지 않는다.
- `product-shell.spec.mjs`의 3실패: 과거 전체 메뉴·새 프로젝트 문구·사이드바 제거 기대가 09-04 shell 및 09-05 단일 시작 결정과 맞지 않는다.
- `exact-preview.spec.mjs:288,297,306`의 3실패: 기본 manifest의 `tracks=[]` → 빈 편집 세션 → `EditorWorkbench`의 `projectIsEmpty=true` → `preview-stage`의 승인된 빈 프로젝트 안내. 이런 fixture로 비어 있지 않은 프로젝트의 proxy 대기/오래됨/실패 안내를 기대한다. 유효한 트랙이 있는 fixture로 실패 경로를 검증하고 빈 프로젝트 안내 검증도 보존한다.
- `z-script-first-vertical.spec.mjs:60`의 1실패: `video.controls=true` 기대. 현재 preview는 사용자 정의 컨트롤 중복을 피하려고 native controls를 제거한다. 실제 재생/탐색 조작을 확인해야 한다.
- 나머지 locator/화면 이동 관련 11실패와 성능 1실패는 아래 의심·추가 조사로 남긴다. 7건의 위 불일치와 합쳐 총 19실패다. 원인별 3묶음을 동일 근원 하네스 불일치 D-02에 연결한다.
- 최소 방향: 현행 승인 화면을 기준으로 selector·선행 이동·fixture를 보정한다. 테스트를 맞추려고 승인된 UI를 되돌리지 않는다. 세부 파일·행·재현 흔적은 `e2e.log`와 trace에 있다.

### S-03 나머지 E2E 조작 11건 — 제품/테스트 원인 미분리

- 분류: 의심 사항 / Important 가능. editor-workbench 5, exact-preview audition 1, library-footage crosslink 2, library-workspace 1, media-recovery 1, voice-tts-settings 1.
- dock 초기 상태, 메뉴/탭 진입, 현재 이름, 숨겨진 회복 안내, 실제 클릭 후 요청 순서를 trace로 조사해야 한다. 타임아웃·locator 실패만으로 저장/undo/음성 기능이 고장났다고 단정하지 않는다.
- 이 실패로 도달하지 못한 핵심 후속 흐름은 미검증이다. 관련 코드가 있다는 이유로 통과 처리하지 않는다.

### S-04 편집 dock 성능 gate 초과 — 측정 사실, 원인 미확정

- 분류: 의심 사항 / Important 가능. `release-gates.spec.mjs:58`.
- 단일 worker Chromium 149, 1920×1080. 5표본 median 120.9ms, 기존 92ms 대비 약 31.4% 증가로 20% 한도를 초과했다. p95 122.4ms, structural_failure=false.
- 기준은 2026-07-23의 보정값이다. 동일 환경·현재/기준 버전의 반복 측정 전에는 제품 성능 회귀를 확정하지 않는다. 임계값 상향·assert 삭제로 통과시키지 않는다.

### D-03 E2E 성능 산출물의 고정 저장 경로 — 확인된 하네스 격리 결함

- 분류: 확인된 결함(검증 하네스) / Minor. 지정한 `--output`과 무관하게 `release-gates.spec.mjs`가 `apps/web/test-results/editor-workbench-performance.json`에 기록한다.
- 이번 점검 중 해당 생성 파일이 기록됐다. 이전 생성 파일이 있었는지·내용이 무엇이었는지 기준 해시가 없어 덮어쓰기 여부는 미확정이다. 점검자가 이를 숨기거나 추정 복구하지 않았다. 기록 사본은 audit artifact에 보존했다.
- 사용자 원본/추적 소스가 변경된 증거는 없다. 향후 출력 경로를 testInfo.outputPath 또는 명시적 audit 경로로 전달하도록 수정하고 외부 경로 미변경을 검사한다.

## 6. 결과물 역방향 검증과 한계

`test_final_render_endpoint_produces_a_real_playable_mp4_end_to_end`의 합성 sine 음성·testsrc 영상·결정적 STT fixture를 사용했다. 실제 FFmpeg 출력은 H.264 1920×1080, AAC 48kHz stereo, 3.000초, 213,373바이트다. 원래 4초 입력 중 타임라인 3초의 결과이므로 길이 차이를 결함으로 세지 않는다. 전체 디코딩 exit 0. 별도 합성 파일 전용 로컬 페이지에서 Chromium의 재생 버튼을 눌러 시간 진행 0.516717초·error=null을 확인했다.

`export_001 → final_render_job_005 → timeline_build_job_004 → timeline_001 → 입력 자산`의 DB 연결, 사용 자산 3개의 복사본/입력 해시 일치를 확인했다. MP4·타임라인·합성 SQLite를 artifact로 보존했다. **이 fixture는 legacy job 경로이며 source_session_id=null이다.** 현재 브라우저 편집 세션의 revision 일치, 자막 출력/번역 품질, PostgreSQL 영속성, 다른 프로젝트/오래된 preview 혼입 방지는 이 결과로 입증하지 않는다. 출력 메타데이터 caption_count=0이며 자막 품질 통과를 주장하지 않는다.

## 7. 마감·우선순위·재개

1. 먼저 최신 변경을 반영한 한 기준선을 고정하고 변경 파일 해시까지 보존한다. D→E의 40파일 목록은 `changes-after-tested-baseline.txt`에 기록한다. 특히 multi-track render/session/transactions, overlay, owner-ready가 재검증 대상이다.
2. D-02/D-03의 검증 결함을 작은 수정 단위로 처리한다. S-01과 S-03의 데이터/핵심 흐름 위험은 재현 조사 우선순위 Important이며 확정될 때만 제품 코드를 수정한다.
3. S-04 성능 환경을 고정해 비교하고 S-02 썸네일 참조를 읽기 전용으로 조사한다.
4. 현재 HEAD 전체 Python·프런트·정적검사·빌드·E2E를 순차 실행한다. 과거 실패는 보존한다. 이후 격리된 PostgreSQL+파일+현재 빌드에서 실제 브라우저의 만들기→자산→편집→유진 적용/undo→저장/재접속→출력→실패/취소/재시도를 수행한다.
5. 전체 복구, 모델/외부 의존성 없는 경우, 실제 STT/TTS/번역·더빙, 선택적 CapCut/Tauri는 별도 증거가 필요하다. 현재 진단 중 운영 쓰기 환경 격리를 구성하지 않았으므로 해당 실제 쓰기 흐름은 차단으로 남긴다.

Critical로 확정한 결함은 없다. 이는 Critical 결함이 없다는 보장이 아니다. 확인된 제품 데이터 손실도 없지만 핵심 실사용 공백이 있어 전체 정상/출시 가능을 선언하지 않는다. 28행은 범위 추적 단위이며 제품 요구사항 전체의 확정된 분모가 아니므로 수행률·기능 통과율 퍼센트를 만들지 않는다. 자동 검사 수치는 위 실행별 숫자만 사용한다.

완료한 점검 활동: SYS-00~02 문서/기준 표본, 전반 자동 검증, SYS-03/05/23 운영 읽기, SYS-16 합성 결과물 검증. 진행 중인 점검 프로세스는 없다. SYS-03~25의 상세 실사용/경계조건은 CSV 판정을 따라 이어간다. SYS-26 실제 전송은 제외, SYS-27은 계획 범위별 재확인이다. 이미 끝난 D 증거를 재작성하지 말고 최신 변경과 공백부터 진행한다.

사용자에게 남은 판단은 실제 시청·청취 품질과 사용 승인, 외부 게시/권리, 범위 밖 확장 결정이다. 재현 가능한 로컬 결함 수정에 불필요한 재승인을 요구하는 뜻은 아니다.

마감 Git: 마지막 스냅샷 `closing-baseline.json`의 HEAD·branch·upstream/worktree·status·diff-check를 기준으로 한다. 이 점검의 추적 소스/기존 지침 변경은 없으며 새 문서 3개만 untracked로 남긴다. 별도 개발자의 커밋은 이 점검 변경에 포함하지 않는다. 보호 경로 `.tmp-final-fence-debug/`, `.tmp-real-video-dogfood/`, `apps/web/.tmp-real-video-dogfood/`는 작업 대상으로 삼지 않았다.

새 기록: 이 보고서, `system-audit-2026-09-10-requirements.csv`, `system-audit-2026-09-10-claude-remediation.ko.md`; artifact의 로그·실행 메타데이터·trace·격리 빌드·합성 출력·검증 스크립트. 파일별 목록·크기는 `generated-files.json`을 따른다(목록 자체는 자기 참조 때문에 제외). 짧은 임시 합성 데이터 디렉터리 3개와 중단한 긴 pytest 디렉터리는 삭제하지 않았다. 위 D-03의 하네스 고정 출력은 격리 예외로 명시한다.

실행 명령 보충은 artifact의 `reproduction-commands.md`, Claude용 작업 순서·완료 기준·추가 검사·복사할 프롬프트는 `system-audit-2026-09-10-claude-remediation.ko.md`를 사용한다.
