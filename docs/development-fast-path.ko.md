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
3. 해당 slice에 맞는 `output-gating`, `preflight-backend`, `preflight-frontend`만 돌려 fail을 확인한다
4. minimal implementation만 넣는다
5. 같은 focused gate를 다시 돌린다
6. slice가 닫히면 `current-focused`로 인접 경계까지 다시 확인한다
7. task 단위가 닫히면 마지막에만 `broader`를 돌린다

추가 운영 규칙:

- `output-gating`은 subtitle/preview/export의 blocker/approval 경계를 기본으로 묶는다
- `preflight-backend`는 targeted-segment normalization, duplicate normalization, unsupported scope rejection, blocked/draft prediction 경계를 기본으로 묶는다
- `preflight-frontend`는 blocked-warning surface, resumed preflight degraded warning, resumed mismatch non-reuse, resumed scope cleanup 경계를 기본으로 묶는다
- 새 slice에서 정확히 1개 테스트만 보고 싶으면 script override를 써서 범위를 더 줄인다
- current status 문서에 `frontend src/app.test.tsx 전체`를 주장할 때는 helper gate와 별도로 `npm test -- --run src/app.test.tsx`를 다시 실행한다
- broader는 slice close 직전까지만 미룬다. 다만 focused 없이 broader부터 돌리지는 않는다

## 4. review-action 변경 시 꼭 보는 함정

- recommendation state가 `project-wide row`인지 `timeline-local artifact`인지 섞이지 않는지 확인
- blocker clear가 `recommendation_id` 단위가 아니라 너무 넓게 지워지지 않는지 확인
- DB update와 timeline artifact update가 서로 모순 상태를 남기지 않는지 확인
- 새 상태 필드가 생기면 fallback normalization이 이전 의미를 깨지 않는지 확인

## 5. 추천 운영 방식

- 작은 slice는 `Subagent-Driven`으로 구현
- spec review와 code-quality review를 분리
- reviewer가 찾은 리스크는 다음 slice 전에 먼저 반영
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
3. 필요한 경우 override pattern으로 RED를 확인한다
4. minimal GREEN만 넣고 같은 override/focused gate를 다시 돌린다
5. slice가 닫히면 `current-focused`를 다시 돌린다
6. 현재 상태 문서에 frontend 전체 수치를 남길 필요가 있으면 `npm test -- --run src/app.test.tsx`를 별도로 돌린다
7. task 단위가 닫히면 `broader`를 돌린다
8. 그 뒤에만 spec review -> code-quality review를 붙인다

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
