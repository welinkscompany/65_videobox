# 트랙을 숨긴 뒤 되돌리기가 먹지 않는다 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 트랙 눈·음소거를 되돌릴 수 있게 하고, 마지막 하나를 다시 켜는 길도 열어 준다.

**Architecture:** 둘 다 **열쇠가 조용히 빠지는** 같은 모양이다. 하나는 되돌리기 스냅샷이 이름을 하나씩 적는데 `track_states`가 안 적혀 있고, 하나는 변경 적용이 열쇠 **삭제**를 전파하지 못한다. 따라 쓸 본보기가 이미 둘 다 저장소 안에 있다.

**Tech Stack:** Python, pytest

**Spec:** 이 계획서의 §"조사 기록". 2026-09-11 코드 정독 기반(실행 검증은 구현자가 한다).

## 조사 기록

**결함 1 — 되돌리기가 트랙 숨김을 안 되돌리고, 칸은 먹는다.**

```
set_track_states (editing_session.py:778)
  → _record_undoable_mutation (editing_session.py:171)
      → apply_user_transaction (editing_transactions.py:32)
          → _snapshot()  ← 여기서 track_states가 탈락
```
`_snapshot()`(`editing_transactions.py:19-29`)은 최상위 열쇠 **넷을 이름으로 적어** 뜬다 — `segments`·`caption_style`·`timeline_placement_overrides`·`tracks`. `track_states`가 없다. `undo()`(`:801-828`)·`redo()`(`:831-858`)도 그 넷만 복원하고, `undo()`는 `deepcopy(session)`으로 시작하므로 **지금의 `track_states`가 그대로 살아남는다.**

`editing_transactions.py:24-27`의 주석이 바로 이 함정을 경고하는데 `track_states`는 안 들어갔다 — **이미 알려진 함정을 다시 밟았다.**

**대표님 눈에 보이는 것** (순서가 있다):
1. 트랙 눈을 끈다 → 회색이 되고 미리보기에서도 빠진다
2. Ctrl+Z → "저장하고 있어요"가 뜨고 **미리보기가 통째로 다시 렌더되고** revision이 오르는데(`editing_session.py:827`가 output freshness를 무효화) **트랙은 그대로 숨겨져 있다**
3. "안 먹었나?" 하고 한 번 더 → **이번엔 그 앞의 진짜 편집이 사라진다**

`redo`는 정상이라 복구는 가능하다(자료 손실은 아니다).

**결함 2 — 마지막 하나를 다시 켜는 길이 막혀 있다** (조사에서 새로 나옴, 더 나쁘다).

`set_track_states`는 `states`가 비면 `updated.pop("track_states", None)`을 한다(`:774-777`). 그런데 `_record_undoable_mutation`의 `mutate`(`:172-175`)는 `for key, value in updated.items()`라 — **`updated`에 없는 열쇠는 draft에서 못 지운다.** draft는 `deepcopy(before)`라 옛 값을 그대로 들고 있다.

화면이 정확히 이 경우를 만든다: `TimelineDock.tsx:258-266`은 **켜진 것만** 담으므로 마지막 하나를 끄면 `{}`가 간다. 다른 트랙이 하나라도 켜져 있으면 정상 동작해서, **"될 때도 있고 안 될 때도 있는"** 모양으로 보인다.

**조사가 걷어낸 걱정 둘 (건드리지 마라):**
- **저장 화이트리스트는 이미 있다** — `local_project_store.py:9110`에 `track_states`가 주석까지 달려 들어 있다.
- **미리보기 지문은 영향 없다** — 지문은 세션의 *현재* `track_states`에서 나오고 스냅샷은 안 먹는다.

## Global Constraints

- 저장소 최상위 지침은 `CLAUDE.md`. 작업 폴더는 `.worktrees/videobox-container-compatibility`이며 main 체크아웃으로 `cd` 하지 않는다.
- **RED → 실패 확인 → 최소 GREEN → 통과 확인.** 실패를 주장할 때는 **시험 이름과 그 시험이 있는 파일**을 대야 한다.
- backend 시험은 반드시 `.venv/Scripts/python.exe -m pytest`.
- **화면은 고칠 것이 없다** — 눈·음소거를 자기 상태로 안 들고 있고 서버가 준 값을 그대로 그린다(`TimelineDock.tsx:239-245`가 그렇게 설계했다고 적어 놓았다). 프런트를 건드리지 마라.
- **없던 상태로 돌아갈 때는 열쇠를 지워야 한다.** `normalize_track_states`와 옛 저장분 호환이 "열쇠 없음 = 전부 기본"에 기대고 있다.
- 주석과 커밋 메시지는 한국어로, **왜**를 적는다.
- 커밋은 각 Task 끝에 하나씩. push는 하지 않는다.

---

### Task 1: 되돌리기가 트랙 숨김·음소거를 되돌린다

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/editing_transactions.py:19-29` (`_snapshot`)
- Modify: `packages/core-engine/src/videobox_core_engine/editing_session.py` — `undo()`(`:819` 근처), `redo()`(`:849` 근처), 그리고 `_restore_session_tracks`(`:786-798`) 옆에 같은 모양의 복원 함수
- Test: `tests/test_track_states.py` (지금 undo/redo 케이스가 **하나도 없다**)

**Interfaces:**
- Consumes: 없음
- Produces: 없음 (Task 2가 같은 파일을 건드리므로 순서대로)

**따라 쓸 본보기 (새로 설계하지 마라):**
- `_restore_session_tracks`(`editing_session.py:786-798`) — **`None`이면 `pop`** 규칙이 이미 있다. 그대로 따라라.
- 시험 모양: `tests/test_timeline_placements.py:94-95`가 두 줄로 `undo`→없음, `redo`→복원을 다 본다.

**깨질 수 있는 자리 하나:** `tests/test_exact_preview_remediation.py:1191-1220`이 `inverse_payload`/`forward_payload`를 **손으로 만든 dict**로 넣는다. 복원을 **존재 확인 후**(`if "track_states" in payload`)로 쓰면 안 깨지고, 무조건 읽으면 `KeyError`가 난다. 어느 쪽을 골랐는지 보고서에 적어라.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`tests/test_track_states.py`에 더한다. 최소 셋:
1. 트랙을 숨긴 뒤 `undo`하면 **다시 보인다**
2. 그 뒤 `redo`하면 **다시 숨겨진다**
3. **숨긴 적 없는 세션**에서 다른 편집을 하고 `undo`해도 `track_states` 열쇠가 **생기지 않는다**(없던 상태로 정확히 돌아간다)

- [ ] **Step 2: 시험을 돌려 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest tests/test_track_states.py -q
```

- [ ] **Step 3: 통과할 만큼만 고친다**
- [ ] **Step 4: 시험을 돌려 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest tests/test_track_states.py tests/test_editor_view_model_api.py tests/test_timeline_placements.py tests/test_exact_preview_remediation.py tests/test_editing_session.py -q
```

- [ ] **Step 5: 변형 탐침** — 스냅샷에서 `track_states`를 다시 빼고 1·2가 죽는지, 복원의 "`None`이면 pop"을 없애고 3이 죽는지. **둘 다** 본다.
- [ ] **Step 6: 커밋한다**

---

### Task 2: 마지막 트랙의 눈을 다시 켤 수 있게 한다

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/editing_session.py:171-179` (`_record_undoable_mutation`의 `mutate`) 또는 `:774-777` (`set_track_states`) — **어느 쪽이 옳은지는 구현자가 정하고 근거를 보고서에 적어라**
- Test: `tests/test_track_states.py`, 그리고 실물 API 경로로 `tests/test_editor_view_model_api.py:290-394` 근처

**Interfaces:**
- Consumes: Task 1의 복원 경로
- Produces: 없음

**배경:**
`mutate`가 `for key, value in updated.items()`라 **삭제를 전파하지 못한다.** 최상위에서 `pop`을 쓰는 곳은 **`editing_session.py:777` 하나뿐**이다(나머지 `updated.pop` 5건은 전부 `undo`/`redo`/`_restore_session_tracks` 안이라 이 경로를 안 탄다). 그러니 고치는 범위는 좁다.

두 갈래가 있다:
- `mutate`가 삭제를 전파하게 한다 — **일반적이지만 다른 변경에도 영향이 갈 수 있다.** 그렇게 고른다면 영향 범위를 어떻게 확인했는지 적어라.
- `set_track_states`가 `pop` 대신 다른 신호를 준다 — **좁지만 특수 사례를 하나 만든다.**

**화면이 만드는 실제 모양을 시험에 넣어라**: `TimelineDock.tsx:258-266`은 켜진 것만 담으므로 마지막 하나를 끄면 **빈 dict `{}`**가 온다. 그게 지금 안 먹는 입력이다.

- [ ] **Step 1: 실패하는 시험을 쓴다** — 트랙 하나만 숨긴 뒤 `{}`를 보내면 **실제로 다시 보인다**. 다른 트랙이 켜져 있는 경우도 함께 밟아 예전 동작이 안 깨졌는지 본다.
- [ ] **Step 2: 시험을 돌려 실패를 확인한다** (시험 이름과 파일)
- [ ] **Step 3: 통과할 만큼만 고친다**
- [ ] **Step 4: 시험을 돌려 통과를 확인한다** (Task 1의 명령 + `tests/test_editing_session.py`)
- [ ] **Step 5: 변형 탐침** — 고친 것을 되돌려 놓고 새 시험이 빨개지는지
- [ ] **Step 6: 커밋한다**

---

## 이 계획이 **안 하는** 것 (일부러)

- **프런트는 안 건드린다.** 화면은 서버 값을 되읽기만 한다 — 서버가 고쳐지면 화면도 따라온다.
- **되돌리기가 미리보기를 통째로 무효화하는 것**(`editing_session.py:827`)은 그대로 둔다. 무동작 되돌리기에 렌더 비용을 치르는 문제는 Task 1이 닫히면 저절로 줄어든다(되돌리기가 실제로 뭔가를 되돌리게 되므로).
