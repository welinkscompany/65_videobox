# 완성본이 대표님 손에 닿는 마지막 한 걸음 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 만든 완성본을 **맞는 파일로, 이름이 붙은 채로, 내보내기라는 이름의 화면에서** 가져갈 수 있게 한다.

**Architecture:** 렌더는 이미 된다. 고장난 것은 **배달**뿐이다 — 링크가 있는 자리, 그 링크가 고르는 파일, 그리고 파일에 붙는 이름. 셋 다 이미 옳게 하는 형제 코드가 저장소 안에 있다. 새로 설계하지 말고 **그것을 따라가라.**

**Tech Stack:** TypeScript, React, Vitest, Python (FastAPI), pytest

**Spec:** 이 계획서의 §"조사 기록"이 근거다. 2026-09-11 코드 감사 + 실기 확인.

## 조사 기록

| 잰 것 | 결과 |
|---|---|
| 앱 전체에서 MP4를 내려받는 링크 | **한 곳뿐** — `apps/web/src/features/editor/export/ExportPopover.tsx:57` |
| `확인과 내보내기` 화면(`OutputsPage`)의 MP4 링크 | **없음**. 재생(`:1095`)·오디오만(`:1098`)·자막(`:1085`)은 있다 |
| 그 하나뿐인 링크가 고르는 파일 | `ExportPopover.tsx:34-42` — `job_type === "final_render"` 중 **마지막 것**. `input_ref` 필터 없음, 낡음 확인 없음 |
| 가로·세로 변형본의 잡 종류 | **같은 `final_render`** (`packages/core-engine/src/videobox_core_engine/local_pipeline.py:2322`) |
| 같은 판정을 제대로 하는 형제 코드 | `apps/web/src/app/OutputsPage.tsx:481` — `job.input_ref === timelineJob.job_id`로 거른다 |
| MP4 내려받기의 파일 이름 | **없음.** `video/mp4`는 인라인이라 `Content-Disposition`을 안 붙인다 (`services/api/src/videobox_api/content_delivery.py:25-29`) → 브라우저가 `content`로 저장 |
| 이름을 붙이는 형제 경로 | 자막 `routers/outputs.py:128` (`filename="subtitle.srt"`), 오디오 `:327` — **주석에 그 이유까지 적혀 있다** |
| 변형본 내려받기 | **없음.** `VariantOutputCard.tsx:31`은 재생만. 주소는 이미 계산돼 있다(`variantOutputState.ts:28-32`) |

## 왜 이것부터인가

2번(틀린 파일)은 **조용히 틀린다.** 화면 어디에도 신호가 없고, 잘못 받은 영상은 **바깥에 올리고 나서야** 안다. 이 저장소가 가장 비싸게 배운 종류다.

## Global Constraints

- 저장소 최상위 지침은 `CLAUDE.md`. 작업 폴더는 `.worktrees/videobox-container-compatibility`이며 main 체크아웃으로 `cd` 하지 않는다.
- **RED → 실패 확인 → 최소 GREEN → 통과 확인.** 실패를 주장할 때는 **시험 이름과 그 시험이 있는 파일**을 대야 한다.
- backend 시험은 `.venv/Scripts/python.exe -m pytest`. 프런트는 `apps/web`에서 `npx vitest run <경로>`, 타입검사 `npx tsc --noEmit -p tsconfig.json`.
- 화면 문구는 창작자 말로(`docs/development-fast-path.ko.md` §10.13). `job`·`revision`·`variant` 같은 개발 용어를 쓰지 않는다.
- **이미 옳게 하는 형제 코드를 따라가라.** 판정 규칙이나 문구를 두 벌로 만들지 마라 — 이 저장소는 갈라진 사본으로 여러 번 값을 치렀다.
- 주석과 커밋 메시지는 한국어로, **왜**를 적는다.
- 커밋은 각 Task 끝에 하나씩. push는 하지 않는다.

---

### Task 1: 내려받는 링크가 **맞는 파일**을 고르게 한다

**Files:**
- Modify: `apps/web/src/features/editor/export/ExportPopover.tsx` (파일 고르는 자리 `:34-42`, 링크 `:57`)
- Test: `apps/web/src/features/editor/export/` 아래 기존 시험 파일(없으면 새로)

**Interfaces:**
- Consumes: 없음
- Produces: "지금 편집본의 마스터 완성본"을 고르는 규칙. Task 2가 같은 규칙을 쓴다 — **사본을 만들지 말고 나눠 쓸 수 있게 내보내라.**

**배경:**
지금 규칙은 `job_type === "final_render" && status === "succeeded"` 중 **마지막 것**이다. 두 가지가 빠졌다.

1. **`input_ref` 필터** — 가로·세로 변형본도 `final_render`다. 세로를 나중에 만들었으면 `MP4 내려받기`가 세로 영상을 준다. `OutputsPage.tsx:481`이 같은 판정을 **제대로** 한다(`job.input_ref === timelineJob.job_id`). 그 규칙을 가져다 쓰라.
2. **낡음 확인** — 편집을 고친 뒤 다시 안 만들었으면 옛 파일을 그대로 준다. `OutputsPage`는 같은 상황에서 "완성본이 최신 편집본과 달라요"라고 말한다(`:1089`). 어떤 값으로 그 판정을 하는지 찾아 **같은 값**을 쓰라.

**낡았을 때 어떻게 할지는 구현자가 정하고 보고서에 근거를 적어라.** 링크를 감출지, 아니면 "이 파일은 최신 편집본이 아니에요"라고 말하고 그래도 받게 할지. **다만 아무 말 없이 낡은 파일을 주는 것만은 안 된다.**

- [ ] **Step 1: 실패하는 시험을 쓴다**

두 경우를 가른다: (a) 마스터 뒤에 변형본을 만들면 **마스터**를 준다, (b) 편집을 고친 뒤 다시 안 만들었으면 **낡았다고 말한다**.

잡 목록 픽스처는 실제 모양(`job_type`, `status`, `input_ref`, 그리고 낡음 판정에 쓰는 값)을 갖춰야 한다 — 모양이 다르면 시험이 아무것도 안 지킨다.

- [ ] **Step 2: 시험을 돌려 실패를 확인한다** (시험 이름과 파일을 적어라)
- [ ] **Step 3: 통과할 만큼만 고친다**
- [ ] **Step 4: 시험을 돌려 통과를 확인한다** + 타입검사
- [ ] **Step 5: 변형 탐침** — `input_ref` 필터를 빼면 (a)가, 낡음 확인을 빼면 (b)가 죽는지 **둘 다** 본다
- [ ] **Step 6: 커밋한다**

---

### Task 2: `확인과 내보내기` 화면에서 완성본을 받을 수 있게 한다

**Files:**
- Modify: `apps/web/src/app/OutputsPage.tsx` (완성본 자리 `:1095` 근처)
- Test: `apps/web/src/app/OutputsPage.test.tsx`

**Interfaces:**
- Consumes: Task 1이 내보낸 "맞는 파일 고르기" 규칙 — **다시 만들지 마라**
- Produces: 없음

**배경:**
이 화면은 완성본을 재생하고(`:1095`), 오디오만 받게 하고(`:1098`), 자막을 받게 하고(`:1085`), 공유 링크를 만들고(`:1102`), 평가를 받는다(`:1123`). **정작 영상 파일만 못 가져간다.**

상단 띠의 `확인과 내보내기`가 가리키는 유일한 출력 목적지이고 이름이 "내보내기"다. 대표님은 완성본을 눈으로 보고도 편집기로 되돌아가 **글자 없는 아이콘 단추**(`EditorWorkbench.tsx:659`)를 찾아야 한다.

이 화면은 이미 낡음을 알고 말한다(`:1089`). 그러니 Task 1의 판정과 **같은 말을 해야** 한다 — 한 화면이 두 가지로 말하면 안 된다.

- [ ] **Step 1: 실패하는 시험을 쓴다** — 완성본이 있으면 그것을 받는 자리가 화면에 있다. 낡았으면 그 사실을 말한다.
- [ ] **Step 2: 시험을 돌려 실패를 확인한다** (시험 이름과 파일)
- [ ] **Step 3: 통과할 만큼만 고친다**
- [ ] **Step 4: 시험을 돌려 통과를 확인한다** + 타입검사
- [ ] **Step 5: 변형 탐침** — 링크를 지워 놓고 시험이 빨개지는지
- [ ] **Step 6: 커밋한다**

---

### Task 3: 받은 파일에 이름을 붙인다

**Files:**
- Modify: `services/api/src/videobox_api/content_delivery.py` 또는 `services/api/src/videobox_api/routers/outputs.py`의 완성본 전달 자리 — **어느 쪽이 맞는지는 형제 경로를 보고 정하라**
- Test: `tests/` 아래 완성본 내려받기를 덮는 시험(먼저 `grep -rn "final-renders" tests/`로 찾아라)

**Interfaces:**
- Consumes: 없음
- Produces: 없음

**배경:**
`video/mp4`는 인라인 취급이라 `Content-Disposition`이 안 붙는다(`content_delivery.py:25-29`). 그래서 브라우저는 `content`라는 이름으로 저장한다.

**형제 경로 둘이 이미 이 함정을 피하고 있다:**
- 자막: `routers/outputs.py:128` — `FileResponse(..., filename="subtitle.srt")`, **주석에 이유까지 적혀 있다**
- 오디오: `:327` — `filename="{job_id}.m4a"`

주인공인 MP4만 빠졌다. **인라인 재생을 깨지 마라** — 같은 주소를 `<video>`가 재생에 쓰고 있다(`OutputsPage.tsx:1095`). 재생과 내려받기가 같은 주소를 쓰는지 먼저 확인하고, 그렇다면 재생이 계속 되게 하면서 이름을 주는 방법을 고르라(구현자가 정하고 보고서에 근거를 적어라).

이름에 무엇을 넣을지도 정하라. `job_id`(UUID)만으로는 여러 번 받았을 때 어느 영상인지 구분이 안 된다. 프로젝트 이름을 쓸 수 있는지 보고, **파일 이름에 쓰기 위험한 글자(경로 구분자·제어문자 등)를 어떻게 다루는지** 보고서에 적어라.

- [ ] **Step 1: 실패하는 시험을 쓴다** — 완성본을 받으면 응답이 파일 이름을 준다. 재생(인라인)도 계속 된다.
- [ ] **Step 2: 시험을 돌려 실패를 확인한다** (시험 이름과 파일)
- [ ] **Step 3: 통과할 만큼만 고친다**
- [ ] **Step 4: 시험을 돌려 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest tests/test_api.py -q -k "final or render or download or content"
```

- [ ] **Step 5: 변형 탐침** — 이름 붙이는 줄을 지워 놓고 시험이 빨개지는지
- [ ] **Step 6: 커밋한다**

---

## 이 계획이 **안 하는** 것 (일부러, 별도 조각)

- **렌더 진행률 보여주기** — 값은 이미 서버에 있다(`local_pipeline.py:2442`, 잡의 `progress_percent`). 화면이 안 물을 뿐이다. 배달 문제와 별개라 따로 한다.
- **변형본 내려받기 + 영어 오류 코드** — `VariantOutputCard.tsx:31,33`. 같은 배달 문제지만 화면이 다르고, 오류 문구는 창작자 말로 옮기는 별도 작업이 붙는다.
- **빈 프로젝트 막다른 길** — 이미 따로 계획이 있다(`2026-09-11-blank-project-is-a-dead-end.md`).
- **유튜브·텔레그램 업로드** — 구현이 아예 없고, 없는 단추를 안 만드는 것은 의도된 결정이다(`ExportPopover.tsx:14-17`).
