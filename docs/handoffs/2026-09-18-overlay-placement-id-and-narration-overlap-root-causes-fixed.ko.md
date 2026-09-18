**대체됨:** `docs/handoffs/2026-09-18-independent-verification-of-todays-four-fixes.ko.md`

# 타임라인 클릭 크래시의 백엔드 근본 원인 둘 + 변형본 충돌 중복 하나를 고쳤다

`docs/handoffs/2026-09-18-timeline-click-selection-was-silently-crashing.ko.md`가
프론트엔드에서 방어적으로 막아 두고 백엔드로 떠넘긴 문제 둘(`task_6f80b621`
오버레이 `placement_id` 중복, `task_ecf8eb71` 내레이션 겹침)과, 같은 날 다른
문서(`2026-09-18-variant-conflict-resolution-actually-wired-to-chat.ko.md`)가
"범위 밖"으로 남긴 변형본 충돌 중복 append 문제를 코디네이터 승인("모두
진행하자") 위에서 고쳤다. 셋 다 project `0907-b26195af`("사진 브이로그 실기
0907")의 실제 데이터로 재현·검증했다.

## 과제 1 -- 오버레이 `placement_id` 중복 (composition_plan.py)

**원인**: `materialize_editing_session_timeline`의 `export_overlays` 재구성
루프(`composition_plan.py`, 이제 636번대)가 `source_targets[source_id]`의
target을 순회하는데, 세그먼트가 분할돼 target이 여럿이어도 각 클립에 주는
`clip_id`가 `source_id`와 `overlay_index`로만 만들어져 **분할 조각 수만큼
똑같은 clip_id가 찍혔다.** `timeline_placements.placement_id(kind="overlay",
base_id=clip_id)`가 이 clip_id를 그대로 물기 때문에, 겹친 clip_id가 겹친
placement_id로 이어져 프론트엔드 `selectClip`이 `RangeError: Rect clipIds
must be unique`로 죽었다.

**고침**: target이 하나뿐이면(분할 없음) 기존과 똑같은 id를 유지해 지문을
안 건드리고, target이 여럿이면(분할됨) `{base_clip_id}@{target_segment_id}`로
갈라서 유일하게 만든다. 기존 broll/bgm/sfx 클립의 이름 충돌 처리(같은 파일
582~603번 줄)와 같은 패턴이다.

**RED→GREEN**: `tests/test_clip_placement.py::
test_splitting_a_segment_with_an_overlay_does_not_duplicate_the_overlay_clip_id`.
`split_segment`로 세그먼트를 쪼갠 뒤 export_overlays 하나를 얹어서 재현 —
고치기 전엔 `['export-overlay-seg_001-0', 'export-overlay-seg_001-0']`로 정확히
실사용 프로젝트와 같은 모양의 중복이 나왔다.

## 과제 2 -- 내레이션 겹침이 트림 커밋을 항상 막았다 (composition_plan.py)

**둘 중 어느 쪽인지 먼저 가렸다**: `apps/web/src/features/editor/timeline/
narrationMutation.ts`의 `validateNarration`은 `end > start`(엄격한 부등호)만
겹침으로 본다 -- 경계가 맞닿는 정상 케이스를 오탐하지 않는다. **검증 로직은
정상이었다.** 실제 postgres 데이터(`editing_sessions` 테이블, `local://
projects/0907-b26195af/editing_sessions/editing_session_001.json`)를 직접
대조해 숫자로 확인 -- `clip_narration_002`(세그먼트 `timeline_001:001__split_2`)
가 `[4.0, 8.0]`을 그대로 물고 있었는데, 그 세그먼트는 세션에서 이미 `[4.0,
5.696969...)`로 더 쪼개진 뒤였다(나머지는 `timeline_001:001__split_2__split_3`,
`__split_2__split_2`가 가져갔다). **데이터가 실제로 겹쳐 있었다** -- 트림
API의 "겹치면 거부"는 정확한 동작이었다.

**원인**: 이 project의 `timeline_002`는 **다시 지은 편집판**이다 -- raw
narration 트랙에 `clip_narration_001`(세그먼트 `timeline_001:001`)과
`clip_narration_002`(세그먼트 `timeline_001:001__split_2`) 둘 다 자기
이름표를 문 클립으로 있다(`session_bound_clip_ids_by_track`가 이미 이 모양을
알고 다룬다, 2026-09-07 주석). 그런데 **둘 다 `source_slices`는 같은 진짜
원본("timeline_001:001")을 가리킨다** -- 재생성이 매체 트림 계보를 안 잃으려고
일부러 이렇게 해 둔 것으로 보인다(정상). 문제는 `clip_narration_002`가 세션
에서 **또 쪼개지면** 벌어졌다 -- `materialize_editing_session_timeline`의
fallback 경로(`elif targets is None and source_id in segments`)가 클립 길이를
**raw 클립이 최초에 물고 있던 낡은 길이**(`raw.end_sec - raw.start_sec` = 옛
`[4.0,8.0]`)로 계산했다. 지금 세그먼트는 `[4.0,5.7)`로 줄었는데 클립은 옛
전체 길이대로 남아 자기 자식(`__split_2__split_3`, `__split_2__split_2`)과
겹쳤다.

**고침**: `own_duration`을 raw 클립이 아니라 **지금 세그먼트**(`own_segment`)
의 `end_sec - start_sec`으로 계산하도록 한 줄 바꿨다. `source_offset_sec=0.0`은
그대로 둬도 맞다 -- 오른쪽이 truncate된 것이므로(왼쪽은 그대로) 소스 시작점은
안 바뀐다.

이 fallback 경로는 narration 전용이 아니라 broll/bgm/sfx까지 공유하는
일반 루프(404번 줄부터)에 있다 -- 같은 "다시 지은 편집판 + 추가 분할" 조합이면
어떤 트랙 종류든 똑같이 겹쳤을 것이다. 고침도 트랙 종류에 상관없이 적용된다.

**RED→GREEN**: `tests/test_clip_placement.py::
test_splitting_an_already_regenerated_segment_further_does_not_overlap_its_own_children`.
처음엔 `build_editing_session`+`split_segment`만으로 재현을 시도했으나
**재현되지 않았다**(그 경로는 분할이 자기 자신을 뿌리로 삼아서 다르다) --
실제 postgres 데이터의 정확한 모양(두 세그먼트가 각자 자기 raw 클립을 갖되
`source_slices`는 같은 원본을 가리킴)을 손으로 지어야 재현됐다. 고치기 전엔
`[(0.0, 4.0), (4.0, 8.0), (5.7, 8.0)]`로 실사용과 정확히 같은 겹침이 나왔다.

**실물 확인(브라우저, API 아님, CLAUDE.md §4)**: 컨테이너 재빌드
(`scripts/owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild`) 후 실제
`0907-b26195af` 프로젝트를 열어 "내레이션 2" 클립을 실제 마우스 드래그로
트림했다. **성공** -- `session_revision` 22→23, `timeline_001:001__split_3`의
`end_sec`이 2.970947→2.6666...로 실제 저장됨을 서버 상태 대조로 확인. 겹침
오류(`RangeError: Narration segments must not overlap`)는 전혀 뜨지 않았다.
검증 뒤 **실행 취소(Ctrl+Z 버튼)로 원상복구**해서 실사용 데이터에 남기지
않았다(`session_revision`은 24가 됐지만 세그먼트 값은 원래대로 복원 확인).

## 과제 3 -- 변형본 충돌 목록의 `story` 13중복 (output_variants.py)

`2026-09-18-variant-conflict-resolution-actually-wired-to-chat.ko.md`가 "발견한
별개 문제"로 남기고 안 고친 것. **원인**: `rebase_variant`가 `conflicts:
list[VariantConflict] = list(variant.conflicts)`로 시작해 `changed_fields`마다
**무조건 append**했다. `story`/`segment_order`는 `_STRUCTURAL_FIELDS`라 마스터
리비전이 바뀔 때마다 이 조건에 늘 걸리므로, owner가 그 충돌을 안 풀고 편집을
계속하면 rebase가 불릴 때마다 같은 field가 하나씩 쌓였다(`conflicts` 상한은
64 -- 언젠가 부딪힐 수 있었다). 바로 옆 함수 `apply_variant_patch`는 이미
`conflicts_by_field = {conflict.field: conflict for conflict in
variant.conflicts}`로 field를 딕셔너리 키로 다뤄서 안 겹치게 하고 있었다 --
`rebase_variant`만 그 패턴을 안 따르고 있었다.

**고침**: `rebase_variant`도 같은 `conflicts_by_field` 딕셔너리 패턴을 쓰도록
바꿨다. 이미 미해결 충돌이 있으면 새로 안 쌓고 **`base_master_revision`(최초
발산 지점)은 남긴 채 `current_master_revision`만 최신으로 갱신**한다.

**RED→GREEN**:
`tests/test_output_variants.py::
test_rebasing_twice_without_resolving_does_not_duplicate_the_same_field_conflict`.
같은 field로 `rebase_variant`를 두 번 부르고(풀지 않고) conflicts에 그
field가 하나만 남는지, `current_master_revision`은 최신(9)인데
`base_master_revision`은 최초(7) 그대로인지 확인. 고치기 전엔 정확히 실사용과
같은 모양(`base=7→8`, `base=8→9` 두 행)으로 중복됐다.

## 기존 project 데이터 정리가 필요한 항목 -- 실행은 안 함, 코디네이터 판단으로 남김

- **과제 1·2는 마이그레이션이 필요 없다.** 고침이 저장된 데이터를 바꾸는 게
  아니라 `materialize_editing_session_timeline`이 **읽을 때 계산하는 방식**을
  고쳤을 뿐이다. 컨테이너 재빌드만으로 이 project를 포함한 전체 project가
  즉시 정상화된다(실물로 확인함, 위 "실물 확인" 참고).
- **과제 3은 이미 저장된 데이터가 있다.** `0907-b26195af`의 세 변형본을
  재확인한 결과:
  - `variant-editing_session_001-horizontal`, `variant-editing_session_001-
    vertical_full` -- `conflicts: []` (이미 정리됨, 오늘 다른 세션이 실제
    채팅으로 `story` 충돌을 풀어서 -- `2026-09-18-variant-conflict-
    resolution-actually-wired-to-chat.ko.md` 참고. `apply_variant_patch`의
    기존 딕셔너리 dedup 덕분에 그 한 번의 정상 해결이 13중복을 자동으로
    한 줄로 접었다.)
  - `variant-1a55a20bd4f0477d88e5530abe9e63fc`(kind=`vertical_highlight`,
    숏폼) -- **여전히 `story` 13중복이 남아 있다.** 실행하지 않았지만,
    가장 안전한 정리 방법은 새 코드나 스크립트 없이 **이 변형본에 대해
    `story` 충돌을 한 번 풀거나(`resolve_conflicts: {"story": "keep_local"}`
    또는 `"rebase_master"`) 아무 patch나 한 번 태우는 것**이다 --
    `apply_variant_patch`의 기존 dedup이 그 즉시 13개를 1개로 접는다(위 두
    변형본에서 실제로 그랬다). 이번 세션은 owner 실사용 데이터를 직접
    쓰지 않는다는 원칙으로 이 조작을 실행하지 않았다 -- 코디네이터가
    owner와 상의해서 결정한다.

## 검증

- **RED**: 세 결함 모두 실제 프로젝트 데이터와 같은 모양으로 재현하는 fixture를
  먼저 만들어 실패를 확인한 뒤 고쳤다(과제 2는 처음 시도한 재현이 빗나가서
  실제 postgres 데이터를 직접 대조해 정확한 모양을 다시 지었다).
- **focused**: `tests/test_clip_placement.py`(27건), `tests/
  test_overlay_video_sound.py`+`test_overlay_motion.py`+`
  test_image_overlay_presets_reach_the_render.py`(합쳐서 60건 중 일부),
  `tests/test_output_variants.py`(36건) 전부 통과.
- **broader (frontend 관련 backend)**: `test_editor_timeline_mutations.py`,
  `test_editing_session.py`, `test_blank_editing_session.py`,
  `test_track_states.py`, `test_multitrack_render_generalization.py`,
  `test_scene_transitions.py`, `test_shortform_ripple_speed.py`,
  `test_shorts_layout.py` 202건 전부 통과.
- **broader (backend 전체, 독립 실행)**: `.venv/Scripts/python.exe -m pytest
  -q`(단독, 43분 33초) -- **5147 passed, 56 skipped, 1 xfailed, 3 failed.**
  실패 3건은 전부 `tests/test_owner_ready_script.py`(`owner-ready.ps1` 스모크
  ·자격증명 분류기 타임아웃 시험)로, 이번 세션이 건드린 파일
  (`composition_plan.py`, `output_variants.py`)과 전혀 무관한 영역이다.
  **독립 재실행으로 확인**: 같은 3건만 따로 돌리니 `13 passed`(전부 통과) --
  전체 pytest 5000건 이상 동시 실행 중의 기계 상태(타이밍)에서만 흔들리는
  시험으로 확인됨(`videobox-smoke-timeout-test-fails-by-machine-state.md`
  메모, `2026-09-18-r1-split-render-byte-diff-diagnosed.ko.md`가 이미 겪은
  것과 같은 패턴). 회귀 아님.
- **역방향(실물, API curl로 대체하지 않음, CLAUDE.md §4)**: 컨테이너 재빌드
  두 번 없이 한 번으로 끝냄(`owner-ready.ps1 -Rebuild`, PASS 전부). 실제
  브라우저로 `0907-b26195af`를 열어 (1) 오버레이 clip_id 중복이 없어졌음을
  playback-manifest로 재대조, (2) 내레이션 클립이 더 이상 안 겹침을 재대조,
  (3) 실제 마우스 드래그로 내레이션 클립을 트림해 서버에 저장까지 확인,
  (4) 실행 취소로 실사용 데이터 원상복구. 콘솔에 `RangeError`류 에러 0건.
- **갭**: 요청받은 과제 셋 모두 RED→GREEN→재빌드→브라우저 확인까지 밟았다.
  못 한 것: 과제 3의 stored data 정리는 owner 승인 없이 실행하지 않음(위
  "기존 project 데이터 정리" 참고).
- **배선**: 세 고침 모두 `materialize_editing_session_timeline`/
  `rebase_variant`라는 **기존에 이미 화면·API가 부르는 자리**를 그대로
  고쳤다 -- 새 API나 새 엔드포인트를 추가하지 않았다.

## 재사용 원칙

- 재사용 후보: 과제 1은 broll/bgm/sfx가 이미 쓰던 "이름 충돌 시
  `@track_id` 접미사" 패턴(582~603번 줄)을 그대로 빌렸다. 과제 3은 바로 옆
  `apply_variant_patch`가 이미 쓰던 `conflicts_by_field` 딕셔너리 패턴을
  그대로 빌렸다.
- 실제 반영: `composition_plan.py` 두 곳(오버레이 clip_id 생성 로직,
  fallback 경로의 `own_duration` 계산), `output_variants.py`의
  `rebase_variant` 한 함수. 테스트 파일 둘에 RED 시험 3개 추가.
- 제외: 과제 3의 기존 저장 데이터(`variant-1a55a20bd4f0477d88e5530abe9e63fc`)
  정리 -- owner 실사용 데이터 직접 조작이라 범위 밖, 코디네이터 판단으로
  남김. 과제 1·2는 저장 데이터를 안 건드려도 되므로 마이그레이션 자체가
  불필요.
- 경계 보존: `UI 구조`·`Google Sheets/Drive`·provider 하드코딩 반입 없음.
  이번 세션이 만지지 않은, 이 worktree에서 동시에 작업 중이던 다른 세션의
  미커밋 변경(`apps/web/e2e/*.spec.mjs` 6개 파일)은 건드리지 않았고 커밋에도
  포함하지 않았다.

## 커밋·푸시

커밋 완료(내 파일 넷만: `composition_plan.py`, `output_variants.py`,
`test_clip_placement.py`, `test_output_variants.py`). 이 worktree에 다른
세션의 미커밋 변경(`apps/web/e2e/*.spec.mjs`)이 함께 있어 `git add`를 파일
단위로 했다. 푸시는 안 한다 -- 코디네이터가 fast-forward 확인 후 진행한다.
