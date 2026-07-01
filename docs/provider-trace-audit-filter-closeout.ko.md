# Provider Trace Audit Filter Closeout

> Historical closeout note: 이 문서는 `provider trace audit filter` 작업 종료 시점의 검증 기록이다. 현재 authoritative 상태/next slice 판단은 `docs/session-context-2026-07-01-system-hygiene.ko.md`, `docs/development-status-2026-06-29.ko.md`의 `## 17`, `docs/implementation-plan.ko.md`의 2026-07-01 체크포인트를 우선 적용한다.

## 1. 이번 작업에서 완료한 것

- `/api/projects/{project_id}/provider-traces`에 `timeline_id`, `job_type`, `artifact_type`, `final_provider`, `fallback_reason` 필터를 추가했다.
- API -> orchestration -> store까지 필터 전달 경로를 연결했다.
- 기본 무필터 응답과 summary 동작은 유지했다.
- 실패한 `preview_render` 감사 기록도 `source_job_id -> timeline_id` 역매핑으로 같은 타임라인 필터에 잡히게 보강했다.
- 빈 문자열 또는 공백 쿼리는 필터 없음으로 정규화했다.
- legacy/backfill 및 기존 provider trace generation/persistence 동작은 바꾸지 않았다.

## 2. 검증 결과

- provider trace endpoint 관련 회귀:
  `pytest tests/test_api.py -k "provider_trace_audit_endpoint" -q`
  - 결과: `19 passed`
- backend 전체 회귀:
  `pytest tests -q`
  - 결과: `116 passed`

검증 기준일:

- 2026-06-29

## 3. 이번 작업에서 추가한 테스트 포인트

- 성공 경로에서 `timeline_id`, `job_type`, `artifact_type` 필터 동작
- 성공/폴백 경로에서 `final_provider`, `fallback_reason` 필터 동작
- 실패한 `preview_render`가 같은 `timeline_id` 필터 조회에 포함되는지 확인
- 빈 문자열/공백 필터가 무필터처럼 동작하는지 확인

## 4. 현재 의미 범위

- 현재 `timeline_id` 필터는 직접 타임라인에 연결된 감사 엔트리와, 같은 타임라인으로 역매핑 가능한 실패 output 엔트리까지 포함한다.
- 아직 timeline provenance 전체 역추적까지는 하지 않는다.
- 즉 `segment_analysis`, `broll_recommendation`, `music_recommendation`를 자동으로 timeline investigation에 확장 포함하지는 않는다.

## 5. 커밋 정보

- 기능 커밋:
  `e5e96df Add provider trace audit filters`

## 6. 다음 추천 작업

- timeline provenance expansion을 추가해서 특정 timeline 조사 시 upstream `segment_analysis`, `broll_recommendation`, `music_recommendation`까지 함께 추적되게 확장
