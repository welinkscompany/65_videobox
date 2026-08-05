# VideoBox 전수조사 기록 및 개발 backlog

작성 시작: 2026-08-05
용도: 전수조사를 진행하며 발견한 결함·결정·범위 충돌을 누적 기록한다.
조사가 끝나면 이 문서를 근거로 순서가 있는 개발 계획을 한 번에 세운다.

이 문서 자체는 공식 Task가 아니다. `§10.8.3`에 따라 조사 산출물이므로 공식 진행률에 포함하지 않는다.

기호: `F` 결함 / `D` 결정 필요 / `A` 아키텍처 발견 / `S` 범위 충돌

---

## 1. 조사 진행 상황

| 대상 | 상태 |
|---|---|
| `CLAUDE.md` 신설, `AGENTS.md` 제거 | 완료 |
| `development-fast-path.ko.md` 전체 (§1~10) | 완료 |
| `docs/decisions/` 2건 | 완료 |
| `implementation-plan.ko.md` §1~8.5 | 완료 |
| 편집기 command 계약 (`editorCommandPort.ts`) | 완료 |
| 미디어 랭킹·라이브러리 아키텍처 | 완료 |
| 컨테이너 런타임 실측 (owner-ready Check, API 실측) | 완료 |
| `development-status-2026-06-29.ko.md` §322 | 완료 |
| `product-plan.ko.md` | 완료 |
| `architecture-plan.ko.md` | 완료 |
| `oss-adoption-map.ko.md` | **미완료** |
| `docs/superpowers/plans` 43건 / `specs` 27건 | **미완료** (필요 시 해당 Task만 열람) |
| Hermes 관련 설계·계약 | **미완료** |
| 백엔드 API 계약 전반 | **미완료** |

---

## 2. 범위 충돌 — 결정이 먼저 필요함

### S-1. 편집기 범위: 계획서 vs owner 기대

`implementation-plan.ko.md` §4 제외 목록과 §8.4가 고정한 경계:

> 풀 자체 편집기 / 실시간 멀티트랙 편집 UI / 고급 모션그래픽 / 색보정 /
> 오디오 믹싱 콘솔 / 자유 키프레임 / 완전 자동 최종본 보장

owner는 세션 중 "캡컷처럼 인터페이스를 만들어야 한다"고 말했다. 계획서가 명시적으로 제외한 범위다.

조사 결과 이 충돌은 **실제로는 크지 않다.** `editorCommandPort.ts` 실측 결과 §8.4의 14개 조작이
사실상 전부 구현돼 있고, 멀티레인 배치와 클립별 볼륨·크롭·속도·게인까지 있다.
부족한 것은 편집 기능이 아니라 **판단 근거(썸네일·길이)와 자동화**다.

- 판정: 계획서 §4 제외 목록을 바꿀 필요가 **없다**고 본다.
  `architecture-plan.ko.md` §14도 "VideoBox의 핵심은 편집기 UI가 아니라 편집 엔진이다"라고 못박는다.
- owner 확인 필요: 캡컷에서 실제로 자주 쓰던 기능 중 현재 없는 것이 있는지.
- 상태: **owner 확인 대기**

### S-2. 자동 적용 정책: 계획서 "분리" vs owner "완전 자동 배치"

- `product-plan.ko.md` §6.4는 "초기에는 B-roll 선택·컷 삭제·음악 배치·비주얼 삽입·TTS 대체를
  무조건 자동 적용하지 않는다"고 규정한다. `architecture-plan.ko.md` §2.4와 §13.5도
  추천과 적용 결과를 분리 저장하라고 요구한다.
- owner는 세션 중 **완전 자동 배치 후 검토**를 원한다고 답했다.
- 그러나 이건 실제 충돌이 아니다. `architecture-plan.ko.md` §6.5의 Recommendation 모델에
  이미 **`auto_apply_allowed`** 필드가 있다. 추천과 적용은 저장상 분리하되,
  어떤 추천을 자동 적용할지는 정책으로 조절하도록 설계돼 있다.
- OSS 채택 계획도 "`초안 만들기` 1회 승인 뒤 ranked placement bundle을 atomic하게 apply"로
  이미 이 방향이다.
- 남은 결정: `auto_apply_allowed`를 어떤 기준으로 켤지(점수 임계값, 자산 종류별 차등 등).
- 상태: **정책 결정 필요**. 구조 변경은 불필요.

---

## 3. 아키텍처 발견 — 이미 만들어져 있으나 꺼져 있음

### A-1. 의미 연관 검색과 라이브러리 재사용은 이미 설계됨

owner 요구사항("의미 연관 검색", "한 B-roll을 여러 채널에서 골고루")은 이미 코드에 반영돼 있다.

`packages/core-engine/src/videobox_core_engine/media_ranking.py` 점수 항목:

```
semantic_similarity, lexical_fallback, structured_tag_match,
duration_match, aspect_match, explicit_conditions,
favorite, recent, repetition, diversity, availability_license, pinned
```

- `semantic_similarity`가 1순위 점수이고, 실패 시 `lexical_fallback`(태그 매칭)으로 강등된다.
- `repetition`은 음수, `diversity`는 양수 점수다. 한 영상 안의 반복을 감점하고 분산을 가점한다.
- `MediaLibraryStore`는 `project_id`를 받지 않는 **전역 저장소**다.
  `ProjectAssetMaterializer`가 SHA 검증과 함께 각 프로젝트로 불변 복사한다.
  여러 채널이 같은 B-roll을 공유하는 경로가 이것이다.
- `EmbeddingProvider` 프로토콜과 LM Studio 연동 코드가 존재한다.

**결론: 새로 설계할 것이 거의 없다. D-2 하나가 막고 있다.**

`architecture-plan.ko.md` §7도 Vision Provider의 역할을 "자산 자동 태깅, 장면 내용 요약,
B-roll 인덱싱 강화"로 이미 규정하고 있다. D-2는 새 기능이 아니라 설계된 자리를 채우는 일이다.

### A-2. 컨테이너 전략이 이미 GPU 로컬 모델을 경고했음

`architecture-plan.ko.md` §11은 컨테이너화 대상을 이렇게 나눈다.

- 컨테이너화 가능: API, worker, 로컬 DB
- 컨테이너화 **비권장**: 데스크톱 앱 전체, FFmpeg 중심 파일 워크플로우, **GPU 의존 로컬 모델 실행**

현재 런타임은 API와 FFmpeg를 한 컨테이너에 넣었고, 그 결과 호스트 GPU에서 도는
LM Studio에 닿기 어려운 상태다. `D-2`의 난이도는 우연이 아니라
아키텍처 계획서가 미리 경고한 지점을 넘어선 결과다.

`§10.14` 네트워크 경계와 함께 `D-2` 설계에서 반드시 함께 검토한다.
선택지는 최소 두 가지다.

1. 컨테이너에서 호스트 LM Studio로 나가는 경계를 명시적으로 여는 방법
2. 분석 worker만 호스트에서 실행해 컨테이너 밖에 두는 방법 (§11 권고에 더 부합)

---

## 4. 미해결 결정 사항

### D-1. 오렌지 팔레트 전환 (승인 게이트 대기)

- owner가 `화이트톤` → `옅은 오렌지` 방향을 지시했다.
- 그러나 승인된 팔레트가 이미 두 건 존재한다.
  - `docs/decisions/creator-workspace-visual-approval.ko.md` (2026-07-17)
    canvas `#FAFAF9` / panel `#FFFFFF` / border `#E7E5E4` / primary `#292524` /
    secondary `#57534E` / accent `#4F46E5` / preview `#18181B`
  - `docs/decisions/2026-07-20-editor-workbench-visual-approval.ko.md` (2026-07-22)
    편집 작업판 5개 viewport 밀도·dock·drawer 승인
- 승인 문서는 artifact aggregate SHA 변경 시 재승인을 요구하며
  `scripts/build_ui_prototype_artifacts.py --require-approved`가 이를 검증한다.
- 시도했던 오렌지 값(보존): canvas `#FFF7ED` / border `#FDBA74` / text `#431407` /
  secondary `#9A3412` / accent `#C2410C` / secondary bg `#FFEDD5`
- 필요 절차: 프로토타입 artifact 재생성 → 새 aggregate SHA → owner 재승인 기록 → 구현
- 상태: **보류**. 승인 없이 CSS를 직접 바꾸지 않는다.

### D-2. 로컬 미디어 분석 worker 연결 — **최우선 후보**

- 현재 컨테이너는 `_UnavailableMediaAnalysisService` 스텁을 사용해
  모든 분석 요청을 즉시 `MEDIA_ANALYSIS_WORKER_UNAVAILABLE`로 차단한다.
- 그 결과 태그·설명·임베딩이 생성되지 않아 `semantic_similarity`가 계산 불가능하고,
  `lexical_fallback`으로 떨어지는데 태그마저 비어 있어 사실상 파일명 매칭이 된다.
- 이 하나를 뚫으면 자동 분류 + 의미 검색 + 재사용 분산이 동시에 살아난다 (`A-1` 참조).
- 제약: `§10.14`가 컨테이너 네트워크 경계를 규정한다.
  호스트 LM Studio(`127.0.0.1:1234`) 연결은 경계를 넘으므로 별도 설계가 필요하다.
- 설계에서 정할 것: 컨테이너→호스트 연결 방식, 분석 모델, 태그 체계 4축
  (찍힌 대상 / 장소·배경 / 분위기·톤 / 구도·움직임), 임베딩 저장 위치, 실패 시 동작.
- 상태: **설계 문서 선행 필요**

### D-3. 대본 생성 기능 — 후순위로 확정

- owner 결정: 당분간 Claude/GPT에서 대본을 만들어 붙여넣는다. 생성 기능은 나중에 개발한다.
- 근거: 입력 계약이 어느 쪽이든 "텍스트"로 동일하고 `script_scene_planner.py`가 장면을 쪼갠다.
  나중에 붙여도 재작업 비용이 거의 없다. 코드에 대본 생성 기능은 현재 **전혀 없다.**
- 상태: **후순위 확정**. 이번 조사·계획 범위에서 제외한다.

---

## 5. 검증된 결함

### F-1. 편집 화면 데드엔드 (높음)

- 위치: `apps/web/src/app/AppRouter.tsx` `CanonicalEditorEntry`
- 초안이 없는 프로젝트에서 `/projects/{id}/editor` 진입 시 사이드바·헤더 없는 흰 화면에
  문장 한 줄만 렌더된다. 되돌아갈 조작 수단이 없다.
- 근거: `<main aria-live="polite"><p>{message}</p></main>` 단독 렌더, ProductShell 미적용
- 수정 방향: ProductShell 유지 + "초안 만들기"로 유도하는 액션 제공

### F-2. 자산 카드에 썸네일·길이 없음 (높음) — **체감 개선 1순위**

- 편집기 좌측 자산 목록이 파일 이름만 보여준다. 썸네일도 길이도 없다.
- 영상을 눈으로 보고 고를 수 없어서, 편집 도구로서 치명적이다.
- 캡컷이 쉬운 이유는 기능 수가 아니라 시각적으로 고를 수 있기 때문이다.
- `D-2` 해결 시 길이·대표 프레임을 함께 얻을 수 있으므로 연계 처리 검토.

### F-3. 타임라인에 내부 식별자 노출 (중간)

- 클립 접근성 이름이 `broll:session-broll-segment_draft_1726b9574a-0 클립 선택` 형태다.
- `§10.13.3`의 내부 용어 금지 취지에 어긋난다.
- 수정 방향: 사람이 읽는 라벨로 치환

### F-4. 미리보기 수동 갱신 (중간)

- 편집 후 자동 갱신이 없고 "미리보기 새로 만들기"를 수동으로 눌러야 한다.
- `stale` 상태를 사용자 화면에 그대로 노출한다.
- 편집→확인 왕복이 끊겨 체감 속도를 떨어뜨린다.

### F-5. 프로젝트 삭제 경로 부재 (중간)

- `services/api/src/videobox_api/routers/projects.py`에 삭제 라우트가 없고 UI에도 수단이 없다.
- 이번 세션에서 만든 `my-project`가 목록에 영구 잔존 중이다.

### F-6. 테마 하드코딩 부채 (중간)

- `apps/web/src/styles/product-shell.css`에 하드코딩 색상 19종이 CSS 변수를 참조하지 않는다.
- 토큰을 바꿔도 셸 전체 색이 바뀌지 않는다. `D-1`의 선행 조건이다.
- 실측: `--primary`를 바꿔도 기본 버튼은 `rgb(91,74,200)` 유지

### F-7. 중복 액션 노출 (낮음)

- `새 영상 만들기`가 사이드바·헤더·본문 카드 3곳에 동시 존재한다.

### F-8. 유진 대화 편집 미연결 (별도 설계)

- Hermes 배관(컨테이너, capability token, six-gate readiness)은 완료됐으나
  실제 대화로 편집을 지시하는 경로가 연결되지 않았다.
- owner가 원하는 핵심 경험 중 하나다.
- `§10.14`와 승인 게이트가 걸려 있어 별도 설계·승인이 필요하다.

---

## 6. 정정 기록 — 초기 분석의 과장·오판

조사 초기에 아래를 "치명적 결함"으로 보고했으나 규정과 승인 기록 확인 후 판정을 정정했다.

| 최초 보고 | 정정된 판정 |
|---|---|
| "색상 시스템 2개 충돌 = 구조적 결함" | 원래 변수·하드코딩 모두 indigo로 일관됐다. 변수만 오렌지로 바꾸면서 **내가 만든** 충돌이다. 하드코딩 부채 자체는 `F-6`으로 유지 |
| "B-roll 자동 분류 영구 차단 = 치명 버그" | 의도적 fail-closed 설계다. 버그가 아니라 구성 공백이며 `D-2`로 분류 |
| "메타데이터 계약 불일치 = 별도 버그" | `D-2`의 파생 결과다. 독립 결함으로 세지 않는다 |
| "자산 중복 임포트 7건" | smoke test 반복 실행 잔여물일 가능성이 크다. 깨끗한 프로젝트에서 재현 확인 전까지 제품 결함으로 단정하지 않는다 |
| "편집기 디자인이 엉망" | 해당 화면은 2026-07-22 owner가 5개 viewport로 명시 승인한 디자인이다 |

---

## 7. 이번 세션에서 이미 반영한 변경

### C-1. 프로젝트 목록에 생성 수단 추가 (커밋 `70a15ee`)

- 프로젝트가 1개 이상이면 새 프로젝트를 만들 UI 경로가 전혀 없었다.
  기존 온보딩 폼은 프로젝트 0개일 때만 렌더된다.
- `ProjectsPage`에 `새 프로젝트 만들기` 버튼과 인라인 폼, 목록 설명 문구 추가
- 검증: RED→GREEN 1건, 프론트엔드 734 passed, `tsc --noEmit` 통과, 브라우저 실측
- `§10.13.2` 승인 어휘만 사용, 금지 용어 없음
- 공식 Task 귀속 없음. 진행률에 포함하지 않는다.

### C-2. 최상위 지침을 CLAUDE.md로 전환 (커밋 `1eef5ca`, `f4c3b07`, `c4d5ac1`)

- `AGENTS.md` 삭제. 코드·스크립트·설정 참조 0건 확인 후 제거했고 내용은 CLAUDE.md로 이관
- `implementation-plan.ko.md`와 `development-fast-path.ko.md`의 최상위 규칙 참조를 CLAUDE.md로 수정
- CLAUDE.md에 제품 범위 경계(§2.1), 승인된 시각 결정 2건, 기본 구현 루프,
  `dev-fast-path.ps1` 헬퍼, `§8.3` 완료 보고 항목 추가

### C-3. Codex 시절 턴 종료 의례 제거 (커밋 `408ec15`)

- `§10.9`가 매 턴 "다음 추천 Goal 프롬프트"를 강제하고 있었다.
  Codex 세션 단절을 메우던 장치이며 현재 환경에서 불필요하다.
- `§10.8`의 매 턴 진행률 강제도 제거했다. 분모가 미정의인 상태에서
  "변동 없음"만 반복 보고되고 있었다.
- 검증 보고와 커밋 여부 같은 실질은 유지했다.

---

## 8. 계획 수립 시 사용법

전수조사가 끝나면 이 문서를 근거로 순서가 있는 개발 계획을 세운다.

착수 시 각 항목마다 `§10.1`에 따라 공식 계획서상 귀속 Task를 먼저 식별하고,
계획서 밖 작업이면 그 사실과 진행률 비포함 여부를 명시한다.

현재까지의 잠정 우선순위 판단은 아래와 같다. 조사 완료 후 확정한다.

1. `D-2` 미디어 분석 worker — 하나로 자동 분류·의미 검색·재사용 분산이 동시 해결
2. `F-2` 자산 썸네일·길이 — 체감 개선 최대, `D-2`와 연계 가능
3. `F-1` 편집 데드엔드 — 사용 흐름을 막는 결함
4. `F-4` 미리보기 자동 갱신
5. `F-6` 테마 하드코딩 → `D-1` 팔레트 재승인
6. `F-3`, `F-5`, `F-7`
7. `F-8` 유진 대화 편집 — 별도 설계·승인
