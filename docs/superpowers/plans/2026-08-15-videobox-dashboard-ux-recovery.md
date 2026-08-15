# VideoBox Dashboard UX Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 전체 pytest(약 30분)는 시간에 민감하므로 **다른 무거운 작업과 절대 동시에 돌리지 않는다** — 2026-08-15에 두 번, 무관한 테스트가 부하 때문에 실패했다.

**Goal:** owner가 실제 테스트에서 "쓰기 어렵다"고 판단한 대시보드를, 판단 대상(영상)이 화면의 주인공이 되고 같은 정보가 한 번만 나오도록 고친다.

**Architecture:** 기존 구조를 재사용한다 — 편집기의 dock/drawer 해석기(`editorWorkbenchLayout.ts`), 접힘 상태 persist 패턴, ProductShell 사이드바. 새 화면·새 경로·새 기능은 만들지 않는다.

**Tech Stack:** React/TypeScript, Vitest, Playwright, editor-workbench.css. 팔레트(`#FAFAFA`/`#C2410C`/`#1C1C1E`)와 intranet 계약(컨트롤 32px, radius 스케일, 채워진 입력, 표면 링)은 그대로다.

---

## 0. 실측 진단 (2026-08-15, 실제 컨테이너 127.0.0.1:5173)

심한 순. 전부 현재 배포본에서 직접 쟀다.

### P1 — 판단 대상인 영상이 화면의 8.5%다

- 재현: `/projects/my-project/editor?session_id=editing_session_draft_5ee4d7c4b924`를 1920×1080으로 열고 video의 실표시 크기를 잰다.
- 1920×1080: 그림 560×314 = **화면의 8.5%**. 1440×900: 476×267 = **9.8%**.
- **원인은 가로가 아니라 세로다.** media shell은 1129px 넓지만 16:9 그림은 높이 316px에 묶여 563px만 쓴다. 세로 예산을 먹는 것: toolbar 63 + 출력 변형 128 + 타임라인 122 + stage 안의 부속 행들(header 37, playback 25, 안내문 16, status 16, **소스 확인 85**).
- **따라서 side dock을 닫는 것만으로는 그림이 커지지 않는다.** 이전 제안 초안(artifact)의 "서랍화로 미리보기 확대" 주장은 메커니즘이 틀렸다 — 서랍화는 어수선함을 줄일 뿐이고, 그림을 키우는 것은 세로 회수다.

### P2 — 홈이 같은 사실을 세 번 말한다

- 재현: `/projects/my-project/home`을 열고 본문 텍스트에서 문구 빈도를 센다.
- "초안 있음" **3회**, "편집 계속하기" 버튼 **2회**, 자산 상태 2회, 완성본 상태 2회. 「다음 할 일」 블록 143px + 카드 그리드 226px = 369px가 새 정보 없이 반복이다.

### P3 — 같은 재료가 세 곳에 나뉘어 있다

- 재현: `/library`(영상 8)와 `/footage`(촬영본 8개)를 열면 같은 8개 파일이 다른 UI로 나온다. 프로젝트 안 `자산` 화면까지 합치면 세 곳이다.
- owner는 "이 일은 어느 화면이지?"를 매번 먼저 풀어야 한다.

### P4 — 사이드바 한 기둥에 범위가 다른 메뉴 두 벌

- 재현: 아무 프로젝트 화면에서 사이드바를 본다. 전역 이동 4개(프로젝트·내 라이브러리·촬영본 정리·설정) + 프로젝트 전환기 + 단계 5개(기획·자산·편집·검토·출력)가 같은 모양으로 한 기둥에 있다.

### 이미 닫힌 것 (이 계획 범위 아님)

Full HD 역전(`5f968ee8f`), "길이 확인 중" 거짓 문구(`f3b93de22`), footage 헤더의 내부 용어(`65d38a8b5`)는 2026-08-15에 수정·배포 완료.

### 판정: HEAD `565582c96` (편집기 기본 preview-only, 미배포)

**유지한다.** 단, 이 변경의 효과는 "그림 확대"가 아니라 "초점"이다(그림은 세로 제약이라 그대로 563px). 어수선함을 줄이고 Task 2~3과 합쳐질 때 의미가 생긴다. 되돌리려면 `git revert 565582c96`.

---

## 원칙

- 매 Task는 **독립 커밋·독립 배포·`git revert` 한 번으로 롤백**된다.
- 화면 문구를 바꾸는 Task는 §10.13 창작자 언어 규정을 RED copy 테스트로 고정한다.
- 완료 판정은 테스트가 아니라 **실제 브라우저**다(CLAUDE.md §4). 배포 후 컨테이너가 새 번들을 내려주는지 반드시 확인한다(번들 해시 비교 — 브라우저 캐시에 두 번 속았다).
- 검증 명령: focused Vitest → 해당 E2E → `npm --prefix apps/web run build` → 배포 → 브라우저. 전체 pytest는 frontend-only 변경에는 돌리지 않는다.

---

### Task 1: 편집기 세로 회수 1 — 출력 변형을 접는다

가장 위험이 낮고 체감이 큰 변경. 출력 변형(128px)은 항상 보는 표면이 아니라 비교할 때 여는 표면이다.

**Files:**
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx` (variants 섹션에 접기 토글)
- Modify: `apps/web/src/styles/editor-workbench.css`
- Modify: `apps/web/src/features/editor/workbench/editorUiState.ts` (접힘 상태 persist — 기존 패턴 재사용)
- Test: `apps/web/src/features/editor/workbench/editor-workbench.test.tsx`
- Test: `apps/web/e2e/exact-preview.spec.mjs` (Full HD 그림 크기 가드 상향)

- [ ] RED: 기본 상태에서 출력 변형이 접혀 있고(헤더 ~40px), 토글로 펼치면 기존 내용 전부 접근 가능하며, 선택이 프로젝트별로 기억되는 것을 실패 테스트로 고정한다. 접힘 토글 버튼 문구는 창작자 언어("출력 변형 열기/닫기" 수준)로 §10.13 audit에 포함한다.
- [ ] GREEN 최소 구현. 펼친 상태의 기존 기능(마스터/가로/세로/나란히, materialize/lock)은 그대로.
- [ ] `exact-preview.spec.mjs`의 Full HD 가드를 상향한다: 접힘 기본에서 media shell ≥ 400px.
- [ ] 실제 브라우저(1920×1080·1440×900): 그림 크기 재측정, 접기/펼치기 동작, 펼친 뒤 모든 버튼 접근, console error 0.
- [ ] 커밋 `feat: collapse output variants until asked` → 배포 → 번들 해시 확인.

**롤백:** 해당 커밋 revert. **예상 효과:** shell 316→약 400px (그림 약 +27%).

### Task 2: 편집기 세로 회수 2 — 소스 확인을 자산 dock으로 옮긴다

미리보기 아래 "소스 확인" 목록(85px)은 참고 자료다. 참고 자료의 자리인 왼쪽 dock(자산과 대본)으로 옮긴다.

**Files:**
- Modify: `apps/web/src/features/editor/preview/preview-stage.tsx` (sources 섹션 제거 또는 prop으로 위임)
- Modify: `apps/web/src/features/editor/workbench/EditorWorkbench.tsx` (왼쪽 dock에 소스 확인 삽입)
- Test: `apps/web/src/features/editor/preview/preview-stage.test.tsx`
- Test: `apps/web/src/features/editor/workbench/editor-workbench.test.tsx`

- [ ] RED: 소스 확인 버튼들이 왼쪽 dock에 있고, 미리보기 아래에는 없으며, audition 동작(원본 열기 → 편집본 돌아가기)이 그대로임을 고정한다. drawer 모드에서도 접근 가능해야 한다.
- [ ] GREEN. audition 경로(`showAudition`/`showExact`)는 옮기지 않고 그대로 부른다.
- [ ] 실제 브라우저: 원본 열기 → 재생 → 편집본으로 돌아가기 전체 경로. 그림 크기 재측정.
- [ ] 커밋 `feat: move source audition into the asset dock` → 배포 → 확인.

**롤백:** revert. **예상 효과:** shell +85px. Task 1과 합치면 그림 약 500px 높이 = **화면의 약 20%** (현재의 2.4배).

### Task 3: `565582c96` 배포와 stage 부속 행 정리

- [ ] 이미 커밋된 preview-only 기본값을 이 시점에 배포에 포함한다(별도 구현 없음).
- [ ] stage의 "자막은 영상에 포함되어 재생됩니다"(16px) 안내를 status 행과 한 줄로 합친다. RED: 두 정보가 모두 접근 가능하되 행이 하나임을 고정.
- [ ] 실제 브라우저: 편집기 첫 진입이 미리보기 단독인지, 툴바 두 버튼으로 dock이 열리는지, 열림이 기억되는지.
- [ ] 커밋 → 배포 → 1920·1440 재측정 결과를 이 파일 아래 "실행 기록"에 남긴다.

**롤백:** stage 행 정리 revert + `git revert 565582c96`.

### Task 4: 홈을 한 번만 말하게 한다

**Files:**
- Modify: `apps/web/src/app/ProductShell.tsx` (ProductHome)
- Test: `apps/web/src/app/AppRouter.test.tsx` 또는 기존 home 테스트 위치

- [ ] RED: "초안 있음"류 상태 문구가 화면에 **1회**, "편집 계속하기" CTA가 **1회**만 나옴을 고정한다. 다음 할 일 1개 + 상태 요약 1벌 + 유진 입력만 남는다. 카드 3장(자산/편집/완성본)은 상태 요약과 통합한다 — 이동 기능은 유지하되 같은 문구를 반복하지 않는다.
- [ ] copy audit: 남는 문구 전부 §10.13 어휘 점검.
- [ ] 실제 브라우저: 홈에서 편집·자산·출력으로 각각 이동 가능, 중복 문구 0.
- [ ] 커밋 `fix: say each home status once` → 배포 → 확인.

**롤백:** revert. 위험: 낮음(한 컴포넌트).

### Task 5: 사이드바 구획 분리

경로·기능 변경 없음. 전역 메뉴 / 프로젝트 전환 / 단계 메뉴를 시각적으로 구분한다(구획 제목·간격·표면 — intranet 계약 안에서).

**Files:**
- Modify: `apps/web/src/app/ProductShell.tsx`, `apps/web/src/styles/product-shell.css`
- Test: 기존 ProductShell 테스트 + `footage-design-system.test.ts` 패턴의 CSS 계약 테스트

- [ ] RED: 세 구획이 구분된 landmark/heading을 갖고, 링크 대상은 하나도 바뀌지 않음을 고정한다.
- [ ] 실제 브라우저: 접힘(icon) 모드 포함 두 상태 확인, 키보드 순회.
- [ ] 커밋 → 배포 → 확인.

**롤백:** revert. 위험: 낮음.

### Task 6: 재료 찾기 한 통로 — 교차 진입

전면 통합은 하지 않는다(아래 "하지 않을 것"). 대신 중복의 비용을 낮춘다: `/library`의 영상 자산 카드에서 그 자산의 `/footage` 정리로 바로 가는 진입점, `/footage` 소스 목록에서 `/library` 미리보기로 돌아오는 진입점.

**Files:**
- Modify: `apps/web/src/features/library/VideoAssetGrid.tsx` 또는 `LibraryPreviewPane.tsx`
- Modify: `apps/web/src/features/footage/FootageSourceList.tsx`
- Test: `LibraryPage.test.tsx`, `FootageOrganizerPage.test.tsx`

- [ ] RED: 라이브러리에서 선택한 영상 자산에 "구간 정리" 진입이 있고 그 자산이 선택된 채 `/footage`가 열림을 고정한다. 문구는 §10.13 audit.
- [ ] 실제 브라우저: 왕복 경로.
- [ ] 커밋 → 배포 → 확인.

**롤백:** revert. 위험: 낮음(링크 추가).

### Task 7: 게이트 — 전체 회귀와 실행 기록

- [ ] 단독으로 `.venv\Scripts\python.exe -m pytest -q` (다른 작업과 동시 금지).
- [ ] `npm --prefix apps/web test` · `run build` · `run test:e2e` · `run test:e2e:editor-workbench` · `git diff --check`.
- [ ] 실제 브라우저 1920×1080·1440×900에서 6개 경로 순회: console error 0, 4xx/5xx 0, 가로 overflow 0, 그림 크기 전후표 작성.
- [ ] 스냅샷 5장 재생성 여부를 owner에게 물어 재승인 받는다(2026-08-15 재승인 절차와 동일).
- [ ] 핸드오프 문서에 결과 추가. **owner acceptance는 별도다** — owner가 직접 화면을 쓰고 판단하기 전에는 완료라 말하지 않는다.

---

## 하지 않을 것

1. **라이브러리·촬영본·프로젝트 자산의 전면 통합(초안의 제안 A)** — 경로·store·E2E가 광범위하게 걸린다. Task 6으로 중복 비용을 먼저 낮추고, owner가 1~6을 써본 뒤 별도 결정으로 진행한다.
2. **5단계를 한 작업판으로(초안의 제안 B)** — 각 단계 화면이 이미 밀도가 높아, 한 화면화는 지금 문제(공간 부족)를 오히려 키울 수 있다. 근거가 더 필요하다.
3. **팔레트·비주얼 방향 변경** — 승인 기록 재승인 없이는 안 한다(CLAUDE.md §6).
4. **새 편집 기능** — §2.1 범위 밖(색보정·마스크·키프레임·멀티캠 등)은 UX 작업에 얹지 않는다.
5. **모바일/태블릿 최적화** — owner 실사용 환경은 데스크톱이다. drawer 모드 회귀만 깨지 않게 지킨다.

## 초안(artifact) 대비 판정

- 진단 P2·P3·P4는 초안과 같고 재검증됐다. **초안 C의 메커니즘("서랍화가 미리보기를 키운다")은 틀렸다** — 그림은 세로 제약이며, 이 계획은 세로 회수(Task 1~3)를 주 수단으로 바꿨다.
- 초안 A·B는 보류로 강등했다(위 "하지 않을 것" 1·2).

## 실행 기록

(각 Task 완료 시 여기에 실측값과 커밋 SHA를 추가한다.)
