# 얹은 영상의 원래 소리도 쓸 수 있게 한다 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 장면 위에 얹은 영상의 **원래 소리**를 완성본에 함께 싣는 칸을 연다. 기본값은 지금과 같은 **무음**이다.

**Architecture:** 촬영본(b-roll)에 이미 똑같은 기능이 있다 — `preserve_source_audio`. 새 개념을 만들지 않고 **그것을 오버레이 클립에도 그대로 태운다.** 렌더러의 오디오 그래프에도 b-roll 분기가 이미 있으므로, 오버레이 분기는 그 모양을 그대로 따른다(소리 스트림이 없는 원본을 건너뛰는 방어까지 포함).

**Tech Stack:** Python (FastAPI, pydantic), TypeScript/React, pytest, Vitest, ffmpeg 필터 그래프

**Spec:** `docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md` §13 (영상 PIP를 연 경위·역방향 검증), 그리고 2026-09-11 조사 결과: 얹은 영상은 렌더에서 **무음**이고 켤 칸이 세 층에 아예 없다.

## Global Constraints

- 저장소 최상위 지침은 `CLAUDE.md`. 작업 폴더는 `.worktrees/videobox-container-compatibility`이며 main 체크아웃으로 `cd` 하지 않는다.
- **RED → 실패 확인 → 최소 GREEN → 통과 확인.** 실패를 눈으로 못 봤으면 그 시험은 아무것도 안 지킨다.
- backend 시험은 반드시 `.venv/Scripts/python.exe -m pytest`. 프런트는 `apps/web`에서 `npx vitest run <경로>`, 타입검사는 `npx tsc --noEmit -p tsconfig.json`.
- **기본값은 꺼짐이다.** 지금 있는 편집본의 완성본이 한 프레임도, 한 샘플도 달라지면 안 된다. 얹은 영상 소리가 갑자기 내레이션을 덮으면 그게 사고다.
- **미리보기 캐시 지문을 깨지 마라.** `CompositionPlan.canonical_dict()`가 지문의 입력이다 — 기본값일 때는 새 열쇠가 실리면 안 된다(`composition_plan.py`의 `_canonical_item`이 `track_order`에 쓰는 수법과 같다).
- 화면 문구에 개발 용어를 쓰지 않는다(`docs/development-fast-path.ko.md` §10.13). 이미 있는 문구 `이 영상의 원래 소리도 함께 쓰기`(`InspectorControls.tsx:864`)를 그대로 재사용한다 — 새 말을 지어내면 같은 것을 두 이름으로 부르게 된다.
- **유진도 같이 연다** — 대표님 상시 지시(2026-09-10): "항상 유진이가 같이 실행할수 있게 배선해줘". 화면에만 열고 끝내지 않는다.
- 주석과 커밋 메시지는 한국어로, **왜**를 적는다.
- 커밋은 각 Task 끝에 하나씩. push는 하지 않는다.

---

### Task 1: 엔진 — 얹은 영상이 소리 설정을 들고 렌더까지 간다

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/editing_session.py` — `update_segment_image_overlay`(1598줄 근처)와 그것이 정규화하는 자리(1550-1555, 1581-1597)
- Modify: `packages/core-engine/src/videobox_core_engine/composition_plan.py:687` — 오버레이 클립을 만드는 자리
- Modify: `packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py` — 오디오 그래프 루프(1350줄 근처)와 오버레이 입력 등록(1552-1560)
- Test: `tests/test_overlay_video_sound.py` (새 파일)

**Interfaces:**
- Consumes: 없음
- Produces: 오버레이 payload에 `preserve_source_audio: bool` 칸이 생긴다. Task 2(API)와 Task 3(화면), Task 4(유진)가 같은 이름을 쓴다. **b-roll과 같은 이름이어야 한다** — 이미 있는 개념이다.

**배경(구현자가 알아야 할 것):**

얹은 영상은 지금 **무음**이다. 렌더러의 오디오 루프(`ffmpeg_final_renderer.py:1350`)가 `broll`과 `bgm/sfx`만 다루고 `overlay` 분기가 아예 없다.

b-roll 분기(`:1352-1381`)가 그대로 본보기다. 특히 두 가지를 반드시 따라 해라:

1. `controls["preserve_source_audio"]`가 꺼져 있으면 `continue` — **기본은 무음**.
2. 원본에 소리 스트림이 없으면 `continue` (`soundless_source_clip_ids`). 없는 `[N:a]`를 그래프에 넣으면 **ffmpeg가 통째로 실패한다**. 지금 그 집합은 b-roll 입력에서만 만들어지므로(`:1653` 근처) 오버레이 입력 등록(`:1552-1560`)에서도 같은 판정을 해야 한다. 얹는 것이 **사진일 수도 있다** — 사진에는 소리 스트림이 없다.

또 하나: 오버레이 클립에는 `source_in_sec`/`source_out_sec`이 안 실려서 기본값(0 ~ 장면 길이)으로 채워진다(`composition_plan.py:965-969`). b-roll 오디오 분기는 그 값으로 `atrim`을 건다 — 오버레이에도 같은 값이 오므로 동작은 하지만, 계산이 맞는지 시험으로 확인해라.

- [ ] **Step 1: 실패하는 시험을 쓴다 — 렌더 그래프에 소리가 실리는가**

`tests/test_overlay_video_sound.py`를 만든다. `CompositionItem`/`CompositionPlan`을 직접 만들어 `build_plan_filter_graph`를 부르는 방식은 `tests/test_image_overlay_presets_reach_the_render.py:145` 근처가 본보기다.

시험 셋을 쓴다.

1. `preserve_source_audio=True`인 오버레이 클립이 있으면 오디오 그래프에 그 클립의 소리가 섞인다.
2. **꺼져 있으면(기본값) 그래프가 예전과 한 글자도 같다** — 이게 제일 중요하다. 기본값이 움직이면 지금 있는 완성본이 전부 바뀐다.
3. 얹은 것이 **사진**이면(소리 스트림 없음) 켜져 있어도 그래프에 `[N:a]`가 안 들어간다 — 넣으면 ffmpeg가 통째로 죽는다.

- [ ] **Step 2: 시험을 돌려 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest tests/test_overlay_video_sound.py -q
```

1번과 3번이 실패하고 2번은 통과해야 한다(2번이 실패하면 시험이 틀린 것이다).

- [ ] **Step 3: 통과할 만큼만 고친다**

세 자리를 잇는다: 세션이 값을 보관하고 → `composition_plan`이 클립의 `media_controls`에 실어 보내고 → 렌더러가 오디오 루프에서 읽는다.

**지문 보호**: 기본값(꺼짐)일 때 `canonical_dict()`에 새 열쇠가 실리면 안 된다. `_canonical_item`이 `track_order`를 0일 때 빼는 것과 같은 수법을 쓴다. 이걸 확인하는 시험도 하나 더한다.

- [ ] **Step 4: 시험을 돌려 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest tests/test_overlay_video_sound.py tests/test_image_overlay_presets_reach_the_render.py tests/test_ffmpeg_final_renderer.py tests/test_editing_session.py -q
```

- [ ] **Step 5: 변형 탐침**

`preserve_source_audio` 검사를 지워서 **항상 소리를 싣게** 해 놓고 돌린다. 2번 시험(기본값 불변)이 죽어야 한다. 그다음 소리 스트림 검사를 지워 놓고 돌린다. 3번이 죽어야 한다. 확인 뒤 되돌린다.

- [ ] **Step 6: 커밋한다**

---

### Task 2: API — 화면이 그 값을 저장할 수 있다

**Files:**
- Modify: `services/api/src/videobox_api/models.py:1380-1388` (`ImageOverlayRequest`)
- Modify: `services/api/src/videobox_api/routers/editing_session.py:896` 근처 (`PATCH .../image-overlay`)와 그 아래 orchestrator 호출
- Test: `tests/test_api_editing_session.py` 또는 오버레이 관련 기존 API 시험 파일(먼저 찾아볼 것)

**Interfaces:**
- Consumes: Task 1의 `preserve_source_audio` 칸
- Produces: `ImageOverlayRequest`가 `preserve_source_audio`를 받는다. Task 3(화면)이 이 이름으로 보낸다.

**배경:**
`ImageOverlayRequest`는 지금 `expected_revision, asset_id, text, vertical, horizontal, size, motion, proposal_id, candidate_id`만 받는다. **넓힌 값은 세 층을 다 봐야 한다**는 것이 이 저장소의 교훈이다(2026-09-05에 엔진만 넓히고 API 스키마를 빼먹어 422가 났다).

**안 보내면 어떻게 되는가**를 반드시 정해라: 지금 화면과 유진은 이 칸 없이 요청을 보낸다. 그때 **이미 켜 둔 설정이 꺼지면 안 된다**(빈칸을 기본값으로 덮는 사고 — `editorCommandPort.ts:81`에 같은 사고 기록이 있다). `None`과 `False`를 구분해라.

- [ ] **Step 1: 실패하는 시험을 쓴다**

세 가지를 가른다: (a) 켜서 보내면 저장된다, (b) 안 보내면 **이미 켜 둔 것이 그대로 남는다**, (c) 꺼서 보내면 꺼진다.

- [ ] **Step 2: 시험을 돌려 실패를 확인한다**

- [ ] **Step 3: 통과할 만큼만 고친다**

- [ ] **Step 4: 시험을 돌려 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest tests/test_api_draft_readiness.py tests/test_api.py -q -k "overlay or image"
```
(먼저 어느 파일이 이 엔드포인트를 덮는지 `grep -rn "image-overlay" tests/`로 찾아라.)

- [ ] **Step 5: 변형 탐침** — (b)를 깨서(안 보내면 꺼지게) 시험이 빨개지는지 본다.

- [ ] **Step 6: 커밋한다**

---

### Task 3: 화면 — 얹은 영상에도 그 칸이 뜬다

**Files:**
- Modify: `apps/web/src/features/editor/inspector/inspectorRegistry.ts` — `image_overlay` 분기의 `fields`
- Modify: `apps/web/src/features/editor/inspector/InspectorControls.tsx:856-866` (이미 있는 체크박스)와 저장 경로
- Modify: `apps/web/src/features/editor/editorCommandPort.ts`, `apps/web/src/api.ts` (요청에 칸 싣기)
- Test: `apps/web/src/features/editor/inspector/InspectorControls.test.tsx`, `inspectorRegistry.test.ts`

**Interfaces:**
- Consumes: Task 2의 API 칸
- Produces: 없음

**배경:**
체크박스와 문구는 **이미 있다** — `InspectorControls.tsx:856-866`의 `이 영상의 원래 소리도 함께 쓰기`. 새로 만들지 마라. 지금 그것이 안 뜨는 이유는 `showMediaField("preserveSourceAudio")`가 `isMediaKind`(`broll|bgm|sfx`)로 막혀 있고 오버레이 target의 `fields`에 그 이름이 없기 때문이다.

**얹은 것이 사진이면 이 칸을 띄우지 마라** — 사진에는 소리가 없다. 눌러도 아무 일 안 일어나는 단추를 두지 않는 것이 이 저장소의 규칙이다(타임라인 트랙 단추가 같은 이유로 종류마다 다르다). 사진/영상 판단은 이미 한 벌 있다: `apps/web/src/features/editor/assetKind.ts`의 `isVideoAssetUri`. **두 번째 사본을 만들지 마라.**

- [ ] **Step 1: 실패하는 시험을 쓴다** — 얹은 **영상** target에는 칸이 뜨고, 얹은 **사진** target에는 안 뜬다.

- [ ] **Step 2: 시험을 돌려 실패를 확인한다**

```bash
cd apps/web && npx vitest run src/features/editor/inspector/
```

- [ ] **Step 3: 통과할 만큼만 고친다**

- [ ] **Step 4: 시험을 돌려 통과를 확인한다** — 인스펙터 스위트 전체 + `npx tsc --noEmit -p tsconfig.json`

- [ ] **Step 5: 변형 탐침** — 사진 쪽 조건을 빼서 사진에도 칸이 뜨게 해 놓고, 시험이 빨개지는지 본다.

- [ ] **Step 6: 커밋한다**

---

### Task 4: 유진 — 말해서도 켤 수 있다

**Files:**
- Modify: `packages/videobox-domain-models/src/videobox_domain_models/yujin_editing_proposals.py` (`SetImageOverlayOperation`) — 정확한 경로는 `grep -rn "class SetImageOverlayOperation"`로 찾을 것
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py` — 명령 스키마(`_EDITING_OPERATION_SCHEMA`의 `set_image_overlay` 항목)와 안내문(`_image_overlay_catalogue`)
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py` — 검증
- Modify: `packages/core-engine/src/videobox_core_engine/editing_session.py`의 `_apply_yujin_editing_operations` — 값 전달
- Test: `tests/test_yujin_image_overlay_presets.py`

**Interfaces:**
- Consumes: Task 1의 세션 칸
- Produces: 없음

**배경 — 이건 대표님 상시 지시다:**
> "항상 유진이가 같이 실행할수 있게 배선해줘" (2026-09-10)

유진 경로는 겹이 셋이고 **셋 다** 봐야 한다: 명령 정의, 안내문·목록, 검증·전달. **안내문을 안 고치면 받을 수 있게 해 놔도 유진은 안 고른다** — 이 저장소가 전환·색감·자산 목록에서 세 번 겪었다.

**지금 걸린 값도 같이 실어라.** `image_overlays_by_segment`가 지금 프리셋 넷을 한 줄로 적는다(`asset-1(bottom/right/small/fade_in)`). 소리가 켜져 있다는 것도 거기 보여야 "얹은 영상 소리 꺼줘"가 통한다. 목록만 주고 지금 값을 안 주면 유진은 "소리가 켜져 있지 않습니다"라고 답한다 — 켜져 있는데도.

- [ ] **Step 1: 실패하는 시험을 쓴다** — (a) 유진이 소리를 켜서 얹는 편집안을 낼 수 있다, (b) 프롬프트에 **지금 켜져 있다는 것**이 실린다.

- [ ] **Step 2: 시험을 돌려 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest tests/test_yujin_image_overlay_presets.py -q
```

- [ ] **Step 3: 통과할 만큼만 고친다** — 명령 이름(`set_image_overlay`)은 **바꾸지 않는다.**

- [ ] **Step 4: 시험을 돌려 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest tests/test_yujin_image_overlay_presets.py tests/test_yujin_can_place_a_photo.py tests/test_yujin_editing_command_evaluation.py tests/test_yujin_editing_proposal_adapter.py -q
```

- [ ] **Step 5: 변형 탐침** — 안내문에서 소리 얘기를 빼 놓고 (b) 시험이 죽는지 본다.

- [ ] **Step 6: 커밋한다**

---

### Task 5: 미리 보기 — 얹은 영상도 `원본 열기`에 뜬다

**Files:**
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx:854-858` (`auditionMediaKind`)
- Test: 같은 폴더의 workbench 시험(`grep -rn "auditionMediaKind\|소스 확인" apps/web/src --include=*.test.tsx`로 덮는 파일을 찾을 것)

**Interfaces:**
- Consumes: `assetKind.ts`의 `isVideoAssetUri` (사본 금지)
- Produces: 없음

**배경:**
```ts
return overlayType === "image_overlay" ? null : "video";   // :857
```
판정을 **자산 종류가 아니라 오버레이 종류로** 한다. 얹은 것이 영상이어도 종류는 `image_overlay`라 `null`이 되고, `null`이면 목록에서 통째로 빠진다(`:507`의 `return mediaKind ? [{...}] : []`). 그래서 `소스 확인` 절에 `원본 열기` 단추가 안 생긴다.

사진일 때 `null`인 것은 **맞는 동작이다** — 재생할 것이 없다. 영상만 갈라내면 된다.

백엔드는 이미 주소를 준다(`editor_playback_manifest.py:83`이 오버레이 클립의 `asset_id`도 담아 `:127`에서 `asset_urls`를 만든다). 막는 것은 이 한 줄이다.

- [ ] **Step 1: 실패하는 시험을 쓴다** — 얹은 영상은 목록에 뜨고, 얹은 사진은 안 뜬다.
- [ ] **Step 2: 시험을 돌려 실패를 확인한다**
- [ ] **Step 3: 통과할 만큼만 고친다**
- [ ] **Step 4: 시험을 돌려 통과를 확인한다** + `npx tsc --noEmit -p tsconfig.json`
- [ ] **Step 5: 변형 탐침** — 사진도 뜨게 해 놓고 시험이 빨개지는지 본다.
- [ ] **Step 6: 커밋한다**

---

## 이 계획이 **안 하는** 것 (일부러)

- **여러 개 얹기.** 지금은 두 번째를 얹으면 첫 번째가 조용히 사라진다(`editing_session.py:1967-1980`이 같은 종류를 빼고 하나 더한다). 사진 기준으로는 **의도된 계약**이고, 여럿을 허용하면 인스펙터가 "어느 것을 고칠지" 가려야 한다 — 2026-09-11에 고친 `영상`/`얹은 영상` 이름 충돌과 같은 종류의 문제가 다시 생긴다. 별도 조각으로 제대로 할 일이다.
- **얹은 영상의 구간 고르기.** 지금은 항상 원본 앞에서부터 장면 길이만큼 쓴다(`composition_plan.py:687`이 `source_in_sec`/`source_out_sec`을 안 싣고 `:965-969`의 기본값이 채운다). 중간 구간을 고르려면 인스펙터에 칸 둘(`시작`/`끝`)이 더 필요하고, 그건 소리보다 뒤 문제다.
- **소리 크기 조절.** 이번에는 켜고 끄는 것만 연다. 음량은 켜 놓고 써 본 뒤에 필요하면 더한다(YAGNI).
