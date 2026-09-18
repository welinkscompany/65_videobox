**대체됨:** `docs/handoffs/2026-09-18-timeline-click-selection-was-silently-crashing.ko.md`

# task_ -- 변형본 충돌 풀기, 진짜로 채팅 경로에 연결했다 (실물 세 번 확인)

owner 승인(2026-09-18, "진행해줘") 위에서, `2026-09-18-variant-conflict-resolution-
via-chat.ko.md`(task_99becf89)가 "채팅에서도 된다"고 주장했지만 이번 세션 재확인
과정에서 **실제로는 작동하지 않는다는 것을 실물로 다시 확인했다.** 원인을 끝까지
좇아서 고쳤고, 이번에는 실제 브라우저 채팅으로 **세 번** 실물 확인까지 봤다.

## 진짜 원인 -- 컨텍스트 문제가 아니라 배선 자체가 없었다

task_99becf89은 "`YujinCreatorContext`에 지금 충돌 중인 필드 목록을 싣는 것을
범위에서 뺐다"고 적었지만, 이번 세션에서 코드를 끝까지 따라가 보니 **그 컨텍스트
자체가 화면 채팅이 쓰는 경로가 아니었다.**

이 저장소에는 유진이 쓰는, 서로 다른 두 개의 "제안" 체계가 있다:

1. **`yujin_creator_proposals.py` / `yujin_creator_proposal_adapter.py`** --
   Hermes 자율 루프가 후보를 만들고, `director/proposals/{id}/batch-apply`로
   적용하는 체계. `resolve_variant_conflict`는 task_99becf89가 **여기에만**
   추가했다.
2. **`yujin_editing_proposal_adapter.py` / `yujin_editing_proposal_service.py`
   (`YujinEditingProposalService`)** -- 화면의 "유진" 채팅
   (`EditorWorkbenchRoute.tsx`의 `interpretAndApplySpokenEdit` ->
   `api.createYujinEditingProposal` -> `POST .../yujin-editing-proposals`)가
   **실제로 부르는** 유일한 체계. `YujinEditingOperation` union에 20개 intent가
   있었는데 그중에 `resolve_variant_conflict`는 **없었다.**

`tests/test_yujin_editing_short_form.py`의 머리말이 2026-09-12에 이미 똑같은
함정을 경고했다: "`yujin_creator_proposals.py`/`hermes_run_service.py` 쪽에 같은
이름의 action을 추가한 적이 있는데, 그 경로는 `apps/web` 어디에서도 안 불린다."
task_99becf89은 이 경고를 못 보고 같은 함정에 다시 걸렸다.

**결과**: `YujinEditingContext`에 충돌 목록을 아무리 채워도, 모델이 낼 수 있는
JSON 스키마 자체에 `resolve_variant_conflict`가 없어 소용이 없었다. 실제로는
매번 `proposal: null`(애매함, 되물음)로 떨어지거나, 적용해도 자막·컷 같은
세션 편집으로 갈 뿐 변형본(`output_variants`)은 전혀 안 건드렸다.

## 고친 것 -- `YujinEditingProposalService`에 새 intent를 실제로 추가

1. **새 operation** `ResolveVariantConflictOperation`
   (`packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py`)
   -- `variant_id`(문자열), `field`(`VariantField`, 기존 표를 그대로 재사용),
   `decision`(`keep_local`/`rebase_master`). `YujinEditingOperation` union에
   21번째로 추가했다.
2. **스키마·컨텍스트**
   (`packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py`)
   -- `_EDITING_OPERATION_SCHEMA`에 스키마 추가, `YujinEditingContext`(정확히는
   `yujin_editing_proposal_adapter.py`에 정의)에 `variant_conflicts: tuple[
   tuple[variant_id, kind, field], ...]` 필드를 새로 추가하고 `_editing_prompt`에
   `_variant_conflict_catalogue`로 실제 충돌 목록을 실었다 -- 다른 "목록과 지금
   값은 한 쌍" 카탈로그들(색감·전환·화면 맞춤)과 같은 패턴.
3. **컨텍스트 배선**
   (`services/api/src/videobox_api/routers/director_proposals.py`의
   `create_yujin_editing_proposal`) -- `store.list_output_variants(project_id=,
   session_id=)`(읽기 전용, `ensure_output_variants` 아님)로 이 세션에 딸린
   변형본을 읽어 `variant_conflicts`를 채운다.
4. **검증기**(`yujin_editing_proposal_adapter.py`의 `_validate_current_targets`)
   -- `resolve_variant_conflict`는 (a) 다른 intent와 안 섞이고, (b) 전부 같은
   `variant_id`를 가리키고, (c) `variant_id`·`field`가 실제 컨텍스트의 충돌
   목록에 있을 때만 통과한다. 지어낸 값은 `variant_conflict_not_current`로
   막는다 -- 색감·전환이 지어낸 이름을 막는 것과 같은 자리.
5. **적용기 배선**(`director_proposals.py`의 `apply_yujin_editing_proposal_route`)
   -- 숏폼 넷(`create_short_form` 등)과 같은 패턴으로, `resolve_variant_conflict`
   조작만 있으면 세션 편집(`apply_yujin_editing_proposal`)으로 보내지 않고 새
   함수 `_apply_variant_conflict_resolution_from_chat`로 보낸다. 이 함수는 화면
   단추 경로(`routers/output_variants.py`의 `patch_variant`)와 **정확히 같은
   세 걸음**(변형본 읽기 -> `apply_variant_patch` -> 저장)을 밟고,
   `vertical_full`의 `story`/`segment_order` 충돌을 `rebase_master`로 풀 때는
   마스터 장면 스냅샷도 같이 갱신한다(2026-09-17에 단추 경로가 겪은 함정과
   같은 자리, 채팅 경로에서도 같은 실수를 반복하지 않게 주석으로 못박았다).
   다만 이 채팅 경로는 `DirectorProposal`(`proposal_id`)도 같이 소진해야 하므로
   `store.update_output_variant`(단추 경로) 대신 숏폼 넷이 쓰는
   `store.apply_director_variant_proposal_transaction`을 쓴다.
6. **완료 목록 문구**(2차, owner 지시는 아니지만 "화면에 기능을 열면 유진도
   같은 조각에서 쓸 수 있게 배선한다"는 상시 지시에 따라 같이 고쳤다) --
   `apps/web/src/features/editor/workbench/yujinEditingSummary.ts`가
   "명령을 늘릴 때마다 여기를 같이 늘려야 한다"고 스스로 경고하고 있었다.
   `resolve_variant_conflict`에 전용 문구("{항목} 충돌을 마스터 기준으로 다시
   맞춰요."/"{항목} 충돌에서 지금 이 변형본 값을 그대로 둬요.")를 추가했다.
   항목 이름표(`conflictFieldLabel`)는 `VariantConflictPanel.tsx`가 이미 갖고
   있던 것을 **내보내서 재사용**했다(그 파일 머리말의 "같은 어휘를 또 만들지
   말라" 경고를 그대로 따름).

## 검증

### RED -- 실제로 실패를 먼저 봤다

`director_proposals.py`의 `variant_conflicts=tuple(...)` 줄을 잠깐
`variant_conflicts=()`로 되돌리고
`tests/test_yujin_editing_variant_conflict.py`를 돌려서 **실패를 먼저 봤다**
(git stash가 아니라 파일을 직접 되돌렸다가 다시 고쳤다 -- 이 worktree의 git
stash는 다른 세션과 공유돼 안전하지 않다는 지침을 따름):

- `test_variant_conflict_catalogue_reaches_the_real_editing_prompt`:
  `assert variant["variant_id"] in prompt` 실패 -- 프롬프트에 `variant_id`가
  전혀 없었다.
- `test_yujin_resolves_a_variant_conflict_from_the_real_chat_and_clears_it`:
  `assert "proposal_id" in proposal` 실패 -- 응답이 `{"status": "rejected", ...}`
  였다(지어낸 `variant_id`/`field`를 검증기가 막았다).

되돌리고 GREEN 확인 후 계속.

### focused / broader

- `tests/test_yujin_editing_variant_conflict.py`(새 시험 3개),
  `tests/test_yujin_editing_proposal_adapter.py`(14건),
  `tests/test_yujin_editing_short_form.py`,
  `tests/test_api_output_variants.py`,
  `tests/test_yujin_creator_proposal_adapter.py`,
  `tests/test_hermes_yujin_profile_distribution.py`,
  `tests/test_yujin_local_conversation.py`,
  `tests/test_api_yujin_creator_context.py`,
  `tests/test_editor_timeline_mutations.py`,
  `tests/test_shortform_ripple_speed.py`,
  `tests/test_yujin_caption_editing.py`,
  `tests/test_yujin_image_overlay_presets.py` -- 전부 통과
  (227+86+3 = 316건 관련 시험, 1 skip).
- 프론트 유닛 시험: `yujinEditingSummary.test.ts`(9건, 새 케이스 2개 포함),
  `VariantConflictPanel.test.tsx`(3건) -- 통과.
- `npx tsc --noEmit` -- 에러 0건.
- 전체 backend pytest(`.venv/Scripts/python.exe -m pytest -q`, 독립 실행,
  45분 10초) -- **5146 passed, 56 skipped, 1 xfailed, 1 failed.** 실패 1건은
  `tests/test_owner_ready_script.py::test_check_blocks_a_data_root_without_
  legacy_windows_path_headroom`(Windows 경로 길이 여유 검사) -- 이번 세션이
  건드린 적 없는 파일이고(`git diff` 0줄), **단독 실행하면 통과한다**(재확인함) --
  이 저장소가 이미 아는 "전체 pytest는 단독으로 돌려라"(tmp_path 길이가 실행
  순서에 따라 달라지는 것으로 보이는 환경 의존 시험) 패턴과 일치한다. 이번
  변경과 무관하다고 판단한다.

### 역방향(가장 중요) -- 실제 브라우저로 세 번 확인

`scripts/owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild`로 **두 번**
재빌드했다(1차는 백엔드만 반영된 상태로 확인, 2차는 완료 목록 문구까지
반영하려고 다시 함 -- 두 번째 재빌드 전 문구가 왜 안 보이는지 잠깐
헷갈렸는데, 원인은 코드가 아니라 **1차 재빌드 시점에는 프론트 문구를 아직
안 고친 상태였다는 것**이었다. 옛 번들 문제가 아니었다).

1. **`0907-b26195af`("사진 브이로그 실기 0907", 대표님 실사용 프로젝트) --
   세로 전체본(`variant-editing_session_001-vertical_full`)**. 실제 채팅에
   "세로 전체 변형에서 스토리 충돌이 있는데, 마스터 기준으로 다시 맞춰줘" ->
   유진이 항목을 되물음(정당한 되물음: '스토리'가 크롭·자막·안전영역·소리까지
   포함하는지 불분명) -> "장면 구성과 순서(스토리)만 마스터 기준으로
   맞춰줘. 크롭·자막·안전영역·소리는 그대로 둬" -> "적용했어요" 답변.
   전후 `GET .../output-variants` 대조: `variant_revision` 15 -> 16,
   `conflicts` 13건(중복 누적된 낡은 행들, 아래 "발견한 별개 문제" 참고) ->
   0건, `master_segment_ids`가 지금 마스터의 실제 6개 장면으로 갱신됨.
2. **같은 프로젝트, 가로본(`variant-editing_session_001-horizontal`)**.
   "가로 변형에서 장면 구성과 순서(스토리)만 마스터 기준으로 맞춰줘.
   크롭·자막·안전영역·소리는 그대로 둬" -> 한 번에 적용(이번엔 안 되물음
   -- 처음부터 항목을 명시했기 때문). `variant_revision` 14 -> 15,
   `conflicts` 13 -> 0.
3. **`0918-ee6bff78`("완료라벨 확인용 0918", 이번 세션이 검증용으로 새로
   만든 깨끗한 프로젝트)** -- 세션 분할 + `/rebase`로 `story` 충돌 1건만
   딱 만들어서 완료 목록 문구까지 함께 확인. "세로 전체 변형의 장면 구성과
   순서(스토리)만 마스터 기준으로 맞춰줘..." -> `variant_revision` 2 -> 3,
   `conflicts` 1 -> 0. **완료 목록에 "스토리 충돌을 마스터 기준으로 다시
   맞춰요."가 정확히 떴다** -- `yujinEditingSummary.ts`의 라벨 배선까지
   실물로 확인.

세 번 다 `curl` 단건이 아니라 **실제 브라우저에서 실제 채팅창에 타이핑해서
보낸 요청**이고, 전후 API 상태를 대조해 "정말 바뀌었는지"를 쟀다(§4).

## 발견한 별개 문제 -- 고치지 않음, owner 확인 필요

`0907-b26195af`의 세 변형본 모두 `conflicts` 배열에 **`story` 필드가 13번
중복** 들어 있었다(`base_master_revision`이 9->10, 10->11, ..., 21->22로 하나씩
다른 13개 행). `apply_variant_patch`가 `conflicts_by_field = {conflict.field:
conflict for conflict in variant.conflicts}`로 필드를 **딕셔너리 키로** 다뤄서
중복이어도 한 번 풀면 전부 지워지므로 기능은 정상 동작했지만, 정상 상태라면
필드당 충돌은 하나여야 한다(`VariantConflict`가 유일성을 강제하지 않는 모델
자체의 허점으로 보인다). 아마 이 프로젝트가 수많은 재빌드·재확인 세션에서
`rebase` 계열 API를 반복 호출당하며 누적된 것으로 보인다. **이번 세션의
변경과는 무관하다**(코드로 확인: `rebase_variant`/`apply_variant_patch`
어디에도 중복을 만드는 로직이 없고, 이 프로젝트는 과거 세션 기록에 이미
`source_session_revision` 불일치가 있었다고 남아 있다 -- 오래 전부터
지저분했던 데이터로 보인다). 고치지 않았다 -- 범위 밖이고, 실사용에 지장은
없어 보인다(기능은 정상 동작했다). owner가 원하면 별도 조사가 필요하다.

## 다음 세션 백로그

1. 위 "발견한 별개 문제"(중복 충돌 행) -- 급하지 않음, owner 판단 필요.
2. `2026-09-12-ca6dd9ed`의 `source_session_revision` 불일치 -- 여전히 미정리
   (`2026-09-18-variant-conflict-resolution-via-chat.ko.md`부터 이어짐).
3. `task_006f1523`(R1 경계 나누기) -- 여전히 대기, 안 급함.
4. 이번 세션이 검증용으로 만든 프로젝트 둘(`red-green-0918-2e0a065a`,
   `0918-ee6bff78` "완료라벨 확인용 0918")은 owner 실사용 데이터가 아니다 --
   필요 없으면 지워도 된다. 지우지 않았다(권한 밖 판단이라 owner 몫으로
   남긴다).

## 재사용 원칙

- 재사용 후보: 화면 단추 경로(`routers/output_variants.py`의 `patch_variant`,
  `apply_variant_patch`)를 그대로 재사용했다 -- 새 검증 로직을 만들지 않았다.
  숏폼 넷이 이미 쓰던 "세션이 아니라 변형본으로 보내는" 배선 패턴
  (`apply_yujin_editing_proposal_route`의 intent 분기)을 그대로 따랐다.
  완료 목록 문구의 항목 이름표(`conflictFieldLabel`)도 `VariantConflictPanel`
  에서 내보내 재사용했다.
- 실제 반영: 새 operation 타입 1개(domain-models), 스키마·프롬프트·컨텍스트
  필드 각 1곳(core-engine), 컨텍스트 배선 1곳 + 적용기 분기 1곳(api 라우터),
  완료 문구 1곳(프론트).
- 제외: `yujin_creator_proposals.py` 쪽의 기존 `resolve_variant_conflict`
  (자율 루프·`batch-apply` 전용)는 건드리지 않았다 -- 그건 여전히 유효한,
  **다른** 기능(Hermes가 스스로 후보를 만들어 제안하는 경로)이고, 이번에
  고친 것은 창작자가 **말로 직접 시키는** 경로다. 둘을 하나로 합치는 것은
  이번 범위 밖이다.
- 경계 보존: `UI 구조`·`Google Sheets/Drive`·provider 하드코딩 반입 없음.
  `apps/web/src/features/editor/timeline/TimelineDock.tsx`와
  `timeline-dock.test.tsx`에 이 세션 시작 전부터 있던 커밋 안 된 변경(다른
  작업으로 보임, 멀티트랙 Phase 5 관련 추정)은 건드리지 않았고 커밋에도
  포함하지 않았다.

## 커밋·푸시

커밋 완료. 코디네이터가 이어받아 전체 backend pytest를 독립적으로 새로 단독
실행하고, fast-forward 확인 후 push까지 진행한다.
