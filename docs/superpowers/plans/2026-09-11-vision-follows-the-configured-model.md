# 영상 분석이 설정한 모델을 쓰게 한다 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 영상 분석과 자료실 색인이 **`VIDEOBOX_LOCAL_MODEL_NAME`이 가리키는 모델**을 쓰게 한다. 지금은 LM Studio에 **먼저 올라온** 비전 모델을 집는다.

**Architecture:** 고를 때 설정한 이름을 **먼저** 본다. 그 모델이 올라와 있고 비전이 되면 그걸 쓰고, 아니면 지금처럼 올라온 것 중에서 고른다(뒤로 물러나는 길을 없애지 않는다 — LM Studio가 꺼져 있거나 다른 모델만 있을 때 분석이 통째로 멈추면 안 된다).

**Tech Stack:** Python, pytest

**Spec:** 이 계획서의 §"실측 기록". 2026-09-11에 대표님 기계에서 직접 확인했다.

## 실측 기록

- `packages/provider-interfaces/src/videobox_provider_interfaces/lm_studio.py:148-160` — `capability_profile()`이 **로드된 목록의 첫 비전 모델**을 고른다. 설정값을 안 본다.
- 쓰는 곳: `packages/core-engine/src/videobox_core_engine/media_analysis.py:105,119,187`(영상 분석), `library_footage_indexer.py:232-241`(자료실 색인).
- 부르는 곳은 **한 군데**: `services/api/src/videobox_api/main.py:1087`. 바로 위 `:1083-1085`에 이미 `resolved_local_runtime_config`(설정한 모델 이름을 들고 있다)가 있다.
- **실제로 일어났다**: 2026-09-11에 옛 모델(`qwen/qwen3.6-35b-a3b`)을 내렸는데 다시 올라와 생성 중이었다. 목록에서 옛 모델이 앞이라 분석이 그걸 집었고, LM Studio의 `justInTimeModelLoading`이 자동으로 올렸다.
- **이건 계속 일어난다**: 대표님이 옛 모델을 **다른 프로젝트에서 계속 쓴다**고 했다(2026-09-11). 그 프로젝트가 올려 두는 순간 VideoBox의 분석이 설정과 무관하게 그걸 쓴다.
- **재부팅 뒤에도 같은 문제다**: 이름을 대고 부르는 경로(유진 대화·기억)는 `justInTimeModelLoading`이 알아서 새 모델을 올린다. 분석만 "먼저 올라온 것"에 걸린다.

## Global Constraints

- 저장소 최상위 지침은 `CLAUDE.md`. 작업 폴더는 `.worktrees/videobox-container-compatibility`이며 main 체크아웃으로 `cd` 하지 않는다.
- **RED → 실패 확인 → 최소 GREEN → 통과 확인.** 실패를 주장할 때는 **시험 이름과 그 시험이 있는 파일**을 대야 한다.
- backend 시험은 반드시 `.venv/Scripts/python.exe -m pytest`.
- **뒤로 물러나는 길을 없애지 마라.** 설정한 모델이 안 올라와 있을 때 분석이 통째로 막히면, 지금 되던 것이 안 되게 된다. 이 저장소는 "LM Studio가 꺼져 있으면 휴리스틱으로 물러난다"는 설계를 이미 갖고 있다.
- 주석과 커밋 메시지는 한국어로, **왜**를 적는다.
- 커밋은 각 Task 끝에 하나씩. push는 하지 않는다.

---

### Task 1: 설정한 모델을 먼저 고른다

**Files:**
- Modify: `packages/provider-interfaces/src/videobox_provider_interfaces/lm_studio.py` — `capability_profile()`(`:148`)
- Modify: `services/api/src/videobox_api/main.py:1087` — 설정 이름을 넘긴다
- Test: `tests/` 아래 `capability_profile`을 덮는 시험(먼저 `grep -rn "capability_profile" tests/`로 찾아라. 없으면 새 파일)

**Interfaces:**
- Consumes: 없음
- Produces: 없음

**배경(구현자가 알아야 할 것):**

지금 규칙은 "로드된 목록의 첫 비전 모델"이다. 새 규칙은 **"설정한 모델이 올라와 있고 비전이 되면 그것, 아니면 지금 규칙"**이다.

**세 경우를 다 다뤄라:**
1. 설정한 모델이 올라와 있고 비전이 된다 → 그것을 쓴다
2. 설정한 모델이 올라와 있는데 비전이 **안 된다** → 지금 규칙으로 물러난다(그리고 그 사실이 어딘가 드러나야 한다 — 조용히 다른 모델을 쓰면 왜 결과가 다른지 알 수 없다)
3. 설정한 모델이 아예 안 올라와 있다 → 지금 규칙으로 물러난다

**텍스트·임베딩 모델도 같은 자리에서 고른다**(`selected["text"]`, `selected["embedding"]`). 텍스트는 설정 이름과 같은 개념이니 함께 맞추는 것이 자연스럽다. **임베딩은 다른 모델이다**(`text-embedding-bge-m3`) — 거기에 텍스트 모델 이름을 들이밀지 마라. 무엇을 바꾸고 무엇을 그대로 뒀는지 보고서에 적어라.

`capability_profile()`의 기존 호출자는 **하나뿐**이다(`main.py:1087`). 인자를 선택(기본값 `None`)으로 더하면 기존 시험이 안 깨진다.

- [ ] **Step 1: 실패하는 시험을 쓴다**

로드된 목록에 비전 가능한 모델이 **둘** 있고 설정한 것이 **뒤에** 있는 상황을 만든다. 지금은 앞엣것이 뽑힌다. 세 경우(위 1·2·3)를 각각 밟아라.

시험은 실제 응답 모양을 써야 한다 — `/api/v1/models`의 `{"models":[{"type":"llm","key":...,"capabilities":{"vision":true},"loaded_instances":[{"id":...}]}]}`. 모양이 다르면 시험이 아무것도 안 지킨다. (2026-09-11 실측: 새 모델은 `type: "llm"`, `capabilities.vision: true`로 나온다.)

- [ ] **Step 2: 시험을 돌려 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest <새 시험 파일> -q
```

- [ ] **Step 3: 통과할 만큼만 고친다**
- [ ] **Step 4: 시험을 돌려 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest tests/ -q -k "lm_studio or capability or media_analysis or vision"
```

- [ ] **Step 5: 변형 탐침** — 설정 우선 규칙을 지워 놓고 새 시험이 빨개지는지. 그리고 폴백을 지워 놓고 "설정 모델이 없을 때" 시험이 빨개지는지. **둘 다** 본다.
- [ ] **Step 6: 커밋한다**

---

### Task 2: 문서 지침을 새 모델로 갱신한다

**Files:**
- Modify: `CLAUDE.md` §2 표 아래 SSOT 줄 또는 §3 — 어디가 맞는지는 읽고 정하라
- Modify: `docs/handoffs/2026-09-08-hermes-egress-and-multitrack-plans.ko.md` §15 (이미 모델 교체 기록이 있다 — 거기 이어 적어라)
- Test: 없음(문서). 다만 **모델 이름을 문서에 또 박지 마라** — 갈라진다.

**Interfaces:**
- Consumes: Task 1이 정한 선택 규칙
- Produces: 없음

**배경 — 대표님 지시(2026-09-11):**
> "신모델로 유진이를 사용한다고 문서 지침도 업데이트해줘"

적어야 할 것:
- 유진의 두뇌는 이제 `qwen/qwen3.8-27b`다.
- **옛 모델(`qwen/qwen3.6-35b-a3b`)은 대표님이 다른 프로젝트에서 계속 쓴다** — 그래서 두 모델이 한 기계에 함께 있고, "안 쓰니까 지워도 된다"고 적으면 안 된다.
- 모델을 바꾸는 법은 **한 명령**이다: `scripts/set-local-model.ps1 <모델id>`. 여섯 곳을 한 번에 바꾸고, LM Studio에 그 모델이 없으면 거부한다.
- 갈라짐 울타리가 있다: `tests/test_local_model_name_is_one_value.py`.
- Task 1 뒤에는 **영상 분석도 설정을 따른다** — 예전에는 "먼저 올라온 것"을 썼다는 사실과 함께 적어라(같은 함정을 다시 파지 않게).

**모델 이름을 문서 본문에 박을지 말지 정하라.** 박으면 다음 교체 때 또 갈라진다. "설정은 `.env.container`의 `VIDEOBOX_LOCAL_MODEL_NAME`이 정한다"처럼 **가리키는 편**이 나을 수 있다 — 판단하고 근거를 보고서에 적어라.

- [ ] **Step 1: 지금 문서가 뭐라고 적혀 있는지 읽는다** (`CLAUDE.md`에서 모델을 언급하는 자리를 `grep`으로 다 찾아라)
- [ ] **Step 2: 고친다**
- [ ] **Step 3: 모델 이름이 새로 박힌 자리가 생겼는지 확인한다** — 생겼다면 울타리 시험이 그것도 지키는지 보고, 안 지키면 박지 마라
- [ ] **Step 4: 커밋한다**
