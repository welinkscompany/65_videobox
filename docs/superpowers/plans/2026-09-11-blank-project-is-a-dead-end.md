# 새로 만든 프로젝트가 막다른 길이다 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `+ 새로 만들기`로 만든 빈 편집판에서 자산을 화면에 깔 수 있게 한다. 그리고 **화면이 창작자의 클릭을 말없이 버리는 일이 다시는 없게** 한다.

**Architecture:** 백엔드는 멀쩡하다(실측). 고장난 것은 화면의 클릭 경로 하나뿐이고, 그것이 **아무 말 없이** 실패한다. 그래서 고칠 것이 둘이다 — (1) 빈 편집판에서 실제로 되게, (2) 어떤 이유로든 편집이 안 나갈 때는 **반드시 말하게**.

**Tech Stack:** TypeScript, React, Vitest, @testing-library/react

**Spec:** 이 계획서의 §"실측 기록"이 근거다. 2026-09-11에 살아 있는 컨테이너에서 직접 밟았다.

## 실측 기록 (추측 아님, 브라우저와 API로 직접 확인)

`+ 새로 만들기` → 빈 편집판 → 자산 카드의 `화면으로 깔기`를 **두 번** 눌렀다.

| 잰 것 | 결과 |
|---|---|
| 단추 상태 | **활성**(`disabled: false`, DOM에서 직접 확인) |
| 누른 뒤 네트워크 요청 | **하나도 없음** (전체 요청 목록 확인) |
| 화면에 뜨는 말 | **없음** — 미리보기는 계속 "왼쪽 미디어에서 파일을 더하면 이 자리에 보여요" |
| 콘솔 오류 | 이 클릭과 관련된 것 없음 |
| 빈 세션의 매니페스트 | 트랙 **0개**, 캡션 1개 |
| 빈 세션의 장면 | **1개** (`timeline_001:001`, 0.0~5.0초) |
| **백엔드에 같은 일을 API로 시키면** | **성공** (`PATCH .../segments/timeline_001:001/broll` → 200, revision 1→2) |
| 그 뒤 새로고침 | 타임라인에 `영상 1번째 장면`이 뜨고 빈 화면 문구가 사라짐 |

**결론: 백엔드도, 편집기 렌더링도 멀쩡하다. 완전히 빈 프로젝트에서만 클릭이 통째로 버려진다.**

## 왜 심각한가

`+ 새로 만들기`는 이 제품에 **하나뿐인 시작 문**이다(`docs/decisions/2026-09-05-one-way-to-start.ko.md`). 그 문으로 들어온 창작자가 화면이 시키는 대로(`왼쪽 미디어에서 파일을 더하면`) 파일을 더하고 단추를 눌러도 **아무 일도 안 일어나고 아무 말도 없다.**

## 용의자 (구현자가 RED로 확정할 것 — 계획이 답을 정해 주지 않는다)

둘 다 "조용히 버린다"는 같은 증상을 낸다. **어느 쪽인지 시험으로 가려라.**

1. `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`의 `commitTimelineMutation` 첫 줄:
   `if (!sessionId || !state.view || mutationInFlight.current || captionPreflightInFlight.current) return;`
   — 네 조건 중 무엇도 창작자에게 말하지 않는다.
2. `apps/web/src/features/editor/assets/EditorAssetBrowser.tsx`의 카드 단추:
   `onClick={() => target && onApply(card, target.segmentId)}`
   — `target`이 없으면 **클릭이 통째로 사라진다**. 단, 화면에는 `적용 구간: 0.00–5.00초`가 떠 있었다(그 문구가 같은 `target`에서 오는지 확인하라 — 다른 값에서 온다면 그 자체가 결함이다).

## Global Constraints

- 저장소 최상위 지침은 `CLAUDE.md`. 작업 폴더는 `.worktrees/videobox-container-compatibility`이며 main 체크아웃으로 `cd` 하지 않는다.
- **RED → 실패 확인 → 최소 GREEN → 통과 확인.** 실패를 주장할 때는 **시험 이름과 그 시험이 있는 파일**을 대야 한다.
- 프런트 시험은 `apps/web`에서 `npx vitest run <경로>`, 타입검사 `npx tsc --noEmit -p tsconfig.json`.
- 화면 문구는 창작자 말로 쓴다(`docs/development-fast-path.ko.md` §10.13). `session`·`view`·`mutation` 같은 개발 용어를 쓰지 않는다.
- **지금 잘 되는 경우의 동작을 바꾸지 마라.** 내용이 있는 편집본에서는 이미 전부 정상이다 — 거기 회귀가 나면 안 된다.
- 주석과 커밋 메시지는 한국어로, **왜**를 적는다.
- 커밋은 각 Task 끝에 하나씩. push는 하지 않는다.

---

### Task 1: 빈 편집판에서 화면을 깔 수 있게 한다

**Files:**
- Modify: 위 용의자 둘 중 시험이 가리키는 자리
- Test: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx` (빈 매니페스트를 주는 픽스처가 필요하면 새로 만들어라)

**Interfaces:**
- Consumes: 없음
- Produces: 없음 (Task 2가 같은 파일을 건드리므로 순서대로 한다)

**배경:** 위 "실측 기록"이 전부다. 특히 **백엔드는 이미 된다** — 고칠 것은 화면뿐이고, 백엔드 쪽은 건드리지 마라.

- [ ] **Step 1: 실패하는 시험을 쓴다**

트랙이 **0개**인 재생 매니페스트(캡션 1개, 세션 장면 1개)로 편집기를 그리고, 자산 카드의 `화면으로 깔기`를 누른 뒤 **API가 실제로 불렸는지** 단언한다. 지금은 안 불린다.

기존 시험들이 쓰는 매니페스트 픽스처를 본떠서 트랙만 비워라. **비운 뒤에도 편집기가 오류 없이 그려지는지 먼저 확인하라** — 안 그려지면 그것부터가 다른 결함이니 보고서에 적어라.

- [ ] **Step 2: 시험을 돌려 실패를 확인한다**

```bash
cd apps/web && npx vitest run src/features/editor/workbench/editor-workbench-route.test.tsx
```

**실패 이유를 눈으로 보고 보고서에 적어라** — 용의자 1인지 2인지, 아니면 제3의 원인인지. 이것이 이 Task의 핵심 산출물이다.

- [ ] **Step 3: 통과할 만큼만 고친다**

원인이 무엇이든 **창작자의 클릭이 버려지지 않게** 한다. 지금 잘 되는 경우(내용이 있는 편집본)의 동작은 그대로여야 한다.

- [ ] **Step 4: 시험을 돌려 통과를 확인한다**

```bash
cd apps/web && npx vitest run src/features/editor/workbench/ src/features/editor/assets/ && npx tsc --noEmit -p tsconfig.json
```

- [ ] **Step 5: 변형 탐침** — 고친 것을 되돌려 놓고 새 시험이 빨개지는지 본다. 확인 뒤 복원.

- [ ] **Step 6: 커밋한다**

---

### Task 2: 편집이 안 나갈 때는 반드시 말한다

**Files:**
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx`의 `commitTimelineMutation`
- Test: `apps/web/src/features/editor/workbench/editor-workbench-route.test.tsx`

**Interfaces:**
- Consumes: Task 1이 확정한 원인
- Produces: 없음

**배경:**
`commitTimelineMutation`은 네 가지 이유로 **조용히 돌아선다**:
```ts
if (!sessionId || !state.view || mutationInFlight.current || captionPreflightInFlight.current) return;
```
Task 1이 그중 하나를 고쳐도 **나머지 셋은 여전히 조용하다.** 이 저장소가 반복해서 값을 치른 것이 정확히 이 모양이다 — 조용한 실패.

**넷을 구분해서 다뤄라.** 전부 같은 말을 하면 안 된다:
- `mutationInFlight` / `captionPreflightInFlight`는 **정상적인 상태**다(이미 저장 중). 창작자에게 "지금 저장하고 있어요, 잠시만요" 같은 말이면 충분하고, 오류처럼 보이면 안 된다.
- `!sessionId` / `!state.view`는 **비정상**이다. 무엇을 해야 하는지(새로고침 등) 말해야 한다.

이미 쓰는 자리가 있다: `setMutation({ isSaving, message })`가 `변경 내용을 저장하고 있어요.`를 띄운다. 새 장치를 만들지 말고 그 자리를 쓰라.

- [ ] **Step 1: 실패하는 시험을 쓴다** — 편집이 나갈 수 없는 상태에서 창작자가 단추를 누르면 **화면에 말이 뜬다**. 최소 두 경우(정상 대기 / 비정상)를 가른다.
- [ ] **Step 2: 시험을 돌려 실패를 확인한다** (시험 이름과 파일을 적어라)
- [ ] **Step 3: 통과할 만큼만 고친다**
- [ ] **Step 4: 시험을 돌려 통과를 확인한다** + 타입검사
- [ ] **Step 5: 변형 탐침** — 말하는 줄을 지워 놓고 시험이 빨개지는지 본다
- [ ] **Step 6: 커밋한다**

---

## 이 계획이 **안 하는** 것 (일부러)

- **빈 편집판을 없애거나 `+ 새로 만들기`의 목적지를 바꾸지 않는다.** 그건 승인된 결정(`2026-09-05-one-way-to-start`)에 닿는 일이라 owner 판단이 먼저다. 지금은 **그 문으로 들어온 사람이 막히지 않게** 하는 것만 한다.
- **빈 편집판의 안내 문구를 새로 쓰지 않는다.** 미리보기가 `미디어`를 가리키는 것이 맞는 안내인지는 위 결정과 함께 볼 일이다.
