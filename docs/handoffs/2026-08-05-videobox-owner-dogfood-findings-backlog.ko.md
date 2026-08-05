# VideoBox 조사 기록 및 개발 backlog

작성 시작: 2026-08-05
용도: 조사하며 발견한 결함·결정·범위 충돌을 누적 기록한다.
조사가 끝나면 이 문서를 근거로 순서가 있는 개발 계획을 한 번에 세운다.

이 문서 자체는 공식 Task가 아니다. `§10.8.3`에 따라 조사 산출물이므로 공식 진행률에 포함하지 않는다.

기호: `F` 결함 / `D` 결정 필요 / `A` 아키텍처 발견 / `S` 범위 충돌

## 0. 근거 등급 — 이 문서를 믿는 방법

이 조사 중 판정을 네 번 정정했다. 모두 원인이 같았다. **확인하지 않고 단정했다.**
그래서 각 항목이 어떤 근거로 적힌 것인지 등급을 붙인다.
등급이 낮은 항목은 착수 전에 반드시 실측으로 승격시킨다.

| 등급 | 뜻 |
|---|---|
| `관측` | 브라우저·API·런타임에서 직접 보거나 실행해 확인했다 |
| `코드` | 소스를 읽고 판단했다. 실제 동작은 확인하지 않았다 |
| `문서` | 계획서·결정 기록에 적힌 내용이다 |
| `미확인` | 근거가 부족하다. 착수 전 실측이 반드시 필요하다 |

| 항목 | 등급 | 확인 방법 |
|---|---|---|
| `F-1` 편집 데드엔드 | `관측` | 실제로 흰 화면을 봤다 |
| `F-2` 썸네일 미연결 | `관측`+`코드` | jpg 파일 존재 확인, 프론트 참조 0건 grep. 렌더 경로 추적은 미완 |
| `F-3` 내부 ID 노출 | `관측` | 접근성 트리에서 확인 |
| `F-4` 미리보기 수동 갱신 | `관측` | 버튼과 `stale` 표시를 화면에서 확인 |
| `F-5` 프로젝트 삭제 없음 | `관측` | 라우터에 delete 없음, 테스트 프로젝트 잔존 |
| `F-6` 테마 하드코딩 | `관측` | 변수값과 실제 렌더값을 브라우저에서 대조 |
| `F-7` 중복 액션 | `관측` | DOM에서 3곳 확인 |
| `F-8`/`D-4` Hermes 대화 편집 | **`미확인`** | **두 번 틀렸다.** 코드와 계획서가 불일치하며 런타임 확인 필요 |
| `D-1` 팔레트 | `문서` | 승인 기록 2건 확인 |
| `D-2` 분석 worker 차단 | `관측` | API가 `MEDIA_ANALYSIS_WORKER_UNAVAILABLE` 반환 |
| `D-3` 대본 생성 부재 | `코드` | 코드 전역 검색 결과 없음 |
| `A-1` 의미검색 설계됨 | `코드` | 점수 항목·저장소 구조를 읽음. **동작은 본 적 없다** (`D-2`에 막힘) |
| `A-2` 컨테이너 경고 | `문서` | `architecture-plan` §11 |
| `S-1`~`S-3` 범위 충돌 | `문서` | 계획서 조항 직접 인용 |

`미확인`과 `코드` 등급 항목은 개발 계획에 넣기 전에 실측한다.
특히 `A-1`은 "설계는 있다"까지만 확인된 것이고 "잘 동작한다"는 근거가 없다.

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
| SSOT 소유권 구조 (`§1.1`) | 완료 |
| 개발 환경 인벤토리 (`§1.2`) | 완료 |
| 백엔드 API 라우터·엔드포인트 규모 | 완료 |
| core-engine 도메인 모듈 목록 | 완료 |
| 썸네일·미디어 probe 경로 | 완료 |
| `oss-adoption-map.ko.md` | 완료 |
| Hermes 대화 편집 경로 (API·SSE·어댑터·UI) | 완료 |
| `implementation-plan.ko.md` §8~§8.2 재사용 게이트 | 완료 |
| `implementation-plan.ko.md` §9~§11 리스크·기간·착수조건 | 완료 |
| `implementation-plan.ko.md` §23 Hermes 현재 slice | 완료 |
| `docs/superpowers/plans` 43건 / `specs` 27건 | 목록만 파악. 개별 Task 착수 시 해당 문서 열람 |

### 커버리지 — 전수조사 아님

2026-08-05 시점에 "전수조사 완료"라고 적었으나 **사실이 아니었다.** 실측 수치는 아래다.

| 대상 | 전체 | 읽은 분량 |
|---|---|---|
| `docs/` 전체 | 450개 파일 / 41,107줄 | 약 1,700줄 (**약 4%**) |
| `development-fast-path.ko.md` | 280줄 | 280줄 (100%) |
| `product-plan.ko.md` | 223줄 | 100% |
| `architecture-plan.ko.md` | 468줄 | 100% |
| `implementation-plan.ko.md` | 1,283줄 | 약 630줄 (49%) |
| `development-status-2026-06-29.ko.md` | 10,772줄 | 16줄 (0.15%) |
| `handoffs/` | 76개 파일 | 1개 |
| `superpowers/plans` + `specs` | 70개 파일 | 2개 |
| `archive/` | 273개 파일 | 0개 |

읽지 않은 주요 구간과 판단:

- `implementation-plan` §12~§22 (약 650줄): 2026-07-01~07-16 시점의 closeout 기록.
  현재 상태는 `development-status` §322가 authoritative하므로 우선순위가 낮다.
- `development-status` 본문 10,756줄: append-only 이력 로그.
  최신 authoritative 항목(§322)은 읽었고 나머지는 과거 기록이다.
- `archive/` 273개: 명시적으로 보관 처리된 과거 문서.
- `plans`/`specs` 70개: Task별 문서. 해당 Task 착수 시 읽는 것이 효율적이다.

**남은 구간을 전부 읽을지 여부는 owner 결정 사항이다.**
읽지 않고 진행하면 개별 Task의 세부 제약을 놓칠 위험이 있고,
전부 읽으면 시간이 크게 든다. 현재는 후자를 선택하지 않았다.

---

## 1.1 SSOT 구조 지도

어떤 문서가 무엇의 authoritative 근거인지 정리한다. 충돌 시 아래 소유권을 기준으로 판단한다.

| 소유 대상 | authoritative 근거 |
|---|---|
| 최상위 개발 지침 진입점 | `CLAUDE.md` |
| 개발 운영 규정 본문 | `docs/development-fast-path.ko.md` `## 10` |
| 제품 정체성·범위·하지 않을 것 | `docs/product-plan.ko.md` |
| 기술 경계·계층·데이터 모델 | `docs/architecture-plan.ko.md` |
| 구현 계획·마일스톤·Task 진행률 | `docs/implementation-plan.ko.md` (상단 블록이 최신 closeout) |
| 현재 상태·검증 근거 | `docs/development-status-2026-06-29.ko.md` (현재 `§322`) |
| 시각·디자인 승인 게이트 | `docs/decisions/` |
| Task별 설계 | `docs/superpowers/specs/` (27건) |
| Task별 구현 계획 | `docs/superpowers/plans/` (43건) |
| 세션 인계·closeout | `docs/handoffs/` |
| OSS 출처·라이선스 lock | `docs/oss/`, `THIRD_PARTY_NOTICES.md` |

런타임 SSOT는 문서가 아니라 코드·데이터에 있다.

- 편집 의사결정 기준: **timeline JSON** (`architecture-plan.ko.md` §2.2)
- 편집 상태 권한: editing-session revision
- 출력 권한: FFmpeg / PyCapCut output과 output-source verifier
- CapCut은 내부 포맷이 아니라 **export 대상**이다 (§10)
- Mem0는 Hermes 보조 기억일 뿐 VideoBox SSOT가 아니다

주의: `implementation-plan.ko.md` 상단과 `development-status` 최신 섹션이 진행률·상태의
current 근거이며, 문서 본문 하단의 오래된 수치(예: `9/22`)는 historical record다.

---

## 1.2 개발 환경 인벤토리

| 항목 | 실측 |
|---|---|
| Python | 3.12.10 (`.venv/Scripts/python.exe`), 테스트 3008개 수집 |
| Node / npm | v24.16.0 / 11.13.0 (pnpm은 전역 미설치, `node_modules/.pnpm` 사용) |
| 백엔드 테스트 | `tests/` 144개 파일 |
| 프론트엔드 테스트 | 52개 파일 / 734 passed |
| E2E | `apps/web/e2e/` Playwright spec 7개 (`.mjs`), 격리 실행 러너 2개 |
| 컨테이너 | `65_videobox-videobox-workspace-1` (127.0.0.1:5173), `-postgres-1`, Hermes dashboard (9119) |
| 데이터 root | `D:/AI_Workspace_louis_office_50/20_project/65_videobox-container-data-v2` (`runtime/` + `snapshot/`) |
| 전역 미디어 라이브러리 | `20_project/videobox-user-library/media_library.sqlite` |
| 개발 서버 정의 | `.claude/launch.json` (web 5199, api 8000) |
| owner 진입점 | `scripts/owner-ready.ps1` (Check/Start/Smoke/Open/OpenCapCut) |
| 검증 스크립트 | `scripts/` 37개 (verifier·smoke·provenance 다수) |

백엔드 API는 라우터 18개, 엔드포인트 약 170개다. 규모 상위는
`editing_session` 38, `assets` 20, `outputs` 17, `director_proposals` 14,
`draft_readiness` 11, `creation_briefs` 11, `media_library` 10이다.

`packages/core-engine`에는 도메인 모듈 60여 개가 있다. 조사 중 확인한 주요 모듈은
`media_ranking`(추천 점수), `media_probe`(길이·프레임), `thumbnail_generator`,
`script_scene_planner`·`script_draft_session`(대본 분할), `timeline_builder`,
`exact_preview`, `ffmpeg_final_renderer`, `capcut_handoff`,
`project_asset_materializer`(라이브러리→프로젝트 복사)다.

`script_draft_session`은 대본 **생성**이 아니라 문자 예산 기준 **분할**이다.
대본 생성 기능은 여전히 코드에 존재하지 않는다 (`D-3` 참조).

---

## 1.3 파일 정리 분류

`§10.12.3–4`에 따라 분류한다. `artifacts/`는 기본 `preserve-evidence`이며,
삭제는 문서·테스트·실행 경로 참조가 없고 재생성 가능한 미추적 파일에만 한정한다.

### 보호 residue — 삭제 완료 (2026-08-05)

owner 승인으로 아래 3개를 삭제했다. 합계 약 133MB.

| 경로 | 크기 |
|---|---|
| `.tmp-final-fence-debug/` | 1.1M |
| `.tmp-real-video-dogfood/` | 132M |
| `apps/web/.tmp-real-video-dogfood/` | 48K |

삭제 근거: 과거 디버그 잔여물이고, 격리만으로는 Bash 읽기 구멍이 남기 때문이다.
삭제로 그 구멍까지 함께 닫혔다. 삭제 후 워킹트리는 완전히 깨끗해졌다.

`.claude/settings.json`의 `permissions.deny` 규칙은 그대로 유지한다.
같은 경로가 다시 생기면 자동으로 차단된다.

**규칙의 알려진 한계**: Bash를 통한 읽기(`cat` 등)는 `permissions.deny`로 막히지 않는다.
또한 세션 시작 시점에 `settings.json`이 없었으므로 규칙 적용은 다음 세션부터일 수 있다.

### 삭제 판정 — 현재 `safe-to-delete` 없음

`artifacts/`는 총 **9.1GB**다. 전부 gitignore 대상이지만, **모든 항목이 문서에서 참조된다.**

| 디렉터리 | 크기 | 문서 참조 |
|---|---|---|
| `owner-sample-edit-20260803-r2` | 2.0G | 3건 |
| `owner-sample-edit-20260803-r4` | 1.7G | 3건 |
| `owner-sample-edit-20260803-r3` | 1.7G | 3건 |
| `owner-sample-edit-20260803` (r1) | 1.4G | 4건 |
| `lfqa` | 1020M | 4건 |
| `long-form-capcut-qa` | 476M | 8건 |
| `task5-smoke` | 256M | 3건 |
| `release-audit-20260731-smoke` | 256M | 2건 |
| `ra31` | 256M | 2건 |
| `owner-dogfood-20260731` | 48M | 2건 |
| `owner-ready` | 108K | 12건 |

추가로 2026-08-04 handoff가 "owner sample r1–r4와 owner-ready receipt는 검증 증거로 보존한다"고
명시한다. 따라서 규정만으로는 **삭제 가능 항목이 0건**이다.

owner가 아래 삭제를 승인했다. 합계 약 **5.6GB**.

| 대상 | 크기 | 삭제 근거 |
|---|---|---|
| `owner-sample-edit-20260803` (r1) | 1.4G | r4가 최종본. r1–r3은 같은 작업의 중간 반복 |
| `owner-sample-edit-20260803-r2` | 2.0G | 위와 동일 |
| `owner-sample-edit-20260803-r3` | 1.7G | 위와 동일 |
| `ra31` | 256M | 스모크 3종 중 문서 참조만 있는 중복본 |
| `release-audit-20260731-smoke` | 256M | 위와 동일 |

보존 대상과 이유:

- `owner-sample-edit-20260803-r4` (1.7G): Task 23C closeout의 최종 근거
- `task5-smoke` (256M): `scripts/dev-fast-path.ps1`이 `--work-root`로 쓰는 **실행 경로 참조**가 있다
- `lfqa`, `long-form-capcut-qa` (1.5G): 서로 다른 기능 검증이며 문서 참조가 많다
- `owner-ready` (108K): Task 23D 검증 receipt. 참조 12건으로 최다
- `owner-dogfood-20260731` (48M): 이전 dogfood 데이터

사용자 원본 영상 5개는 `OneDrive/바탕 화면/영상샘플`에 그대로 있다.
artifacts에 있던 것은 전부 복사본과 처리 결과물이므로 원본 손실은 없다.

**실행 완료 (2026-08-05)**: owner 재승인 후 삭제했다. `artifacts`는 **9.1GB → 3.6GB**로 줄었다.
보존 대상 무결성을 확인했다. `owner-sample-edit-20260803-r4`는 파일 43개가 온전하고,
`lfqa`, `long-form-capcut-qa`, `task5-smoke`, `owner-dogfood-20260731`, `owner-ready`도 그대로다.
워킹트리는 깨끗하다.

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

### S-3. 대본 생성이 계획서에서 명시적으로 차단됨

`implementation-plan.ko.md` §23.3은 유진의 업무 영역을 정하면서 이렇게 못박는다.

> VideoBox는 영상 편집·검수·CapCut 인계에 집중하며,
> **대본·제목·썸네일·추천 영상의 생성 또는 제안은 현재 제품 범위 밖으로 차단한다.**

§23.3의 허용 산출물 표도 "대본·제목·썸네일·추천 영상 요청 → `blocked`와 짧은 이유"로 규정한다.
§23.3A.4는 Qwen에 대해서도 "title generation과 대본·썸네일·추천 영상 생성은
VideoBox의 현 영상 편집 전용 제품 범위 밖이므로 `disabled`"라고 반복한다.

owner는 대본 생성을 "나중에 개발"하겠다고 했다(`D-3`). 즉 방향 자체는 유효하나,
착수하려면 §23.3의 차단 규정을 공식적으로 바꾸는 결정이 선행되어야 한다.
현재는 "후순위"가 아니라 **"계획서상 금지"** 상태다.

- 상태: **결정 필요**. `D-3` 착수 전 §23.3 개정이 선행 조건이다.

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

### F-0. 컨테이너에서 핵심 provider 셋이 비활성 (치명) — **최우선**

근거 등급 `관측`. 컨테이너 런타임 안에서 직접 실행해 확인했다.

| Provider | 컨테이너 기본값 | 실제 동작 |
|---|---|---|
| 음성 인식 (STT) | `enabled=False` | `MockSTTProvider` |
| 본인 목소리 (TTS) | `enabled=False` | `None` |
| CapCut 내보내기 | `enabled=False` | `None` |
| 로컬 LLM | `enabled=True` | 활성 |

확인한 체인:

1. `docker/workspace-supervisor.py:48`이 `uvicorn videobox_api.main:create_app --factory`를
   **인자 없이** 실행한다
2. `services/api/src/videobox_api/main.py:462` `whisper_stt_config or WhisperSTTConfig()`
   → 기본 `enabled=False`
3. `provider_factories._build_stt_provider`가 `MockSTTProvider()`를 반환한다
4. `MockSTTProvider.transcribe`는 오디오 내용과 무관하게
   `"Line one."`과 `"Line two with restart from {파일명}."`을 반환한다
5. 컨테이너 안에서 `_build_stt_provider(WhisperSTTConfig())` 실행 결과가
   `MockSTTProvider / mock_stt`임을 직접 확인했다
6. `_build_tts_provider`와 `_build_pycapcut_exporter`는 비활성 시 `None`을 반환한다
7. 컨테이너와 venv 모두 `faster_whisper`가 설치되어 있지 않다

`scripts/run_api.py:25`(개발 서버)는 STT만 `enabled=True`로 켠다. TTS·CapCut은 어느 경로에서도 꺼져 있다.

**역방향 검증 결과 (2026-08-05) — 최초 주장을 정정한다.**

처음에는 "자막·세그먼트·B-roll 매칭이 모두 `MockSTTProvider`의 가짜 두 줄 위에 세워진다"고 적었다.
실제 산출물에서 거꾸로 추적하니 **기전이 달랐다.** r4 자막은 실제 한국어였다.

`artifacts/owner-sample-edit-20260803-r4`의 `analysis/transcripts/transcript_001.json`:

```
"provider_name": "deterministic_korean_smoke_stt"
"segments": [ {0.0 → 300.0}, {300.0 → 600.0} ]
```

`scripts/verify-production-readiness-smoke.py:103` `DeterministicKoreanSTTProvider`:

- `del request`로 **오디오를 통째로 버린다**
- 고정 문장 `SOURCE_CAPTIONS`와 고정 경계 `0–300`, `300–600`을 반환한다

같은 파일의 `DeterministicWaveTTSProvider`는 `b"\x10\x00"` 반복으로
**일정한 톤**을 쓴다. 사람 목소리가 아니다.

정정된 사실:

1. 컨테이너 런타임은 `MockSTTProvider`를 쓴다 (별개 경로, 위 체인으로 확인)
2. r4 증거물은 `deterministic_korean_smoke_stt`로 만들어졌다 (산출물에서 확인)
3. 둘 다 실제 음성 인식이 아니다. **어느 경로에서도 실제 STT가 실행된 적이 없다**
4. r4 자막 텍스트가 한국어인 이유는 stub이 대본 문장을 되돌려주기 때문이다.
   실제 발화를 인식한 결과가 아니다
5. r4 자막 타이밍은 10분을 정확히 반씩 나눈 고정값이다. 실제 음성 정렬이 아니다
6. r4의 TTS 산출물은 목소리가 아니라 일정한 톤이다

**따라서 r4는 "실제 편집 결과물"이 아니라 파이프라인 배관 검증물이다.**
2026-08-04 handoff가 r4를 "검증 증거"로 보존하라고 한 것은 배관 검증 증거로는 맞지만,
**사람이 r4를 보고 들어서 품질을 판정하는 용도로는 쓸 수 없다.**
Task 9 acceptance를 r4로 수행하면 실제 품질에 대해 아무것도 알 수 없다.

`verify-production-readiness-smoke.py`의 docstring도
"Only LLM/STT/TTS providers are deterministic"이라고 명시한다.
기존 검증은 의도적으로 실제 AI 경로를 우회하며, 그 사실을 숨기지 않았다.
문제는 그 결과물이 이후 "owner sample 검증 증거"로 승격되어 인용된 것이다.

### F-1. 편집 화면 데드엔드 (높음)

- 위치: `apps/web/src/app/AppRouter.tsx` `CanonicalEditorEntry`
- 초안이 없는 프로젝트에서 `/projects/{id}/editor` 진입 시 사이드바·헤더 없는 흰 화면에
  문장 한 줄만 렌더된다. 되돌아갈 조작 수단이 없다.
- 근거: `<main aria-live="polite"><p>{message}</p></main>` 단독 렌더, ProductShell 미적용
- 수정 방향: ProductShell 유지 + "초안 만들기"로 유도하는 액션 제공

### F-2. 편집기 자산 카드가 썸네일을 렌더하지 않음 (높음) — **체감 개선 1순위, 난이도 낮음**

증상은 "편집기 좌측 자산 목록이 파일 이름만 보여준다"이다. 영상을 눈으로 고를 수 없다.

조사 결과 **백엔드는 이미 완성돼 있다.** 빠진 것은 UI 연결 한 곳뿐이다.

- `packages/core-engine/.../thumbnail_generator.py`의 `generate_video_thumbnail`이 존재한다.
- `local_pipeline.py:496`이 B-roll 임포트 시 `_try_generate_broll_thumbnail`을 호출하고
  `thumbnail_uri`를 metadata에 기록한다.
- API 엔드포인트 `GET /api/projects/{project_id}/assets/{asset_id}/thumbnail`이 있다.
- 프론트엔드 헬퍼 `api.assetThumbnailUrl`도 `apps/web/src/api.ts`에 있다.
- 실제 썸네일 파일도 생성돼 있다.
  `.../b-roll-smoke-test/derived/thumbnails/`에 jpg 4개 존재.

**그런데 `api.assetThumbnailUrl`을 호출하는 프론트엔드 코드가 한 곳도 없다.**
`apps/web/src/features/editor/assets/`에 `thumbnail` 문자열 자체가 없다.
`local_pipeline.py:502` 주석도 "picker just falls back to a text label when no thumbnail exists"라고
적혀 있어, 폴백만 살아 있고 정상 경로가 연결되지 않은 상태로 보인다.

- 길이 역시 `media_probe.py`의 `probe()`가 `duration_sec`를 반환하므로 재료는 있다.
  다만 자산 목록 응답에 실리는지는 별도 확인이 필요하다.
- `D-2`(비전 분석)와 **무관하다.** 썸네일은 ffmpeg 프레임 추출이라 분석 worker 없이도 동작한다.
- 수정 방향: 편집기 자산 카드에 `assetThumbnailUrl` 연결 + 썸네일 부재 시 기존 텍스트 폴백 유지.

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

### F-8. 유진 대화 편집 — **구현 완료. 인증만 남음** (판정 정정)

초기에 "대화로 편집을 지시하는 경로가 연결되지 않았다"고 기록했으나 **오판이었다.**
경로는 end-to-end로 구현돼 있다.

백엔드:

- `services/api/.../routers/hermes_conversation.py`: `create_run`, `cancel_run`, `retry_run`,
  SSE `events` 스트림
- `packages/core-engine/.../yujin_creator_proposal_adapter.py`:
  유진 출력을 파싱해 Director DTO로 투영하고 **candidate-only proposal**을 만든다.
  media candidate attestation, 대상 세그먼트 정렬, 지원 control 검증까지 포함한다.

프론트엔드:

- `apps/web/src/features/editor/workbench/hermesSseClient.ts`: SSE 수신
- `RightDock.tsx`: `유진에게 요청하기` 입력창
  (placeholder `예: 이 구간에 어울리는 B-roll을 추천해 줘`),
  `요청 보내기` 버튼, `선택한 추천 적용` 버튼
- `YujinMemoryPanel.tsx`: 보조 기억 패널
- `api.createHermesRun`: run 생성 호출

즉 owner가 원하는 "대화로 지시하면 추천이 뜨고 골라서 적용" 경험은 **이미 만들어져 있다.**
`추천과 적용 분리`(`product-plan` §6.4) 원칙도 candidate-only 설계로 지켜져 있다.

**그러나 "인증만 하면 동작한다"는 판정도 틀렸다 (2차 정정).**

`implementation-plan.ko.md` §23을 읽고 나서 다시 정정한다. 계획서는 아래를 명시한다.

- §23.0: "유진 profile, Hermes→VideoBox API 권한중개, egress allowlist gateway,
  OAuth login, mem0, **편집 mutation은 아직 만들지 않았다**"
- §23.1 `[~] 진행 중`: "egress allowlist gateway가 별도 gate를 통과하기 전에는
  `hermes model`을 실행하지 않는다" → **OAuth 로그인 자체가 선행 게이트에 막혀 있다**
- §23.2.6 `[ ] 미완료`: "signer는 아직 어떤 VideoBox API route나 Hermes container에도
  배포하지 않는다"
- §23.3 `[ ] 미완료`: 첫 slice의 유진은 "action 없는 approval request 제안만" 한다.
  장면·자산·음향 제안에 대해 "Gateway가 허용하는 tool: 첫 slice에서는 없음"
- §23.4 `[ ] 미완료`: "`applied`는 이 slice 범위 밖이며, 첫 slice에서 proposal은
  durable하지만 **action 없는 기록**이다"

**코드와 계획서가 불일치한다.** 코드에는 run/SSE/proposal adapter/composer/적용 버튼이
존재하지만, 최상위 계획서는 gateway·signer·OAuth·편집 mutation을 미완료로 표기한다.
계획서 §23은 2026-07-19/20 기준이고 코드는 이후 Task 23까지 진행됐으므로,
계획서가 stale일 수도 있고 코드가 게이트 전에 앞서 만들어진 UI일 수도 있다.

**어느 쪽인지 확정하려면 런타임 확인이 필요하며, 그 확인 자체가 인증을 요구한다.**
현재 상태에서 "동작한다" 또는 "동작하지 않는다"를 단정하지 않는다.

- 재분류: `D-4` **코드·계획서 불일치 해소 필요**
- 선행 작업: §23의 각 `[ ]`/`[~]` 항목을 현재 코드 상태와 대조해 계획서를 갱신하거나,
  코드가 게이트를 앞질렀다면 그 사실을 기록한다.
- 상태: **확인 필요**. owner 로그인만으로 해결된다고 주장하지 않는다.

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

**규정 위반 기록**: 이 작업은 `implementation-plan.ko.md` §8.1 재사용 게이트를 거치지 않았다.
§8.1은 모든 구현 goal에 적용되는 상위 규칙인데 당시 해당 문서를 읽지 않아 몰랐다.
사후 분류를 남긴다.

| 재사용 후보 | 분류 | 이유 |
|---|---|---|
| `ProjectOnboarding` | `exclude` | 나레이션·스크립트 경로를 필수로 요구해 단순 생성에 맞지 않는다. 프로젝트 0개 경로에서는 기존대로 재사용을 유지했다 |
| shadcn `Button`, `Input` | `adopt as-is` | pinned source component를 그대로 사용 |
| 신규 인라인 폼 | `rewrite` | 이름 하나만 받는 최소 폼. 새 의존성·새 API 없음 |

경계 보존: 새 API를 만들지 않고 기존 `POST /api/projects`만 호출했다. repo 경계 오염 없음.

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

## 7.1 이 기록을 개발 계획으로 바꾸는 방법

조사 기록은 폐기하지 않는다. 아래 순서로 **계획의 입력**으로 쓴다.

### 1단계 — 런타임 진실 기준선

실제 대본과 실제 B-roll로 파이프라인을 처음부터 끝까지 한 번 돌리고,
**이 문서의 각 항목을 체크리스트로 삼아** 실제 동작을 확인한다.

- `미확인`·`코드` 등급 항목을 `관측`으로 승격하거나 반증한다
- 특히 `D-4`(Hermes 코드 vs 계획서 불일치)와 `A-1`(의미검색 실제 품질)을 확정한다
- 문서가 주장하는 "Task 23 4/4 100%"가 실사용 기준으로도 맞는지 확인한다

이 단계는 owner의 Task 9 acceptance와 같은 작업이므로 별도 비용이 아니다.

### 2단계 — 문서를 실측에 맞추기

1단계 결과로 어긋난 문서를 갱신한다. 최소 대상은 `implementation-plan` §23이다.
이걸 해야 다음 세션이 잘못된 전제로 시작하지 않는다.

### 3단계 — backlog를 순서대로 구현

`§8`의 우선순위대로 진행한다. 각 항목 착수 시:

1. `§10.1`에 따라 귀속 Task를 식별하고, 해당 `plans`/`specs` 문서만 읽는다
2. `§8.1` 재사용 게이트를 먼저 통과한다
3. TDD로 RED → GREEN
4. `§8.3` 완료 보고 항목을 남긴다

70개 plan/spec을 미리 다 읽지 않고 착수 시점에 해당 문서만 읽는 이유는,
그것이 `§10.1`과 `§8.1`이 원래 요구하는 방식이고 더 정확하기 때문이다.

## 8. 계획 수립 시 사용법

전수조사가 끝나면 이 문서를 근거로 순서가 있는 개발 계획을 세운다.

착수 시 각 항목마다 `§10.1`에 따라 공식 계획서상 귀속 Task를 먼저 식별하고,
계획서 밖 작업이면 그 사실과 진행률 비포함 여부를 명시한다.

전수조사 결과 확정한 순서다.

### owner가 직접 해야 하는 것 (코드 작업 아님)

| 항목 | 내용 |
|---|---|
| `D-4` | Hermes provider OAuth 로그인. 이것만 하면 유진 대화 편집이 즉시 동작한다 |
| artifacts 삭제 | 승인된 5.6GB 삭제 명령 실행 (안전 분류기가 AI 실행을 차단함) |
| `S-1` 확인 | 캡컷에서 자주 쓰던 기능 중 현재 없는 것이 있는지 |

### 개발 착수 순서

| 순서 | 항목 | 근거 | 난이도 |
|---|---|---|---|
| 1 | `F-2` 자산 썸네일 UI 연결 | 백엔드·API·헬퍼 완성. UI 호출만 빠짐. 체감 개선 최대 | 낮음 |
| 2 | `F-1` 편집 데드엔드 | 사용 흐름 자체를 막는 결함 | 낮음 |
| 3 | `F-4` 미리보기 자동 갱신 | 편집→확인 왕복 체감 | 중간 |
| 4 | `F-3`, `F-5`, `F-7` | 내부 ID 노출, 삭제 경로 부재, 중복 액션 | 낮음 |
| 5 | `F-6` 테마 하드코딩 통일 | `D-1`의 선행 조건 | 중간 |
| 6 | `D-1` 오렌지 팔레트 재승인 | artifact 재생성 → 새 SHA → owner 승인 | 중간 |
| 7 | `D-2` 미디어 분석 worker | 자동 분류·의미 검색·재사용 분산을 한 번에 해결. `A-2` 때문에 설계 선행 필수 | 높음 |
| 8 | `S-2` 자동 적용 정책 | `auto_apply_allowed` 임계값 결정. `D-2` 이후가 자연스럽다 | 낮음 |

### 순서 근거

`F-2`가 1순위인 이유는 조사 중 난이도가 뒤집혔기 때문이다. 초기에는 "썸네일 기능이 없다"고
봤으나 실제로는 생성·저장·API·프론트 헬퍼가 전부 있고 편집기 UI가 호출만 하지 않았다.
가장 적은 변경으로 가장 큰 체감 개선을 낸다.

`D-2`를 뒤로 미룬 이유는 난이도와 선행 조건 때문이다. `A-2`가 밝힌 대로 컨테이너 경계
설계가 먼저 필요하고, 그 전에 1~6번의 값싼 개선을 끝내는 편이 owner 체감이 빠르다.
다만 `D-2`는 owner의 핵심 요구(B-roll 자동 분류·의미 검색)와 직결되므로,
1~4번을 끝낸 뒤 곧바로 설계에 들어가는 것을 권한다.

`F-8`은 개발 항목에서 빠졌다. 이미 구현돼 있고 `D-4` 인증만 남았기 때문이다.
