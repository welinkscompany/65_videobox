# VideoBox 개발 Fast Path

목적:

- 반복 명령 기억 비용을 줄인다
- slice별 닫는 기준을 고정한다
- 빠르게 개발하되 false green을 줄인다

## 1. 기본 원칙

- 항상 `plan reconcile -> RED -> minimal GREEN -> focused verification -> broader verification` 순서를 지킨다
- 새 UI를 만들기 전에 기존 흐름 재사용 가능 여부를 먼저 본다
- `review recommendation` 류 변경은 버튼보다 상태 계약을 먼저 본다
- broad regression은 마지막에만 돌리되, focused gate 없이 건너뛰지 않는다

## 2. 바로 쓰는 명령

현재 브랜치의 기본 helper는 `scripts/dev-fast-path.ps1`이다.
닫힌 review-action family 유지보수에는 기존 `scripts/review-action-fast-path.ps1`를 별도로 둔다.

저장소 루트에서 아래 스크립트를 사용한다.

```powershell
./scripts/dev-fast-path.ps1 -Mode status
./scripts/dev-fast-path.ps1 -Mode output-gating
./scripts/dev-fast-path.ps1 -Mode preflight-backend
./scripts/dev-fast-path.ps1 -Mode preflight-frontend
./scripts/dev-fast-path.ps1 -Mode current-focused
./scripts/dev-fast-path.ps1 -Mode current-focused-parallel
./scripts/dev-fast-path.ps1 -Mode broader
```

의미:

- `output-gating`
  - review-required / approval-required 출력 경계 관련 backend focused pytest만 실행
- `preflight-backend`
  - partial-regeneration preflight read-only/prediction 관련 backend focused pytest만 실행
- `preflight-frontend`
  - blocked-warning / resumed preflight degraded warning / resumed-candidate scope cleanup 관련 frontend focused gate만 실행
- `current-focused`
  - 현재 우선순위인 `output gating -> preflight backend -> preflight frontend`를 한 번에 실행
- `current-focused-parallel`
  - 위 `current-focused`와 같은 검증 범위를 병렬로 실행해 slice-close 대기 시간을 줄인다
- `broader`
  - frontend build + full backend regression 실행
- `status`
  - 현재 focused pattern과 추천 실행 루프를 출력

패턴 override 예시:

```powershell
./scripts/dev-fast-path.ps1 -Mode output-gating -BackendPattern "reopening_approved_review_with_residual_blockers_returns_blocked_status"
./scripts/dev-fast-path.ps1 -Mode preflight-frontend -FrontendPattern "blocked preflight warning"
```

## 3. 이 helper를 써도 되는 범위

이 helper의 기본 범위는 현재 next-priority인 `approval-output hardening / preflight contract`다.
일반적인 편집기 전반이나 닫힌 review-action family 전체를 다시 기본 레일로 삼지는 않는다.

이 helper가 맞는 경우 기본 루프는 아래다.

1. plan과 현재 변경 상태를 먼저 맞춘다
2. failing test 1개만 추가한다
3. RED 단계에서는 exact test 1개만 먼저 돌려 fail을 확인한다
4. minimal implementation만 넣는다
5. GREEN 단계에서도 같은 exact test를 먼저 다시 돌린다
6. 그 다음 해당 slice에 맞는 `output-gating`, `preflight-backend`, `preflight-frontend` lane만 돌린다
7. slice가 닫히면 기본값으로 `current-focused-parallel`로 인접 경계까지 다시 확인한다
8. task 단위가 닫히면 마지막에만 `broader`를 돌린다

추가 운영 규칙:

- `output-gating`은 subtitle/preview/export의 blocker/approval 경계를 기본으로 묶는다
- `preflight-backend`는 targeted-segment normalization, duplicate normalization, unsupported scope rejection, blocked/draft prediction 경계를 기본으로 묶는다
- `preflight-frontend`는 blocked-warning surface, resumed preflight degraded warning, resumed mismatch non-reuse, resumed scope cleanup 경계를 기본으로 묶는다
- 새 slice에서 RED/GREEN은 helper 전체 대신 정확히 1개 테스트만 먼저 본다
  - backend: `pytest tests/test_api.py -q -k "<exact test name>"`
  - frontend: `npm test -- --run <canonical test file> -t "<exact test name>"`
- lane close가 필요하면 script override를 써서 helper 범위를 더 줄인다
- current status 문서에 특정 canonical frontend test file 전체를 주장할 때는 helper gate와 별도로 그 파일을 다시 실행한다
- broader는 slice close 직전까지만 미룬다. 다만 focused 없이 broader부터 돌리지는 않는다

속도 우선 기본값:

1. RED/GREEN 단계에서는 exact test만 돌린다
2. lane close에서는 해당 lane helper만 돌린다
3. slice close에서는 `current-focused` 대신 `current-focused-parallel`을 먼저 쓴다
4. 문서 수정은 focused green 이후로 미룬다
5. canonical focused test file 전체 재실행은 상태 문서 갱신이나 task close가 필요할 때만 돌린다

## 4. review-action 변경 시 꼭 보는 함정

- recommendation state가 `project-wide row`인지 `timeline-local artifact`인지 섞이지 않는지 확인
- blocker clear가 `recommendation_id` 단위가 아니라 너무 넓게 지워지지 않는지 확인
- DB update와 timeline artifact update가 서로 모순 상태를 남기지 않는지 확인
- 새 상태 필드가 생기면 fallback normalization이 이전 의미를 깨지 않는지 확인

## 5. 추천 운영 방식

- 작은 slice도 기본은 메인 에이전트가 직접 TDD로 구현하고, `Subagent-Driven`은 실제로 속도/정확도 이득이 분명할 때만 최소 범위 explorer로 사용한다
- spec review, code-quality review, gap 검증, 역방향 동작 검증은 매 turn의 고정 의무가 아니라 리스크 대비 효율이 높을 때만 선택적으로 붙인다
- reviewer가 찾은 리스크는 채택한 경우 다음 slice 전에 먼저 반영한다
- 현재 브랜치에서 반복되는 검증은 priority helper로 통일

## 6. 이 문서를 언제 쓰는가

- review-action family의 historical/maintenance 범위
- approval/output hardening
- subtitle/preview/export gating 같이 출력 계약이 민감한 작업
- TTS approval/output contract 같이 review 상태와 출력 상태가 같이 묶이는 작업

## 7. 현재 브랜치에서의 적용 규칙

현재 브랜치에서 아래 순서를 기본값으로 고정하는 범위는 `approval-output hardening / preflight contract` 계열 slice다.
그 외 slice는 이 helper를 억지로 맞추지 말고, 직접 관련 테스트/명령을 더 좁게 잡는다.

1. `./scripts/dev-fast-path.ps1 -Mode status`로 현재 gate와 pattern을 먼저 확인한다
2. 다음 최소 slice에 대해 failing test 1개만 추가한다
3. RED/GREEN은 가능한 한 exact test 1개로 먼저 확인한다
4. minimal GREEN만 넣고 같은 exact test를 다시 돌린다
5. lane close가 필요하면 관련 helper만 돌린다
6. slice가 닫히면 `current-focused-parallel`을 다시 돌린다
7. 현재 상태 문서에 frontend 전체 수치를 남길 필요가 있으면 `npm test -- --run`을 별도로 돌린다
8. task 단위가 닫히면 `broader`를 돌린다
9. 그 뒤에만 spec review -> code-quality review를 붙인다

이 순서의 의도:

- 구현 전에 계획/리스크를 다시 길게 재정리하는 시간을 줄인다
- 전체 test file 실행 대신 현재 우선순위와 직접 연결된 focused gate만 먼저 본다
- reviewer는 slice green 이후에만 붙여서, RED 단계에서의 왕복 비용을 줄인다

## 8. Historical Prompt 위치

닫힌 review-action family 당시의 바로 붙여넣기 프롬프트는 아래 문서에 남겨 둔다.
현재 브랜치의 next-priority goal SSOT로 쓰지 말고 historical reference로만 본다.

- `docs/superpowers/goals/review-action-next-slice-subagent-prompt.ko.md`

## 9. Review-Action 유지보수 Helper

review-action family의 maintenance나 rollback hardening만 다시 볼 때는 기존 helper를 그대로 쓴다.
이 helper를 현재 기본 레일로 다시 승격시키지는 않는다.

```powershell
./scripts/review-action-fast-path.ps1 -Mode status
./scripts/review-action-fast-path.ps1 -Mode backend-focused
./scripts/review-action-fast-path.ps1 -Mode frontend-focused
```

## 10. 고정 운영 규정

아래 규정은 현재 브랜치의 개발 운영 기본값으로 고정한다.
이 문서에 적힌 규정은 저장소 루트 `CLAUDE.md`와 함께 이후 turn에서도 별도 재지시가 없는 한 계속 따른다.
사용자가 turn 중에 추가로 확정한 운영 선호도도 이 섹션에 흡수해 SSOT로 유지한다.

### 10.0 Local Media Director 출력 모드와 acceptance 경계

1. `preview` 모드는 로컬 후보·제어값·권리 경고를 읽기 전용으로 확인하는 자동 검증 경로다. 편집 세션이나 타임라인을 변경하지 않는다.
2. `final render` 모드는 승인된 현재 타임라인만 FFmpeg MP4로 만든다. project-local SHA/revision 및 권리 경고 provenance를 다시 확인하고, user-owned unknown 권리는 로컬 출력은 허용하되 MP4 metadata에 저작권 확인 경고를 기록한다.
3. `CapCut draft` 모드는 같은 현재 타임라인을 real draft JSON으로 만든다. 동일 SHA/revision 검증과 `videobox_output_metadata` 권리 경고를 기록하며, CapCut Desktop을 자동 실행하지 않는다.
4. 자동 acceptance는 API contract, SHA/freshness, preview, FFmpeg, draft JSON, Korean SRT, warning metadata까지다. Desktop CapCut open/edit/export 사용성, publish 전 실제 권리 확인, 사람의 영상·음향 품질 판단은 human acceptance로 남긴다.

### 10.1 작업 목표와 우선순위

1. 항상 현재 프로젝트의 공식 계획서, 구현 계획, 체크리스트를 기준으로 작업한다.
2. 계획서가 여러 개면 전체 계획 구조와 현재 작업이 속한 범위를 먼저 식별한다.
3. 작업은 가능한 한 공식 Task, Step, 완료 기준에 맞춰 진행한다.
4. 계획서 밖의 작업이 필요하면, 왜 필요한지와 공식 Task 완료로 계산되는지 여부를 구분해서 설명한다.

### 10.2 구현 방식 선택

1. TDD는 기본 규칙으로 유지한다.
   - 다만 실제 코드나 동작이 바뀌지 않는 문서 정리, 상태 정리, closeout-only 작업에는 기계적으로 적용하지 않는다.
2. 서브에이전트 드리븐은 항상 쓰지 않고, 메인 에이전트 대비 실제 효율이나 최적화 이득이 명확할 때만 최소 범위 explorer로 사용한다.
3. code review, gap 검증, 역방향 동작 검증도 고정 의무가 아니라, 실제 리스크를 줄이는 데 효과적일 때만 선택적으로 수행한다.
4. 턴 종료 시 어떤 방식을 선택했고 왜 그 방식이 가장 간단하고 검증 가능했는지 짧게 설명한다.
5. 불필요한 형식적 절차 때문에 속도가 떨어지면 더 단순하고 검증 가능한 방식을 우선한다.

### 10.3 실행 하네스 규정

1. 가능하면 프로젝트 안의 기존 스크립트, 테스트, 검증 명령, 빌더, verifier를 우선 사용한다.
2. 같은 검증을 길게 반복 설명하지 말고 프로젝트의 표준 검증 경로를 재사용한다.
3. 새 기능이나 새 검증 흐름이 반복될 가능성이 높으면, 일회성 수동 확인보다 재사용 가능한 스크립트나 테스트 하네스로 정리한다.
4. 빌드, 테스트, 검증, materialization, closeout은 가능한 한 고정된 명령 경로로 수행한다.
5. 수동 확인보다 자동 검증을 우선하되 자동화 비용이 과도하면 필요한 범위까지만 자동화한다.
6. backend 검증은 프로젝트 루트의 `.venv\\Scripts\\python.exe -m pytest`를 사용한다. bare `pytest`, 전역 `py`, 시스템 Python은 결과 근거로 쓰지 않는다.

### 10.4 컨텍스트와 토큰 절약 규정

1. 이미 검증된 사실은 길게 반복하지 말고 현재 작업에 필요한 차이만 설명한다.
2. 파일 전체 반복 요약보다 필요한 섹션, 변경점, 결론만 전달한다.
3. 관련 없는 로그, 장황한 출력, 중복 설명은 줄인다.
4. 큰 문서를 다룰 때는 공식 Task 번호, 완료 기준, 현재 상태를 기준으로 압축해서 설명한다.
5. 진행률 설명은 항상 짧고 명확하게 유지한다.

### 10.5 정확성과 검증 규정

1. 완료라고 말하기 전에 해당 작업 범위에 맞는 테스트, 검증 스크립트, diff 검사, 상태 검사를 직접 수행한다.
2. 테스트가 없으면 최소한 재현 가능한 검증 명령이나 확인 절차를 남긴다.
3. 검증이 부족하거나 불가능하면 완료로 단정하지 말고, 검증된 것과 미검증 항목을 구분해서 설명한다.
4. `readiness`, `connected`, `green`, `verified` 같은 표현은 실제 실행 가능 상태와 다를 수 있으면 의미 차이를 분명히 구분한다.

### 10.6 런타임과 핫패스 규정

1. hot path와 inspection/debug path를 구분해서 설계한다.
2. 직원 런타임이나 실시간 프롬프트에 항상 로드되는 데이터는 최소화한다.
3. 이벤트 인덱스, 온톨로지, 대형 요약 그래프, 장문 로그는 기본적으로 inspection surface로 취급한다.
4. hot path에는 실제 실행에 필요한 작고 안정적인 derived artifact만 올린다.
5. derived artifact는 SSOT를 대체하지 못하며, 공식 문서와 정책을 약화하거나 재해석하면 안 된다.

### 10.7 커밋과 푸시 규정

1. 특별한 blocker가 없는 한 turn 종료 시에는 항상 커밋한다.
2. push는 매 turn 강제가 아니라, 작업 단위가 논리적으로 닫혔는지, 원격 반영이 적절한지, 다음 작업과 분리하는 것이 유리한지를 보고 판단한다.
3. 커밋 또는 푸시를 하지 않았다면 이유를 짧게 설명한다.
4. 워킹트리는 가능한 한 깨끗하게 유지한다.

### 10.8 진행률 계산 규정

이 규정은 진행률을 **보고할 때 어떻게 계산하는가**를 정한다. 매 턴 보고를 강제하지 않는다.
진행률은 Task를 실제로 열거나 닫을 때, 또는 사용자가 물을 때 보고한다.

1. 진행률은 이번 턴 기준이 아니라 전체 공식 계획서 기준 누적으로 계산한다.
2. 여러 계획서가 동시에 있으면 각 계획서의 공식 Task 수 또는 명시된 완료 단위를 기준으로 전체 모수와 완료 수를 계산한다.
3. 비공식 조사, 메모, 연결 점검, 아이디어 정리, 사전 분석은 공식 Task 완료율에 포함하지 않고 준비 작업으로 별도 표시한다.
4. 진행률을 적을 때는 모수와 계산 기준을 함께 밝힌다. 모수가 정의되지 않았으면 수치를 지어내지 말고 미정의 사실을 그대로 말한다.

### 10.9 턴 종료 보고

턴이 끝날 때 아래를 전달한다. 고정 서식이 아니라 내용 요건이다.
해당 없는 항목은 적지 않는다. 대화형 턴에 보고서 형식을 억지로 씌우지 않는다.

1. 이번 턴에 실제로 한 일을 쉬운 말로 짧게.
2. 수행한 검증과, 검증하지 못한 채 남은 것.
3. 커밋·푸시 여부. 하지 않았으면 이유.
4. 막힌 지점이나 사용자 결정이 필요한 사항. 있을 때만.

다음 세션용 복사-붙여넣기 프롬프트는 남기지 않는다.
Codex 시절 세션 단절을 메우던 장치이며, 현재 개발 환경에서는 불필요하다.
세션 간 인계가 필요하면 프롬프트가 아니라 `docs/handoffs/` 문서로 남긴다.

**인계 문서를 새로 쓰면 `CLAUDE.md` §2 표의 `최신 세션 인계` 줄도 같이 옮긴다.**
`docs/handoffs/`에는 문서가 여든 개 넘게 쌓여 있어서, 새 세션이 어느 것을 읽어야
하는지 알려 주는 것은 이 한 줄뿐이다. 갱신을 잊으면 다음 세션이 옛 상태를 현재로
믿고 그 위에 쌓는다. 낡는 순간 `tests/test_handoff_entry_point.py`가 깨진다.

**같은 날 인계를 두 번 쓰면 옛 문서 맨 위에 `**대체됨:** \`새 문서 경로\`` 한 줄을
넣는다.** 날짜는 파일 이름으로 알 수 있지만 같은 날 안의 순서는 알 수 없다 --
2026-08-18에 실제로 나중 문서가 알파벳 앞이라 위 테스트가 옛 문서를 최신이라고
했다. 이 줄이 있으면 옛 문서를 연 사람도 첫 줄에서 어디로 갈지 바로 안다.

인계 문서에는 **"안 된 것"과 "확인하지 못한 것"을 나눠서** 적는다. 뭉뚱그리면
다음 세션이 되는 것으로 착각하고 그 위에 쌓는다. 커밋 목록은 `git log`로 언제든
볼 수 있으므로, `git log`에 남지 않는 것 — 왜 그렇게 됐는지와 교훈 — 을 우선한다.

### 10.10 변경 범위 통제

1. 현재 목표와 직접 관련 없는 코드나 문서 구조는 건드리지 않는다.
2. 더 나은 대안은 제안할 수 있지만 실제 수정은 현재 목표와 검증 범위 안에서만 진행한다.
3. 사용자 의도보다 정확성과 현실성을 우선하되, 불필요한 질문으로 작업을 멈추지 않는다.

### 10.11 개발 편의성 최적화 규정

1. 반복되는 작업은 가능한 한 스크립트, 템플릿, 검증 명령으로 고정해서 다음 턴 비용을 줄인다.
2. 새 규칙이나 새 산출물이 생기면 다음 작업자가 바로 이어받기 쉽게 경로와 역할을 명확히 남긴다.
3. 설명은 항상 쉬운 말로 요약하되, 기술적으로 중요한 경계와 리스크는 숨기지 않는다.
4. 속도보다 정확성이 중요한 영역과, 정확성보다 반복 속도가 중요한 영역을 구분해서 다룬다.
5. 사용자에게 설명할 때는 기본적으로 존댓말을 유지한다.

### 10.12 개발 종료 Release Audit 규정

1. 배포 또는 논리적으로 닫힌 개발 단위를 종료할 때는 `docs/superpowers/plans/2026-07-13-release-audit-protocol.ko.md`의 6개 gate를 적용한다: 코드리뷰, 계획 대비 갭 검증, 역방향 동작 검증, 전체 시스템 점검, 문서·지침 점검, 찌꺼기 파일 분류·정리.
2. gate는 형식적 체크가 아니라 위험 기반으로 수행하되, Critical/Important finding은 수정과 관련 재검증이 끝나기 전에는 closeout pass로 기록하지 않는다.
3. `artifacts/`, CapCut local export, 재현·QA 증거는 **다시 만들 수 있는가**로 판단한다 (owner 승인, 2026-08-09 — 판단 기준은 `CLAUDE.md` §5). 검증 스크립트가 매번 새로 쓰는 산출물과 지난 실행의 로그는 지워도 된다. 라이선스 증거, 외부에서 받아 온 소스 캐시, 테스트가 실제로 읽는 파일은 남긴다. 지우기 전에 경로 참조를 먼저 찾고 무엇을 왜 지웠는지 보고한다.
4. 삭제는 `safe-to-delete`로 분류되고 문서·테스트·실행 경로의 참조가 없으며 재생성 가능한 미추적 파일에만 한정한다. 대상이 없으면 삭제하지 않은 사실을 closeout에 남긴다.
5. 종료 상태 문서에는 gate별 evidence, finding severity, 남은 human acceptance, `git status/diff` 결과와 commit/push 여부를 남긴다.

### 10.15 자산 검색 체계 (2026-08-09)

1. 음악·효과음·촬영본을 한 문으로 찾는다: `POST /api/media-library/search`.
   `media_type`은 `music|sfx|broll` 중 하나가 **필수**다 — 장면이 효과음을 찾는데 음악이
   나오면 안 된다. `orientation`은 `broll`에만 허용하고 나머지엔 422로 거절한다.
   조용히 무시하면 owner는 걸러진 줄 안다.
2. **새 자산은 저절로 잡힌다.** 대기 판정의 열쇠가 둘이다 — 음악·효과음은 팩 `sha256` +
   `DESCRIPTION_VERSION`(`library_audio_indexer.py`), 촬영본은 파일 내용 해시 +
   `FOOTAGE_DESCRIPTION_VERSION`(`library_footage_indexer.py`). 같은 파일을 이름만
   바꿔 다시 넣어도 재분석하지 않는다.
3. **설명 문장 형식을 바꾸면 버전만 올린다.** 저장된 벡터는 그때의 문장을 가리키므로,
   버전을 올리면 전부 자동 재색인된다. 유지보수 루프가 1분마다 부른다(오디오 8개,
   촬영본 2개) — 화면 분석이 무거우므로 한 번에 처리하는 수를 작게 둔다.
4. **모델에 한국어로 답하라고 명시한다.** 안 하면 영어로 나오고, 언어가 어긋나면 검색
   점수가 0.52~0.59로 떨어진다(우리말끼리는 0.63~0.70). 두 색인기와 프로젝트 분석이
   `VISION_ANALYSIS_PROMPT` 하나를 공유한다.
5. **설명 문장이 획일적이면 검색이 사실상 무작위가 된다.** 고정 틀로 두 단어만 다르게
   하면 벡터가 거의 평행해진다 — 실제로 "신나고 빠른 음악"에 보통/보통 곡이 1등이었고
   2등과 0.002 차였다. 측정값마다 다른 표현을 써야 한다.
6. 측정과 임베딩을 분리한다. 측정은 ffmpeg만, 임베딩은 로컬 모델이 필요하다. 모델이
   없을 때 측정 결과를 버리지 않고, 벡터만 다음 차례에 받는다.

### 10.13 Creator-language dashboard copy 규정

1. 이 규정은 모든 현재·향후 개발 계획과 그 구현에 적용한다. 새 plan 또는 기존 plan의 수정은 visible text·accessible name·placeholder·status/error copy를 creator 결과/행동 언어로 분류하는 dashboard user-copy 범위와 검증 방법을 명시해야 한다.
2. 기본 dashboard와 그 안의 assistant/recommendation/empty/error surface는 사용자가 영상을 만드는 결과와 다음 행동만 말한다. 기본 어휘는 `영상`, `프로젝트`, `대본`, `장면`, `미디어`, `음악`, `자막`, `미리보기`, `추천`, `고르기`, `적용`, `내보내기`다.
3. 기본 dashboard의 visible text, accessible name, placeholder, error/status copy에는 개발·시스템·프로그래밍 내부 용어를 쓰지 않는다. 금지 예시는 `provider`, `runtime`, `fallback`, `loopback`, `API key`, `model`, `context`, `revision`, `pipeline`, `job`과 `시스템`, `개발`, `런타임`, `공급자`, `제공자`, `모델`, `API 키`, `루프백`, `폴백`, `컨텍스트`, `리비전`, `파이프라인`, `job`이다. 실패 상태는 내부 원인 대신 사용자가 할 다음 행동을 안내한다.
4. provider/model/diagnostic 설정은 기본 dashboard로 새로 노출하지 않는다. 별도 관리 설정이 필요하면 해당 surface를 dashboard와 구분하고, plan에 이유와 접근 경계를 기록한다.
5. 각 관련 Task는 RED/GREEN test 또는 재현 가능한 copy audit으로 visible/ARIA copy를 검증하고, review·closeout에 이 규정 충족 여부를 남긴다. 이 규정에 어긋나는 새 dashboard copy는 merge 대상이 아니다.

### 10.14 VideoBox Hermes local-MVP 네트워크 규정

1. `videobox-hermes-provider-egress`의 직접 egress는 VideoBox 개인 로컬 MVP에서 owner-operated `openai-codex` OAuth provider 연결을 위한 임시 한계다. production gateway allowlist가 아니며, provider host·redirect·IP 범위를 제한하거나 감사하는 보안 gateway로 주장하지 않는다.
2. Hermes dashboard는 VideoBox data, media mount, PostgreSQL, `videobox-internal`, `videobox-edge`에 연결하지 않는다. 대시보드의 보조 기억은 그 provider 설정으로만 연결하며, 전용 `/opt/data`에는 인증 상태만 둔다.

2-A. **유진 기억용 Mem0 경로 — owner 승인 (2026-08-08).** 대시보드 경로와 별개로,
   VideoBox 유진의 기억은 `videobox-hermes-memory-adapter`가
   `videobox-hermes-provider-egress`를 통해 Mem0에 연결한다. 승인 배경은
   유진의 로컬 기억이 한 번에 5개·각 280자로 제한돼 실제 사용에 부족했기 때문이다.
   **이 경로로 owner의 영상 기획과 대화 내용이 외부로 나간다.** 이 사실을 문서에서
   숨기지 않는다. 아래 경계는 조항 1의 "보안 gateway가 아니다"라는 전제 위에서 읽는다.

   - 어댑터는 `videobox-hermes-memory-network`와 `videobox-hermes-provider-egress`에만
     붙는다. VideoBox data, media mount, PostgreSQL, `videobox-internal`,
     `videobox-edge`에 **연결하지 않는다.** 조항 2의 제한이 어댑터에도 그대로 적용된다.
   - 나가는 것은 **정확히 두 가지뿐**이다. 스키마가 `extra="forbid"`로 고정돼 있어
     그 밖의 필드는 실을 수 없다.
     - 저장(`ApprovedMemoryStoreRequest`): `text`(280자 이내), `category`
       (`pacing|caption|audio|tone|workflow` 5종), `external_ref`, `operation_id`.
       **owner가 승인한 항목만** 나가며, 대화 전체를 자동으로 올리지 않는다.
     - 검색(`GatewayMemorySearchRequest`): `query`(280자 이내)와 `limit`(최대 5).
   - 원본 영상, 자산 파일, 대본 파일, 프로젝트 경로, 프로젝트 식별자는 나가지 않는다.
   - **로컬이 기억의 원본이고 Mem0는 검색·순위만 맡는다.** 조회 시 로컬 기록을 먼저 읽고,
     게이트웨이가 돌려준 항목 중 **로컬과 정확히 일치하는 것만** 채택한다
     (`yujin_memory_service.py:181` `if exact not in local: continue`).
     따라서 외부가 기억을 **주입할 수 없다.** 이 대조를 제거하지 않는다.
   - `MEM0_API_KEY`가 비어 있으면 어댑터는 뜨더라도 Mem0로 나가지 않는다.
   - **조회 폴백이 있다(owner 판단 2026-08-31).** 게이트웨이가 없거나 이번
     호출이 실패하면 `retrieve_approved_memories()`가 로컬에 저장된 승인
     기억을 저장 순서 그대로(뜻 기반 순위 없이) 돌려준다
     (`yujin_memory_service.py`의 `_local_fallback_order`/`_cap_preferences`).
     **로컬 원본이 없을 때만(승인·저장된 기억 자체가 0개)** 빈 결과다.
     예전엔 게이트웨이가 없으면 무조건 빈 결과였다 — owner가 "뜻으로 못
     고르더라도 아예 안 꺼내는 것보다 낫다"고 판단해 이걸로 정했다. 순위·
     예산 캡(5개, 총 1,400자)은 게이트웨이 경로와 동일하게 유지한다.
     즉 **Mem0를 켜도 게이트웨이가 없다고 기억이 완전히 사라지지는
     않는다** — 뜻으로 고른 순위 대신 저장 순서로 내려갈 뿐이다.
   - 이 승인은 **Mem0 기억 경로 하나에만** 적용된다. 다른 외부 전송, Telegram intake,
     host bridge, CapCut bridge의 근거가 아니다(조항 4 유지).
2-B. **유진 로컬 두뇌 경로 — owner 승인 (2026-08-08).** workspace 컨테이너가
   호스트의 LM Studio(`host.docker.internal:1234`)에 연결한다. 승인 배경은
   `base_url`이 `http://127.0.0.1:1234/v1`로 못박혀 있어 **컨테이너 안에서는 두뇌에
   닿을 수가 없었고**, 화면의 유진 대화가 `LOCAL_NETWORK_ERROR`로 전부 실패했기 때문이다.

   - **이 경로로 나가는 것은 이 컴퓨터 밖으로 나가지 않는다.** `host.docker.internal`은
     도커 호스트, 즉 같은 기계다. 조항 1의 provider egress와 성격이 다르다.
   - 허용 값은 **두 개뿐**이다: `http://127.0.0.1:1234/v1`(로컬 실행)과
     `http://host.docker.internal:1234/v1`(컨테이너). `settings.py`의
     `LocalOpenAICompatibleRuntimeConfig.__post_init__`이 그 밖의 값을 거부한다.
     scheme·port·path를 바꾼 값, 자격 증명이 붙은 값은 전부 거부된다.
   - 이 승인은 **호스트의 LM Studio를 부르는 경로에만** 적용된다. 대화 경로
     (`settings.py`의 `LocalOpenAICompatibleRuntimeConfig`)와 B-roll 분석의
     비전·임베딩 경로(`lm_studio.py`의 `LMStudioHTTPTransport`) **둘 다 같은
     주소·같은 기계**이며, 두 곳이 각각 못박고 있어 따로 열어야 했다.
     다른 host bridge의 근거가 아니다(조항 4 유지).

2-C. **대본에 맞춘 이미지 생성 경로 — owner 승인 (2026-08-20).** workspace 컨테이너가
   호스트의 ComfyUI(`host.docker.internal:8188`)에 연결한다. 승인 배경은 owner가
   **대본의 각 장면에 맞는 그림을 만들어 자산 공백을 채우기를** 원하기 때문이다.
   지금은 그 자리에 "장면을 보여 줄 영상이 없어요"만 남고 owner가 손으로 채운다.

   - **이 경로로 나가는 것은 이 컴퓨터 밖으로 나가지 않는다.** `host.docker.internal`은
     도커 호스트, 즉 같은 기계다. 2-B와 같은 성격이고 조항 1의 provider egress와 다르다.
   - 허용 값은 **두 개뿐**이어야 한다: `http://127.0.0.1:8188`(로컬 실행)과
     `http://host.docker.internal:8188`(컨테이너). 2-B가 `LocalOpenAICompatibleRuntimeConfig`
     `__post_init__`에서 그 밖의 값을 거부하는 것과 **같은 방식으로** 막는다.
     scheme·port·path를 바꾼 값, 자격 증명이 붙은 값은 거부한다.
   - 이 승인은 **호스트의 ComfyUI를 부르는 경로에만** 적용된다. 다른 host bridge의
     근거가 아니다(조항 4 유지).

   **함께 못박는 것 — 라이선스.** 2026-08-20 실측에서 이 경로를 막고 있던 것은
   하드웨어가 아니라 라이선스였다. 디스크의 유일한 이미지 모델이 **FLUX.1-dev
   (비상업)**인데 이 제품의 용도는 수익 유튜브다. 따라서:

   - **상업 이용이 허용된 모델만 쓴다.** 확보 대상은 `FLUX.1-schnell`(Apache-2.0).
   - 모델 이름을 설정에서 바꿀 수 있게 만든다면, **비상업 모델이 들어왔을 때
     조용히 돌아가게 두지 않는다.** 라이선스는 실행 중에 눈에 보이지 않는 종류의
     제약이라, 사람이 기억하는 것에 맡기면 반드시 새어 나간다.

   **아직 재지 않은 것 (승인과 별개로 남는다).**

   - 장당 생성 시간과 실제 VRAM 점유. `FLUX.1-schnell`을 확보한 뒤 ComfyUI 단독으로
     먼저 잰다. **LM Studio(유진의 두뇌)를 켜 둔 채로** 재야 한다 — 내리고 재면
     같이 못 쓰는 조합을 된다고 판단하게 된다.
   - 주의: ComfyUI `/system_stats`의 `vram_free`는 **남의 프로세스 점유를 못 본다.**
     용량 판단은 `nvidia-smi`로 한다.
   - ComfyUI API는 OpenAI 모양이 아니다(`POST /prompt` 그래프 JSON → `/history` 폴링
     → `/view` 회수). 2-B의 provider를 재사용할 수 없고 새로 짜야 한다.
   - ~~`docs/llm-provider-strategy.ko.md`가 "ComfyUI는 범위 밖"이라고 적고 있다.~~
     **2026-08-21에 같이 고쳤다.** 그 문서 §5가 이제 범위 안이라고 적고, 왜 LLM
     provider 경계와 종류가 다른지도 함께 적는다.

3. OAuth device code, account identity, credential contents, auth state와 memory contents는 source, `.env`, status document, verifier 출력에 기록하지 않는다. 검증은 mount/network/image/user/dependency 같은 경계 정보만 출력한다.
4. 이 local-MVP 경계는 VideoBox asset/file mutation, Telegram intake, egress gateway, host bridge, CapCut bridge의 활성화 근거가 아니다. 각각은 별도 구현·검증으로 닫는다.

## 11. 명령·주소·스크립트

`CLAUDE.md`에서 내려온 목록이다. 진입점 문서는 판단에 필요한 것만 담고,
외워 쓰는 목록은 여기에 둔다.

### 검증 명령

backend 검증은 반드시 프로젝트 루트의 venv를 쓴다. bare `pytest`나 시스템 Python은
근거로 쓰지 않는다. Windows에서 `python`은 Microsoft Store 별칭으로 잡혀 실패한다.

```bash
.venv/Scripts/python.exe -m pytest -q
```

```bash
npm --prefix apps/web test
```

```bash
npm --prefix apps/web run build
```

프론트엔드 타입 검사:

```bash
npm --prefix apps/web exec tsc -- --noEmit
```

### 로컬 실행

컨테이너 스택은 `scripts/owner-ready.ps1`로 조작한다. 직접 `docker compose`를 치지 않는다.

```powershell
.\scripts\owner-ready.ps1 -Mode Check
```

```powershell
.\scripts\owner-ready.ps1 -Mode Start
```

유진 기억 스택까지 켜려면 `-WithYujinMemory`를 붙인다. 이 스위치는 유진 프로필 설치를
포함한다 — 설치를 건너뛰면 컨테이너가 `Profile 'videobox-yujin' does not exist`로 죽는다.

```powershell
.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory
```

유진 비밀값이 자리표시자면 한 번만 생성한다. 값은 화면에 표시되지 않는다.

```powershell
.\scripts\new-hermes-yujin-secrets.ps1
```

- VideoBox: `http://127.0.0.1:5173/`
- Hermes 대시보드: `http://127.0.0.1:9119/`
- 개발 서버는 `.claude/launch.json`에 정의돼 있다 (web 5199, api 8000)
- `.env.container`는 gitignore 대상이다. 실제 credential을 커밋하지 않는다

### 검증 스크립트

`scripts/` 아래에 verifier가 다수 있다. 새 검증 흐름을 만들기 전에 기존 것을 먼저 찾는다.
예: `verify-editor-ui-system.ps1`, `verify_container_stack.ps1`,
`verify-editor-ui-source-provenance.ps1`, `verify-hermes-yujin-runtime.ps1`

### 유진 대화가 안 될 때

먼저 두 로그의 차단 사유부터 본다. 화면 문구는 어느 원인이든 똑같아서 구분이 안 된다.

```bash
docker logs --tail 50 65_videobox-videobox-agent-gateway-1
```

```bash
docker logs --tail 50 65_videobox-videobox-workspace-1
```

`hermes stream blocked: <사유>` 와 `hermes run blocked: <사유>` 를 찾는다.

### 데이터 폴더가 두 벌이다 — 먼저 알아야 할 함정

VideoBox는 두 가지로 뜰 수 있다. **2026-08-10부터 데이터 폴더는
`20_project\65_videobox-project` 하나다**(owner 지시). 예전에는
`65_videobox-container-data`, `-v2`, `65_videobox-project` 세 벌이었고, 어느 쪽으로
띄웠는지 모르면 "어제 만든 프로젝트가 사라졌다"로 보였다. 폴더는 합쳤지만
**저장소는 여전히 갈린다** — 아래 표를 볼 것.

**어느 쪽을 보고 있는지 확인하는 법:** 시작 로그 한 줄이 말해 준다.
`데이터베이스 저장소를 씁니다 (...)` 면 컨테이너(Postgres),
`파일 저장소를 씁니다 (...)` 면 로컬이다. 컨테이너 모드에서 주소가 없으면
이제 **뜨지 않는다** — 조용히 빈 파일 저장소를 여는 경로는 없앴다.

| 실행 | 주소 | 저장소 | 프로젝트 데이터 |
|---|---|---|---|
| 컨테이너 | `127.0.0.1:5173` | Postgres | `20_project\65_videobox-project\runtime\projects` |
| 로컬 | web `5199` / api `8000` | 파일 | `20_project\65_videobox-project\projects` |

2026-08-08 확인 결과 **양쪽 모두에 `b-roll-smoke-test`가 있었고 크기가 달랐다**
(92MB 대 123MB). 화면만 봐서는 구분할 수 없어 "어제 만든 프로젝트가 사라졌다"로
보이기 쉽다. **한쪽을 정해서 계속 쓴다.** 지금 owner의 실제 작업 데이터는 컨테이너 쪽이다.

어느 쪽을 보고 있는지는 `/health`가 알려준다.

```bash
curl -s http://127.0.0.1:5173/health
```

`store`(`postgres`/`local`)와 `projects_root`가 함께 나온다. 작업 전에 이걸 먼저 본다.

**어느 쪽인지 가르는 것은 `store`다.** 컨테이너로 뜨면 `projects_root`가
`/videobox-data`(컨테이너 안에서 본 경로)로 나오므로, 호스트의 실제 폴더는 위 표에서
읽는다. 로컬로 뜨면 호스트 경로가 그대로 나온다.

```
컨테이너: {"status":"ok","store":"postgres","projects_root":"/videobox-data"}
로컬:     {"status":"ok","store":"local","projects_root":"D:\\...\\65_videobox-project"}
```

**아직 정리되지 않은 것:** 두 폴더를 합칠지, 한쪽을 버릴지는 owner의 영상 데이터에
대한 결정이라 미뤄 두었다. `runtime\projects\projects\`처럼 한 겹 더 들어간 잔재도
남아 있다(2026-08-05자 `_intake_probe.mp4` 31MB). 코드에도 이력에도 이 이름이 없어
과거 수동 시험의 잔재로 보이지만, 확정하지 않았다.

### 10.16 `artifacts/` 정리 기준 (owner 승인, 2026-08-09)

CLAUDE.md §5에 있던 세부를 이리로 옮겼다(2026-08-16). 진입점은 짧게 유지한다.

무조건 보존이 아니라 **다시 만들 수 있는가**로 판단한다. 아래 둘 중 하나면 지워도 된다.

- 검증 스크립트가 매번 새로 쓰는 산출물(`--work-root` 결과 등)
- 지난 실행의 로그

아래는 남긴다. 다시 만드는 데 값이 들거나 아예 못 만드는 것들이다.

- 라이선스 증거 — 출처가 사라지면 복구할 수 없다
- 외부에서 받아 온 소스 캐시 — 다시 받으려면 네트워크가 필요하고 원본이 옮겨졌을 수 있다
- 테스트가 실제로 읽는 파일

지우기 전에 **경로로 참조되는 곳이 있는지 먼저 찾고**, 무엇을 왜 지웠는지 보고한다.
스크립트가 없으면 자동으로 다시 만드는 fixture는 지워도 되지만, 다시 만드는 시간이
길면 남기는 쪽을 택한다.

### 10.17 이음매마다 대조 장치를 하나 둔다 (2026-08-20)

한쪽을 고치면 다른 쪽이 막히는 사고는 **양쪽을 따로만 확인하고 이음매 자체는
아무도 재지 않아서** 생긴다. 2026-08-20 하루에 깨진 다섯 건이 전부 같은 모양이었다.

- **화면의 칸은 완성본의 픽셀을 바꿔야 한다.** 값을 바꿨을 때 출력이 달라지는지를
  **문자열로 재지 마라.** `배경 색`은 ASS 문자열을 분명히 바꾸면서도 화면에는 한
  픽셀도 닿지 않았다. 색·투명도는 ffmpeg로 구워서 픽셀로 잰다.
  → `tests/test_caption_style_fields_reach_the_render.py`
- **기본값이 가리키는 이름은 실제 목록에 있어야 한다.** 기본 글꼴 이름이 세 곳에
  따로 박혀 있었고 셋 다 목록 밖이었다.
  → `tests/test_caption_fonts.py`
- **저장소 스키마를 부수며 바꾸는 이관은 제품과 같은 방식으로 세운 DB에서 잰다.**
  `sqlite3.connect`로 새로 만든 시험용 DB에는 그 파일을 함께 쓰는 다른 저장소의
  표·트리거가 없다. 그 조건이 없으면 이관은 재지 않은 것이다. 부수는 DDL을 새로
  쓰면 `tests/test_schema_migrations_are_measured_on_a_product_shaped_database.py`의
  표에 재는 시험을 적어야 한다. **다만 그 표는 시험이 정말 옛 모양을 재현하는지는
  못 본다** — 저장소 클래스로 세우는지만 본다. 옛 모양을 재현했는지는 사람이 판단한다.

면제가 필요하면 **한 곳에 이름과 이유를 적고** 그것만 면제한다. 면제 목록이
길어지는 것 자체가 신호가 되게 한다.

### 10.18 이음매 가드 라우터와 훅 두 개 (2026-08-20)

**무엇을 고쳤나.** 이 저장소에는 이음매를 대조하는 좋은 장치가 이미 여러 개 있었다.
문제는 그것들이 **31분짜리 전체 pytest에서만 돌았다**는 것이다. 2026-08-20에 화면 파일
해시 갱신을 잊은 것을 31분 뒤에야 알았고, 그 사이 병합·푸시·배포까지 끝나 있었다.
그래서 **31분을 몇 초로 줄이는 배차 장치**를 붙였다. 새 검사를 만든 게 아니라,
이미 있던 검사를 제때 부르는 것이다.

**어디에 있나.**

| 것 | 경로 |
|---|---|
| 라우터 + 매핑 표 | `scripts/guard_router.py` |
| 표가 낡는 것을 잡는 테스트 | `tests/test_guard_router_table.py` |
| 훅 설정 | `.claude/settings.json` |

**훅 두 개가 하는 일.**

- **PostToolUse (`Edit`/`Write`)** — 방금 저장한 파일에 걸린 **빠른** 장치만 즉시 돌린다.
  통과하면 아무 말도 안 한다. 실패하면 그 자리에서 막고 실패 내용을 돌려준다.
  느린 장치는 여기서 절대 안 돈다. 편집마다 느려지면 사람이 훅을 꺼 버리기 때문이다.
- **Stop (턴 종료)** — 이번에 바뀐 파일 전체(작업 트리 + base 이후 커밋)를 훑어
  **느린 장치까지** 한 번 돌린다. 2026-08-20에 놓친 자리가 정확히 여기다.

빠름/느림은 의견이 아니라 **실측 초**로 가른다(`FAST_LIMIT_SECONDS = 10초`).
표의 `seconds`는 짐작해서 채우지 않는다. 테스트를 추가하거나 무거워졌으면 다시 재서 고친다.

**표 보기.**

```bash
.venv/Scripts/python.exe scripts/guard_router.py --list
.venv/Scripts/python.exe scripts/guard_router.py --files apps/web/src/app/ProductShell.tsx
.venv/Scripts/python.exe scripts/guard_router.py --changed --speed all
```

**훅이 못 하는 것 — 이 선을 넘지 않는다.**

훅은 **"화면에서 실제로 밟아 봤는가"를 판단하지 못한다.** 2026-08-20의 라이브러리 전면
차단(모든 자산 추가 500)과 자막 배경색 죽음은 **화면에서 써 봐야만** 나왔다. 그래서
Stop 훅은 "화면에 닿는 파일을 고쳤다"는 **사실만** 알려 주고 거기서 멈춘다. 그 이상을
검사하는 척하면 초록불이 또 한 번 거짓말이 된다.

**거짓 실패도 만들지 않는다.** 상태가 셋이다.

- `통과` — 실제로 돌아서 초록불이었다
- `실패` — 실제로 돌아서 깨졌다
- `안 돌아감` — 못 돌렸다. venv가 없거나, 시간 안에 안 끝났거나, 표가 없는 테스트를
  가리켰다. **이것을 `통과`로도 `실패`로도 바꾸지 않는다.**

검증용 인터프리터는 `<repo>/.venv`만 쓴다. 시스템 Python으로 슬쩍 넘어가지 않는다(§10.3.6).
없으면 "돌리지 못했다"고 말한다. 다른 venv를 쓰려면 `VIDEOBOX_GUARD_PYTHON`으로 지정한다.

**주의 — 에이전트 worktree에는 `.venv`가 없다.** 그러면 라우터는 `안 돌아감`을 보고하고,
`scripts/start-hermes-yujin.ps1`처럼 `<repo>/.venv`를 직접 찾는 스크립트의 테스트도
환경 때문에 빨간불이 된다. **그 빨간불을 코드 결함으로 오진하지 마라.**

**표가 낡지 않게 하는 장치.** `tests/test_guard_router_table.py`가 매번 확인한다.
표가 가리키는 테스트 파일이 실제로 있는지, 패턴이 실제 파일을 가리키는지,
`docs/oss/editor-ui-source-map.json`에 핀된 반입 파일이 **전부** provenance 가드로
배차되는지, 그리고 `.claude/settings.json`의 훅이 harness가 읽는 모양 그대로인지.
마지막 항목이 중요하다 — 훅 형식이 틀리면 조용히 아무 일도 안 하고, 그게 최악이다.
