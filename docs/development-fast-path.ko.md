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
이 문서에 적힌 규정은 이후 turn에서도 별도 재지시가 없는 한 계속 따른다.

1. TDD는 기본 규칙으로 유지한다.
   - 다만 실제 코드/동작이 바뀌지 않는 문서 정리, 상태 정리, closeout-only 작업에는 기계적으로 적용하지 않는다.
2. 서브에이전트 드리븐은 항상 쓰지 않고, 메인 에이전트 대비 실제 효율이나 최적화 이득이 명확할 때만 최소 범위 explorer로 사용한다.
3. code review, gap 검증, 역방향 동작 검증도 고정 의무가 아니라, 실제 리스크를 줄이는 데 효과적일 때만 선택적으로 수행한다.
4. turn 종료 시에는 가능한 한 커밋을 기본으로 하고, push는 브랜치 상태와 검증 상태를 보고 최적일 때만 진행한다.
5. 추천 작업이나 구현 slice가 끝나면 항상 계획서 기준으로 벗어나지 않았는지 점검하고, 다음 goal 프롬프트를 함께 남긴다.
6. 작업 설명은 항상 요약해서 쉬운 말로 설명한다.
7. 계획서 기준 전체 진행률과 남은 비율은 매 closeout 때 추정치임을 밝히고 함께 보고한다.
8. 구현 slice를 추천하거나 수행한 뒤에는 아래 closeout 순서를 기본으로 유지한다.
   - 계획서 기준으로 이번 slice가 맞게 진행됐는지 점검한다.
   - 완료/미완료/다음 slice/검증/리스크를 짧게 정리한다.
   - 다음 turn에서 바로 붙일 수 있는 goal 프롬프트를 남긴다.
   - 전체 계획서 기준 진행률과 남은 비율을 추정치로 함께 적는다.
