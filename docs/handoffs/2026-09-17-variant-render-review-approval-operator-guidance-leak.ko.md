# task_4defd174 실제로 고침 -- 가로·세로 출력 승인이 재시도마다 사라지던 결함

대표님이 이번 세션에서 남은 결함들을 순차적으로, TDD로 처리하라고 지시했다.
이 문서는 그 순서의 첫 번째(`task_4defd174`)다.

## 재현된 증상

`POST /api/projects/{id}/variant-renders`로 세로 전체본(`vertical_full`)을
만들고 검토를 승인해도, 똑같은 요청으로 다시 렌더를 시도하면 매번
`final_output_requires_review_approval`로 다시 막혔다. 프로젝트
`0907-b26195af`의 `variant-editing_session_001-vertical_full`로 5회 연속
재현됐다(앞 세션 인계에서 이미 확인됨). 대조군인 세로 하이라이트(숏폼)
변형본은 같은 문제가 없었다.

## 처음 세운 가설은 틀렸다

처음에는 "매 호출마다 새 timeline_id를 만드는 것 자체가 문제"라고
가정하고, `LocalProjectStore`(파일 저장소)로 같은 흐름을 그대로 재현해
봤다 -- 그런데 거기서는 **승인 후 재시도가 정상적으로 성공했다.** 캐시
재사용 로직(`_materialize_variant_for_output`의 `variant_timeline_needs_
rebuild`) 자체는 멀쩡했다는 뜻이다. 실제 프로젝트(Postgres 저장소)에
직접 API를 두드려 재현해야 했다.

## 진짜 원인

컨테이너에 떠 있는 실제 프로젝트 `0907-b26195af`로 직접 재현하고, 매
호출 전후의 타임라인 원본 JSON을 비교해 찾았다:

**대표님이 마스터 편집본의 `영상 검토` 화면을 한 번이라도 열면**
(`GET /review-snapshots/{job_id}` → `get_review_snapshot` →
`save_operator_guidance`), 유진이 지은 검토 안내문(`operator_guidance`)이
마스터 타임라인의 JSON 파일에 그대로 박힌다.

`_materialize_variant_for_output`/`materialize_variant_route`가 공통으로
쓰는 `build_variant_timeline_payload`(`packages/core-engine/src/
videobox_core_engine/output_variants.py`)는 마스터 타임라인의 필드를
`_MASTER_ONLY_TIMELINE_KEYS`에 있는 것만 빼고 그대로 베끼는데,
`operator_guidance`가 그 제외 목록에 없었다. 그래서:

1. 변형본을 처음 만들 때는 캐시가 없으니 새 timeline을 만들고, 그 안에
   마스터의 `operator_guidance` 값이 복사된다.
2. 검토를 승인해도(`approve_timeline_review`) 승인은 `review_approvals`
   테이블에만 남고 timeline JSON은 안 바뀐다.
3. 다음 호출에서 `variant_timeline_needs_rebuild`가 "지금 다시 계산한
   payload"와 "캐시된 timeline"을 비교하는데, **마스터의 `operator_
   guidance`가 그 사이에 갱신돼 있으면**(재시도 사이에 검토 화면을 다시
   열거나, 유진 안내문이 재생성되면) 두 값이 달라 **항상** 다시 빌드
   대상으로 판정된다.
4. 새로 만든 timeline은 승인 기록이 없는 채 시작하므로, 렌더 워커가
   `_ensure_timeline_ready_for_output`에서 바로 막힌다.

`operator_guidance`는 마스터 자신의 검토 화면을 위한 캐시일 뿐 변형본
렌더 내용과는 무관한데, 그게 변형본 payload 비교에 섞여 들어가 "입력이
안 바뀌었다"는 판정을 영원히 못 하게 만들고 있었다.

## 고친 것

`packages/core-engine/src/videobox_core_engine/output_variants.py`의
`_MASTER_ONLY_TIMELINE_KEYS`에 `"operator_guidance"`와
`"_operator_guidance_reuse_key"` 두 키를 추가했다(주석에 이유를 남겼다).
수정은 이 한 줄짜리 집합에 두 원소를 더한 것뿐이다 -- 재사용 판단·렌더
경로·승인 로직 자체는 건드리지 않았다.

owner 게이트(명시적 거부/재오픈은 몰래 승인하면 안 된다)는 그대로다.
이 고침은 "같은 timeline을 재사용할지"만 바꾸고, 그 timeline의 검토
상태(`review_approvals`)는 여전히 owner가 누른 것만 반영한다 --
`검토 다시 열기`로 되돌린 승인은 캐시 재사용과 무관하게 그대로 되돌려진
채 남는다(아래 시험이 지킨다).

## 검증

**RED→GREEN(TDD)**: `tests/test_api_output_variants.py`에 2건 추가.
- `test_variant_render_review_approval_survives_retry_when_master_has_
  operator_guidance` -- 마스터에 `operator_guidance`를 심어 두고
  `/variant-renders`를 두 번 부르면, 수정 전에는 서로 다른
  `timeline_id`가 나오고(RED로 먼저 확인), 승인이 다음 재시도까지
  안 이어졌다. 수정 후 같은 `timeline_id`를 재사용하고 승인이 유지된다.
- `test_variant_render_reopened_review_stays_blocked_across_reused_
  retries` -- **갭검증**: 캐시 재사용이 owner 게이트를 몰래 뚫지 않는지
  확인한다. 승인 후 `검토 다시 열기`를 누르면, 같은 timeline을 재사용하는
  다음 재시도도 다시 "승인됨"으로 보이면 안 된다는 것을 시험으로 못박았다.

포커스 검증: `test_api_output_variants.py`, `test_output_variant_store.py`,
`test_output_variants.py`, `test_local_pipeline_final_render.py`,
`test_final_render_idempotency.py`, `test_yujin_editing_short_form.py` --
122건 전부 통과.

**역방향검증(실물)**: `scripts/owner-ready.ps1 -Mode Start -WithYujinMemory
-Rebuild`로 이 수정을 올려 재빌드했다. 재빌드 후 프로젝트
`0907-b26195af`로 API를 직접 다시 두드렸다 -- 이번에는 재시도가 **같은
`timeline_011`을 재사용**했고, 승인 후 재시도한 렌더가 `succeeded`로
끝났다(`export_009`, 1080x1920, 8.0초). 화면(`http://127.0.0.1:5173/
projects/0907-b26195af/editor` → `확인과 내보내기` → `가로·세로 출력
만들기`)에서도 실제로 눌러서 확인했다 -- 세로 영상 칸이 "실제 결과를
재생한 뒤 확인해 주세요"로 바뀌었다(렌더가 끝까지 갔다는 뜻). 가로
영상은 마스터 자체 검토가 아직 미승인이라 별도로 막혀 있었는데, 이건
이번 결함과 무관한 정상 동작이다(마스터 검토 게이트는 그대로 지켜야
한다).

**넓은 검증**: 포커스 시험 뒤 `.venv/Scripts/python.exe -m pytest -q`
전체를 백그라운드로 단독 돌렸다 -- **5137 passed, 56 skipped, 1 xfailed,
실패 0건**(42분 14초). 회귀 없음.

## 재사용 게이트 메모

- 확인한 재사용 후보: 없음 -- 기존 캐시 판정 로직(`variant_timeline_
  needs_rebuild`)과 마스터 전용 키 제외 목록(`_MASTER_ONLY_TIMELINE_
  KEYS`)이 이미 있었고, 그 목록에 빠진 항목 두 개를 채우는 것으로 충분했다.
- 실제 반영: `output_variants.py` 한 파일, `_MASTER_ONLY_TIMELINE_KEYS`
  집합에 원소 2개 추가.
- 제외한 것: `review_flags`/`pending_recommendations`/
  `applied_recommendations`는 마스터에서 그대로 물려받아야 하는 실제
  콘텐츠라(제목 띠·크기처럼 "변형본 고유"가 아니라 "장면 자체의 상태")
  건드리지 않았다.
- 경계 보존: UI·라우터·승인 로직·렌더 파이프라인은 손대지 않았다.
  `output_variants.py` 순수 함수 계층 안에서만 고쳤다.
