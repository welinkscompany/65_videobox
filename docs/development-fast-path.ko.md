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

저장소 루트에서 아래 스크립트를 사용한다.

```powershell
./scripts/review-action-fast-path.ps1 -Mode backend-focused
./scripts/review-action-fast-path.ps1 -Mode frontend-focused
./scripts/review-action-fast-path.ps1 -Mode broader
./scripts/review-action-fast-path.ps1 -Mode all
./scripts/review-action-fast-path.ps1 -Mode status
```

의미:

- `backend-focused`
  - review action slice 관련 backend focused pytest만 실행
- `frontend-focused`
  - review shell 관련 frontend focused test만 실행
- `broader`
  - frontend build + full backend regression 실행
- `all`
  - focused -> broader를 한 번에 실행
- `status`
  - 현재 focused pattern과 추천 실행 루프를 출력

패턴 override 예시:

```powershell
./scripts/review-action-fast-path.ps1 -Mode backend-focused -BackendPattern "reject_pending_recommendation"
./scripts/review-action-fast-path.ps1 -Mode frontend-focused -FrontendPattern "marked for manual edit"
```

## 3. 지금 repo에서 빠르게 가는 추천 루프

1. plan과 현재 변경 상태를 먼저 맞춘다
2. failing test 1개만 추가한다
3. `backend-focused` 또는 `frontend-focused`만 돌려 fail을 확인한다
4. minimal implementation만 넣는다
5. 같은 focused gate를 다시 돌린다
6. slice가 닫히면 마지막에만 `broader`를 돌린다

추가 운영 규칙:

- `backend-focused`는 현재 approve/reject timeline-local hardening 관련 backend 회귀 5개를 기본으로 묶는다
- `frontend-focused`는 전체 `app.test.tsx`가 아니라 review-action 관련 focused test 2개만 기본으로 돌린다
- 새 slice에서 정확히 1개 테스트만 보고 싶으면 script override를 써서 범위를 더 줄인다
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
- 현재 브랜치에서 반복되는 검증은 스크립트로 통일

## 6. 이 문서를 언제 쓰는가

- review action family
- editing session persistence
- output gating
- TTS/output propagation 같이 상태 계약이 민감한 작업

## 7. 지금 브랜치에 바로 적용할 실행 레일

반복 속도를 올리기 위해 현재 브랜치에서는 아래 순서를 기본값으로 고정한다.

1. `./scripts/review-action-fast-path.ps1 -Mode status`로 현재 gate와 pattern을 먼저 확인한다
2. 다음 최소 slice에 대해 failing test 1개만 추가한다
3. 필요한 경우 override pattern으로 RED를 확인한다
4. minimal GREEN만 넣고 같은 override/focused gate를 다시 돌린다
5. slice가 닫히면 기본 focused gate 전체를 다시 돌린다
6. task 단위가 닫히면 `broader`를 돌린다
7. 그 뒤에만 spec review -> code-quality review를 붙인다

이 순서의 의도:

- 구현 전에 계획/리스크를 다시 길게 재정리하는 시간을 줄인다
- 전체 test file 실행 대신 review-action 관련 초점 테스트만 먼저 본다
- reviewer는 slice green 이후에만 붙여서, RED 단계에서의 왕복 비용을 줄인다

## 8. 다음 Subagent-Driven goal 프롬프트 위치

다음 review-action slice용 바로 붙여넣기 프롬프트는 아래 문서에 고정한다.

- `docs/superpowers/goals/review-action-next-slice-subagent-prompt.ko.md`
