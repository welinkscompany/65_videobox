# VideoBox 마감 안정화 및 최종 정리 계획

작성일:

- 2026-07-05

목적:

- 현재 브랜치의 남은 작은 안정화 slice와
- 프로젝트 마감 직전의 전체 검증/QA/정리 작업을
- 서로 섞지 않고 순서대로 끝내기 위한 실행 계획을 고정한다.

## 1. 현재 판단

현재 브랜치는 `대형 신규 기능 개발` 단계가 아니다.
핵심 기능 연결은 이미 닫혀 있고, 지금 남은 일은 크게 두 묶음이다.

1. `review/output gating`, `TTS approval/output`, `preflight contract` 주변의 작은 stale-shape 경계 안정화
2. 그 안정화가 충분히 닫힌 뒤 수행할 전체 마감 검증과 정리

즉, 지금 해야 할 일은 무작정 전체 QA부터 시작하는 것이 아니라:

1. 먼저 작은 경계 버그를 더 줄이고
2. 그 다음 전체 검증과 정리로 넘어가는 것이다.

## 2. 작업을 두 페이즈로 나누는 이유

작은 stale-shape 경계가 남아 있으면 아래 작업이 계속 흔들린다.

- end-to-end 동작 검증
- QA 결과
- 문서 최신화
- 정리 리팩터링
- 찌꺼기 파일 정리

반대로 작은 경계를 먼저 더 닫아두면:

- 전체 검증이 덜 흔들리고
- QA 결과가 더 오래 유지되며
- 문서와 코드 정리를 한 번에 끝내기 쉬워진다.

## 3. 페이즈 A: 남은 안정화 slice 정리

목표:

- 가장 가까운 exact regression 1개씩만 골라
- `RED -> minimal GREEN -> focused verification`으로 닫는다.

우선순위:

1. `review/output gating`
2. `TTS approval/output`
3. `preflight contract`

작업 규칙:

1. 한 번에 exact regression 1개만 고른다.
2. RED는 exact test 1개로만 확인한다.
3. minimal GREEN만 넣는다.
4. focused verification만 먼저 돌린다.
5. broader verification은 이 페이즈의 실제 종료 직전까지 미룬다.

이번 페이즈에서 주로 볼 면:

- review guidance prompt
- output operator copy prompt
- preview renderer
- subtitle render
- CapCut export
- review approval / decision extraction consumer
- output readiness / gating read path

페이즈 A 종료 조건:

- 위 우선순위 1~3에서 새 exact regression을 골랐을 때
- 더 이상 바로 인접한 작은 stale-shape 경계가 쉽게 나오지 않거나
- 나와도 broader/QA 페이즈를 막을 수준이 아닌 상태라고 설명 가능해야 한다.

## 4. 페이즈 B: 전체 동작 검증과 마감

페이즈 A가 충분히 닫히면 아래 순서로 넘어간다.

### 4.1 자동 검증

반드시 수행:

- `./scripts/dev-fast-path.ps1 -Mode current-focused-parallel`
- `./scripts/dev-fast-path.ps1 -Mode broader`

상황에 따라 추가:

- `npm test -- --run src/app.test.tsx`
- provider trace audit focused slice
- happy-path smoke 시나리오 관련 기존 verifier / test

검증 목표:

- backend output gating
- backend preflight
- frontend preflight
- full backend regression
- frontend build

### 4.2 전체 동작 검증

확인할 핵심 흐름:

1. review snapshot -> editing session handoff
2. preflight -> rerun -> candidate restore
3. approve / reject / manual edit
4. approved timeline -> subtitle / preview / export
5. TTS replacement approval -> preview / export 반영

이 단계에서는 `작동함`이 아니라 아래를 본다.

- 실제로 끝까지 이어지는지
- 중간 상태 표시가 헷갈리지 않는지
- stale persisted shape가 다시 끼어들지 않는지

### 4.3 QA

수동 QA 체크:

1. 버튼 enable/disable 상태
2. blocked / approved / draft 상태 문구
3. 에러 메시지와 degraded warning
4. multi-step 복귀 흐름
5. operator-facing guidance 문구의 오해 가능성

### 4.4 시스템 검증

확인 항목:

1. persistence truth
2. provider trace audit
3. Gemini fallback / heuristic fallback
4. output gating read truth
5. editing session SSOT와 returned response surface 일치

## 5. 페이즈 C: 문서 최신화와 정리

페이즈 B까지 통과한 뒤 수행한다.

### 5.1 문서 최신화

반드시 맞출 문서:

- `docs/implementation-plan.ko.md`
- `docs/development-status-2026-06-29.ko.md`
- 필요한 최신 closeout 문서

정리 원칙:

- 실제 현재 동작과 맞지 않는 오래된 서술 제거 또는 historical 위치 명시
- next slice가 아니라 final closeout 단계라면 그에 맞게 상태 문구 갱신

### 5.2 코드 정리 리팩터링

우선 대상:

- review/output prompt 쪽 중복 normalization 규칙
- stale-shape filtering helper 중복
- 테스트 fixture 중 과도하게 퍼진 중복 shape

주의:

- 이 단계는 `동작 안정화 이후`에만 한다.
- 리팩터링 때문에 새 리스크를 만들면 안 된다.

### 5.3 찌꺼기 파일 정리

정리 후보:

- 임시 실험 파일
- 더 이상 쓰지 않는 dead helper
- 역할이 끝난 중복 메모 문서

주의:

- closeout 기록 자체는 함부로 지우지 않는다.
- historical 가치가 있는 문서는 삭제보다 위치/역할 명시를 우선한다.

## 6. 실제 실행 순서

다음 턴부터는 아래 순서로 실행한다.

1. 상태/SSOT 확인
2. exact regression 1개 선택
3. RED
4. minimal GREEN
5. focused verification
6. closeout / commit
7. 1~6 반복
8. 페이즈 A 종료 판단
9. current-focused-parallel
10. broader
11. 전체 동작 검증
12. QA
13. 시스템 검증
14. 문서 최신화
15. 정리 리팩터링
16. 찌꺼기 파일 정리
17. 최종 closeout / final commit / push

## 7. 지금 시점의 추천

현재 추천은 아래다.

1. 자동 baseline green과 representative Phase B evidence가 이미 확보됐는지 먼저 기준 문서와 상태 로그에서 재확인한다.
2. 새 exact regression을 억지로 더 열지 말고, `Phase C`의 문서 최신화와 현재 상태 문구 정리를 먼저 닫는다.
3. 그 다음 실제 중복이 확인된 작은 리팩터링 후보와 찌꺼기 파일 후보를 안전 범위에서만 선별한다.
4. 마지막 closeout 직전에만 broad 재검증이 다시 필요한지 판단한다.

쉽게 말하면:

- 지금은 `문서 최신화와 마감 정리`
- 그다음은 `필요 최소한의 정리와 최종 검수`

## 8. 이번 문서의 역할

이 문서는 다음 턴부터의 `정리 마감 작업 기준 계획`이다.
즉:

- 지금 무엇을 먼저 해야 하는지
- 전체 QA와 마감 정리는 언제 들어가야 하는지
- 어떤 순서로 닫아야 하는지

를 다시 설명하지 않고 이 문서를 기준으로 바로 실행한다.
