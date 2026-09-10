# 얹은 것을 다시 조정해도 앞서 고른 게 사라지지 않게 한다 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 유진에게 "얹은 것 좀 작게"라고 말했을 때 **앞서 정한 자리가 조용히 사라지지 않게** 한다. 동시에 화면에서 `안 고름`으로 되돌리는 길은 그대로 남긴다.

**Architecture:** 지금은 "칸이 없음" 하나가 **두 가지 뜻**으로 쓰인다 — 화면에서는 "지워줘"(창작자가 `안 고름`을 골랐다), 유진에게는 "그 얘긴 안 했다". 같은 신호라 한쪽을 고치면 다른 쪽이 깨진다. 그래서 **세 상태로 가른다**: 칸 없음 = 지금 값 유지, `null` = 지워서 안 고름으로, 값 = 그걸로. 화면은 넷을 항상 실어 보내되 안 고른 것은 `null`로 보내고, 유진은 말한 것만 싣는다.

**Tech Stack:** Python (FastAPI, pydantic v2), TypeScript/React, pytest, Vitest

**Spec:** `docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md` §14.4 (이 결함의 발견 경위와 왜 그때 같이 못 고쳤는지)

## Global Constraints

- 저장소 최상위 지침은 `CLAUDE.md`. 작업 폴더는 `.worktrees/videobox-container-compatibility`이며 main 체크아웃으로 `cd` 하지 않는다.
- **RED → 실패 확인 → 최소 GREEN → 통과 확인.** 실패를 주장할 때는 **시험 이름과 그 시험이 있는 파일**을 대야 한다.
- backend 시험은 반드시 `.venv/Scripts/python.exe -m pytest`. 프런트는 `apps/web`에서 `npx vitest run <경로>`, 타입검사 `npx tsc --noEmit -p tsconfig.json`.
- **"안 고름"은 실제 상태다.** 프리셋을 안 고른 오버레이는 화면 가운데에 가득 얹히고, 그건 `middle`/`center`를 **명시적으로 고른 것과 다른 모습**이다(`InspectorControls.tsx`의 `IMAGE_PRESET_UNSET` 선택지가 "화면 가득"이라고 적혀 있다). 그러니 "안 고름"으로 되돌리는 길이 사라지면 안 된다.
- **지금 저장돼 있는 오버레이의 모습이 바뀌면 안 된다.** 열쇠가 없는 옛 오버레이를 기본값으로 채우지 않는다.
- **미리보기 캐시 지문을 깨지 마라.** `CompositionPlan.canonical_dict()`가 지문의 입력이다.
- `set_image_overlay`·`remove_image_overlay`·`apply_media`의 `media_type` 값은 이름을 바꾸지 않는다.
- 화면 문구에 개발 용어를 쓰지 않는다. 새 낱말을 지어내기 전에 이미 있는 문구를 먼저 찾는다.
- **유진도 같이 배선한다** — 대표님 상시 지시(2026-09-10).
- 주석과 커밋 메시지는 한국어로, **왜**를 적는다.
- 커밋은 각 Task 끝에 하나씩. push는 하지 않는다.

---

### Task 1: 엔진 — 안 준 프리셋은 지금 값을 그대로 둔다

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/editing_session.py` — `update_segment_image_overlay`(1575줄 근처)
- Test: `tests/test_overlay_presets_are_not_erased.py` (새 파일)

**Interfaces:**
- Consumes: 없음
- Produces: `update_segment_image_overlay`가 프리셋 넷에 대해 **세 상태**를 받는다. 신호 이름과 모양을 Task 2~4가 그대로 쓴다.

**배경(구현자가 알아야 할 것):**

지금 `update_segment_image_overlay`는 안 준 프리셋의 **열쇠를 안 적는다**. 그런데 `_upsert_segment_overlay`가 옛 오버레이를 통째로 버리고 새 payload만 남기므로, 결과적으로 안 준 프리셋은 **지워진다**. 그래서 유진에게 "오른쪽 아래로" 한 다음 "좀 작게"라고 하면 앞서 정한 자리가 조용히 없어진다.

**핵심 함정 — 이걸 놓치면 화면이 깨진다:** 그냥 "안 주면 유지"로 바꾸면 안 된다. 화면에는 `안 고름` 선택지가 있고(`InspectorControls.tsx`의 `IMAGE_PRESET_UNSET`), 창작자가 그걸 고르면 지금은 **그 칸을 빼서** 보낸다. "안 주면 유지"로 바꾸는 순간 화면에서 `안 고름`으로 되돌릴 방법이 사라진다.

그래서 **세 상태**가 필요하다:

| 부르는 쪽이 하는 것 | 뜻 |
|---|---|
| 인자를 아예 안 준다 | 지금 값을 그대로 둔다 |
| `None`을 준다 | **지워서 "안 고름"으로** |
| 값을 준다 | 그 값으로 |

`None`이 이미 "안 줌"의 기본값이므로 **파수꾼(sentinel) 기본값**이 필요하다. 모듈 수준에 `_KEEP` 같은 것을 하나 두고 기본값으로 쓴다. **`preserve_source_audio`는 건드리지 마라** — 그건 `False`가 진짜 값이라 지울 상태가 없고, 이미 "안 주면 유지"로 맞게 돌고 있다.

지금 값을 읽어 오는 방법은 이미 있다: `_current_image_overlay_preserve_source_audio`(같은 파일)가 `_iter_matching_overlay_containers`로 그 일을 한다. **그 순회를 다시 짜지 마라** — 네 번째 사본을 만들면 안 된다.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`tests/test_overlay_presets_are_not_erased.py`를 만든다. 시험 다섯:

1. 자리를 정해 얹은 뒤 **크기만** 다시 주면, 자리가 **그대로 남는다**. (이게 대표님이 겪는 결함이다.)
2. 넷을 아무것도 안 주면 넷 다 그대로 남는다.
3. **`None`을 명시적으로 주면 그 칸이 지워진다** — 화면의 `안 고름`이 이 길로 온다.
4. 값을 주면 그 값으로 바뀐다.
5. 프리셋을 한 번도 안 고른 오버레이는 **열쇠가 안 생긴다**(기본값으로 채우지 않는다).

- [ ] **Step 2: 시험을 돌려 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest tests/test_overlay_presets_are_not_erased.py -q
```

1·2번이 실패해야 한다. 3·5번은 지금도 통과할 수 있다 — 그건 정상이다(지금 동작이 우연히 3번과 같다).

- [ ] **Step 3: 통과할 만큼만 고친다**

- [ ] **Step 4: 시험을 돌려 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest tests/test_overlay_presets_are_not_erased.py tests/test_editing_session.py tests/test_yujin_image_overlay_presets.py tests/test_image_overlay_presets_reach_the_render.py tests/test_overlay_video_sound.py -q
```

**기존 시험이 깨지면 주의 깊게 보라.** 지금 "안 주면 지워진다"에 기대고 있는 시험이 있을 수 있다. 그 시험이 지키던 것이 **의도된 계약이었는지** 아니면 **결함을 굳혀 놓은 것이었는지** 판단하고, 보고서에 그 판단과 근거를 적어라. 시험을 고쳤다면 왜 고쳐도 되는지 적어라.

- [ ] **Step 5: 변형 탐침**

"안 주면 유지"를 다시 "안 주면 지움"으로 되돌려 놓고 돌린다. 1·2번이 죽어야 한다. 그다음 `None`을 "유지"로 읽게 해 놓고 돌린다. 3번이 죽어야 한다. **둘 다 확인해야 한다** — 하나만 보면 세 상태 중 둘만 지켜진다.

- [ ] **Step 6: 커밋한다**

---

### Task 2: API — 세 상태가 HTTP를 건너간다

**Files:**
- Modify: `services/api/src/videobox_api/models.py` — `ImageOverlayRequest`
- Modify: `services/api/src/videobox_api/routers/editing_session.py` — `PATCH .../image-overlay`
- Modify: `services/api/src/videobox_api/orchestration.py`, `packages/core-engine/src/videobox_core_engine/editing_session_and_regeneration.py` — 사이 층
- Test: `tests/test_api.py` (오버레이 시험이 모여 있는 자리를 먼저 찾아라)

**Interfaces:**
- Consumes: Task 1의 세 상태 신호
- Produces: `PATCH .../image-overlay`가 세 상태를 가른다. Task 3(화면)이 이 계약대로 보낸다.

**배경:**

JSON에서 "칸이 아예 없음"과 "`null`"은 다른 것인데, pydantic의 `str | None = None`은 **둘을 구분하지 못한다.** pydantic v2의 `model_fields_set`이 그 구분을 준다 — 요청 본문에 실제로 실려 온 칸 이름만 담긴다.

이 저장소는 **엔진만 넓히고 API 스키마를 빼먹어 422가 난 적이 있다**(2026-09-05). 층을 하나도 빼먹지 마라: 요청 모델 → 라우터 → orchestrator → 서비스 메서드 → 엔진 함수.

- [ ] **Step 1: 실패하는 시험을 쓴다**

세 상태를 각각 HTTP로 밟는다: (a) 칸을 빼고 보내면 지금 값이 남는다, (b) `null`로 보내면 지워진다, (c) 값으로 보내면 그 값이 된다.

- [ ] **Step 2: 시험을 돌려 실패를 확인한다** — 시험 이름과 파일을 보고서에 적어라.

- [ ] **Step 3: 통과할 만큼만 고친다**

- [ ] **Step 4: 시험을 돌려 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest tests/test_api.py tests/test_editing_session.py tests/test_overlay_presets_are_not_erased.py -q
```

- [ ] **Step 5: 변형 탐침** — (a)를 깨서(칸을 빼면 지워지게) 시험이 빨개지는지 본다.

- [ ] **Step 6: 커밋한다**

---

### Task 3: 화면 — `안 고름`으로 되돌리는 길을 지킨다

**Files:**
- Modify: `apps/web/src/features/editor/inspector/InspectorControls.tsx` — 오버레이 저장 payload(1315줄 근처)
- Modify: `apps/web/src/features/editor/editorCommandPort.ts`, `apps/web/src/api.ts` — 세 상태를 그대로 흘린다
- Test: `apps/web/src/features/editor/inspector/InspectorControls.test.tsx`, `apps/web/src/features/editor/editorCommandPort.test.ts`

**Interfaces:**
- Consumes: Task 2의 API 계약
- Produces: 없음

**배경:**

지금 화면은 값이 있을 때만 칸을 싣는다:
```tsx
...(imagePresets.vertical ? { vertical: imagePresets.vertical } : {}),
```
새 계약에서 "칸 없음"은 **"지금 값 유지"**가 되므로, 이대로 두면 창작자가 `안 고름`을 골라도 아무 일이 안 일어난다.

화면은 **넷의 지금 상태를 늘 알고 있다**(`imagePresets`). 그러니 넷을 **항상** 싣되, 안 고른 것은 `null`로 싣는다. 화면에는 "말 안 함"이라는 상태가 없다 — 창작자가 화면을 보고 저장을 누르는 순간 넷 다 의사 표시가 된 것이다.

- [ ] **Step 1: 실패하는 시험을 쓴다** — 창작자가 `안 고름`을 골라 저장하면 그 칸이 `null`로 실려 나간다. 값을 고르면 그 값이 실린다.

- [ ] **Step 2: 시험을 돌려 실패를 확인한다** — 시험 이름과 파일을 적어라.

- [ ] **Step 3: 통과할 만큼만 고친다**

- [ ] **Step 4: 시험을 돌려 통과를 확인한다** — 인스펙터·workbench 스위트 + `npx tsc --noEmit -p tsconfig.json`

- [ ] **Step 5: 변형 탐침** — `null` 싣는 것을 도로 빼 놓고 시험이 빨개지는지 본다.

- [ ] **Step 6: 커밋한다**

---

### Task 4: 유진 — 말한 것만 바꾸고, "원래대로"도 말할 수 있다

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/editing_session.py` — `_apply_yujin_editing_operations`의 `set_image_overlay` 자리
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py` — 안내문(`_image_overlay_catalogue`)
- Test: `tests/test_yujin_image_overlay_presets.py`

**Interfaces:**
- Consumes: Task 1의 세 상태
- Produces: 없음

**배경 — 이게 대표님이 실제로 겪는 결함이다:**

유진의 `SetImageOverlayOperation`은 프리셋 넷이 전부 선택이고, 말 안 한 것은 `None`으로 온다. 지금은 그 `None`이 그대로 엔진에 흘러가 **지워진다**. Task 1 뒤에는 `None`이 "지워줘"라는 뜻이 되므로, **그대로 흘리면 결함이 더 나빠진다** — 반드시 "말 안 한 것"과 "지우라고 한 것"을 갈라서 넘겨야 한다.

유진의 명령 스키마에는 지금 '되돌림' 값이 없다. **`preserve_source_audio`가 이번 조각에서 이미 같은 모양을 만들어 뒀다**(`None` = 안 말함) — 그 자리를 본보기로 삼아라.

안내문도 같이 고친다: 말 안 한 프리셋은 그대로 남는다는 것, 그리고 "가운데로 되돌려줘" 같은 말을 어떻게 표현하는지. **목록과 안내문은 한 쌍이다** — 이 저장소가 전환·색감·자산 목록에서 세 번 겪었다.

- [ ] **Step 1: 실패하는 시험을 쓴다**

(a) 유진이 크기만 말하면 앞서 정한 자리가 **남는다**, (b) 유진이 "원래대로"를 표현하면 그 칸이 지워진다, (c) 안내문이 "말 안 한 것은 그대로 남는다"를 말한다.

(b)를 어떤 모양으로 표현할지는 구현자가 정하고 보고서에 근거를 적어라 — 스키마에 값을 더할지, 아니면 기존 `remove_image_overlay` + 다시 얹기로 충분한지. **필요 없는 것을 만들지 마라**(YAGNI): 창작자가 실제로 "위치 설정을 없애줘"라고 말할 일이 있는지부터 생각하고, 없다고 판단하면 (b)를 만들지 않고 그 판단을 근거와 함께 적어라.

- [ ] **Step 2: 시험을 돌려 실패를 확인한다** — 시험 이름과 파일을 적어라.

- [ ] **Step 3: 통과할 만큼만 고친다**

- [ ] **Step 4: 시험을 돌려 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest tests/test_yujin_image_overlay_presets.py tests/test_yujin_can_place_a_photo.py tests/test_yujin_editing_command_evaluation.py tests/test_yujin_editing_proposal_adapter.py tests/test_overlay_presets_are_not_erased.py -q
```

- [ ] **Step 5: 변형 탐침** — 유진의 `None`을 도로 그대로 흘리게 해 놓고 (a)가 죽는지 본다.

- [ ] **Step 6: 커밋한다**

---

## 이 계획이 **안 하는** 것 (일부러)

- **도형 오버레이(`shape_overlay`)는 안 건드린다.** 화면이 프리셋 넷을 늘 통째로 보내므로(`...shapeOverlay`) 같은 결함이 없다. 유진 경로에 같은 모양이 있는지는 확인만 하고, 있으면 원장에 적되 이번에 고치지 않는다.
- **`preserve_source_audio`는 안 건드린다.** `False`가 진짜 값이라 "지움" 상태가 없고, 이미 "안 주면 유지"로 맞게 돈다.
