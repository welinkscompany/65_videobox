# VideoBox 개발 상태 점검 2026-06-29

## 1. 결론

현재 개발은 계획서에서 크게 새지 않았다.
그리고 `경량 후편집기 UI`가 아니라 `편집 세션 기반`으로 먼저 가야 한다는 방향도 실제 코드로 반영됐다.

현재까지 반영된 핵심은 아래다.

- `editing session` 모델
- 수정 저장 구조
- 수정 API
- 부분 재생성 규칙

## 2. 확인된 사실

현재 기준 아래는 코드와 테스트로 확인됐다.

- 로컬 프로젝트/자산/job 저장 구조 존재
- segment analysis 파이프라인 존재
- transcript alignment 존재
- B-roll 추천과 음악 추천 존재
- timeline 생성과 review approval 존재
- subtitle render, preview render, CapCut export 존재
- Local Qwen 우선 + Gemini fallback runtime 존재
- editing session 생성/조회 존재
- caption / cut / B-roll / visual overlay / music override 수정 API 존재
- partial regeneration request contract와 validation 존재
- 전체 테스트 `194 passed`

## 3. 아직 부족한 부분

아래는 다음 단계 전에 필요한 핵심 빈칸이다.

- partial regeneration을 실제 재실행 job으로 연결하는 단계
- 설명 카드/이미지/표 수정 규칙을 지금보다 더 세분화하는 단계
- TTS 대체를 추천에서 실제 편집 선택으로 넘기는 연결이 없다
- 편집 세션 수정 결과를 timeline 재작성 또는 후속 생성 단계와 연결하는 규칙이 아직 최소 수준이다

## 4. 왜 지금 UI부터 가면 안 되는가

UI부터 만들면 아래 문제가 바로 생긴다.

- 수정 결과를 어디에 저장할지 기준이 없다
- 부분 재생성을 어디까지 다시 돌릴지 합의가 없다
- 자막 수정, 컷 수정, B-roll 교체가 서로 다른 임시 구조로 흩어질 가능성이 크다
- 나중에 오픈소스 편집기 셸을 붙일 때 다시 뜯어고치게 된다

그래서 순서는 `편집 규칙 고정 -> 얇은 UI 검증 -> 필요 시 OSS 셸 반입`이 맞다.

## 5. 다음 구현 범위 고정

다음 goal은 아래 범위로 묶는 것이 맞다.

1. partial regeneration request를 실제 job 실행으로 연결
2. 편집 세션 수정 결과를 timeline 반영 규칙과 연결
3. 설명 자산 수정 범위를 더 세분화
4. TTS 대체 선택을 편집 세션 mutation으로 연결
5. 해당 범위 TDD 완료

## 6. 이번 단계에서 의도적으로 안 하는 것

- 풀 편집기 UI
- 오픈소스 편집기 통째 반입
- 고급 오디오 믹싱
- 색보정
- 자유 키프레임
- 프리미어급 멀티트랙 편집 기능

## 7. 구현 시작 조건

현재 브랜치/워킹트리 기준으로 바로 다음 goal 구현 시작 가능하다.
테스트 베이스라인은 안정적이고, 계획서 기준 다음 빈칸도 명확하다.

## 8. 2026-06-29 추가 검증 기록

이번 재검증에서 아래를 다시 확인했다.

- 전체 백엔드 회귀 테스트 `194 passed`
- blank caption 거부 동작 정상
- invalid partial regeneration request 거부 동작 정상
- unknown session segment / unsupported field 거부 동작 정상
- `editing_sessions` 저장/조회와 기존 프로젝트 self-heal 동작 유지

이번 재검증 기준 신규 치명 버그는 다시 확인되지 않았다.
다만 다음 구현 전 반드시 채워야 할 빈칸은 여전히 아래다.

- partial regeneration 실제 job 실행 연결
- editing session 수정 결과의 timeline 반영 규칙
- 설명 자산 수정 범위 세분화
- TTS 대체의 editing session mutation 연결
