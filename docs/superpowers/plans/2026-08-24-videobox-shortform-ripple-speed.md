# VideoBox 숏폼 장면 리플 배속 구현 계획

> **실행 방식:** 현재 goal에서 이 계획을 순서대로 실행한다. 같은 브랜치에 다른 AI 도구를 병행하지 않는다.

**목표:** 선택한 한 장면을 1×·1.5×·2×로 재생해 길이를 줄이고, 내레이션·자막·장면 종속 영상/효과음을 같은 비율로 줄이며, 뒤 장면을 빈틈 없이 앞으로 당긴다.

**구조:** 원본 구간을 자르는 `set_segment_bounds`와 별개로 세션 segment에 `ripple_playback_rate`를 저장한다. 공통 `materialize_editing_session_timeline`이 축소된 배치와 각 clip의 `playback_rate`를 만들며, 정확 미리보기·최종 렌더·CapCut 내보내기는 이미 이 materialize 경로를 쓰므로 같은 결과를 소비한다. 화면은 기존 편집 항목 안에 작은 텍스트 단추만 추가하며 팔레트·배치 CSS를 바꾸지 않는다.

**기술:** Python core engine/FastAPI/Pydantic, TypeScript/React/Vitest

---

### 작업 1: 세션의 리플 배속 도메인 동작을 RED로 고정한다

**파일:**
- 수정: `tests/test_editor_timeline_mutations.py`
- 수정: `packages/core-engine/src/videobox_core_engine/editing_session.py`

1. `tests/test_editor_timeline_mutations.py`에 실제 편집 세션 fixture(3개 연속 장면, 두 번째 장면의 B-roll·SFX·자막)를 만들고 `set_segment_ripple_playback_rate`를 아직 import하지 않아 RED가 되는 시험을 추가한다.
2. 2× 선택 시 둘째 장면의 source slice는 그대로 4초이고 표시 구간만 4–6초에서 4–5초로 축소되며, 셋째 장면이 8–12초에서 5–9초로 당겨지는지 확인한다. 원래 세그먼트의 자막·미디어 선택이 사라지지 않는지도 확인한다.
3. 1×로 되돌리면 원래 경계로 복원되는지, undo/redo가 속도와 모든 경계를 함께 복원하는지 확인한다.
4. 허용값은 `1.0`, `1.5`, `2.0`만 허용하고 0·음수·3·NaN은 `segment_ripple_playback_rate_invalid`으로 거절하며 원 세션을 바꾸지 않는 시험을 추가한다.
5. 최소 표시 길이(`MIN_SEGMENT_DURATION_SEC`)를 침해하는 비율은 별도 오류로 거절한다.
6. 시험이 RED임을 `.venv\Scripts\python.exe -m pytest tests/test_editor_timeline_mutations.py -q`로 확인한다.
7. `editing_session.py`에 상수·유효성 검사·`set_segment_ripple_playback_rate`를 구현한다. source slice/source window/content window는 보존하고, 모든 세그먼트의 표시 경계만 현재 순서에 따라 다시 계산한다. 이 변경은 `_record_undoable_mutation(..., mutation_type="segment_ripple_speed_update")` 한 번으로 남긴다.
8. 같은 focused pytest가 GREEN인지 확인한다.

### 작업 2: materialize가 실제 출력용 재생률과 시간축을 만든다

**파일:**
- 수정: `tests/test_exact_preview_remediation.py`
- 수정: `packages/core-engine/src/videobox_core_engine/composition_plan.py`
- 필요 시 수정: `packages/core-engine/src/videobox_core_engine/editor_playback_manifest.py`

1. atomic draft에서 생성한 원본 timeline과 `materialize_editing_session_timeline`을 쓰는 RED 시험을 추가한다. 직접 완성 timeline을 손으로 만들지 않는다.
2. 중간 장면 2×에서 narration·caption·B-roll·SFX clip의 `start_sec`/`end_sec`가 축소되고 `playback_rate == 2.0`이 되며, 다음 장면 clip이 당겨지는지 검증한다. 전역 BGM은 rate 1×를 유지하되 출력 끝에서 잘리는지 검증한다.
3. B-roll 개별 `media_controls.speed`와 장면 속도를 곱해 clip의 실제 `playback_rate`를 계산한다. 곱한 값이 0.25–4 범위를 넘으면 materialize 전에 세션 변경을 거절하는 RED 시험을 추가한다.
4. `composition_plan.py`에서 source slice 지속시간과 표시 지속시간을 분리한다. source in/out은 말과 영상의 전체 내용을 보존하고, 표시 end는 `source_duration / ripple_playback_rate`로 계산한다. 생성한 모든 종속 clip에 `playback_rate`를 전파한다.
5. global narration을 caption 기준으로 조각내는 기존 분기도 같은 재생률을 싣도록 보완한다. caption과 overlay window의 배치도 축소된 window에 맞춘다.
6. `editor_playback_manifest.py`가 materialized payload만 읽는지 확인하고, 별도 시간 계산이 있으면 같은 `playback_rate`를 노출한다.
7. focused pytest를 GREEN으로 만든다.

### 작업 3: 렌더·정확 미리보기·CapCut 출력이 재생률을 실제로 소비하게 한다

**파일:**
- 수정: `tests/test_broll_speed_and_volume.py`
- 수정: `tests/test_exact_preview_remediation.py`
- 수정: `tests/test_capcut_export_track_states.py` 또는 출력 경로 전용 시험 파일
- 수정: `packages/core-engine/src/videobox_core_engine/local_pipeline.py` (필요한 경우만)
- 수정: `packages/core-engine/src/videobox_core_engine/composition_plan.py` 또는 기존 FFmpeg/CapCut adapter

1. RED 시험에서 `materialize_editing_session_timeline`이 만든 2× narration/B-roll clip으로 exact preview render 명령과 CapCut export payload를 만든다.
2. 영상 필터가 2×를 적용하고, 음성은 FFmpeg의 유효한 `atempo` 체인으로 2×를 적용하며, 출력 duration이 materialized 구간과 같은지 검사한다. 자막은 축소된 cue 경계를 사용해야 한다.
3. CapCut payload가 source 구간을 유지하면서 speed/trim duration을 materialized `playback_rate`와 경계로 표현하는지 검증한다. 내보내기 전용의 수동 fixture가 아니라 session materializer 결과를 사용한다.
4. renderer가 이미 generic `playback_rate`를 소비한다면 중복 변환을 만들지 말고 테스트만 공통 자료로 교체한다. 소비하지 않는 경로만 최소 변경한다.
5. focused backend pytest들을 GREEN으로 확인한다. 실제 FFmpeg 결과를 쓰는 기존 시험은 결과 파일 길이까지 확인한다.

### 작업 4: revision 보호 API를 세션 서비스까지 연결한다

**파일:**
- 수정: `services/api/src/videobox_api/models.py`
- 수정: `services/api/src/videobox_api/routers/editing_session.py`
- 수정: `services/api/src/videobox_api/orchestration.py`
- 수정: `packages/core-engine/src/videobox_core_engine/editing_session_and_regeneration.py`
- 수정: 해당 API 시험 파일(기존 bounds/transition API 시험 또는 새 focused 파일)

1. `RipplePlaybackRateRequest(expected_revision, rate)` Pydantic 모델과 `PATCH /api/projects/{project_id}/editing-sessions/{session_id}/segments/{segment_id}/ripple-playback-rate`를 RED 시험으로 고정한다.
2. stale revision은 기존 `EditingSessionConflict` 응답 형식을 유지하고, 유효하지 않은 rate 또는 합성 B-roll speed 범위 위반은 422로 응답하는지 확인한다.
3. orchestration과 `EditingSessionAndRegeneration`에 얇은 위임 메서드를 추가한다. 저장은 기존 `_save_editing_session_with_revision`만 사용하여 revision 증가·출력 stale 표시·undo history가 한 transaction에 묶이게 한다.
4. API focused pytest를 GREEN으로 확인한다.

### 작업 5: 기존 편집 항목에서 선택 장면의 단추를 연결한다

**파일:**
- 수정: `apps/web/src/api.ts`
- 수정: `apps/web/src/features/editor/editorCommandPort.ts`
- 수정: `apps/web/src/features/editor/editorCommandPort.test.ts`
- 수정: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx`
- 수정: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`
- 수정: `apps/web/src/features/editor/workbench/editorWorkbenchReadOnlyAdapters.tsx`
- 수정: `apps/web/src/features/editor/workbench/RightDock.tsx`
- 수정: `apps/web/src/features/editor/workbench/right-dock.test.tsx`
- 수정: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`

1. API type과 request method를 RED 시험으로 추가한다. payload에는 `rate`와 현재 `expected_revision`만 포함한다.
2. `EditorCommandPort`에 `setSegmentRippleSpeed({ segmentId, rate })`를 추가하고 revision을 잊지 않고 전달하는지 unit test한다.
3. 이미 선택 장면을 보여 주는 RightDock의 `편집 항목` 안에 1×/1.5×/2× 텍스트 단추만 추가한다. 새 패널·색·CSS·배치 변경은 하지 않는다.
4. 선택 장면이 없을 때는 단추가 나타나지 않고, 저장 중에는 막히며, 현재 속도에는 `aria-pressed`가 설정되는 RED UI 시험을 작성한다.
5. 화면 문구는 개발 용어 없이 `장면 길이`, `기본`, `1.5배`, `2배`로 쓴다. `provider`, `runtime`, `job`, `revision`, `pipeline`을 노출하지 않는다.
6. 클릭이 selected segment id와 expected revision으로 API를 부르고, 성공 시 기존 mutation refresh를 거쳐 새 길이를 표시하는지 route test로 검증한다. conflict/offline 기존 처리도 유지한다.
7. `cd apps/web; npx vitest run <focused files>` 및 `npx tsc --noEmit`을 GREEN으로 확인한다.

### 작업 6: 회귀 검증·문서·커밋·인계를 마무리한다

**파일:**
- 수정: `docs/handoffs/2026-08-24-videobox-shortform-ripple-speed-handoff.ko.md`
- 수정: `CLAUDE.md`

1. 각 논리 단위(도메인/materialize, API·출력, 웹 연결) 후 한국어 커밋 메시지로 별도 커밋한다. credential, `.env.container`, 승인된 CSS는 stage하지 않는다.
2. backend focused suite와 웹 focused suite를 다시 실행한 뒤, 백엔드 전체는 다른 작업과 병렬로 하지 않고 `.venv\Scripts\python.exe -m pytest -q`로 단독 실행한다.
3. `apps/web`에서 `npx vitest run`, `npx tsc --noEmit`을 실행한다. 실패하면 테스트를 되돌리지 말고 실제 materialize/API/renderer 문제를 고친다.
4. handoff에는 실제로 한 일, 검증했지만 못 끝낸 일, 목요일에 화면으로 확인할 일을 각각 쓴다. `CLAUDE.md` §2의 최신 세션 인계 링크도 새 handoff로 바꾼다.
5. commit hash, 정확한 테스트 결과, 미실행/사람 확인 경계를 보고한다. push·외부 게시·컨테이너 네트워크 변경은 하지 않는다.

---

## 완료 기준

- 선택한 하나의 장면만 1×/1.5×/2×로 바꾸며 뒤 장면이 같은 세션 mutation으로 당겨진다.
- 영상, 나레이션, 자막, 장면 종속 B-roll/SFX/overlay는 같은 시간축과 재생률을 쓰고, 전역 BGM은 빨라지지 않는다.
- undo/redo, revision conflict, 허용하지 않은 rate, 합성 B-roll rate 초과가 모두 검증된다.
- exact preview, 최종 렌더, CapCut export가 수동으로 조립한 timeline이 아니라 `materialize_editing_session_timeline`의 결과를 소비하는 시험으로 증명된다.
- 화면 단추 동작은 자동 시험으로 확인하되, 목요일의 실제 화면·청취 확인 전에는 사용성 완료라고 말하지 않는다.
