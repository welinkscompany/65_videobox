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
  - frontend: `npm test -- --run src/app.test.tsx -t "<exact test name>"`
- lane close가 필요하면 script override를 써서 helper 범위를 더 줄인다
- current status 문서에 `frontend src/app.test.tsx 전체`를 주장할 때는 helper gate와 별도로 `npm test -- --run src/app.test.tsx`를 다시 실행한다
- broader는 slice close 직전까지만 미룬다. 다만 focused 없이 broader부터 돌리지는 않는다

속도 우선 기본값:

1. RED/GREEN 단계에서는 exact test만 돌린다
2. lane close에서는 해당 lane helper만 돌린다
3. slice close에서는 `current-focused` 대신 `current-focused-parallel`을 먼저 쓴다
4. 문서 수정은 focused green 이후로 미룬다
5. `frontend src/app.test.tsx` 전체 재실행은 상태 문서 갱신이나 task close가 필요할 때만 돌린다

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
7. 현재 상태 문서에 frontend 전체 수치를 남길 필요가 있으면 `npm test -- --run src/app.test.tsx`를 별도로 돌린다
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
이 문서에 적힌 규정은 저장소 루트 `AGENTS.md`와 함께 이후 turn에서도 별도 재지시가 없는 한 계속 따른다.
사용자가 turn 중에 추가로 확정한 운영 선호도도 이 섹션에 흡수해 SSOT로 유지한다.

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

### 10.8 진행률 보고 규정

1. 턴 종료 시 진행률은 이번 턴 기준이 아니라 전체 공식 계획서 기준 누적으로 계산한다.
2. 여러 계획서가 동시에 있으면 각 계획서의 공식 Task 수 또는 명시된 완료 단위를 기준으로 전체 모수와 완료 수를 계산한다.
3. 비공식 조사, 메모, 연결 점검, 아이디어 정리, 사전 분석은 공식 Task 완료율에 포함하지 않고 준비 작업으로 별도 표시한다.
4. 항상 전체 공식 계획서 기준 진행률과 남은 비율을 함께 적는다.
5. 진행률 계산 기준도 짧게 설명한다.

### 10.9 턴 종료 보고 형식

1. 턴이 끝날 때마다 아래 내용을 반드시 포함한다.
   - 이번 턴에서 실제로 한 작업을 쉬운 말로 짧게 요약
   - 계획서 기준으로 이번 턴이 어느 범위를 진행했는지
   - 전체 공식 계획서 기준 누적 진행률
   - 전체 공식 계획서 기준 남은 비율
   - 진행률 계산 기준
   - 수행한 핵심 검증
   - 커밋과 푸시 여부
   - 다음 추천 Goal 프롬프트
2. 추천만 한 turn이어도 같은 closeout 형식을 적용한다.
3. 필요하면 `completed / pending / next slice / verification / risks` 형식을 쓰되, 위 필수 항목이 빠지지 않게 유지한다.

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
