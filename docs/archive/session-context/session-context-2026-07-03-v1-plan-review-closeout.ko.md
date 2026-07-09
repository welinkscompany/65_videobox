# VideoBox 세션 컨텍스트

작성일:

- 2026-07-03

주제:

- 2일 내 1차 데모 완성 계획서 전문가 검토 및 재정렬

## 1. 이번 turn에서 실제로 끝낸 것

- `docs/superpowers/plans/2026-07-03-v1-two-day-completion-and-upgrade-plan.ko.md`를 새로 만들고, 그 뒤 전문가 서브에이전트 3종 의견과 로컬 코드/테스트 상태를 반영해 다시 좁혔다
- 계획서를 `기능 확장형`에서 `demo-critical path 중심`으로 재정렬했다
- `implementation-plan.ko.md`의 `## 13. 다음 실제 작업` 아래에, 2026-07-03 기준 2일 데모 실행 레일은 별도 plan 문서를 따른다는 연결 규칙을 추가했다

## 2. 이번 turn에서 확인한 핵심 판단

- 현재 2일 목표에서 기본 실행 범위로 유지해야 하는 것은 아래 3개뿐이다
  1. approved TTS persisted truth gap 1개 확인
  2. 실제 프로젝트 1개 happy-path smoke
  3. evidence / closeout / SSOT freeze
- 아래 항목은 기본 범위에서 내리는 것이 더 효율적이다
  - reopen 후 residual blocker 추가 경계
  - preflight stale-shape 신규 normalization
  - thin operator UI 새 gating 규칙
- 이유는 아래와 같다
  - 이미 유사 회귀가 많다
  - `local_pipeline.py` 변경 반경이 크다
  - 2일 데모 설득력에는 직접 기여가 작다

## 3. 서브에이전트 의견 요약

- architecture / risk
  - `Task 1`은 유지하되 더 작은 persisted-truth 검증부터 시작하는 것이 맞다
  - 기존 계획의 `Task 2~4`는 기본 실행 범위에서 빼는 편이 낫다
  - `local_pipeline.py`를 넓게 건드리는 것은 2일 플랜에서 가장 큰 리스크다
- TDD / verification
  - 기존 `test_approved_tts_replacement_flows_through_preview_and_export_outputs`와 export adapter 테스트가 이미 강한 기반이다
  - 새 failing test는 더 작은 원인 분리형 RED여야 한다
  - 검증 순서는 `exact -> lane -> current-focused-parallel -> 마지막 broader 1회`로 줄이는 것이 효율적이다
- product / demo realism
  - 데모에서 꼭 보여줘야 하는 것은 `project -> timeline -> review snapshot -> editing session -> preflight -> rerun -> approve -> subtitle/preview/export` 한 줄 흐름이다
  - reopen flow, provider trace 세부 설명, broader 수치 그 자체는 보조 요소다

## 4. 계획서 반영 결과

- 기본 태스크는 2개로 재구성했다
  1. approved TTS persisted truth gap 검증
  2. 실제 프로젝트 1개 smoke + evidence freeze
- 조건부 backlog를 따로 분리했다
  - reopen residual blocker
  - new preflight normalization gap
  - extra operator UI gating
- 조건부 backlog는 exact failing test 1개가 실제 gap을 재현할 때만 다시 올린다

## 5. 이번 turn에서 의도적으로 안 한 것

- 실제 코드 구현
- 테스트 재실행
- broader verification
- 커밋 / 푸시

이번 turn은 `구현 전 계획 정렬과 기록 저장`에만 집중했다.

## 6. 다음 세션 첫 시작점

1. 새 계획서 기준 `Task 1`만 시작한다
2. exact failing test 1개는 `approve 후 persisted timeline narration clip asset_uri가 실제로 바뀌는지`부터 잡는다
3. 그 test가 green이 된 뒤에만 `output job이 persisted timeline truth를 소비하는지` 두 번째 exact test를 붙인다
4. 그 다음 `./scripts/dev-fast-path.ps1 -Mode output-gating`
5. 그 뒤 `current-focused-parallel`
6. 실제 프로젝트 1개 smoke는 마지막에만 돌린다

## 7. 다음 세션 시작 프롬프트

```text
D:\AI_Workspace_louis_office_50\10_workspace\65_videobox repo에서 이어서 작업해.
브랜치는 codex/tts-approved-runtime 기준으로 진행.

먼저 아래 문서를 읽고 현재 SSOT와 최신 계획서를 맞춰라.
- docs/implementation-plan.ko.md
- docs/development-status-2026-06-29.ko.md
- docs/development-fast-path.ko.md
- docs/superpowers/plans/2026-07-03-v1-two-day-completion-and-upgrade-plan.ko.md
- docs/session-context-2026-07-03-v1-plan-review-closeout.ko.md

시작 직후 아래를 확인해라.
- git status --short --branch
- git log -4 --oneline

이번 세션 목표:
1. 계획서 Task 1만 구현해라.
2. exact failing test 1개로만 RED를 시작해라.
3. 첫 RED는 `approve 후 persisted timeline narration clip asset_uri가 실제로 바뀌는지`로 잡아라.
4. 그 test green 뒤에만 output job consumer proof exact test 1개를 추가해라.
5. focused verification 후에만 current-focused-parallel을 돌리고, broader는 아직 돌리지 말아도 된다.
6. editing-session SSOT, review/output rules, Gemini fallback, provider trace audit, persistence behavior를 깨뜨리지 마라.
7. unrelated 파일/구조는 건드리지 말고 apply_patch만 사용해라.

출력 형식:
- completed
- pending
- next slice
- verification
- risks
```

## 8. closeout judgment

- session progress 저장: 완료
- SSOT 업데이트: 완료
  - `docs/implementation-plan.ko.md`
  - `docs/superpowers/plans/2026-07-03-v1-two-day-completion-and-upgrade-plan.ko.md`
- AK-Wiki promotion judgment: 보류
