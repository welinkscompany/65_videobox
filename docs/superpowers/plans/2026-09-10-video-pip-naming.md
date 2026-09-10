# 얹은 영상을 "그림"이라 부르지 않는다 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 영상을 화면 위에 얹었을 때 타임라인 막대와 인스펙터가 그것을 "그림"·"이미지"가 아니라 **영상**이라고 부르게 한다.

**Architecture:** 오버레이 클립은 사진이든 영상이든 `overlay_type: "image_overlay"` 하나를 쓴다(백엔드에 새 종류를 더하면 응답 모델·CapCut 어댑터·인스펙터 등록부가 함께 흔들린다). 그래서 **부르는 이름만** 클립이 이미 들고 있는 `assetUri`의 확장자로 가른다. 백엔드는 한 줄도 안 바뀐다.

**Tech Stack:** TypeScript, React, Vitest, @testing-library/react

**Spec:** `docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md` §13 (영상 PIP 조사·게이트 개방·역방향 검증 기록)

## Global Constraints

- 저장소 최상위 지침은 `CLAUDE.md`다. 작업 폴더는 `.worktrees/videobox-container-compatibility`이며 main 체크아웃으로 `cd` 하지 않는다.
- **RED → 실패 확인 → 최소 GREEN → 통과 확인**. 실패를 눈으로 못 봤으면 그 시험은 아무것도 안 지킨다.
- 화면에 나가는 말은 개발 용어를 쓰지 않는다(`docs/development-fast-path.ko.md` §10.13). `provider`·`overlay`·`asset` 같은 말을 사용자 문구에 넣지 않는다.
- 프런트 시험은 `apps/web`에서 `npx vitest run <경로>`로 돌린다. 타입검사는 `npx tsc --noEmit -p tsconfig.json`.
- 주석과 커밋 메시지는 한국어로, **왜**를 적는다. 무엇을 했는지는 diff가 말한다.
- 기존 사진 오버레이의 이름(`그림`, `이미지`)은 **한 글자도 바뀌면 안 된다**. 바뀌면 지금 쓰는 편집본의 화면 문구가 함께 바뀐다.
- 커밋은 각 Task 끝에 하나씩. push는 하지 않는다(마지막에 사람이 판단한다).

---

### Task 1: 타임라인 막대가 얹은 영상을 "영상"이라 부른다

**Files:**
- Modify: `apps/web/src/features/editor/timeline/clipNames.ts:17-21` (`ClipContentInput`), `:55-57` (`image_overlay` 분기)
- Modify: `apps/web/src/features/editor/timeline/TimelineDock.tsx` — `clipContentLabel(...)`을 부르는 자리에서 클립의 `assetUri`를 같이 넘긴다
- Test: `apps/web/src/features/editor/timeline/clipNames.test.ts`

**Interfaces:**
- Consumes: 없음(이 계획의 첫 Task)
- Produces: `ClipContentInput`에 `assetUri?: string | null` 칸이 생긴다. Task 2가 같은 판단 규칙을 쓴다 —
  판단 함수를 `clipNames.ts`에서 `export function isVideoAssetUri(assetUri: string | null | undefined): boolean`로 내보낸다.

**배경(구현자가 알아야 할 것):**
`clipContentLabel`은 타임라인 막대에 적을 이름을 만든다. 지금은 `overlayType === "image_overlay"`면 얹은 자산이 사진이든 영상이든 무조건 `"그림"`이다. 실제 화면에서 `오버레이 1 · 그림`으로 찍히는 것을 2026-09-10에 확인했다(얹은 것은 mp4였다).

**판단 규칙**: `assetUri`의 마지막 `.` 뒤 확장자가 `mp4`, `mov`, `m4v`, `webm`, `mkv`, `avi` 중 하나면 영상. 대소문자를 가리지 않는다. 확장자가 없거나 모르면 **사진으로 본다**(지금 동작 유지 — 모르는 것을 영상이라 부르면 기존 편집본의 문구가 바뀐다).

- [ ] **Step 1: 실패하는 시험을 쓴다**

`apps/web/src/features/editor/timeline/clipNames.test.ts`에 더한다. 기존 시험들의 서술 방식(한국어 주석으로 *왜*를 적는다)을 따른다.

```typescript
it("얹은 것이 영상이면 그림이라 부르지 않는다", () => {
  // 2026-09-10에 실제 화면에서 `오버레이 1 · 그림`으로 찍혔다 -- 얹은 것은 mp4였다.
  expect(clipContentLabel({
    overlayType: "image_overlay",
    overlayPayload: {},
    assetUri: "local://projects/p1/assets/asset_1.mp4",
  })).toBe("영상")
})

it("얹은 것이 사진이면 예전 이름 그대로다", () => {
  // 지금 쓰는 편집본의 문구가 바뀌면 안 된다.
  expect(clipContentLabel({
    overlayType: "image_overlay",
    overlayPayload: {},
    assetUri: "local://projects/p1/assets/asset_1.jpg",
  })).toBe("그림")
})

it("무엇인지 모르면 사진으로 본다", () => {
  // 확장자가 없는 옛 자산이 있다. 모르는 것을 영상이라 부르면 멀쩡한 문구가 바뀐다.
  expect(clipContentLabel({
    overlayType: "image_overlay",
    overlayPayload: {},
    assetUri: "local://projects/p1/assets/asset_1",
  })).toBe("그림")
})

it("창작자가 적은 글이 있으면 그 글이 이긴다", () => {
  // 종류 이름은 **적을 것이 없을 때의 대비책**이다. 이 순서가 뒤집히면
  // 창작자가 적은 말이 사라진다.
  expect(clipContentLabel({
    overlayType: "image_overlay",
    overlayPayload: { text: "매대 모습" },
    assetUri: "local://projects/p1/assets/asset_1.mp4",
  })).toBe("매대 모습")
})
```

- [ ] **Step 2: 시험을 돌려 실패를 확인한다**

```bash
cd apps/web && npx vitest run src/features/editor/timeline/clipNames.test.ts
```

넷 중 셋이 통과하고 **첫 번째만 실패**해야 한다(`"그림"` != `"영상"`). 다른 것이 실패하면 시험이 틀린 것이니 시험을 고친다.

- [ ] **Step 3: 통과할 만큼만 고친다**

`ClipContentInput`에 `assetUri?: string | null`를 더하고, `isVideoAssetUri`를 내보내고, `image_overlay` 분기에서 글이 없을 때 `isVideoAssetUri(input.assetUri) ? "영상" : "그림"`을 돌려준다.

- [ ] **Step 4: 시험을 돌려 통과를 확인한다**

`clipNames.test.ts` 전부 통과. 이어서 `npx vitest run src/features/editor/timeline/`로 타임라인 스위트 전체(143건)가 그대로 초록인지 본다.

- [ ] **Step 5: 부르는 자리를 잇는다**

`TimelineDock.tsx`에서 `clipContentLabel`을 부르는 곳에 클립의 `assetUri`를 넘긴다. **여기를 안 이으면 함수만 고쳐지고 화면은 그대로다** — 이 저장소가 반복해 온 "부품은 있는데 부르는 자리가 없다"이다.

`npx vitest run src/features/editor/timeline/` 와 `npx tsc --noEmit -p tsconfig.json` 둘 다 통과해야 한다.

- [ ] **Step 6: 변형 탐침 — 시험이 정말 지키는지 본다**

`isVideoAssetUri`가 늘 `false`를 돌려주게 잠깐 고쳐 놓고 시험을 돌린다. **첫 번째 시험이 죽어야** 한다. 죽지 않으면 그 시험은 아무것도 안 지키는 것이니 시험을 고친다. 확인 뒤 되돌린다.

- [ ] **Step 7: 커밋한다**

---

### Task 2: 인스펙터 절 이름이 얹은 영상을 "이미지"라 부르지 않는다

**Files:**
- Modify: `apps/web/src/features/editor/inspector/inspectorRegistry.ts:278-281` (`image_overlay` 분기의 `label`)
- Test: `apps/web/src/features/editor/inspector/inspectorRegistry.test.ts`

**Interfaces:**
- Consumes: Task 1이 내보낸 `isVideoAssetUri` — **다시 만들지 말고 가져다 쓴다.** 판단 규칙이 두 벌이 되면 타임라인과 인스펙터가 서로 다른 말을 하게 된다.
- Produces: 없음(마지막 Task)

**배경:**
얹은 것을 조정하는 인스펙터 절 이름이 `"이미지"`로 박혀 있다. 영상을 얹은 창작자는 방금 얹은 것을 조정하려고 "이미지"라는 이름을 찾아야 한다. `overlayKind`(`"image"`)와 `fields`는 **바꾸지 않는다** — 자리·크기·움직임 프리셋은 영상에도 그대로 쓰이고, 그 값을 바꾸면 인스펙터 컨트롤 등록부가 함께 흔들린다. **부르는 이름만** 바꾼다.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`inspectorRegistry.test.ts`의 기존 오버레이 시험(`label: "이미지"`를 기대하는 것이 `:123`, `:146`에 있다) 옆에 더한다.

```typescript
it("얹은 것이 영상이면 절 이름이 영상이다", () => {
  // 영상을 얹어 놓고 조정하려면 "이미지"를 찾아야 했다.
  // 종류(`overlayKind`)와 조절 칸은 그대로다 -- 자리·크기·움직임은 영상에도 같다.
})

it("얹은 것이 사진이면 절 이름은 예전 그대로 이미지다", () => {
})
```

기존 시험 두 개(`:123`, `:146`)가 쓰는 클립 fixture를 그대로 본떠 쓰되, `assetUri`만 `.mp4`/`.jpg`로 가른다. fixture에 `assetUri` 칸이 없으면 더한다.

- [ ] **Step 2: 시험을 돌려 실패를 확인한다**

```bash
cd apps/web && npx vitest run src/features/editor/inspector/inspectorRegistry.test.ts
```

새 시험 중 **영상 쪽만** 실패해야 한다.

- [ ] **Step 3: 통과할 만큼만 고친다**

`label`을 `isVideoAssetUri(clip.assetUri) ? "영상" : "이미지"`로. `clipNames.ts`에서 가져온다.

- [ ] **Step 4: 시험을 돌려 통과를 확인한다**

`npx vitest run src/features/editor/inspector/` 전체와 `npx tsc --noEmit -p tsconfig.json`.

- [ ] **Step 5: 변형 탐침**

`label`을 늘 `"이미지"`로 되돌려 놓고 돌린다. 새 영상 시험이 죽어야 한다. 확인 뒤 되돌린다.

- [ ] **Step 6: 커밋한다**

---

### Task 3: 유진도 얹은 것이 영상이라는 것을 알고 말한다

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py` — `_image_overlays_by_segment` 값을 만드는 자리, 그리고 그 값을 프롬프트에 싣는 자리
- Test: `tests/test_yujin_image_overlay_presets.py`

**Interfaces:**
- Consumes: 없음(백엔드라 Task 1·2와 파일이 안 겹친다)
- Produces: 없음

**배경 — 이건 대표님 상시 지시다:**
> "항상 유진이가 같이 실행할수 있게 배선해줘" (2026-09-10)

화면에 기능을 열면 유진 경로도 **같은 작업 안에서** 연다. 영상을 얹는 것은 이미 열었다(커밋 `c43abf4b1`: `_OVERLAYABLE_ASSET_TYPES`). 남은 것은 **말**이다.

유진에게 "지금 얹혀 있는 것"을 알려 주는 줄(`image_overlays_by_segment`)이 사진과 영상을 구별하지 않는다. 그래서 대표님이 "얹은 영상 좀 작게 해줘"라고 하면 유진은 얹혀 있는 것이 영상인지 모른 채 답한다. **목록과 안내문은 한 쌍**이라는 이 저장소의 되풀이된 교훈이 그대로 걸리는 자리다(전환·색감이 정확히 그렇게 틀렸다).

**주의:** 유진이 실제로 부르는 명령 이름(`set_image_overlay`)과 `apply_media`의 `media_type` 값은 **바꾸지 않는다.** 이름을 바꾸면 2026-09-05에 고친 것이 도로 깨진다. 바뀌는 것은 유진이 읽는 **설명 문구**뿐이다.

- [ ] **Step 1: 지금 값이 어떻게 만들어지는지 읽는다**

`yujin_editing_proposal_service.py`에서 `image_overlays_by_segment`를 만드는 함수를 찾는다. 지금 형식은 `asset-1(bottom/right/small/fade_in)` 같은 한 줄이다(`tests/test_yujin_image_overlay_presets.py`의 `_image_overlays_by_segment` 헬퍼가 그 형식을 쓴다). 그 값이 프롬프트 어디에 실리는지도 같이 확인한다.

- [ ] **Step 2: 실패하는 시험을 쓴다**

`tests/test_yujin_image_overlay_presets.py`에 더한다.

```python
def test_yujin_is_told_whether_the_thing_on_screen_is_a_photo_or_a_video() -> None:
    """대표님 상시 지시: 화면에 열면 유진도 같이 연다.

    얹는 것은 이미 열렸다(`_OVERLAYABLE_ASSET_TYPES`). 그런데 유진에게
    "지금 얹혀 있는 것"을 알려 주는 줄은 사진과 영상을 구별하지 않는다 --
    "얹은 영상 작게 해줘"에 유진은 무엇이 얹혀 있는지 모른 채 답한다.
    목록과 지금 걸린 값은 한 쌍이라는 것을 이 저장소는 전환·색감에서
    이미 두 번 배웠다.
    """
```

세션에 영상 자산을 얹은 뒤 프롬프트(또는 그 값을 만드는 함수)를 만들어, 그 안에 **영상이라는 신호**가 들어 있는지 본다. 사진을 얹었을 때는 예전 문구가 그대로여야 한다(시험 두 개로 가른다).

- [ ] **Step 3: 시험을 돌려 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest tests/test_yujin_image_overlay_presets.py -q
```

새로 더한 것 중 **영상 쪽만** 실패해야 한다.

- [ ] **Step 4: 통과할 만큼만 고친다**

얹힌 자산이 영상이면 그 신호를 값에 싣는다. 판단 근거는 세션이 이미 들고 있는 것(자산 주소의 확장자, 또는 자산 종류)을 쓴다 — **새 저장 칸을 만들지 않는다.**

- [ ] **Step 5: 시험을 돌려 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest tests/test_yujin_image_overlay_presets.py tests/test_yujin_can_place_a_photo.py tests/test_yujin_editing_command_evaluation.py tests/test_yujin_editing_proposal_adapter.py -q
```

전부 통과해야 한다(기준선 43건).

- [ ] **Step 6: 변형 탐침**

영상 신호를 다시 빼 놓고 돌린다. 새 시험이 죽어야 한다. 확인 뒤 되돌린다.

- [ ] **Step 7: 커밋한다**
