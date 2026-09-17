# task_5d021de9 실제로 고침 -- 변형본 충돌 해결이 장면 스냅샷을 안 갱신하던 결함

대표님이 "task_5d021de9 칩 눌러서 바로 시작해줘"라고 하셔서(칩은 못 누르니)
이 세션에서 바로 이어받았다.

## 원래 진단이 틀렸었다

앞 인계(`2026-09-17-vertical-fill-fit-real-render-check.ko.md`)에서
`task_5d021de9`로 올린 내용은 "변형본의 story 충돌이 revision을 따라잡아도
안 지워진다"였다. **실제로는 틀린 진단이었다** -- 화면에 이미 정상 작동하는
해결 버튼이 있었는데(편집 작업판 → `가로·세로 비교` → `세로` 탭 →
`마스터 기준 다시 맞추기`), 지난 세션엔 그 화면을 안 열어 보고 `/rebase`
API를 직접 두드리다 막힌 것을 결함으로 오인했다.

## 진짜 결함

그 버튼을 실제로 눌러 보니 `conflicts`는 지워지는데(`서버 연결됨`으로
바뀜), 그 직후 렌더를 시도하면 **다른 오류**(`vertical_full_segment_
order_or_membership_changed`)로 다시 막혔다. 원인:
`packages/core-engine/src/videobox_core_engine/output_variants.py`의
`apply_variant_patch`가 `resolve_conflicts: {"story": "rebase_master"}`를
받아도 `conflicts`·`locks`만 지우고 **`master_segment_ids`(장면 목록
스냅샷)는 그대로 뒀다.** `materialize_variant`는 `vertical_full`에 한해
이 스냅샷과 실제 마스터 장면 목록이 정확히 같아야만 통과시키므로
(296~298줄), 마스터가 편집된 뒤에는 충돌을 풀어도 영원히 막혀 있었다.
버튼 이름("마스터 기준 다시 맞추기")이 약속하는 것과 실제 동작이 달랐다.

## 고친 것

- `apply_variant_patch`에 `current_master_segment_ids` 매개변수 추가.
  `vertical_full`이 구조 필드(`story`/`segment_order`) 충돌을
  `rebase_master`로 풀 때만, 넘겨받은 현재 마스터 장면 목록으로
  `master_segment_ids`를 새로 세운다. 이 함수는 저장소를 모르는 순수
  함수라(모듈 머리말 그대로 지킴) 호출자가 직접 읽어서 넘긴다.
- 그 현재 마스터 장면 목록을 뽑는 로직(`segment_ids_from_master`)을
  새 함수로 뽑아 뒀다 -- 저장소 쪽 `ensure_output_variants`가 이미 같은
  추출을 갖고 있어서, 세 번째 자리에 또 베끼면 이 저장소가 반복해서 걸린
  "같은 로직 두 자리" 함정에 또 걸릴 뻔했다(재사용은 안 했다, 위험이
  낮고 저장소 쪽 코드는 이번 범위 밖이라 안 건드림 -- 다만 헬퍼는
  공유되게 core-engine에 뒀다).
- 라우터(`services/api/src/videobox_api/routers/output_variants.py`의
  `patch_variant`)가 `resolve_conflicts`를 포함한 patch를 `vertical_full`
  변형본에 보낼 때만 마스터 세션을 읽어 그 목록을 넘긴다(다른 patch에는
  불필요한 DB 조회를 안 함).

## 검증

**RED→GREEN(TDD)**: `tests/test_output_variants.py`에 2건 추가(마스터
기준 다시 맞추기가 스냅샷을 갱신하는지, `직접 조정 유지`는 스냅샷을
그대로 두는지) -- 새 매개변수가 없어 `TypeError`로 먼저 실패하는 것을
확인한 뒤 구현했다. `tests/test_api_output_variants.py`에 라우터
통합 시험 1건 추가(마스터에 장면을 하나 더한 뒤 충돌→해결→materialize
전체 경로가 실제로 뚫리는지).

**관련 파일 전체(381건, 관련 API·store·숏폼·유진 제안 파일 전부) 회귀
없음.**

**실물 확인**: 이 수정으로 컨테이너를 재빌드(`owner-ready.ps1 -Mode Start
-WithYujinMemory -Rebuild`)한 뒤, 실제로 막혀 있던 프로젝트 둘에서 화면의
그 버튼을 실제로 눌렀다.

- `2026-09-12-742e1924`: `가로·세로 비교` → `세로` 탭 → `마스터 기준
  다시 맞추기` 클릭 → "서버 연결됨"으로 바뀜. API로 재확인:
  `master_segment_ids`가 10개(옛 스냅샷)에서 15개(진짜 현재 마스터와
  일치)로 갱신됨.
- `0907-b26195af`: 같은 버튼 클릭 → 확인. `master_segment_ids`가 실제
  마스터(2개 장면)와 일치.

**전체 backend pytest(단독 실행, 41분 53초)**: 5134 passed, 56 skipped,
1 xfailed, **1 failed** -- `test_handoff_entry_point.py::test_entry_map_
points_at_the_newest_handoff`. 이건 이번 수정과 무관하고 **내가 만든
결함**이다: 같은 날 인계 문서를 두 개 남겨서(`...generalized-to-padding-
threshold`, `...real-render-check`) "하루 하나" 규칙을 깼다. 이 문서를
쓰면서 앞의 두 문서 첫 줄에 대체 표시를 넣어 지금 이 문서 하나로
수렴시켰다 -- 이 규칙을 지키는 시험(`test_handoff_entry_point.py`)만
다시 돌려 초록 확인함(전체 재실행은 안 함, 40분 걸리고 이 한 파일의
결과가 그 규칙과 독립적이라 근거로 충분).

## 못 끝낸 것 -- 완전히 별개의 새 결함을 찾음

렌더를 끝까지 밀어붙여 세로(blur) 배경 실물까지 보려 했으나, 위 수정과
**무관한** 결함에 또 막혔다: `POST /variant-renders`는 호출마다 입력이
안 바뀌어도 매번 새 `timeline_id`를 새로 빌드하는데, 검토 승인
(`review_approvals`)은 `timeline_id` 하나에만 묶인다. 그래서 방금 만든
timeline을 승인해도 다음 재시도는 또 다른 새 timeline이라 또
`final_output_requires_review_approval`로 막힌다 -- 5번 연속 재현.
`task_4defd174`로 새로 큐에 올렸다. `task_acfd8147`(세로 배경 blur 육안
확인)은 이 결함이 풀려야 마저 할 수 있다.

## 다음 세션이 할 일

1. `task_4defd174`(검토 승인이 새 timeline을 못 따라감) -- owner가 칩을
   누르면 시작.
2. 그게 풀리면 `task_acfd8147`(세로 blur 육안 확인)을 마저 -- 장면 수
   적은 프로젝트로, 이번에 고친 변형본들(`0907-b26195af`,
   `2026-09-12-742e1924`)을 바로 쓸 수 있다(둘 다 이미 충돌 없음).
3. `task_e24fda89`(숏폼 만들면 세로영상 출력이 깨짐), `task_006f1523`
   (R1 경계 나누기)은 여전히 대기.

## 서버·환경 상태

- 컨테이너: 이 세션이 이 수정으로 재빌드해서 켜져 있음(healthy).
- worktree: `.worktrees/videobox-container-compatibility`, 브랜치
  `codex/videobox-container-compatibility`.
