**대체됨:** `docs/handoffs/2026-09-18-variant-conflict-resolution-actually-wired-to-chat.ko.md`

# task_c68ba644 -- 유진 채팅 30초 타임아웃을 60초로 올렸다, 실물 확인까지 봤다

owner 승인(2026-09-18, "진행해줘, 자율모드로") 위에서, `2026-09-18-variant-conflict-
resolution-via-chat.ko.md`가 넘긴 백로그 1번(로컬 구조화 LLM 호출 타임아웃 30초가
실사용에 너무 짧다)을 고쳤다.

## 원인 재확인

- 단일 SSOT: `LocalOpenAICompatibleRuntimeConfig.timeout_seconds`
  (`packages/core-engine/src/videobox_core_engine/settings.py`), 환경변수
  `VIDEOBOX_LOCAL_RUNTIME_TIMEOUT_SECONDS`로 덮어쓸 수 있다. 옛 기본값은 30.
- 이 값이 `LocalQwenHTTPTransport`(HTTP 요청 자체의 timeout)까지 그대로 흘러간다
  (`services/api/src/videobox_api/orchestration.py`의
  `build_local_qwen_structured_provider`가 생성자에 그대로 넘긴다) -- 두 곳에
  30이 하드코딩된 것처럼 보였지만 실제로 값을 결정하는 자리는 하나다.
- **소비자 카운트** -- `generate_structured(`을 부르는 자리가 프로덕션 코드에
  14곳: `caption_translation_service`, `infographic_service`(자체 140초 타임아웃
  있음, 무관), `memory_librarian`, `output_operator_copy`, `recommenders`(2곳),
  `scene_image_prompt`, `review_guidance`, `script_draft_writer`,
  `script_scene_planner`, `short_form_scene_pick`(2곳, `footage_organizer`.
  이 중 **`short_form_scene_pick`만** 자기 `wait_seconds`를 들고 온다(실측
  130~267초짜리 숏폼 훑기·짜기 전용). **나머지 12곳은 전부 전역 기본값에
  의존한다** -- 화면 채팅의 실제 실행 경로 둘 다 포함:
  `yujin_editing_proposal_service.create`(크롭·초점·자막 배치·안전 영역·소리
  보정·변형본 충돌 풀기 등 output_variant 계열, 화면의 "만들기" 버튼과
  `POST .../yujin-editing-proposals`)와 `yujin_local_conversation.py`
  (자유 문장 채팅, `POST .../director/conversations/.../messages`가 참조를
  결정론적으로 못 풀 때만 타는 길).

## 실측

컨테이너가 이미 떠 있었다(`curl 127.0.0.1:5173/health` 200). `lms ps`로 GPU
확인 -- `qwen/qwen3.8-27b` 하나만 떠 있고 `IDLE`(경합 없음).

실제 화면이 밟는 API를 그대로 호출해 쟀다(`POST .../yujin-editing-proposals`,
크롭 지시), 95장면짜리 실제 대표님 프로젝트(`2026-09-12-ca6dd9ed`)에서:

- 1차 12초, 2차 25초, 3차 16초, 4차 14초.
- 장면 1개짜리 작은 시험 프로젝트에서는 23초.

**30초에 아슬아슬하게 걸치거나 넘기는 범위**라는 게 실측으로 확인됐다 --
이전 세션이 정확히 이 경로에서 반복 실패한 이유와 일치한다. 60초는 이
저장소의 라이브 smoke 시험(`tests/test_yujin_local_conversation_live_smoke.py`)이
같은 모델에 이미 쓰던 값과 같고, 실측 최댓값(25초) 대비 약 2.4배 여유다.
무한정 늘리지 않았다 -- 화면이 멈춘 것처럼 보이는 것을 피하기 위해서다.

## 고친 것

1. `packages/core-engine/src/videobox_core_engine/settings.py` --
   `LocalOpenAICompatibleRuntimeConfig.timeout_seconds` 기본값 30 → 60.
2. `compose.yaml` -- `VIDEOBOX_LOCAL_RUNTIME_TIMEOUT_SECONDS: ${...:-60}`을
   명시로 추가했다(이전에는 아예 없어서 `.env.container`로도 조정할 방법이
   없었다). 기존 `VIDEOBOX_LOCAL_MODEL_NAME`·`VIDEOBOX_LOCAL_RUNTIME_BASE_URL`과
   같은 패턴이다 -- 재빌드 없이 owner가 값을 조정할 수 있는 문을 열어 둔다.
3. `tests/test_local_runtime_config.py` --
   `test_local_runtime_default_timeout_is_not_30_seconds`(RED로 먼저 확인,
   옛 기본값 30에서 실패하는 것을 봤다).

## 화면 쪽(대기 표시) -- 이미 되어 있어서 손대지 않았다

owner 상시 지시("기다림에는 항상 표시가 있어야 한다")를 확인했다. 이 채팅
경로는 이미 `thinking: {phase: "answering"}` 상태를 켜고(`EditorWorkbenchRoute.tsx`
`setDirectorThinking({phase: "answering"})`), `YujinPanel.tsx`가
`role="status"`로 "유진 진행 상태" 문구와 기다린 시간을 보여준다(2026-09-12에
숏폼 판단 437초·605초가 화면을 조용히 멈추게 한 결함을 고치며 만든 장치,
`videobox-waiting-work-must-always-show-something` 메모). 60초로 늘어난
기다림도 이미 이 장치가 덮는다 -- 새 화면 작업은 필요 없다고 판단했다.

## 검증

- RED: `test_local_runtime_default_timeout_is_not_30_seconds` 단독 실행,
  `AssertionError: assert 30 == 60`로 실패 확인 → 최소 수정 → GREEN.
- 갭: `tests/test_compose_contract.py`, `test_hermes_yujin_compose_contract.py`,
  `test_local_model_name_is_one_value.py`, `test_set_local_model_script.py`,
  `test_local_runtime_config.py` 75건 통과 -- `compose.yaml` 수정이 다른 계약을
  안 깼다.
- 갭: `test_api_yujin_creator_context.py`, `test_yujin_editing_proposal_adapter.py`,
  `test_yujin_local_conversation.py`, `test_api_output_variants.py`,
  `test_local_media_ai_providers.py` 141건 통과.
- **역방향(가장 중요)**: `scripts/owner-ready.ps1 -Mode Start -WithYujinMemory
  -Rebuild`로 재빌드. `docker exec ... env`로 컨테이너 안
  `VIDEOBOX_LOCAL_RUNTIME_TIMEOUT_SECONDS=60` 직접 확인. **실제 브라우저로
  `2026-09-12-ca6dd9ed` 편집 화면을 열고, 유진 채팅에 이전 세션이 정확히
  실패했던 그 문장("세로 전체 변형에서 크롭 충돌이 있는데, 마스터 기준으로
  다시 맞춰줘")을 다시 타이핑해 보냈다** -- 이전에는 두 번 다
  "유진의 답을 받지 못했어요."로 실패했던 기록이 대화 이력에 그대로 남아
  있는데, 이번에는 약 20초 만에 실제 답변("네, 실측 숏폼 2026-09-12의 세로
  전체 변형에서 크롭 충돌을 마스터 기준으로 다시 맞춰 실행합니다...")이
  돌아왔다. 세션 리비전은 11로 그대로였다(실행이 아니라 응답만 확인, 실제
  변형 충돌이 이미 이전 세션에서 정리돼 있어서 부작용 없음).
- 넓은 검증: 전체 backend pytest(`.venv/Scripts/python.exe -m pytest -q`,
  독립 실행)를 배경에서 돌렸다 -- 결과는 아래 채운다.

## 전체 pytest 결과

코디네이터가 독립적으로 새로 단독 실행했다 -- **5144 passed, 56 skipped,
1 xfailed, 실패 0건**(43분 33초). 회귀 없음.

## 다음 세션 백로그

1. `2026-09-12-ca6dd9ed`의 `source_session_revision` 불일치(12 vs 실제 11) --
   여전히 미정리. `2026-09-18-variant-conflict-resolution-via-chat.ko.md`가
   남긴 항목 그대로다.
2. `task_006f1523`(R1 경계 나누기) -- 여전히 대기, 안 급함.
3. 60초도 여전히 부족한 사례가 실사용에서 나오면(더 무거운 프롬프트, 더
   긴 프로젝트) 재측정이 필요하다 -- 이번 실측은 95장면 프로젝트 기준
   12~25초였고, 그보다 훨씬 큰 프로젝트나 더 무거운 action(대본 다시 쓰기
   등)은 별도로 재보지 않았다.

## 재사용 원칙

- 재사용 후보: `short_form_scene_pick.py`가 이미 쓰던 "느린 일은 자기
  `wait_seconds`를 들고 온다" 패턴을 참고했지만, 이번엔 **전역 기본값
  자체**를 고치는 것이 맞다고 판단했다(짧아야 할 대화까지 전부 30초에
  끊기고 있었으므로) -- 새 오버라이드 메커니즘을 만들지 않았다.
- 실제 반영: `settings.py` 기본값 1줄, `compose.yaml` 1줄, 시험 1개.
- 제외: 더 작은/빠른 모델로 이 호출만 라우팅하는 것, 프롬프트 축소 --
  가장 직접적인 해결책(타임아웃 조정)이 실측으로 충분히 여유를 만들어서
  범위를 넓히지 않았다.
- 경계 보존: `UI 구조`·`Google Sheets/Drive`·provider 하드코딩 반입 없음.

## 커밋·푸시

코디네이터가 이어받아 커밋·fast-forward 확인 후 push 완료.
