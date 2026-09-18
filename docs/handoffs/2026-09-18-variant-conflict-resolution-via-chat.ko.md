**대체됨:** `docs/handoffs/2026-09-18-r1-split-render-byte-diff-diagnosed.ko.md`

# task_99becf89 -- 변형본 충돌 풀기를 유진 채팅에도 열었다

`2026-09-17-vertical-blur-fill-confirmed-on-real-render.ko.md`가 남긴 백로그
1번(유진에게도 변형본 충돌 풀기를 열어 줄지)을 owner 승인(2026-09-18, "진행해줘,
자율모드로") 위에서 구현했다.

## 한 일

1. **새 유진 action `resolve_variant_conflict`**
   (`packages/domain-models/src/videobox_domain_models/yujin_creator_proposals.py`의
   `VariantConflictResolutionParameters`) -- `field`·`decision`
   (`keep_local`/`rebase_master`) 둘 다 **필수**로 받는다. `VariantParameters`
   union에 추가.
2. **적용기 확장**
   (`packages/core-engine/src/videobox_core_engine/yujin_creator_proposal_adapter.py`)
   -- `variant_patch_from_yujin_candidate`가 이 action을 `overrides`가 아니라
   화면 단추와 **정확히 같은 자리**(`{"resolve_conflicts": {field: decision}}`)로
   보낸다. `merged_variant_patch_from_yujin_candidates`도 여러 필드 결정을
   합칠 수 있게 고쳤다.
3. **배선 버그를 하나 새로 만들 뻔한 자리를 미리 잡았다**
   (`services/api/src/videobox_api/routers/director_proposals.py`의
   `batch_apply`) -- `vertical_full`의 `story`/`segment_order` 충돌을
   `rebase_master`로 풀 때 `current_master_segment_ids`를 안 넘기면 충돌
   딱지만 지워지고 렌더는 여전히 막힌다(단추 경로가 2026-09-17에 실제로
   겪은 결함과 같은 종류). RED로 먼저 재현하고(`master_segment_ids`가
   옛 값으로 남는 것을 확인) 고쳤다 --
   `tests/test_api_output_variants.py::test_yujin_resolves_a_vertical_full_story_conflict_through_chat_and_unblocks_materialize`.
4. **애매하면 되묻는 안전장치**
   (`packages/core-engine/src/videobox_core_engine/yujin_local_conversation.py`의
   `_YUJIN_SYSTEM_PROMPT`) -- 오늘 이 세션 앞부분에 고친 "애매한 확인 문장은
   되묻는다"(`그걸로`/`그거`) 지침 옆에, 변형본 충돌도 같은 원칙(어느 필드·
   어느 결정인지 둘 다 분명해야 실행)을 추가했다.
5. **프로필 안내문(세 번째 겹)** -- 처음에 빠뜨렸다가
   `tests/test_hermes_yujin_profile_distribution.py::test_creator_skill_tells_yujin_how_to_cut_a_short_form`의
   동적 스키마 대조(RED)로 잡혔다.
   `config/hermes/yujin/skills/videobox-creator/SKILL.md`에
   `action: resolve_variant_conflict` 계약을 아홉 번째 변형 action 옆에
   추가했다. **이걸 빠뜨리면 스키마·적용기가 있어도 유진은 이 action을
   골라 쓸 방법 자체를 모른다** -- 이 저장소가 반복해서 겪은 함정
   (`docs/surveys/2026-09-11-yujin-command-gap.ko.md`)과 같은 종류다.

## 검증

- `tests/test_yujin_creator_proposal_adapter.py`(58건),
  `tests/test_api_output_variants.py`(36건, 새 통합 시험 포함),
  `tests/test_hermes_yujin_profile_distribution.py`(62건+1 skip),
  `tests/test_yujin_local_conversation.py`(37건) -- 전부 통과.
- 4번 안전장치는 RED로 먼저 확인했다: 현재 시스템 프롬프트가
  `"변형본 충돌"`·`"짐작해서 실행하지 말고 정확히 되물어라"` 문구를
  **아직 안** 담고 있는 상태에서 시험이 실패하는 것을 본 뒤 프롬프트를
  고쳤다.
- 3번 배선 버그는 고치기 전 코드로 되돌려 RED를 실측했다
  (`master_segment_ids`가 `["seg-a","seg-b"]`로 남는 것 확인, 기대값은
  `["seg-a","seg-new","seg-b"]`) -- 우연히 통과하는 시험이 아님을 확인.
- 컨테이너를 **두 번** 재빌드했다 -- 첫 번째는 SKILL.md 편집이 끝나기
  전에 시작해서 옛 프로필이 실렸다(`grep resolve_variant_conflict` 0건).
  `docker exec`으로 실제 배포된 프로필 파일을 직접 대조해 잡았고, 두
  번째 재빌드 뒤 1건 확인.
- 실제 브라우저(Browser pane)로 `2026-09-12-ca6dd9ed`("실측 숏폼
  2026-09-12") 프로젝트를 열어 확인:
  - `확인과 내보내기`(Outputs) 화면과 `편집`(Editor) 화면 양쪽에서
    `VariantConflictPanel`이 실제 크롭 충돌("세로 편집과 마스터가
    달라요")을 정확히 그린다.
  - 편집 화면의 "유진" 채팅에 "세로 전체 변형에서 크롭 충돌이 있는데,
    마스터 기준으로 다시 맞춰줘"를 실제로 타이핑해 보냈다.

## 못 끝낸 것 -- 채팅으로 실제 충돌 풀기까지는 못 봤다

**로컬 모델 호출이 타임아웃으로 계속 실패해서, "명시적 문장에 실제로
풀린다"는 마지막 단계는 실물로 못 봤다.** 원인을 먼저 내 탓인지 확인했다 --
아니다:

- `director/conversations/.../messages`가 부르는 로컬 구조화 호출의
  기본 타임아웃은 **30초** (`LocalOnlyRuntimeConfig.timeout_seconds`,
  `packages/core-engine/src/videobox_core_engine/settings.py:382`).
- 같은 프로젝트의 같은 대화 기록에 **2026-09-12·09-13에도 같은
  `LOCAL_TIMEOUT`**이 남아 있다(내가 손대기 전, 완전히 다른 메시지
  "숏폼 다시 만들어줘"에서). 이번 세션에서 새로 만든 아주 작은 시험
  프로젝트(장면 1개)로도 똑같이 30초에 걸려 실패했다.
- `lms ps`로 GPU 경합이 없는 것(모델 하나만 `GENERATING`)까지 확인했다 --
  27B 모델이 이 하드웨어에서 구조화 JSON을 만드는 데 30초보다 오래
  걸리는 것 자체가 원인이다. 내 SKILL.md 추가(문단 하나)가 이미 빠듯한
  여유를 조금 더 깎았을 수는 있지만, **같은 실패가 내 변경 전에도
  100%였다.**
- 즉 `resolve_variant_conflict`만의 문제가 아니라 **이 대화 경로
  전체**(크롭·초점·숏폼 다시 만들기 등 기존 output_variant action
  전부)가 지금 이 컨테이너·모델 조합에서 30초 안에 거의 못 끝난다는
  뜻이다 -- 더 큰, 별도 범위의 문제다.

**대신 확인한 것**: 스키마·적용기·배선을 API를 통해 유진이 만드는 것과
똑같은 모양의 요청으로 직접 재현해 통과시켰다
(`test_yujin_resolves_a_vertical_full_story_conflict_through_chat_and_unblocks_materialize`).
이것도 "화면 확인"의 대체는 아니다 -- `§4`의 "API 단건 확인은 화면 확인을
대체하지 못한다" 원칙을 그대로 지킨다고 주장하지 않는다. 실제로 채팅
답이 오는 것까지는 **못 봤다.**

## 실제 프로젝트에 남은 시험 흔적 -- owner 확인 필요

`2026-09-12-ca6dd9ed`("실측 숏폼 2026-09-12")는 대표님이 실측에 쓰던
진짜 프로젝트다. 충돌 패널이 실제로 뜨는지 보려고 그 프로젝트의 세로
전체본 변형(`variant-editing_session_002-vertical_full`)에 크롭 잠금 +
덮어쓰기 + 가짜 리비전 상승을 만들었다가, 정상 API(`resolve_conflicts`
keep_local → unlock → override 제거)로 되돌렸다.

**충돌·잠금·크롭 덮어쓰기는 다 지워졌다** -- 지금 그 변형을 보면 깨끗하다.
다만 **`source_session_revision`이 12로 남아 있고 실제 마스터 편집 세션은
11이다** (내가 시험용으로 `/rebase`를 12로 미리 불렀기 때문). 실제 마스터
세션 값을 직접 고치는 시도(읽기 포함)는 권한 시스템이 "공유 자원 수정"으로
막아서 못 했다 -- 이 저장소가 실행 중인 컨테이너의 실 데이터라 자동
차단된 것으로 보인다.

**영향**: 이 상태에서 이 변형을 지금 바로 `완성본 만들기`(materialize)
하면 `stale_master_revision` 오류가 날 수 있다. 마스터 편집 세션이
다음 실제 편집으로 리비전 12에 닿으면(활발히 편집 중인 프로젝트라
곧 그럴 가능성이 크다) 숫자가 우연히 다시 맞아 저절로 없어지는
불일치지만, 그 전에 시도하면 막힌다. 확인·필요하면 직접 고치는 결정은
대표님 몫으로 남긴다 -- `/api/projects/2026-09-12-ca6dd9ed/output-variants/variant-editing_session_002-vertical_full/rebase`를
실제 마스터 리비전으로 다시 부르면 정리된다.

## 다음 세션 백로그

1. **로컬 구조화 LLM 호출 타임아웃(30초)이 실사용에 너무 짧다** -- 이번
   세션에서 새로 확인. `director/conversations` 채팅 경로 전체(내
   `resolve_variant_conflict`뿐 아니라 기존 크롭·초점·숏폼 액션 전부)가
   지금 이 값으로는 거의 항상 실패할 수 있다. `VIDEOBOX_LOCAL_RUNTIME_
   TIMEOUT_SECONDS` 환경변수로 조정 가능한 걸 확인했다 -- 얼마로 올릴지,
   부작용은 없는지는 별도 조사가 필요하다(이번 범위 밖이라 안 건드렸다).
2. `2026-09-12-ca6dd9ed`의 `source_session_revision` 불일치 확인/정리
   (위 항목).
3. `task_006f1523`(R1 경계 나누기) -- 여전히 대기, 안 급함.

## 재사용 원칙

- 재사용 후보: 화면 단추 경로(`routers/output_variants.py`의
  `patch_variant`, `apply_variant_patch`의 `resolve_conflicts` 처리)를
  그대로 재사용했다 -- 새 검증 로직을 만들지 않았다.
- 실제 반영: 유진 쪽 action 이름·필드만 새로 추가했고, 적용 로직은
  기존 `apply_variant_patch`를 그대로 부른다.
- 제외: `YujinCreatorContext`에 "지금 실제로 충돌 중인 필드 목록"을
  싣는 것은 이번 범위에서 뺐다 -- 없어도 `apply_variant_patch`가 적용
  시점에 `unknown_variant_conflict:{field}`로 최종 확인하므로 안전하고,
  범위를 넓히면 컨텍스트 예산·프롬프트 크기 문제(위 타임아웃 문제와
  직결)가 더 커진다.
- 경계 보존: `UI 구조`·`Google Sheets/Drive`·provider 하드코딩 반입 없음.

## 커밋·푸시

커밋 완료(`f22e42700`). 코디네이터가 이어받아 전체 backend pytest를
독립적으로 새로 단독 실행했다 -- **5143 passed, 56 skipped, 1 xfailed,
실패 0건**(41분 53초). 회귀 없음. fast-forward 확인 후 push 완료.
