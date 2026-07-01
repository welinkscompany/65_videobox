# VideoBox 세션 컨텍스트

> Historical note: 이 문서는 `경량 후편집기 범위 확정` 당시의 중간 저장 기록이다. 현재 authoritative 제품 방향과 next slice 판단은 최신 SSOT 문서를 우선 적용한다: `docs/session-context-2026-07-01-system-hygiene.ko.md`, `docs/development-status-2026-06-29.ko.md`의 `## 17`, `docs/implementation-plan.ko.md`의 2026-07-01 체크포인트.

작성일:

- 2026-06-29

주제:

- 경량 후편집기 범위 확정
- 오픈소스 편집기 반입 시점 계획 반영

## 1. 이번 세션에서 확정한 것

- VideoBox는 `자동 초안 생성기 + 설명형 영상용 경량 후편집기` 방향으로 범위를 올린다.
- 기존 문서의 `얇은 review UI` 표현은 이제 부족하다고 보고, `경량 후편집기`로 바꾼다.
- CapCut은 여전히 export/handoff 대상이지만, 최종 수정이 반드시 CapCut에서만 일어나야 하는 구조로 보지 않는다.

## 2. 경량 후편집기 범위

포함:

- 컷 유지/삭제
- 컷 경계 미세 조정
- 세그먼트 병합/분리
- 자막 텍스트 수정
- 자막 타이밍 미세 조정
- B-roll 교체
- 배경 영상/이미지 교체
- 설명 카드/이미지/표 삽입
- 음악 선택/제거/교체
- 효과음 추천 선택/제거
- review flag 확인/해제
- 원본/자동/수정 비교
- 수정 이력 저장
- 부분 재생성

제외:

- 프리미어급 풀 편집기
- 고급 모션그래픽 편집
- 복잡한 오디오 믹싱 콘솔
- 색보정 툴 전체
- 자유곡선 키프레임 시스템

## 3. 오픈소스 편집기 반입 판단

현재 판단:

- 오픈소스 편집기는 `지금 바로 통째 반입`하지 않는다.
- 먼저 편집 도메인 모델과 수정 API를 고정해야 한다.
- 그 다음 얇은 자체 검수 UI로 실제 수정 흐름을 검증한다.
- 그 다음 `OpenReel Video` 같은 편집기 셸을 `partial port` 방식으로 검토한다.

참고 후보:

- `Augani/openreel-video`: `partial port` 후보
- `aqm857886159/Nomi`: `reference only`
- `chatman-media/timeline-studio`: `reference only`
- `palmier-io/palmier-pro`: `reference only`

## 4. 이번에 수정한 문서

- `docs/implementation-plan.ko.md`
- `docs/product-plan.ko.md`
- `docs/oss-adoption-map.ko.md`
- `docs/development-context.ko.md`

## 5. 다음 추천 작업

업데이트된 계획서 기준으로 다음 작업은 아래가 맞다.

1. 경량 후편집기 편집 도메인 모델 고정
2. 수정 API와 부분 재생성 규칙 고정
3. 원본/자동/수정 비교 및 수정 이력 저장 구조 정의
4. 그 다음 얇은 자체 검수 UI
5. 그 다음 오픈소스 편집기 셸 선별 반입 검토

## 6. 바로 이어서 쓸 Goal 요약

- `editing session` 데이터 모델, 수정 API, 부분 재생성 규칙을 먼저 설계하고 구현할 것
