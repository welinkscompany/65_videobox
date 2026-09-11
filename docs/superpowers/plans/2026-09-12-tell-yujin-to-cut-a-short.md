# 유진에게 "숏폼으로 잘라줘"라고 말하면 나온다 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 대표님이 유진에게 **"이거 숏폼으로 잘라줘"**라고 말하면, 유진이 **무엇이 볼 만한지 판단해** 장면을 고르고, **세로 영상**으로 나온다.

**Architecture:** 세 조각 중 둘은 이미 있다 — 세로 렌더는 2026-09-11에 끝났고(1080×1920, 검은 띠 0%), 하이라이트 변형이라는 그릇도 있다. **없는 것은 (가) 유진이 그걸 부를 말, (나) 고르는 기준이다.** 지금 기준은 자막 글자 밀도 하나뿐이고, 코드에도 "AI 참여도 예측이 아니다"라고 정직하게 적혀 있다.

**Tech Stack:** Python, TypeScript, 로컬 LLM(LM Studio)

**Spec:**
- 대표님 지시 2026-09-11: "숏폼용 세로 영상도 만들수 있어야되", "롱폼을 주면 그걸 마케팅용으로 알아서 판단해서 숏폼용으로 자동으로 잘라주는 기능도 있어야 되고", "전부다 유진이 한테 명령하면 실행되도록 배선 연결이 다 되어야되"
- 실측 근거: `docs/surveys/2026-09-11-yujin-command-gap.ko.md`
- 자동 하이라이트 자체는 **2026-08-28에 이미 승인된 기능**이다. 새 승인이 필요한 확장이 아니라 **덜 만들어진 기능을 마저 만드는 일**이다.

## 조사 기록 (2026-09-11 실측)

| 잰 것 | 결과 |
|---|---|
| 세로로 렌더되나 | **된다.** 1080×1920, 검은 띠 0%, 화면에서 눌러 확인 |
| 하이라이트 그릇 | 있다 — `vertical_highlight` 변형, `selected_segment_ids`로 장면을 고른다 |
| 고르는 기준 | `highlight_scoring.py:_segment_score` — **자막 글자 수 ÷ 길이**. 그뿐이다 |
| 그 파일이 스스로 밝힌 한계 | "AI 참여도 예측이 아니다… 단순 휴리스틱이다" |
| 유진이 하이라이트를 아나 | **모른다.** `config/hermes/yujin/` 아래 `highlight` 문자열 0건 |
| 유진이 변형본을 고칠 수 있나 | 스키마·적용기는 있는데(`output_variant`) **프로필 안내문에 0건** — 배울 방법이 없다 |
| 들어가는 문 | 편집기의 `가로·세로 비교` 모드 안. 출력 화면에는 유진이 **아예 없다** |

## Global Constraints

- 저장소 최상위 지침은 `CLAUDE.md`. 작업 폴더는 `.worktrees/videobox-container-compatibility`이며 main 체크아웃으로 `cd` 하지 않는다.
- **RED → 실패 확인 → 최소 GREEN → 통과 확인.** 실패를 주장할 때는 **시험 이름과 그 시험이 있는 파일**을 대야 한다.
- backend는 `.venv/Scripts/python.exe -m pytest`. 프런트는 `apps/web`에서 `npx vitest run`.
- **전체 pytest는 단독으로 돌린다**(약 40분). 조각을 닫을 때만.
- **화면에 나가는 말에 개발 용어를 쓰지 않는다.** `job`·`revision`·`variant`·`renderer`·`pipeline` 금지. 대표님께는 `숏폼`·`세로 영상`·`장면`이다.
- **유진을 고칠 때는 세 겹을 다 본다**: 의도 스키마 → 적용기 → **프로필 안내문**. 안내문을 빼면 할 수 있어도 안 고른다. 절차는 조사 문서 §5.
- **유진 시험은 새 세션에서** 한다. 앞 요청이 세션 상태를 바꿔서 같은 이유로 두 번 틀린 적이 있다.
- 주석과 커밋 메시지는 한국어로, **왜**를 적는다.
- 커밋은 각 Task 끝에 하나씩. push는 하지 않는다.
- **`git stash`를 쓰지 않는다** — 이 worktree는 여러 에이전트가 공유한다. 치워야 하면 WIP 커밋.

---

### Task 1: 유진이 변형본을 고칠 수 있다는 걸 알게 한다 (가장 값싼 구멍)

**Files:**
- Modify: `config/hermes/yujin/skills/videobox-creator/SKILL.md`
- Modify: `tests/test_hermes_yujin_profile_distribution.py` (정확한 부분 문자열을 고정하고 있다)

**배경:**
`output_variant`는 스키마(`yujin_creator_proposals.py:462`)도 적용기(`yujin_creator_proposal_adapter.py:72` ← `director_proposals.py:1025`)도 **이미 배선돼 있다.** 그런데 유진에게 "이런 게 있다"고 말해 주는 문장이 한 군데도 없어서 능력이 죽어 있다. 문단 하나로 닫힌다.

`set_crop`·`set_focal`·`set_caption_layout`·`set_safe_area`·`correct_audio` 다섯을 다른 항목(`broll`·`bgm`…)과 **같은 서식**으로 적는다. 서식이 다르면 모델이 다르게 대한다.

- [ ] **Step 1: 실패하는 시험을 쓴다** — 배포된 프로필에 다섯 동작이 적혀 있다
- [ ] **Step 2: 시험을 돌려 실패를 확인한다** (시험 이름과 파일)
- [ ] **Step 3: 통과할 만큼만 고친다**
- [ ] **Step 4: 시험을 돌려 통과를 확인한다**
- [ ] **Step 5: 커밋한다**

---

### Task 2: 유진이 숏폼 컷을 만들 수 있다

**Files:**
- Modify: `packages/domain-models/src/videobox_domain_models/yujin_creator_proposals.py` — `output_variant` 동작에 장면 고르기 추가, 또는 새 kind
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_creator_proposal_adapter.py`
- Modify: `config/hermes/yujin/skills/videobox-creator/SKILL.md`
- Test: 해당 시험 파일들

**Interfaces:**
- Consumes: Task 1이 연 프로필 자리
- Produces: 유진이 숏폼 컷을 만드는 경로 (Task 3이 판단을 채운다)

**배경:**
지금 `output_variant`가 할 수 있는 다섯은 전부 **모양 조정**(크롭·포컬·자막배치·안전영역·오디오)이고, **어느 장면을 넣을지**는 없다. 숏폼의 본질은 장면 고르기다.

**정할 것:**
- `vertical_highlight` 변형을 **만드는 것**까지 유진이 할지, 이미 있는 것을 **고치는 것**만 할지. 만드는 쪽이 대표님 한 마디에 더 가깝지만 적용기 경로가 다르다 — 읽고 판단해 근거를 적어라.
- `selected_segment_ids`를 통째로 주는 형태로 할지, "이 장면 빼/넣어"로 할지. **되돌리기가 되는가**를 기준으로 판단하라 — 유진 편집은 확인 클릭 없이 바로 적용되고, 안전장치가 되돌리기다(2026-09-01 결정).

**주의:** `materialize_variant`는 `vertical_full`일 때 장면 순서·구성이 바뀌면 `vertical_full_segment_order_or_membership_changed`로 거부한다(`output_variants.py`). 하이라이트는 다르다 — 그 차이를 먼저 읽어라.

- [ ] **Step 1: 실패하는 시험을 쓴다** — 유진 제안이 숏폼 장면 선택으로 적용된다
- [ ] **Step 2: 시험을 돌려 실패를 확인한다** (시험 이름과 파일)
- [ ] **Step 3: 통과할 만큼만 고친다**
- [ ] **Step 4: 시험을 돌려 통과를 확인한다**
- [ ] **Step 5: 변형 탐침**
- [ ] **Step 6: 커밋한다**

---

### Task 3: 고르는 기준이 자막 글자 수가 아니라 유진의 판단이다

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/highlight_scoring.py` 또는 그 옆에 새 경로
- Test: `tests/test_highlight_scoring.py` (있으면) 또는 새로

**Interfaces:**
- Consumes: Task 2가 연 경로

**배경:**
지금 기준은 `len(caption_text) / duration` 하나다. 말이 빽빽하면 좋은 장면이라는 가정 하나뿐이고, 파일 자신이 그 한계를 적어 뒀다. 대표님이 원하는 것은 **마케팅용 판단**이다 — 훅이 되는 첫 문장, 결론, 숫자·결과가 나오는 대목.

**제품 방향과 맞는다:** `CLAUDE.md` §2.1 — "차별점은 자산이 아니라 **고르는 일**이다. 대본을 읽고 장면마다 뭘 쓸지 유진이 고른다." 숏폼 장면 고르기는 정확히 그 일이다.

**반드시 정할 것 — 유진이 못 고를 때:**
로컬 모델이 없거나 응답이 깨지거나 느릴 수 있다. 그때 **지금의 자막 밀도 휴리스틱으로 내려가는가**, 아니면 **멈추고 말하는가**? 이 저장소에는 둘 다의 선례가 있다 — 더빙은 엔진이 없으면 **조용히 기계 목소리로 대신 읽지 않고 멈춘다**. 판단하고 근거를 적어라. **조용한 대체는 하지 마라** — 대표님이 유진의 판단이라고 믿는 결과가 사실은 글자 수 세기면 그게 제일 나쁘다.

**정직하게 남길 것:** 지금 파일의 머리말은 한계를 정직하게 적어 둔 좋은 예다. 바꾼 뒤에도 **무엇에 근거해 골랐는지**를 같은 수준으로 적어라.

- [ ] **Step 1: 실패하는 시험을 쓴다** — 자막이 빽빽하지만 알맹이 없는 장면보다, 자막이 적어도 결론이 있는 장면을 고른다
- [ ] **Step 2: 시험을 돌려 실패를 확인한다** (시험 이름과 파일)
- [ ] **Step 3: 통과할 만큼만 고친다**
- [ ] **Step 4: 시험을 돌려 통과를 확인한다**
- [ ] **Step 5: 변형 탐침** — 유진이 응답하지 않을 때 정한 대로 동작하는지
- [ ] **Step 6: 커밋한다**

---

### Task 4: 실물에서 말해 본다

**배경:**
`CLAUDE.md` §4: 완료는 대표님이 화면에서 실제로 쓸 수 있는가다. 시험이 아니라 제품에서 확인한다. 이 저장소는 유진 관련해서 "후보가 안 간 것"과 "갔는데 못 고르는 것"을 구분 못 해 네 겹을 헛돈 적이 있다 — **유진이 실제로 받은 것을 로그로 봐라.**

- [ ] **Step 1:** `scripts/owner-ready.ps1 -Mode Start -Rebuild -WithYujinMemory`. 프로필을 고쳤으면 `scripts/install-hermes-yujin-profile.ps1`도 다시 돌린다
- [ ] **Step 2:** **새 세션**에서 편집기를 열고 유진에게 한국어로 "이거 숏폼으로 잘라줘"라고 말한다
- [ ] **Step 3:** 유진이 실제로 받은 것과 돌려준 것을 로그로 확인한다
- [ ] **Step 4:** 나온 숏폼을 **내려받아 `ffprobe`로 잰다** — 1080×1920인가, 원본보다 짧은가, 검은 띠는 없는가
- [ ] **Step 5:** 고른 장면이 **말이 되는지** 사람 눈으로 본다. 자막 밀도만 봤을 때와 다른가
- [ ] **Step 6:** 잰 값을 그대로 보고서에 적는다

---

## 이 계획이 **안 하는** 것 (일부러)

- **출력 화면에 유진 진입점 만들기.** `OutputsPage.tsx`에 유진이 0건이라 완성본 만들기·변형 렌더·CapCut 내보내기를 유진에게 시킬 수 없다. 큰 구멍이지만 **화면을 새로 짓는 일**이라 크기가 다르다. 이 계획은 편집기 채팅(이미 있는 문)으로 숏폼을 뽑는 데까지만 간다. 다음 조각으로 뗀다.
- **장면 분할/합치기, 도형 오버레이, 트랙 숨김, 자막 번역·더빙의 유진 배선.** 조사 문서에 목록이 있다. 숏폼과 직접 관계없어 따로 뗀다.
- **`overrides.crop`·`focal` 화면 UI.** 지금은 값이 없을 때 잘 나오는 것이 목표였고 그건 됐다.
