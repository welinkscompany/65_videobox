# VideoBox Task 18 caption time authority repair closeout

## 완료한 보완

- caption의 시간은 narration segment에서 생성한 bounds만 쓴다. `caption:*`은 manifest의 표시·선택 identity로는 남지만, generic timeline placement mutation 대상은 아니다.
- 과거 session에 남은 `caption:*` override는 삭제하거나 revision을 올리지 않고 materialization에서만 무시한다. 따라서 다음 editor manifest, exact preview/final composition, CapCut draft는 narration-derived caption 시간을 사용한다.
- 새 caption placement 요청은 placement collection에 존재하지 않아 `timeline_placement_unknown`으로 거부되고 session mutation/CAS까지 진행하지 않는다. B-roll/BGM/SFX/overlay placement와 알 수 없는 비-caption override의 fail-closed 동작은 유지한다.
- caption PATCH는 top-level segment와 matching `content_windows[].source_segment_id`를 같은 revisioned mutation에서 갱신한다. 따라서 merge 뒤 특정 child caption을 저장해도 다른 child window는 보존되고, materializer·manifest·exact/final composition에 새 text가 전달된다.
- caption save가 진행 중이면 대본 행, textarea, 저장 버튼을 모두 잠근다. native disabled를 우회한 합성 change 이벤트도 draft를 바꾸지 않도록 guard를 추가했다.

## 검증 근거

- TDD RED: core caption authority test `3 failed, 12 passed`; pending textarea forced-change test는 원문 대신 새 값이 들어가는 실패를 재현했다. content-window text regression은 regular/API path의 stale text와 merged child lookup의 `KeyError`를 재현했다.
- GREEN: targeted Python `78 passed, 1 warning` (`starlette`의 기존 `multipart` PendingDeprecationWarning), focused frontend `7 files / 71 passed`.
- frontend full: `48 files / 464 passed`. 기존 React `act(...)`, jsdom navigation, intentional ErrorBoundary stderr는 실패가 아니다.
- production build 성공. 기존 500 kB chunk warning만 남았다.
- independent spec/quality/gap/reverse review는 Critical/Important 0으로 종결했다. 최종 역방향 검토는 caption PATCH→window→materializer→manifest→preview/final composition과 legacy/new placement·save lock을 재추적했다.
- 전체 Python regression은 실행하지 않았다.

## 범위와 상태

- source copy, OpenCut runtime, provider/Hermes/Mem0, 새 API, asset browser는 변경하지 않았다.
- 보호 대상 `?? .tmp-final-fence-debug/`는 기존 범위 밖 잔재로 보존했으며 stage/remove하지 않는다.
- Task 9 사람/환경 acceptance는 별도이며 공식 누적은 **9/22 (40.9%)**, 잔여 **59.1%**를 유지한다.

## 다음 goal

Task 19 editor asset browser/safe preview/apply는 별도 written spec과 사용자 승인 뒤에만 시작한다. 기존 `ManualMediaLibrary`, `AssetPreviewPlayer`, `PreviewCoordinator`, revision-bound `EditorCommandPort`를 조사하되, 별도 asset truth·direct API·자동 apply를 만들지 않는다.
