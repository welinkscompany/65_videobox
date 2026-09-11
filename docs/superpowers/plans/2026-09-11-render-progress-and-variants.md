# 만드는 동안 보이게, 만든 것은 가져가게 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 완성본을 만드는 몇 분 동안 **진행이 보이게** 하고, 만든 **가로·세로 변형본을 파일로 가져가게** 하고, 실패했을 때 **영어 코드 대신 할 수 있는 일**을 보여준다.

**Architecture:** 셋 다 값은 이미 있다. 진행률은 서버가 이미 기록하고, 변형본 주소는 이미 계산돼 있고, 오류 코드를 한국어 문장으로 옮기는 표도 이미 있다. **화면이 그걸 안 쓸 뿐이다.** 새 배관을 만들지 말고 있는 것을 이으라.

**Tech Stack:** TypeScript, React, Vitest

**Spec:** 2026-09-11 출력 구간 코드 감사. 아래 §"조사 기록"이 근거다.

## 조사 기록

| 잰 것 | 결과 |
|---|---|
| 완성본 만들기 진행률 | 서버에 **이미 있다** — ffmpeg가 퍼센트를 올리고(`packages/core-engine/src/videobox_core_engine/local_pipeline.py:2442-2444`) 잡 기록의 `progress_percent`에 저장된다(`packages/storage-abstractions/src/videobox_storage/local_project_store.py:7415`) |
| 화면이 그걸 읽는가 | `apps/web/src/app/OutputsPage.tsx:903-916` — POST 뒤 **한 번만** 읽고 끝. 폴링 없음 |
| 그래서 화면에 뜨는 것 | `완성본을 만드는 중이에요.` + `완료될 때까지 기다린 뒤 상태를 다시 확인해 주세요.`(`:1089`, `:1146`)에서 멈춘다. 맨 아래 `상태 다시 확인`(`:1181`)을 직접 눌러야 바뀐다 |
| 단추 표시 | `isRenderingFinal`이 POST 끝나는 1초 안에 꺼져(`:929`), 실제 렌더 도는 몇 분 동안 단추는 **`완성본 만들기`인데 회색**이다. "만드는 중"이라고 말하지 않는다 |
| 유일한 진행률 표시 | 상단 `작업 상태` 팝업(`apps/web/src/features/jobs/JobRecovery.tsx:238`) — **그것도 폴링 안 한다**(`:149-157`, 열 때 한 번). 게다가 내보내기 팝업이 모달이라 그걸 누르려면 팝업을 닫아야 한다 |
| 변형본 내려받기 | **없다.** `apps/web/src/features/outputs/VariantOutputCard.tsx:31`은 재생만. 주소는 이미 계산돼 있다(`variantOutputState.ts:28-32`) |
| 변형본 실패 문구 | 영어 내부 코드가 그대로 뜬다 — `VariantOutputCard.tsx:33`의 `사유: {item.error_code}` → `사유: final_output_requires_review_approval` 같은 문장 |
| 한국어로 옮기는 표 | **이미 있다** — `OutputsPage.tsx:92-146`이 백엔드 코드를 할 일 문장으로 옮긴다. 이 저장소에서 가장 잘 돼 있는 자리다 |

## Global Constraints

- 저장소 최상위 지침은 `CLAUDE.md`. 작업 폴더는 `.worktrees/videobox-container-compatibility`이며 main 체크아웃으로 `cd` 하지 않는다.
- **RED → 실패 확인 → 최소 GREEN → 통과 확인.** 실패를 주장할 때는 **시험 이름과 그 시험이 있는 파일**을 대야 한다.
- 프런트 시험은 `apps/web`에서 `npx vitest run <경로>`, 타입검사 `npx tsc --noEmit -p tsconfig.json`.
- **화면에 나가는 말에 개발 용어를 쓰지 않는다**(`docs/development-fast-path.ko.md` §10.13). `job`·`revision`·`variant`·`renderer` 금지.
- **있는 것을 이으라.** 진행률 값·변형본 주소·오류 문구 표가 전부 이미 있다. 새로 만들면 두 벌이 된다.
- 주석과 커밋 메시지는 한국어로, **왜**를 적는다.
- 커밋은 각 Task 끝에 하나씩. push는 하지 않는다.

---

### Task 1: 만드는 동안 진행이 보인다

**Files:**
- Modify: `apps/web/src/app/OutputsPage.tsx` — 완성본 만들기 뒤 상태를 계속 읽는 자리(`:903-916`), 단추 표시(`:1147`), 문구(`:1089`, `:1146`)
- Test: `apps/web/src/app/OutputsPage.test.tsx`

**Interfaces:**
- Consumes: 없음
- Produces: 없음

**배경:**
지금은 POST 한 번 보내고 끝이라, 몇 분 걸리는 작업 내내 화면이 안 바뀐다. 대표님 눈에는 **회색 단추와 안 변하는 문구**뿐이라 멈춘 건지 도는 건지 알 수 없다.

**본보기가 이미 있다**: 미리보기가 같은 일을 한다 — `apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx:698-711`이 `pending/running`이면 1200ms마다 다시 묻는다. **그 모양을 따르라.** 이 구간에서 자동 갱신이 있는 유일한 자리다.

**세 가지를 함께 정하라:**
- 얼마나 자주 물을지 — 미리보기는 1200ms다. 완성본은 몇 분 걸리므로 더 느려도 된다. 고르고 근거를 적어라.
- **언제 멈출지** — 끝났거나 실패했으면 반드시 멈춘다. 안 그러면 영원히 서버를 두드린다.
- 화면을 떠나면 멈추는가 — 정리(cleanup)를 안 하면 없어진 화면을 갱신하려 들고 경고가 뜬다.

진행률(`progress_percent`)을 **보여줄지도 정하라.** 값은 있다. 숫자가 안 움직이는 구간이 길면 오히려 불안하게 만들 수도 있다 — 판단하고 근거를 보고서에 적어라.

- [ ] **Step 1: 실패하는 시험을 쓴다** — 완성본 만들기를 시작하면 화면이 **스스로** 상태를 다시 읽고, 끝나면 **멈춘다**.
- [ ] **Step 2: 시험을 돌려 실패를 확인한다** (시험 이름과 파일)
- [ ] **Step 3: 통과할 만큼만 고친다**
- [ ] **Step 4: 시험을 돌려 통과를 확인한다** + `npx tsc --noEmit -p tsconfig.json`
- [ ] **Step 5: 변형 탐침** — 멈추는 조건을 없애 놓고 "끝나면 그만 묻는다" 시험이 빨개지는지
- [ ] **Step 6: 커밋한다**

---

### Task 2: 가로·세로 변형본을 파일로 가져간다

**Files:**
- Modify: `apps/web/src/features/outputs/VariantOutputCard.tsx:31` 근처
- Test: `apps/web/src/features/outputs/` 아래 해당 시험(없으면 새로)

**Interfaces:**
- Consumes: Task 1 없음(독립)
- Produces: 없음

**배경:**
변형은 `CLAUDE.md` §2.1이 명시한 제품 범위다. 만들고 재생까지 되는데 **가져가는 마지막 한 줄이 없어서** 만든 것이 화면 안에 갇힌다. 주소는 이미 `variantOutputState.ts:28-32`에 계산돼 있다.

**따라 쓸 본보기**: 같은 화면의 `SRT 자막 파일 내려받기`(`OutputsPage.tsx:1085`)와 `완성본 영상 내려받기`(2026-09-11에 추가). 모양과 자리를 맞춰라.

**주의**: 완성본 내려받기는 **낡았으면 감춘다**는 규칙이 있다(`masterFinalRender.ts`). 변형본에도 같은 판단이 필요한지 보고, 필요하면 **그 규칙을 다시 만들지 말고** 있는 것을 쓰라. 변형본은 마스터와 판단 기준이 다를 수 있으니, 다르다면 왜 다른지 보고서에 적어라.

- [ ] **Step 1: 실패하는 시험을 쓴다**
- [ ] **Step 2: 시험을 돌려 실패를 확인한다** (시험 이름과 파일)
- [ ] **Step 3: 통과할 만큼만 고친다**
- [ ] **Step 4: 시험을 돌려 통과를 확인한다** + 타입검사
- [ ] **Step 5: 변형 탐침**
- [ ] **Step 6: 커밋한다**

---

### Task 3: 실패했을 때 할 수 있는 일을 보여준다

**Files:**
- Modify: `apps/web/src/features/outputs/VariantOutputCard.tsx:33`
- Modify: `apps/web/src/features/outputs/VariantConflictPanel.tsx:17` (같은 병 — `conflict.field`/`conflict.reason`을 그대로 찍는다)
- Test: 위 두 컴포넌트의 시험

**Interfaces:**
- Consumes: `OutputsPage.tsx:92-146`의 한국어 문구 표
- Produces: 없음

**배경:**
지금 뜨는 것: `사유: final_output_requires_review_approval`, `사유: stale_master_revision`, `사유: renderer_failed`. 대표님이 **할 수 있는 일이 그 안에 하나도 없다.**

`OutputsPage.tsx:92-146`에 백엔드 코드를 한국어 할 일 문장으로 옮기는 표가 **이미 있다.** 모르는 코드도 "무언가 낡았다"까지는 말한다. **그 표를 나눠 쓰라 — 두 번째 표를 만들지 마라.**

`VariantConflictPanel`의 `reason`은 `Literal["master_changed_while_locked", "master_changed_while_overridden"]`이다(`packages/domain-models/src/videobox_domain_models/output_variants.py:77`). 이것도 사람 말로 옮겨야 한다.

**모르는 코드가 왔을 때** 무엇을 보여줄지 정하라. 코드를 그대로 보여주면 지금과 같아지고, 감추면 무슨 일인지 알 수 없다 — 표가 이미 쓰는 방식을 따르고 근거를 적어라.

- [ ] **Step 1: 실패하는 시험을 쓴다** — 알려진 코드는 사람 말로 뜨고, **모르는 코드도** 정한 방식대로 뜬다
- [ ] **Step 2: 시험을 돌려 실패를 확인한다** (시험 이름과 파일)
- [ ] **Step 3: 통과할 만큼만 고친다**
- [ ] **Step 4: 시험을 돌려 통과를 확인한다** + 타입검사
- [ ] **Step 5: 변형 탐침**
- [ ] **Step 6: 커밋한다**

---

## 이 계획이 **안 하는** 것 (일부러)

- **`작업 상태` 팝업의 폴링**(`JobRecovery.tsx:149-157`)은 안 건드린다. Task 1이 완성본 화면에 진행을 보여주면 그 팝업에 기대지 않아도 된다. 팝업까지 폴링하게 만들면 같은 값을 두 곳에서 두드린다.
- **캡컷 초안 내려받는 문**(`routers/outputs.py`에 `content` 라우트가 없다)은 별도다. 백엔드 라우트를 새로 여는 일이라 크기가 다르다.
