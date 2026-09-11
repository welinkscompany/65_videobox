# 세로 영상이 세로가 아니다 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `세로 영상`을 만들면 **정말 세로로** 나온다. 지금은 마스터와 **바이트까지 같은** 가로 영상이 나온다.

**Architecture:** 변형본 타임라인이 마스터 타임라인의 복사본이라 출력 크기(`output`)가 마스터 그대로다. 크기는 `kind`에서 다시 정해야 한다. 값을 넣을 자리는 이미 있다(`_ORIENTATION_OUTPUT_SIZES`, `timeline["output"]`) — **새 배관이 아니라 빠진 한 줄이다.**

**Tech Stack:** Python, FFmpeg, pytest

**Spec:** `CLAUDE.md` §2.1이 `가로세로 변형`을 제품 범위로 못박았다. 지금 그 기능이 거짓말을 한다.

## 조사 기록 (2026-09-11 실물 측정)

컨테이너를 새로 세우고 `project-e6c75c36`에서 가로·세로 변형본을 **실제로 성공시킨 뒤** 받아서 쟀다.

| 잰 것 | 결과 |
|---|---|
| 완성본 / 가로 / 세로 크기 | **셋 다 1920×1080** |
| 셋의 md5 | **전부 `fabad09e7d51d4334c2cd71185eb9d34`** — 바이트까지 같다 |
| 렌더러가 크기를 어디서 읽나 | `composition_plan.py:932` — `timeline.get("output")` |
| 그 값을 누가 넣나 | `local_pipeline.py:1534` — `build_timeline`에서 `_ORIENTATION_OUTPUT_SIZES[orientation]` |
| 변형본 타임라인은 | `_materialize_variant_for_output`(`local_pipeline.py:2205-2226`)이 마스터 payload를 통째로 베낀다. 제외 키는 `timeline_id`·`project_id`·`file_uri`·`created_at`·`summary`뿐이라 **`output`도 `output_mode`도 딸려 온다** |
| 그래서 실물 값 | `timeline_016.output == {"width":1920,"height":1080}`, `output_mode == "review"` (세로 변형본인데도) |
| 진짜 종류는 어디 있나 | `timeline_016.source_variant_id == "variant-…-vertical_full"` — 이것만 믿을 수 있다 |

## Global Constraints

- 저장소 최상위 지침은 `CLAUDE.md`. 작업 폴더는 `.worktrees/videobox-container-compatibility`이며 main 체크아웃으로 `cd` 하지 않는다.
- **RED → 실패 확인 → 최소 GREEN → 통과 확인.** 실패를 주장할 때는 **시험 이름과 그 시험이 있는 파일**을 대야 한다.
- backend 검증은 반드시 `.venv/Scripts/python.exe -m pytest`. bare `pytest` 결과는 근거로 쓰지 않는다.
- **전체 pytest는 단독으로 돌린다**(약 40분). 조각을 닫을 때만.
- **크기를 주장하려면 재라.** `ffprobe`로 실제 픽셀을 재지 않은 주장은 근거가 아니다. 이 결함이 오래 안 보인 이유가 바로 아무도 안 쟀기 때문이다.
- 주석과 커밋 메시지는 한국어로, **왜**를 적는다.
- 커밋은 각 Task 끝에 하나씩. push는 하지 않는다.

---

### Task 1: 변형본 타임라인이 자기 크기를 갖는다

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/local_pipeline.py` — `_materialize_variant_for_output`의 `timeline_payload` 조립(`:2205-2226`)
- Test: `tests/test_output_variants.py` 또는 `tests/test_local_pipeline_final_render.py` (있는 것에 붙인다)

**배경:**
마스터 payload를 베낄 때 `output`이 딸려 와서 세로 변형본도 1920×1080으로 적힌다. `kind`에서 크기를 다시 정해야 한다. `_ORIENTATION_OUTPUT_SIZES`(`:1423`)에 값이 이미 있다 — **두 번째 표를 만들지 마라.**

**같이 정할 것 — `output_mode`도 고칠까:**
지금 변형본 타임라인의 `output_mode`는 `review`다(payload가 인자를 덮는다). 고치면 `output_mode`가 정직해지지만 **그 값을 읽는 다른 자리가 깨질 수 있다.** `output_mode`를 읽는 곳을 전부 grep해서 세고, 고칠지 말지 판단해 근거를 보고서에 적어라. 안 고치기로 했다면 그 사실을 코드 주석에 남겨 다음 사람이 또 속지 않게 하라 — 이미 한 번 속았다(`services/api/src/videobox_api/routers/outputs.py`의 `_download_shape_for_render` 주석 참고).

- [ ] **Step 1: 실패하는 시험을 쓴다** — `vertical_full` 변형본을 materialize 하면 그 타임라인의 `output`이 1080×1920이다. `horizontal`은 1920×1080 그대로다.
- [ ] **Step 2: 시험을 돌려 실패를 확인한다** (시험 이름과 파일)
- [ ] **Step 3: 통과할 만큼만 고친다**
- [ ] **Step 4: 시험을 돌려 통과를 확인한다**
- [ ] **Step 5: 변형 탐침** — 크기를 다시 정하는 줄을 없애고 시험이 빨개지는지
- [ ] **Step 6: 커밋한다**

---

### Task 2: 나온 파일이 정말 세로다

**Files:**
- Test: `tests/test_local_pipeline_final_render.py` (실제 FFmpeg를 돌리는 시험이 이미 여기 있다)
- Modify: 필요하면 렌더러 쪽 — **Task 1만으로 될 수도 있다. 먼저 재고 판단하라.**

**Interfaces:**
- Consumes: Task 1의 타임라인 `output`

**배경:**
타임라인에 크기를 적는 것과 **나온 mp4가 그 크기인 것**은 다른 주장이다. 이 저장소는 그 차이로 여러 번 데였다. 실제로 렌더를 돌려 `ffprobe`로 재라.

**판단할 것 — 가로 원본을 세로 칸에 어떻게 담을까:**
렌더러에 두 갈래가 이미 있다(`ffmpeg_final_renderer.py:1976-1978`): `fit == "crop"`이면 `increase,crop`(꽉 채우고 잘라낸다), 아니면 `decrease,pad`(줄이고 검은 띠를 넣는다). 1920×1080 원본을 1080×1920에 담으면 **pad는 위아래가 거의 다 검은 띠**가 된다 — 세로 영상으로는 못 쓴다. 어느 쪽이 맞는지 정하고 근거를 적어라. 변형본에는 `overrides.crop`·`focal`이 이미 있다(`output_variants.py`) — 그것들이 이 판단에 어떻게 들어가는지도 같이 보고하라.

- [ ] **Step 1: 실패하는 시험을 쓴다** — 세로 변형본을 실제로 렌더하고 `ffprobe`로 1080×1920인지 잰다
- [ ] **Step 2: 시험을 돌려 실패를 확인한다** (시험 이름과 파일)
- [ ] **Step 3: 통과할 만큼만 고친다**
- [ ] **Step 4: 시험을 돌려 통과를 확인한다**
- [ ] **Step 5: 변형 탐침**
- [ ] **Step 6: 커밋한다**

---

### Task 3: 실물에서 밟는다

**배경:**
`CLAUDE.md` §4: 완료는 대표님이 화면에서 쓸 수 있는가다. 시험이 아니라 제품에서 확인한다.

- [ ] **Step 1:** `scripts/owner-ready.ps1 -Mode Start -Rebuild -WithYujinMemory`로 다시 세운다
- [ ] **Step 2:** 브라우저에서 출력 화면을 열고 **새로** 가로·세로 변형본을 만든다 (옛 변형본은 낡은 타임라인을 물고 있으니 다시 만들어야 한다)
- [ ] **Step 3:** 둘 다 내려받아 `ffprobe`로 **크기를 재고 md5를 비교한다.** 셋이 같으면 안 고쳐진 것이다
- [ ] **Step 4:** 재생도 확인한다 — 세로 영상이 화면에서 세로로 나오는지
- [ ] **Step 5:** 잰 값을 보고서에 그대로 적는다

---

## 이 계획이 **안 하는** 것 (일부러)

- **`vertical_highlight`의 장면 고르기**는 안 건드린다. 이미 `highlight_scoring.py`가 한다. 여기서 고치는 것은 **크기**뿐이다.
- **옛 변형본 다시 만들기**는 안 한다. 이미 나온 잘못된 파일을 소급해 고치지 않는다 — 다시 만들면 된다.
- **`overrides.crop`·`focal` UI**는 범위 밖이다. 값이 있으면 쓰되, 없을 때 잘 나오는 것이 이 계획의 목표다.
