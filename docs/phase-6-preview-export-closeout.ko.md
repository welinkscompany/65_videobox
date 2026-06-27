# VideoBox Phase 6 마감 메모

## 1. 이번 단계에서 완료한 것

- reviewed timeline job 결과를 기준으로 preview render job을 시작할 수 있게 만들었다.
- preview 결과를 로컬 파일과 metadata record로 함께 저장하도록 연결했다.
- CapCut export job을 timeline job 기준으로 시작할 수 있게 만들었다.
- CapCut payload 파일과 보조 안내 파일을 프로젝트 폴더에 저장하도록 연결했다.
- preview/export job 상태가 API와 dashboard에 노출되도록 연결했다.
- dashboard에서 preview render와 CapCut export를 직접 실행할 수 있게 만들었다.
- review blocker가 남아 있으면 preview/export를 차단하도록 backend와 dashboard를 함께 고정했다.
- preview/export 실패 시 failed job이 남도록 job 상태 추적을 보강했다.
- export index에도 timeline_id를 저장해서 timeline 대비 export provenance를 맞췄다.
- dashboard가 최신 timeline과 연결되지 않은 오래된 preview/export를 현재 산출물처럼 보여주지 않도록 보정했다.

## 2. 현재 저장 구조

- preview artifact:
  `projects/<project_id>/previews/preview_001.json`
- CapCut export payload:
  `projects/<project_id>/exports/capcut/export_001/capcut_payload.json`
- CapCut export handoff note:
  `projects/<project_id>/exports/capcut/export_001/README.txt`

## 3. 검증 결과

- backend 전체 테스트:
  `py -m pytest tests -q`
- frontend 테스트:
  `npm test`
- frontend build:
  `npm run build`
- Python compile 검증:
  `py -m compileall services/api/src packages/core-engine/src packages/storage-abstractions/src packages/domain-models/src packages/timeline-schema/src packages/capcut-export/src`
- preview/export API 스모크:
  `py -m pytest tests/test_api.py::test_preview_and_capcut_export_flow_persist_outputs_and_statuses -q`

위 검증은 2026-06-28 기준 현재 워크트리에서 통과했다.

## 4. 현재 제한사항

- preview renderer는 아직 실제 영상 렌더러가 아니라 `mock_preview_bundle` 구조화 artifact를 생성한다.
- CapCut export도 초기 adapter boundary 단계이며, 현재는 `mock` handoff payload를 생성한다.
- timeline 검수 승인 상태를 더 세밀하게 강제하는 정책은 다음 단계에서 강화할 여지가 있다.
- 실제 미디어 렌더 품질, 음악 믹싱, subtitle 파일 출력은 아직 본격 구현 전 단계다.

## 5. 다음 단계 추천

- preview artifact를 실제 mp4 또는 player-compatible preview bundle로 확장
- subtitle/srt 출력 추가
- review 승인 정책을 명시적 상태 전이로 강화
- CapCut adapter payload를 실제 샘플 프로젝트 기준으로 추가 검증
- dashboard에 preview/export artifact 상세 보기 추가
