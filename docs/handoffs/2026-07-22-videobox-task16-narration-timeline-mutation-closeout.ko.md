# VideoBox Task 16 closeout — 2026-07-22

- 범위: 내레이션 clip의 시작/끝 trim과 순서 변경을 TimelineDock에서 기존 revision-bound editing-session command로 연결했다. `EditorCommandPort.reorderNarration`은 complete `segmentIds`와 `boundsById`를 필수로 받고 backend의 `segment_ids`·`bounds_by_id`로 한 번만 변환한다.
- 동작: 포인터 이동은 로컬 초안만 바꾼다. 실제 이동 없이 놓거나 cancel하면 요청하지 않고, 이동 후 release에서만 한 번 요청한다. trim은 rational FPS의 반올림·한 프레임 최소 길이·이웃/전체 timeline 경계를 지키며, reorder는 duration을 보존한 연속 layout을 만든다. 키보드 trim/reorder와 저장 중 disabled 상태도 유지한다.
- 실패 안전: Route는 현재 revision command port로 요청하고 모든 결과 뒤 manifest를 재조회한다. conflict/실패에는 안전한 안내만 보이며 자동 재시도·force apply·preview generation은 없다. A→B→A route race에서도 늦은 이전 결과가 현재 mutation state를 덮지 않는다.
- 경계: Task 14 순수 수학은 그대로다. Task 16은 Dock 안의 local pointer draft만 허용한다. Dock의 API/command port import, direct request/`mutate()`, preview write, canvas, non-narration mutation, backend/API 변경, provider/Hermes/Mem0, OpenCut runtime은 추가하지 않았다.
- 검증: focused Task 16 quality re-review 승인(Critical/Important/Minor 0); frontend full `44 files / 443 passed`; production build 성공(기존 500 kB chunk warning); provenance pytest `21 passed`(기존 multipart warning 1); PowerShell verifier 성공; `git diff --check` 성공. 전체 Python regression은 실행하지 않았다.
- 진행률: Task 9의 실제 사람/환경 acceptance와 분리한다. 공식 누적은 **9/22 (40.9%)**, 잔여 **59.1%**다.
- 다음 goal: Task 17의 다중 lane 편집 또는 다음 interaction 범위를 written spec으로 먼저 확정하고 사용자 승인을 받는다.
