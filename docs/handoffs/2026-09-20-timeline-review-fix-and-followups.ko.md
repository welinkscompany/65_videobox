# 검토 화면 최신 편집 반영 고침 + 후속 점검 (2026-09-20)

## 요청과 배경

`docs/handoffs/2026-09-20-timeline-manual-editing-bug-hunt.ko.md`의 "다음 세션
시작 프롬프트"를 그대로 이어받았다. 검토 화면(`GET /timelines/{job_id}`)이
저장된 tracks를 그대로 읽어서 장면을 나눈 뒤 "현재 편집본으로 검토본 다시
만들기"를 눌러도 경계가 안 바뀌던 버그를 제대로 고치는 것이 본 작업, 나머지는
시간이 되면 하는 후속 점검이었다.

## 고친 것 (검증 완료, 커밋 `018c7aee`)

**증상**: `GET /timelines/{job_id}`가 저장된 timeline 문서의 `tracks`를 그대로
읽어서, 분할·트림 같은 편집을 해도 검토 화면의 장면 경계가 바뀌지 않았다.

**이번 수정**: 저장된 `timeline["tracks"]`는 전혀 손대지 않는다(`composition_plan.py`의
`source_durations`/`source_bounds`가 그 값을 원본 소스 길이 계산 기준으로도
읽기 때문 -- 첫 시도(`2183eec0`, 되돌림)가 이걸 몰라서 broll/overlay 클립의
`overlay_type`/`overlay_payload`를 날려 422를 냈었다). 대신 렌더 경로
(`build_editor_playback_manifest`)가 이미 쓰는 패턴대로, **읽을 때마다**
`materialize_editing_session_timeline`을 다시 불러서 **응답에 실을 사본만**
새로 만든다.

- `packages/core-engine/src/videobox_core_engine/editing_session_and_regeneration.py`에
  `_materialize_timeline_tracks_for_review` 추가. `timeline["source_session_id"]`로
  편집 세션을 찾아 다시 materialize하고, 자막 트랙(따로 만들어지지 않는다)만
  저장된 값을 그대로 붙인다. broll/bgm/sfx/overlay 클립에 없는 `clip_type`은
  트랙의 `track_type`에서 채운다(응답 계약 `TimelineClipResponse.clip_type`이
  필수).
- `local_pipeline.py`의 `get_timeline_result`에서 `_hydrate_timeline_review_status`
  다음에 이 함수를 호출하도록 배선.
- `tests/test_atomic_draft_bundle.py`에
  `test_timeline_review_response_reflects_the_latest_split_without_mutating_storage`
  추가 -- **저장된 값은 그대로**이고 **응답만** 최신 편집을 반영하는지, 그리고
  `TimelinePayloadResponse` 계약까지 통과하는지 함께 잰다.

**검증**: RED→GREEN 확인, 백엔드 전체 회귀 459건 통과(`test_atomic_draft_bundle.py`
포함 `test_api.py`/`test_vertical_composition.py`/`test_auto_apply_policy.py`/
`test_local_pipeline_capcut_draft_export.py`). 컨테이너 재빌드
(`owner-ready.ps1 -Mode Start -Rebuild`) 후 **실제 프로젝트 `0907-b26195af`**에서
브라우저로 장면을 나누고(7→8컷) "현재 편집본으로 검토본 다시 만들기"를 눌러
검토 화면의 `narration` 트랙이 실제로 8개 클립·새 경계로 나오는 것을 API 응답으로
직접 확인했다. 확인 뒤 편집기에서 되돌리기로 원래 7컷 상태로 복구했다.

## 버그 아닌 것으로 정정된 것

- **숏폼 다시 만들기가 "읽을 자막이 없어서 전체 장면을 그대로 뒀다"고 함** —
  프로젝트 `0907-b26195af`의 실제 세션 데이터를 확인해 보니 모든 장면의
  `caption_text`가 진짜로 빈 문자열이다(화면의 "캡션 1..7" 라벨은 빈 캡션
  슬롯일 뿐). 자막 없이는 숏폼이 하이라이트를 고를 근거가 없으므로 메시지와
  동작이 데이터와 일치한다 -- 결함이 아니다.

## 새로 찾아 남긴 것 (별도 세션으로 분리, task_08c5f062)

검토/내보내기 화면의 "출력" 섹션이 프로젝트 `0907-b26195af`에서 항상 "출력
상태를 불러오지 못했어요"로 뜬다. `GET /final-renders/final_render_job_004`가
404를 낸다 -- `/jobs` 목록에는 이 job이 `status=succeeded`,
`output_ref=export_001`로 남아 있는데 실제 렌더 기록을 저장소가 못 찾는다.
오늘 세션 코드와 무관해 보이는 낡은 데이터 문제로 보이나 확인은 못 했다.
스폰 태스크(`task_08c5f062`)로 남겼다 -- 실사용 프로젝트라 원본 손상 없이
조사하라는 주의를 같이 적었다.

## 아직 재현 못 한 것

- **최초 진입 시 클립이 2px로 렌더** — 이번 세션에서 컨테이너를 두 번(`docker
  restart` 직후 바로 편집기 로드) 다시 노렸지만 재현 안 됨. 지난 세션까지
  합쳐 7~8회 시도 중 1회만 재현된 만큼 이번에도 못 잡은 것 자체는 이상하지
  않다. 재현 스크립트 없이는 다음 세션도 운에 맡겨야 한다 -- `TimelineDock.tsx`
  251-265행의 `useReducer` lazy initializer가 유력한 용의자라는 추정은 그대로
  유효하다(원인 코드는 못 봄, 재현 실패로 디버깅 진행 못함).

## 시간이 부족해서 못 한 것

- 숏폼 화면은 "숏폼 다시 만들기"/"전체 장면으로 되돌리기" 버튼 동작만 확인했고,
  세로 변형의 크롭 편집이나 제목 카드 생성까지는 안 봤다.
- 업로드 화면은 이번에도 못 봤다 -- 라우트(`resolveProjectStage`의 `output`
  스테이지 안쪽으로 추정)를 찾다가 시간이 부족했다. 검토 승인 이후에만
  열리는 화면일 가능성이 있다.
- 완성본 만들기(final render) 화면은 위 404 건 때문에 정상 경로를 못 밟았다 --
  그 결함이 먼저 풀려야 화면 검증이 의미가 있다.

## 다음 세션 시작 프롬프트

```
docs/handoffs/2026-09-20-timeline-review-fix-and-followups.ko.md를 읽고 이어서:

1. task_08c5f062(완성본 상태 조회 404, 프로젝트 0907-b26195af)를 먼저 처리하거나
   상태를 확인해줘 -- 이게 안 풀리면 완성본/업로드 화면을 정상 경로로 못 밟는다.
2. 업로드 화면을 브라우저로 직접 찾아서 밟아줘 -- 이번 세션엔 라우트를 못 찾았다.
   프로젝트 0907-b26195af의 검토를 승인한 뒤 "output" 스테이지 안쪽을 뒤져봐라.
3. 시간이 남으면 최초 진입 시 클립이 2px로 렌더되는 버그를 다시 노려봐줘
   (컨테이너를 docker restart 직후 바로 편집기를 열어야 한다 -- 지금까지
   7~8회 시도 중 1회만 재현됐다).
```
