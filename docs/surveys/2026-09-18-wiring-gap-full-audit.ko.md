# 유진 배선 누락 전수 조사 (2026-09-18)

owner 지시: 오늘 세션이 `resolve_variant_conflict`가 Hermes 자율 루프 체계
(`yujin_creator_proposals.py`)에만 배선되고 화면 채팅이 실제로 부르는 체계
(`YujinEditingProposalService`)에는 없던 결함을 고쳤다
(`docs/handoffs/2026-09-18-variant-conflict-resolution-actually-wired-to-chat.ko.md`).
같은 패턴이 또 있는지 **다시 깊게 조사**하라는 지시로, "다 고쳐라"가 아니다.

`docs/surveys/2026-09-11-yujin-command-gap.ko.md`(이하 "09-11 조사")가 방법론과
그때의 발견 목록을 이미 남겨 뒀다. 이 문서는 그 뒤(멀티트랙 Phase 4/5, 여러
커밋)로 **오늘 기준 코드를 다시 세어** 갱신한 것이다 — 09-11 문서를 베끼지
않았다. 근거는 전부 파일:줄/grep 결과다.

## 0. 유진은 시스템이 여전히 셋이다 (09-11과 동일)

| 시스템 | 어디서 | 프롬프트가 사는 곳 | 적용 방식 |
|---|---|---|---|
| **A. 직접 편집 대화** | `interpretAndApplySpokenEdit` (`EditorWorkbenchRoute.tsx:2119`) | `yujin_editing_proposal_service.py`의 `_editing_prompt`(코드 안 문자열) | **바로 적용** |
| **B. Director/Creator 대화** | 같은 전송 단추가 동시에 부름 → `submitDirectorMessage` (`EditorWorkbenchRoute.tsx:1913`) → Hermes 컨테이너 | `config/hermes/yujin/SOUL.md` + `skills/videobox-{editor,creator}/SKILL.md` | **후보만**, 사람이 화면에서 적용 |
| **C. 자료 정리 대화** | 편집기 밖, 자료 가져오기 | `routers/footage_organizer.py` | 후보만 |

메시지 한 번이 A와 B를 동시에 부른다. 이 조사는 A·B·(화면)·(SKILL.md 계약)
네 표면을 코드로 직접 세어 교차 대조했다.

## 1. 표면별 실측 개수 (오늘 기준)

### 1-A. 직접 편집 의도 -- **21개** (09-11 당시 16개에서 5개 늘었다)

`packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py`의
`YujinEditingOperation` union(`:339`)을 직접 셌다:

`set_scene_speed`, `set_segment_bounds`, `set_cut_action`, `reorder_segments`,
`set_caption_text`, `set_caption_font`, `set_scene_look`, `set_photo_motion`,
`set_scene_transition`, `set_picture_cleanup`, `set_sound_cleanup`,
`set_scene_transform`, `set_image_overlay`, `remove_image_overlay`,
`apply_media`, `remove_media`, `create_short_form`, `remake_short_form`,
`unfold_short_form`, `render_short_form`, `resolve_variant_conflict`.

셋(스키마·프롬프트·적용기) 다 있는지 21개 전부 `yujin_editing_proposal_service.py`
안에서 grep count(최소 2회, schema const + 프롬프트 문장)로 직접 확인했다 --
**전부 있다.** A는 내부적으로 일관됐다.

### 1-B. Hermes 창작 제안 -- **8 kind, `output_variant` 안에 11 action**

`packages/domain-models/src/videobox_domain_models/yujin_creator_proposals.py`:

- `YujinOperation` union(`:649`): `broll`, `bgm`, `sfx`, `caption`, `voice`,
  `overlay`, `output_check`, `output_variant`.
- `caption`은 `set_text`/`set_style` 2개, `overlay`는
  `explanation_card`/`image`/`table` 3개.
- `output_variant`의 `VariantParameters`(`:560`) 11개:
  `set_crop`, `set_focal`, `set_caption_layout`, `set_safe_area`,
  `correct_audio`, `resolve_variant_conflict`, `set_shorts_title`,
  `select_segments`, `create_short_form`, `remake_short_form`,
  `unfold_to_editing_board`.

적용기(`yujin_creator_proposal_adapter.py:79-134`)가 11개 전부(`select_segments`,
`resolve_variant_conflict`, 나머지 5개 patch action, 그리고 `create_short_form`
류 셋은 `:568` 근처 별도 분기)를 실제로 처리한다 -- 스키마만 있고 적용기가
없는 것은 **없었다.**

### 1-C. SKILL.md(videobox-creator) 계약 -- **B의 8 kind·11 action 전부 문서화됨**

09-11 조사가 지목한 "가장 값싼 구멍"(`output_variant`, `set_crop` 등 SKILL.md에
0건)은 **이미 고쳐져 있다.** `config/hermes/yujin/skills/videobox-creator/SKILL.md`
`:81-151`에 11개 action 전부(`set_crop`부터 `unfold_to_editing_board`까지)가
파라미터·범위·되묻기 지침과 함께 문서화돼 있다. 언제 고쳐졌는지는 이 조사
범위에서 확인하지 않았지만(git blame 안 봄), **현재 상태는 정상**이다. 09-11
문서의 "§2 가장 값싼 구멍"과 "§4 첫 줄"은 더 이상 유효하지 않다 -- 이 문서가
갱신한다.

### 1-D. 화면(UI) 명령 -- `editorCommandPort.ts` + `OutputsPage.tsx`

`apps/web/src/features/editor/editorCommandPort.ts`의 `EditorCommandPort`
인터페이스(`:34-67`)가 화면이 실제로 부르는 편집 명령 전부다. `OutputsPage.tsx`는
별도로 완성본·CapCut·공유·검토 명령을 낸다(§3 참고).

## 2. 교차 대조 -- 실제로 남아 있는 구멍만

### 2-1. 화면(A 후보)엔 있는데 A(직접 편집 채팅)엔 없는 것

| 화면 명령 | 근거(`editorCommandPort.ts`) | A(21개)에 있는가 | 비고 |
|---|---|---|---|
| 트랙 숨김/음소거 | `setTrackStates` (`:49`), 실사용: `EditorWorkbenchRoute.tsx` | **없음** | 09-11부터 안 고쳐짐 |
| 장면 분할/합치기 | `splitNarration`/`mergeNarration` (`:42-43`), 실사용: `EditorWorkbenchRoute.tsx:1174-1175` | **없음** | 09-11부터 안 고쳐짐 |
| 타임라인 배치 드래그 | `setTimelinePlacements` (`:47`) | **없음** | 판단 필요 -- 드래그는 원래 위치 지정 UI라 말로 옮기기 애매함(§4) |
| 도형·화살표·아이콘 오버레이 | `applyOverlay({kind:"shape"})` (`:19`) | **없음**(B에도 없음, 아래 2-2) | 09-11부터 안 고쳐짐 |
| 설명 카드 / 표 오버레이 | `applyOverlay({kind:"explanation-card"\|"table"})` (`:9,17`) | **없음**(B에는 있음, 2-2 참고) | A·B 역할 분담일 수 있음(§4) |
| TTS 후보 적용/지우기 | `applyTtsCandidate`/`clearTtsCandidate` (`:55-56`) | **없음**(B에 `voice` 적용만 있음, 지우기는 B에도 없음) | |
| 자막 색·외곽선·배경·정렬 | `setCaptionStyle` (`:60`) | **없음**(A엔 글꼴·크기만, `SetCaptionFontOperation`) | B의 `caption`/`set_style`엔 있음(§4 역할 분담 후보) |
| 자막 언어(번역본) 선택 | `setCaptionLanguage` (`:66`) | **없음** | |
| 자막 번역 / 더빙 시작 | `captionTranslationProgress.ts`, `dub-narration` 계열 | **없음**(A·B 둘 다) | 09-11부터 안 고쳐짐. 비동기 전용 통로라 애초에 채팅 대상이 아닐 수 있음(§4) |
| 미리보기(previewCaptionStyle) | `:61` | 해당 없음 | 미리보기는 저장이 아니라 명령 대상이 아님 |

### 2-2. 화면(OutputsPage)엔 있는데 A·B 둘 다 없는 것 -- 09-11 §3 "출력 화면에 유진이 없다"가 구조적으로 여전히 유효

`OutputsPage.tsx`에 `Yujin`/`유진` 문자열이 이제 **5건** 있지만(09-11 당시 0건),
전부 "숏폼 버튼을 누르면 유진이 알아서 판단한다"는 **설명 문구**이지 채팅 입력
지점이 아니다(`:1163-1336` 근방). 이 화면 자체에는 채팅창이 없다.

| 화면 동작 | 근거 | A·B 어디에도 없음을 확인한 방법 |
|---|---|---|
| 완성본 만들기(마스터 렌더) | `OutputsPage.tsx:1051` `api.startFinalRender` → `orchestration.py:1765` `start_final_render` | grep `start_final_render` across `director_proposals.py`/`yujin_*` -- 화면 라우터(`routers/outputs.py:285`)에서만 불림 |
| 가로/세로 전체 변형 렌더하기 | `OutputsPage.tsx:734` `api.startVariantRenders` (임의 `variant_ids`) | A의 `render_short_form`(`yujin_editing_proposals.py:326`)은 **`current_short_form_variant`(세로 하이라이트)만** 찾아 렌더한다(`director_proposals.py:753-772`) -- 가로/세로 전체는 대상이 아니다. 코드로 확인 |
| 검토 승인/반려 | `api.getReviewApproval`/승인 흐름 | grep `approve_review`/`review_approval`/`approveReview` in `director_proposals.py`, `yujin_editing_proposal_service.py`, `yujin_creator_proposal_adapter.py` -- 0건 |
| CapCut 초안 내보내기 | `OutputsPage.tsx:1094` `api.startCapcutDraftExport` | 위와 같은 grep, `capcut_draft_export`/`startCapcutDraftExport` -- 0건 |
| CapCut 핸드오프 등록 | `OutputsPage.tsx:1137` `api.registerCapcutDraftHandoff` | 0건 |
| 공유 링크 발급/취소 | `OutputsPage.tsx:1012,1030` `api.createPreviewShare`/`revokePreviewShare` | 0건 |

**우선순위 판단**: 이 여섯은 전부 "판단"이 필요한 창작 결정이 아니라 이미 정해진
산출물을 내보내거나 승인하는 **기계적 마무리 동작**이다. `CLAUDE.md` §2.1의
"차별점은 고르는 일"과는 거리가 있어서, 채팅으로 시키는 효용이 크지 않을 수
있다(§4에서 판단 근거를 더 적었다). 다만 "완성본 만들기"와 "가로·세로 변형
렌더하기"는 owner가 실제로 "이거 렌더해 줘"라고 말할 법한 동작이라 **상대적으로
값이 크다.**

### 2-3. B(Hermes)엔 있는데 A엔 없는 것, 또는 역방향 -- 오늘 발견한 것과 같은 유형

| 항목 | A(21개) | B(8 kind/11 action) | 판단 |
|---|---|---|---|
| `broll`/`bgm`/`sfx` **추천** 자체(제안→승인 목록) | `apply_media`/`remove_media`(직접 배치, 추천 아님) | `broll`/`bgm`/`sfx` kind | **역할 분담**(추천 vs 직접 지정), 버그 아님 |
| `caption` 스타일 전체(`set_style`, 11개 필드) | `set_caption_font`(글꼴·크기만) | `caption`/`set_style` | A가 B보다 좁다 -- 2-1에 이미 반영 |
| `voice`(TTS 후보 적용) | 없음 | `voice` | A에 없음. B는 추천 승인 경로라 "바로 적용" 채팅(A)과 다른 자리일 수 있음 |
| `overlay`(explanation_card/image/table) | `set_image_overlay`(이미지만) | 셋 다 | A가 카드·표를 못 다룸 -- 2-1에 반영 |
| `output_check`(read-only 진단) | 없음 | `output_check` | A엔 읽기 전용 진단이 원래 없어도 됨(직접 편집 성격 아님) |

**오늘 발견한 것과 똑같은 유형(어느 한쪽에만 배선되고 반대쪽엔 스키마조차 없는
것)은 이제 없다** -- `resolve_variant_conflict`는 A·B 양쪽에 다 있고(A:
`yujin_editing_proposals.py:320`, B: `yujin_creator_proposals.py:411`), 서로
다른 적용 경로(A는 즉시 적용, B는 후보→승인)를 정당하게 갖는다. 위 표의
나머지는 애초에 "추천 vs 직접 지정"이라는 의도된 역할 분담으로 보인다(§4).

### 2-4. 멀티트랙 Phase 5(트랙 추가·삭제·순서) -- 아직 "배선 누락"이 아니다

`git log`(`151da8d14`)에 이미 스스로 적어 뒀듯 **화면조차 이 API를 아직 안
쓴다**(Phase 7 예정, 타임라인이 5줄로 코드에 박혀 있음). 이 조사의 기준(화면엔
있는데 채팅엔 없는 것)에 해당하지 않는다 -- 화면에도 없다. 다만 Phase 7에서
화면이 이 API를 쓰게 되면, **그 순간 바로 A·B에도 같이 배선해야
한다**(owner 상시 지시) -- 이번에도 "엔진만 만들고 멈추면 반복"이라고 커밋
메시지가 스스로 경고했다. 다음 세션이 Phase 7을 열 때 이 조사를 참고하라고
남긴다.

## 3. 오늘 직접 고친 것 -- 좁고 명백한 결함 1건

**증상**: A의 21개 의도 중 최근 추가된 숏폼 넷(`create_short_form`,
`remake_short_form`, `unfold_short_form`, `render_short_form`)이 실제로는
정상 적용되는데(백엔드 스키마·적용기·프롬프트 다 있음, §1-A), **owner에게
보여주는 완료 한 줄 요약**(`apps/web/src/features/editor/workbench/
yujinEditingSummary.ts`)에는 이 넷이 빠져 있어서 `"편집 항목을
바꿔요."`라는 의미 없는 문구로 떨어지고 있었다. 이 파일 머리말이 스스로
"명령을 늘릴 때마다 여기를 같이 늘려야 한다"고 경고했는데 그 경고를 못
지킨 자리였다 -- 오늘 `resolve_variant_conflict`를 고칠 때는 이 파일도 같이
고쳤지만(`docs/handoffs/2026-09-18-variant-conflict-resolution-actually-wired-to-chat.ko.md`
§6), 그보다 먼저 들어온 숏폼 넷은 놓쳐 있었다.

**영향**: "말한 편집은 바로 적용된다"(2026-09-01 결정)는 제품 방향에서 이 한 줄이
"무엇이 바뀌었는지 알려 주는 유일한 자리"(파일 머리말)라, owner가 채팅으로
"숏폼 만들어 줘"를 실행해도 실제로는 만들어졌는데 화면엔 "편집 항목을 바꿔요"라고만
떠서 **성공했는지 확신할 수 없었다.** "기다림에는 항상 표시가 있어야 한다"(2026-09-12
상시 지시)와 같은 자리의 문제다.

**고침**: `yujinEditingSummary.ts`의 `yujinEditingOperationSummary`에 4개 분기
추가 -- `create_short_form` → "숏폼을 새로 만들어요.", `remake_short_form` →
"숏폼 장면을 다시 골라요.", `unfold_short_form` → "숏폼을 편집본으로 펼쳐요.",
`render_short_form` → "숏폼을 완성본으로 뽑아요."

**검증**:
- RED: `yujinEditingSummary.test.ts`에 새 테스트("숏폼 넷도 제 이름으로 말한다")
  추가 후 실패를 먼저 봤다(`기대: "숏폼을 새로 만들어요." / 실제: "편집 항목을
  바꿔요."`).
- GREEN: 위 4개 분기 추가 후 통과.
- focused: `yujinEditingSummary.test.ts` 10건 전부 통과.
- broader: `apps/web` 쪽 `src/features/editor` 전체(`vitest run
  src/features/editor`) -- **71 files, 961 tests, 전부 통과.** `npx tsc
  --noEmit` -- 에러 0건.
- **역방향(브라우저) 검증은 하지 않았다** -- 순수 문자열 매핑 함수이고
  입력값은 이미 검증된 pydantic 모델이 주는 고정된 필드 모양(넷 다 파라미터
  없음, `intent`만)뿐이라 실물 편차가 생길 여지가 거의 없다고 판단했지만,
  이것도 **단정이지 실측은 아니다.** 다음에 owner가 실제로 "숏폼 만들어 줘"를
  채팅으로 시키면 화면 한 줄이 맞게 뜨는지 한 번은 눈으로 확인해 볼 가치가
  있다.

## 4. 판단이 필요해 고치지 않은 것 -- 우선순위·비용 추정

심각도는 "owner가 실제로 이렇게 말할 법한가" × "지금 막혀서 owner가 화면으로
돌아가야 하는가"로 매겼다. 비용은 오늘 `resolve_variant_conflict`를 고친
작업량(도메인 모델 1개, 스키마·프롬프트·컨텍스트 각 1곳, 적용기 분기 1곳,
완료 문구 1곳, 총 316개 관련 시험 재확인, 45분 pytest)을 "중간" 기준으로 삼았다.

| # | 항목 | 심각도 | 비용 추정 | 이유 / 대안 |
|---|---|---|---|---|
| 1 | **완성본 만들기(마스터 렌더)를 채팅으로** | 높음 | 중간 -- 새 intent 1개(파라미터 없음, `render_short_form`과 같은 모양), `director_proposals.py`에 분기 추가, `start_final_render_job` 재사용 | "완성본 만들어 줘"는 owner가 실제로 할 법한 말이고, 지금은 화면으로 돌아가야 한다. `render_short_form`이 만든 패턴을 그대로 재사용 가능 |
| 2 | **가로·세로 전체 변형 렌더하기를 채팅으로** | 높음 | 중간 -- `render_short_form`을 일반화하거나 `render_variant(variant_kind)` 신설, `startVariantRenders`가 이미 임의 `variant_ids`를 받으므로 어댑터 쪽 대상 판별만 늘리면 됨 | 숏폼만 되고 가로/세로는 안 되는 비대칭이 어색하다. 다만 "어느 변형본을 뽑을지"가 여러 개일 수 있어(가로+세로 동시 존재) 대상 특정 문구 설계가 필요 |
| 3 | **자막 색·외곽선·배경·정렬을 A(직접 편집)에도** | 중간 | 낮음 -- `SetCaptionStyleOperation`을 B의 `CaptionStyleParameters`(11개 필드) 그대로 재사용해서 추가, `set_caption_font`와 자리만 나누면 됨 | "글자 색 빨갛게 해줘"는 자연스러운 말인데 지금은 글꼴·크기만 된다. 화면엔 이미 있는 기능이라 재사용 후보(B의 스타일 필드)가 명확 |
| 4 | **트랙 숨김/음소거를 채팅으로** | 낮음~중간 | 낮음 -- `set_track_state(track_id, hidden?, muted?)` 신설, `updateEditingSessionTrackStates` 재사용 | 실사용 빈도가 낮아 보이지만(트랙을 직접 껐다 켰다 하는 건 편집 후반 작업), 화면엔 이미 있는 흔한 조작 |
| 5 | **장면 분할/합치기를 채팅으로** | 중간 | 낮음~중간 -- "몇 초에서 잘라줘"는 시간 지정이 필요해 좌표(초) 인자가 있어야 함. `SetSegmentBoundsOperation`과 비슷한 모양 | "이 장면 여기서 잘라줘"는 자연스러운 말이지만, split은 정확한 초 단위 지정이 필요해 음성으로 정확히 짚기 어려울 수 있다 -- **owner 확인 필요**(제품 판단) |
| 6 | **검토 승인/CapCut 내보내기/공유 링크**를 채팅으로 | 낮음 | 낮음(각각) ~ 중간(전부 합치면) | 셋 다 "산출물을 내보내는 마무리 버튼"이라 `CLAUDE.md` §2.1 "차별점은 고르는 일"의 핵심에서 먼 기계적 동작이다. 채팅으로 승인/게시를 시키는 것은 owner가 원치 않을 수도 있다(되돌리기 어려운 외부 게시·공유 쪽은 특히) -- **owner 판단이 꼭 필요한 항목**. 만약 원한다면 CapCut 내보내기가 가장 값싸다(파라미터 없음, `startCapcutDraftExport`만 부르면 됨) |
| 7 | **도형·화살표·아이콘 오버레이를 A·B 둘 다에** | 낮음 | 중간 -- `2026-08-20 승인 5항`이 "좌표·초 단위·키프레임은 밖"이라고 이미 범위를 좁혀 놨으니, 프리셋만 추가하면 이미지 오버레이(`set_image_overlay`)와 같은 모양으로 확장 가능 | 이미지 오버레이는 되는데 도형만 안 되는 비대칭. 다만 실사용 빈도가 낮을 수 있음 |
| 8 | **TTS 후보 적용/지우기를 A에도** | 낮음 | 낮음 -- B의 `VoiceParameters`(candidate_id, asset_id)를 A로 옮기면 됨. "지우기"는 B에도 없어 신설 필요 | B의 추천 승인 경로로 이미 적용 가능하다면 A 중복은 우선순위가 낮음 -- **B 경로가 실제로 화면에서 쓰이는지 먼저 확인 필요**(이번 조사에서 확인 못함) |
| 9 | **자막 언어(번역본) 선택 / 번역·더빙 시작을 채팅으로** | 낮음 | 더빙·번역은 **의도적으로 비동기 전용 통로**(`editorCommandPort.ts:62-64` 주석: nginx 330초 벽 때문에 폴링 전용)라 즉시 적용 모델인 A의 모양과 안 맞을 수 있다. 채팅으로 "시작"만 트리거하고 진행은 화면이 보여주는 절충은 가능 | 제품 판단 필요 -- 09-11부터 그대로 남아 있다 |

## 5. 확인하지 못한 것 (추측으로 쓰지 마라)

- SKILL.md의 11개 `output_variant` action이 **언제** 채워졌는지(git blame 안
  봄) -- 09-11 이후 언젠가로 추정하지만 이 조사에서 날짜를 확정하지 않았다.
- B의 `voice`(TTS 후보 적용) 추천이 실제로 화면 어느 자리에서 승인되는지 --
  이 조사는 스키마·적용기 존재만 확인했고 화면 소비 경로는 안 봤다(§4 8번의
  전제).
- Hermes가 `videobox-editor`와 `videobox-creator` 스킬 중 **어느 쪽으로
  라우팅하는지** -- 09-11이 이미 "이 저장소 밖"이라 확정 못 한다고 적었고,
  이번에도 재확인하지 않았다.
- C(자료 정리, `footage_organizer.py`) 6개 의도는 이번 조사의 핵심 대조
  대상(A·B·화면·SKILL.md)에 포함되지 않았다 -- owner 지시가 지목한 넷에
  C가 없었고, 09-11 이후 변경 이력도 못 봤다. 필요하면 별도 조사로 남긴다.

## 6. 요약

- 대조한 표면: 화면 명령(`editorCommandPort.ts` + `OutputsPage.tsx`), A(21개
  직접 편집 의도), B(8 kind·11 action Hermes 창작 제안), SKILL.md 계약 문서 --
  4개.
- 발견 총계: **직접 고친 것 1건**(§3, 숏폼 넷 완료 문구 누락), **판단 필요로
  남긴 것 9건**(§4, 우선순위 순), **이미 해결된 것으로 확인** 1건(§1-C,
  09-11이 지목한 SKILL.md 구멍).
- 가장 심각해 보이는 것: (1) 완성본 만들기, (2) 가로·세로 전체 변형 렌더하기 --
  둘 다 owner가 실제로 말할 법한데 지금은 화면으로 돌아가야 하고, 비용도
  중간(오늘 고친 패턴 재사용 가능)이라 다음 착수 후보로 적당해 보인다.
- 오늘 발견한 것과 **똑같은 유형**(한쪽 체계에만 스키마가 배선되고 반대쪽엔
  아예 없는 것)은 §2-3에서 확인한 대로 **지금은 없다.**
