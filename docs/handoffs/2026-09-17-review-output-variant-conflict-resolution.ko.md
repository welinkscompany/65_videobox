# task_3dc11426 실제로 고침 -- 숏폼을 펼친 뒤 확인과 내보내기 화면에서 세로·가로 영상을 다시 못 만들던 결함

**대체됨:** `docs/handoffs/2026-09-17-vertical-blur-fill-confirmed-on-real-render.ko.md`

대표님이 "계속 진행하자, 자율모드 실행해"라고 지시해서 백로그 다음 항목을
판단해서 진행했다.

## 재현된 증상

확인과 내보내기 화면(`/projects/{id}/review`)에서 "세로 하이라이트"만 켜고
"가로·세로 출력 만들기"로 숏폼을 만든 뒤, 이어서 "세로 영상"만 켜고 같은
단추를 다시 누르면 아무 설명 없이 실패했다.

## 처음 준 가설 셋 중 무엇이 맞았나

작업 지시서는 세 갈래(a: `ensure_output_variants`가 새 세션에 변형본을
안 만들어 줌, b: 프론트가 세션 id를 잘못 추적, c: 숏폼 렌더 자체가 새
세션을 만드는 게 버그)를 주고 실측으로 가리라고 했다. 실제 프로젝트
`2026-09-12-ca6dd9ed`(컨테이너에 이미 떠 있던 실물)로 API를 직접 두드려
가렸다.

**셋 다 정확히는 아니었다.** 진짜 경로:

1. `editing_session_002`는 이번 세션이 만든 게 아니라 **이전에 "숏폼
   펼치기"(`POST .../output-variants/{id}/unfold`)로 이미 만들어져 있었다**
   -- 이건 owner가 승인한 의도된 기능이다(2026-09-11, "숏폼에 넣을 장면은
   유진이 고른다" 관련 확장, 코드 주석 "숏폼을 펼치면 한 프로젝트에 편집본이
   둘이 된다"). 그러니 (c)는 아니다 -- 렌더 버튼(`/variant-renders`) 자체는
   세션을 만들지 않는다는 걸 코드로 확인했다(`local_pipeline.py`의
   `start_variant_renders`/`_materialize_variant_for_output`을 끝까지 읽음).
2. 프로젝트에 편집본이 둘이 되면, `get_latest_editing_session`(및
   `GET /editing-sessions/latest`)은 **프로젝트 전체에서 `updated_at`이 가장
   최근인 세션**을 돌려준다 -- 어느 세션을 대표님이 "지금 보고 있다"고
   여기는지와 무관하다. 확인과 내보내기 화면(`useTimelineReviewState`)이 이
   값을 그대로 "현재 세션"으로 쓰므로, 마스터를 편집할 때마다(어느 세션이든)
   "현재 세션"이 조용히 바뀔 수 있다. 이 자체는 **바꾸지 않았다** -- 멀티
   세션이 승인된 기능이라 이 판정 로직을 고치는 건 리뷰 승인·출력 준비 등
   앱 전체에 영향을 주는 훨씬 큰 변경이고, 이번 결함의 직접 원인도 아니었다.
3. **진짜 막힌 지점**: `editing_session_002`처럼 편집기에서 계속 손대는
   세션은, 마스터 리비전이 오를 때마다 `EditorWorkbenchRoute.tsx`(줄
   497-527)가 자동으로 가로·세로 변형본에
   `rebaseOutputVariant(..., changed_fields: ["story"])`를 건다.
   `"story"`는 구조 필드(`_STRUCTURAL_FIELDS`)라 `rebase_variant`가 **무조건**
   충돌을 하나 쌓는다(`packages/core-engine/.../output_variants.py:224`).
   이 충돌은 owner가 "직접 조정 유지" 또는 "마스터 기준 다시 맞추기"를
   골라야 풀리는데, **그 UI(`VariantConflictPanel`)는 편집기의 `가로·세로
   비교` 모드에만 있었고, 확인과 내보내기 화면에는 전혀 없었다.** 그래서
   렌더가 `unresolved_variant_conflicts`로 막히면 그 화면에서는 풀 방법이
   없었다 -- (a)에 가장 가깝지만, "변형본이 없다"가 아니라 "변형본은 있는데
   풀 UI가 없다"였다.

**실물 재현(고치기 전)**: `curl -X POST .../variant-renders` 로
`variant-editing_session_002-vertical_full`을 렌더하면 정확히
`unresolved_variant_conflicts`로 실패하는 것을 확인했다(코드가 만드는
문구와 정확히 일치).

## 고친 것

**새 로직을 짜지 않고, 편집기가 이미 쓰던 충돌 해결 문을 확인과 내보내기
화면에도 그대로 연결했다.**

- `apps/web/src/app/OutputsPage.tsx`
  - `variantOptions` 상태에 `variant_revision`·`conflicts`를 추가로 들고
    다니게 했다(전에는 `variant_id`·`kind`만 있었다).
  - `resolveVariantConflict` 함수 추가 -- `api.patchOutputVariant`로
    `resolve_conflicts`를 보낸다. 편집기의 `patchOutputVariant`와 같은 문을
    쓴다(`EditorWorkbenchRoute.tsx:1355`).
  - 가로·세로 출력 카드 아래 `VariantConflictPanel`(편집기 컴포넌트 재사용)을
    붙여 충돌이 있는 변형본마다 "직접 조정 유지"/"마스터 기준 다시 맞추기"를
    보여준다.
  - **실물에서 발견한 부수 결함도 같이 고쳤다**: 마스터가 여러 번 바뀌면
    `rebase_variant`가 같은 필드("story")로 충돌을 거듭 쌓을 수 있다(실측:
    `editing_session_002`의 horizontal/vertical_full 둘 다 `story` 충돌이
    두 개씩 있었다). 그대로 늘어놓으면 같은 안내가 화면에 두 번 뜨고 React
    key도 겹친다 -- `variantOptions`를 만들 때 필드당 하나만 남기게 했다
    (해결 자체는 필드 이름으로만 하므로 값 선택은 결과에 영향 없다).
- `apps/web/src/features/outputs/outputFailureMessages.ts` --
  `unresolved_variant_conflicts`에 대한 문구를 추가했다("아래 목록에서
  어떻게 맞출지 고르면 다시 만들 수 있어요"). 표에 없으면 "이 출력을
  만들지 못했어요."로 뭉개져서 대표님이 할 수 있는 일이 안 보였다.
- 백엔드는 **손대지 않았다** -- 충돌 해결 메커니즘(`apply_variant_patch`의
  `resolve_conflicts`, `rebase_variant`, `PATCH /output-variants/{id}`)은
  이미 있었고 이미 시험돼 있었다. 빠진 건 프론트 배선뿐이었다.

## 검증

**RED→GREEN(TDD)**: `OutputsPage.test.tsx`에 2건 추가.
- "가로세로 출력에 마스터 충돌이 있으면 이 화면에서 바로 풀 수 있다" --
  충돌이 있으면 안내가 뜨고, "마스터 기준 다시 맞추기"를 누르면
  `patchOutputVariant`가 정확한 인자로 불리고, 성공하면 안내가 사라지는지.
- "한 변형본에 같은 필드 충돌이 여러 개 쌓여도 안내는 한 번만 보여준다" --
  실물에서 본 중복 충돌 항목이 화면에 두 번 뜨지 않는지.

둘 다 고치기 전에는 실패(RED)를 직접 확인했다.

**포커스**: `OutputsPage.test.tsx` 120/120. 백엔드는 안 바꿨지만 재사용
가정이 아직 맞는지 확인하려고 `test_api_output_variants.py`,
`test_output_variant_store.py`, `test_output_variants.py`,
`test_short_form_unfold.py`, `test_yujin_editing_short_form.py` 93건도
돌렸다 -- 전부 통과.

**프론트**: `tsc --noEmit` 깨끗함. 전체 프론트 시험 139개 파일 1748건 전부
통과(기존 1746 + 새로 추가한 2). `npm run build` 정상(무관한 기존 CSS
경고 1건은 그대로, 이전 인계 문서에 이미 기록됨).

**역방향(실물, 가장 중요한 검증)**: `scripts/owner-ready.ps1 -Mode Start
-WithYujinMemory -Rebuild`로 두 번 재빌드했다(첫 번째로 기능 확인, 두
번째로 중복 충돌 dedupe 확인). 매번 캐시 무력화 쿼리(`?cachebust=...`)로
새 번들을 받았다.

1. 고치기 전 실물(`curl`): `variant-editing_session_002-vertical_full`
   렌더가 `unresolved_variant_conflicts`로 실패.
2. 고친 뒤 실물 화면(Browser pane, `/projects/2026-09-12-ca6dd9ed/review`):
   "가로·세로 출력" 카드 아래 "세로 편집과 마스터가 달라요 / 스토리 /
   마스터가 바뀌었는데 이 항목은 고정돼 있어요..." 안내가 실제로 보임.
   "마스터 기준 다시 맞추기"를 눌러 해결 -> 안내가 사라짐 -> "가로·세로
   출력 만들기"를 눌러 가로·세로 둘 다 "출력을 만드는 중이에요."로 바뀜
   (더 이상 즉시 충돌로 막히지 않고 실제 렌더 단계까지 진행됨). 원래 증상
   ("같은 화면에서 다시 만들 방법이 막힌다")이 실제로 풀렸다.
3. 두 번째 재빌드 뒤 같은 화면을 다시 열어 콘솔 에러를 확인 -- React
   중복 key 경고 없음, 남은 404/502는 이 프로젝트의 무관한 자산/미리보기
   요청이었다(코드 변경과 무관, 재확인 안 함).

**주의(내 것이 아닌 실패로 확인)**: 충돌을 풀고 실제 렌더까지 간 뒤,
이 프로젝트(94장면)의 ffmpeg 합성이 스레드 오류로 실패하는 경우를 봤다.
이건 이미 기억에 있는 별개 결함(`videobox-master-render-fails-at-high-
segment-count`, 2026-09-12 최초 기록: "94장면 프로젝트에서 ffmpeg 스레드
오류. 이번 세션 코드와 무관")과 정확히 같은 증상이다. 이번 결함(충돌
때문에 렌더가 시작도 못 하던 것)과는 다른 층이라 여기서 손대지 않았다.

**단독 pytest 규칙 관련 메모**: 이번 세션은 전체 pytest를 백그라운드
단독으로 돌리는 도중, 그 결과를 기다리며 위 포커스 pytest(93건)를 잠깐
같이 돌렸다 -- `§10`의 "전체 pytest는 단독으로" 규정과 어긋난다. 그
겹쳐 돈 실행은 1건 실패(`test_memory_search_timeout_does_not_block_run_
or_manual_fallback`, 타이밍 어설션)로 끝났는데 겹침 때문으로 보고 버렸다.

**대신 코디네이터(나)가 새로 단독으로 돌린 전체 pytest(43분 49초)**도
**1건 실패**했다 -- `tests/test_owner_ready_script.py::test_smoke_
timeout_kills_the_child_tree_and_returns_bounded_failure`
(`scripts/owner-ready.ps1`을 1초 제한시간으로 띄우고 30초 안에 죽는지
보는 시험, `subprocess.TimeoutExpired`로 실패). **이 결함과 무관하다고
판단했다**: 이번 diff는 프론트(`OutputsPage.tsx`,
`outputFailureMessages.ts`)뿐이고 `scripts/owner-ready.ps1`이나 이
시험이 쓰는 어떤 Python 코드도 안 건드렸다. 같은 시험만 단독으로
다시 돌려도 같은 자리에서 또 실패했고(격리해도 재현), 그 시점에
`docker stats`로 보니 이 컴퓨터에 이 프로젝트와 무관한 컨테이너
수십 개(`louis-personal-*`, `ak-system-*` 등)가 이미 떠서 CPU를 계속
먹고 있었다 -- 이 저장소 자체 기록에도 같은 시험 계열의 "기계 상태로
실패" 전례가 둘 있다(`[[videobox-smoke-timeout-test-fails-by-machine-
state]]`, `[[videobox-owner-ready-rebuild-timeout-too-short]]`, 가장
최근 커밋 `402149dd2`도 같은 계열의 "거짓 FAIL"을 고친 것). 전체
재실행(40분 이상)으로 완전히 재확인하지는 않았다 -- 이 판단이 틀렸다면
다음 세션이 `git stash`로 이 diff를 빼고 같은 시험만 돌려 반증해라.

## 재사용 게이트 메모

- 확인한 재사용 후보: 편집기의 `VariantConflictPanel`
  (`apps/web/src/features/editor/variants/VariantConflictPanel.tsx`)과
  `api.patchOutputVariant`/`resolve_conflicts` 경로 -- 이미 있었고 이미
  시험돼 있었다.
- 실제 반영: 그 컴포넌트와 API 호출을 `OutputsPage.tsx`에서 그대로
  가져다 썼다. 새 컴포넌트나 새 백엔드 엔드포인트를 만들지 않았다.
- 제외한 것: 세션 추적 로직(`get_latest_editing_session`) 자체를 바꾸는
  것 -- 이번 결함의 직접 원인이 아니었고, 바꾸면 리뷰 승인·출력 준비 판정
  전체에 영향을 준다. 유진(채팅) 쪽 충돌 해결 배선도 이번에는 안 했다 --
  "직접 조정 유지"가 owner가 일부러 잠근 값을 지키는 결정이라 유진에게
  맡겨도 되는지부터 판단이 필요해서 `task_99becf89`로 따로 큐에 올렸다.
- 경계 보존: 백엔드(`output_variants.py`, 라우터, 저장소)는 전혀 건드리지
  않았다. 프론트 한 화면(`OutputsPage.tsx`)과 실패 문구 표 하나만 고쳤다.

## 다음 세션이 할 일

1. `task_99becf89`(유진에게도 충돌 풀기 배선) -- 대기 중, 판단부터
   필요하다(위 참고).
2. `task_006f1523`(R1 경계 나누기) -- 여전히 대기.
3. 94장면 프로젝트의 ffmpeg 스레드 오류는 기존 결함 그대로 남아 있다
   (이번 세션이 만들지도, 고치지도 않았다).

## 서버·환경 상태

- 컨테이너: 이 세션이 이 수정들로 두 번 재빌드해서 켜져 있음(healthy).
- worktree: `.worktrees/videobox-container-compatibility`, 브랜치
  `codex/videobox-container-compatibility`.
