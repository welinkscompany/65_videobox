---
paths:
  - "apps/**"
  - "services/**"
  - "packages/**"
  - "scripts/**"
  - "tests/**"
  - "docker/**"
  - "config/**"
---
# 재사용 게이트와 기본 구현 루프 (CLAUDE.md §3)

CLAUDE.md §3 에서 2026-10-09 W1428 에 원문 그대로 옮겼다. CLAUDE.md 에는 §3 안내 줄이 남아 있다. 구현 파일을 다룰 때 자동으로 읽힌다.

### 재사용 게이트 (모든 구현 goal에 적용)

`docs/implementation-plan.ko.md` §8.1이 정한 상위 규칙이다. 시작 **전에** 판단한다:
이미 있는 내부 소스·외부 OSS가 있는가, `adopt as-is`/`partial port`/`rewrite`/`exclude`
중 무엇인가, 실제 반영 단위는 무엇인가, 제외 후보와 그 이유는 무엇인가.

기준은 소스 복제보다 경계 유지, 통째 복사보다 선별 이식이다.
`UI 구조`, `Google Sheets/Drive 결합`, `provider 직접 호출 하드코딩`은 반입 금지다.

### 기본 구현 루프

`plan reconcile → RED → minimal GREEN → focused verification → broader verification`

- 새 UI를 만들기 전에 기존 흐름을 재사용할 수 있는지 먼저 본다.
- RED/GREEN 단계에서는 정확히 테스트 1개만 돌린다. broader는 Task가 닫힐 때만.
