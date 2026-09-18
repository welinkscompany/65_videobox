# 2026-09-10 진단 후속 작업 결과 (2026-09-18 수행)

`docs/system-audit-2026-09-10-claude-remediation.ko.md`(정본)의 작업 순서를 따라
FIX-00~FIX-02, INVEST-01~04, VERIFIED-01을 수행한 결과다. 작업 시작 시점:
D=`b590353b406f6a08d41654db679a547e527eb931`(2026-09-10),
E=`dc64ca7838a979c1392bfcbe54675ccbd66154aa`(2026-09-11), 시작 HEAD=`04d9af569`
(153개 커밋 뒤처짐). 작업 도중 다른 세션이 `515779e21`(오버레이 `placement_id`
중복·내레이션 분할 겹침·변형본 충돌 append 고침, `composition_plan.py`·
`output_variants.py`)을 커밋했다 — 이 문서의 범위(E2E) 밖이라 손대지 않았다.

## FIX-00 — 기준 재확정

- 활성 worktree/브랜치는 프롬프트가 가리킨 그대로였다.
- `apps/web/e2e/` 디렉터리는 **2026-09-01 이후 한 번도 수정되지 않았다**
  (`git log -1 -- apps/web/e2e/` = `367538211` "fold the standalone media
  stage into the editor dock"). 즉 2026-09-10 진단 문서의 E2E 실패 목록은
  09-01 이전 화면 기준으로 작성된 낡은 테스트가 09-01·09-04·09-05·08-27·
  08-30·09-07의 여러 승인된 UI 변경(모두 09-01 이후)과 어긋난 것이지,
  진단 이후 153개 커밋 어딘가에서 새로 생긴 결함이 아니다.
- 시작 시 `git status --short`는 다른 세션이 작업 중이던
  `packages/core-engine/src/videobox_core_engine/composition_plan.py`,
  `output_variants.py`, `tests/test_clip_placement.py`,
  `tests/test_output_variants.py`를 dirty로 보여 줬다. 이 파일들은 이번
  세션 내내 건드리지 않았고, 그 세션이 `515779e21`로 커밋한 뒤에는 clean
  상태로 확인됐다.
- 이번 수정 범위는 **`apps/web/e2e/*.spec.mjs` 아홉 파일뿐**이다(아래 표).
  멀티트랙 render/session/transaction, 유진 overlay, owner-ready 변경은
  이번 세션에서 손대지 않았고(다른 세션이 같은 날 별도로 진행), 그 변경이
  이번 E2E 수정에 영향을 주지 않았음을 커밋 경계로 확인했다.

## FIX-01 — 승인된 화면에 맞게 E2E 검증 복구

세 파일 모두 **실제로 재현**한 뒤(과거 실패를 그대로 베끼지 않고 현재
HEAD에서 직접 `node ./e2e/run-isolated.mjs <file>`로 실행) 고쳤다. 지운·
skip한 시험은 없다. 승인된 UI를 되돌리지 않았다 — 전부 테스트 쪽 기대값을
현재 승인된 동작에 맞췄다.

### `product-shell.spec.mjs` (원래 26·36·46번 줄, 3건)

| 시험 | 원인 | 고침 |
|---|---|---|
| "local catalog renders the creator shell…" | `/projects/local-draft/home`에는 접힌 "전체 메뉴" 단추가 더 이상 없다 — 2026-09-05 owner 지시로 상시 노출 왼쪽 `SideNav`("화면 이동")가 그 자리를 대신한다(`ProductShell.tsx`의 `sideNavPlace`가 `home`/`library`/`voices`/`footage`/`settings`에서 `hideGlobalMenu`를 켠다) | `getByRole("navigation",{name:"화면 이동"})`로 교체 |
| "an empty local catalog keeps project creation…" | 단추 문구가 "+ 새 프로젝트 만들기"에서 "+ 새로 만들기"로 바뀌었다(2026-08-30 owner 재지시, 이름을 안 묻고 바로 편집기로) | 문구 갱신 |
| "desktop shell keeps global destinations separate…" | `/home`은 이제 SideNav를 쓰므로 접힌 "전체 메뉴"가 없다. 접힌 메뉴는 단계 화면(이야기/편집/확인과 내보내기)에는 그대로 남아 있다 | 시험 대상 경로를 `/create`로 바꿔 실제로 접힌 메뉴가 있는 화면에서 같은 계약을 확인 |

### `exact-preview.spec.mjs` (원래 288·297·306·322번 줄, 4건)

- 288/297/306번: 세 시험 모두 `tracks: []`(빈 타임라인) fixture를 쓰면서
  exact_preview 상태별(pending/stale/failed) 안내 문구를 기대해 **자기
  모순**이었다. `PreviewStage`는 `projectIsEmpty`(=`view.tracks.length===0`)가
  참이면 상태와 무관하게 "여기에 영상이 나와요"(빈 프로젝트 안내)만
  그린다(2026-09-04 owner 지시: "아직 아무것도 안 넣었으면 실패라고 말하지
  않는다"). 세 시험에 최소한의 트랙(내레이션 클립 1개)을 채워 넣어
  모순을 없앴다 — 빈 프로젝트 안내 자체를 지키는 시험(`empty-project-stage.test.tsx`)은 그대로 둔다.
- 322번(현재 335번): "B-roll · 1번째 장면 원본 열기" 단추가 이제 네이티브
  `<details>`("원본 확인")로 접혀 있다(`EditorAssetBrowser.tsx`). 열지 않으면
  안의 단추가 `hidden`이다. 또 "B-roll"이 2026-09-07에 "영상"으로
  이름이 통일됐다. 둘 다 고침.

### `z-script-first-vertical.spec.mjs` (원래 60번 줄, 1건)

네이티브 `video.controls`를 기대하던 부분을 없앴다 — 이 화면은 브라우저
기본 컨트롤을 **의도적으로 끈다**(2026-08-28 owner 지적: 기본 컨트롤과
자체 재생줄이 겹쳐 단추가 둘씩 보였다). 대신 이 컴포넌트가 실제로 그리는
재생/일시정지·탐색(`currentTime` 이동)·음소거 단추를 눌러 미디어 상태가
실제로 바뀌는지 확인하도록 재작성했다(재생→일시정지 전환, seek 반영, 음소거
토글). native controls를 다시 켜서 통과시키지 않았다.

## FIX-02 — E2E 성능 결과 저장 격리

`release-gates.spec.mjs`가 `path.resolve("test-results", …)`로 cwd 기준 고정
경로에 쓰던 것을 `testInfo.outputPath(...)`로 바꿨다 — Playwright가 실제
설정된 outputDir(기본값 또는 `--output` 지정값)을 반영하고, 이 시험 전용
하위 폴더로 자동 격리한다.

검증: `--output=<임시 경로>`로 실행해 결과 JSON이 **그 경로 안에만** 생기고
기존 `test-results/`에는 안 생기는 것을 직접 확인했다
(`<지정 경로>/release-gates-workbench-do-…/editor-workbench-performance.json`
존재, `test-results/editor-workbench-performance.json` 없음). 판정 의미
(구조적 실패·20% 회귀 기준)는 그대로다.

## INVEST-01 — 후보 구간 입력 손실

재현 시도: `npx vitest run`(전체 프런트 스위트, 139 파일)을 현재 HEAD에서
그대로 돌렸다. **1752개 전부 통과**, 해당 시험도 포함해 실패 없음. 격리
실행(35개)도 통과.

판정: **재현 안 됨.** 원래 진단 문서(2026-09-10)가 언급한 알려진 후속
수정(소스 비디오 자료실 연결)이 사실상 원인을 없앤 것으로 보이나, 그
인과관계를 직접 증명하지는 못했다 — 시작값을 0으로 바꾸거나 timeout을
늘리는 임의 조치는 하지 않았고, 재현되지 않는 이상 손대지 않았다.

## INVEST-02 — E2E 나머지 조작 실패 11건

11건 전부 trace/실제 UI로 재현한 뒤 원인을 locator 실패(테스트가 낡음)와
제품 로직 실패로 분리했다. **11건 모두 승인된 UI 변경을 테스트가 못
따라간 것**이었고, 제품 결함으로 새로 확인된 것은 없다(단, 그 과정에서
INVEST-04와 별개로 후속 세션에 넘길 사항 하나를 아래 "추가로 확인된 것"에
남긴다).

### `editor-workbench.spec.mjs` (원래 134·183·236·292·415번 줄, 5건)

| 원인 | 근거 | 고침 |
|---|---|---|
| "세부 정보" 오른쪽 도크는 더 이상 접히지 않는다 | `EditorWorkbench.tsx` 주석: "캡컷의 오른쪽 '세부 정보' 패널은 접을 방법이 없다(상시 노출) -- owner 지시 2026-08-30" | 닫으려는 시도 대신 "눌러도 안 닫힌다"를 확인하는 것으로 시험 의도를 뒤집음 |
| "미디어"는 도구줄 단추가 아니라 상시 노출 왼쪽 띠(`role=tab`)로 옮겨졌다 | owner 승인 2026-08-30 2단계, `EditorWorkbench.tsx` 694번 줄 `<nav class="…__rail" role="tablist">` | `getByRole("tab",…)`로 별도 확인, 도구줄 스크롤 대상에서 제외 |
| 단추 문구 "크롭·자막 잠금" → "크롭·캡션 잠금" | `VariantServerControls.tsx` | 문구 갱신 |
| 유진 패널은 "세부 정보" 도크와 분리된 독립 열림 상태를 가진 떠 있는 패널이 됐다 | `EditorWorkbench.tsx`: "캡컷 EditPilot처럼 도크와 무관하게 화면 구석에 뜬다(owner 지시 2026-08-30)" | "세부 정보" 클릭 대신 "유진" 단추로 열고, 닫기도 "유진 닫기"로 |
| **말로 시킨 편집은 확인 클릭 없이 바로 적용된다** | `EditorWorkbenchRoute.tsx`의 `interpretAndApplySpokenEdit`(owner 2026-09-01, `decisions/2026-09-01-yujin-chat-applies-edits-directly.ko.md`) | "이 대화로 편집안 만들기 → 편집안 보기 → 미리보기 → 적용" 네 단계를 "요청 보내기" 한 번으로 바로 적용되는 것으로 재작성. 미리보기 안전성(적용 전 세션 무변경) 검증은 이 시나리오로는 더 이상 안 걸림 — 범위 밖으로 남김(아래 참고) |

### `exact-preview.spec.mjs` 추가 1건 (원래 322번, 현재 335번)

FIX-01 표에 포함(위 참고).

### `library-footage-crosslink.spec.mjs` (원래 58·87번 줄, 2건)

- "라이브러리에서 보기" → "자료실에서 보기"(2026-08-29 전체 메뉴 이름 통일,
  `FootageSourceList.tsx`).
- "…미디어 화면 열기"/`/assets` → "…편집기에서 열기"/`/editor`(독립 미디어
  화면이 2026-09-01에 편집기로 접히면서 `resolveProjectStage(id,"edit")`가
  가리키는 곳이 바뀌었다, `LibraryPreviewPane.tsx`).

### `library-workspace.spec.mjs` (원래 186번 줄 1건, 열어 보니 안의 단추
이름도 2건 더 걸렸다 — 같은 근본 원인 계열이라 하나로 묶어 처리)

- "전체 메뉴" 단추가 `/library`에도 없다 — `product-shell.spec.mjs`와 같은
  이유(SideNav). `getByRole("navigation",{name:"화면 이동"})`로 교체,
  링크 개수는 3이 아니라 **6**(프로젝트·자료실·촬영본 정리 + 내 자산
  구역의 내 영상·음악·효과음·내 목소리 — "설정"은 버튼이라 제외)로 정정.
- "음악"/"효과음" 필터 단추가 새로 생긴 "음악·효과음"(합친 갈래) 단추와
  부분 일치로 겹쳤다(`LibrarySidebar.tsx`에 `broll`처럼 세분화된 `music`·
  `sfx` 필터가 추가됨). 이름 뒤 공백/끝으로 좁히는 정규식으로 교체.

### `media-recovery.spec.mjs` (원래 5번 줄, 1건 — 안에서 2건 더 나옴)

- 분석 상태 패널이 네이티브 `<details>`("미디어 분석")로 접혀 있다
  (`EditorAssetBrowser.tsx` 610번 줄). 열지 않으면 상태 문구가 `hidden`.
- 태그 입력 칸 접근성 이름이 "미디어 3 태그"가 아니라 "회의 장면 태그"다 —
  `assetTitle()`은 자산에 실제 제목이 있으면 그것을 쓴다(fake-api-server
  시드에 `asset-media-review`의 제목이 "회의 장면"으로 이미 있었다).

### `voice-tts-settings.spec.mjs` (원래 35번 줄, 1건 — 안에서 상당한
재구성이 필요했다)

- `/assets`(구주소 별칭)가 `return_to` 없이 들어오면 **항상 `/editor`로
  리다이렉트된다**(`AppRouter.tsx` beforeLoad — 독립 "미디어" 화면이
  2026-09-01에 편집기로 접힘). 옛 "자산 화면 안의 내레이션 탭" 자체가
  없다.
- 내레이션은 이제 탭이 아니라 **팝업**이다(owner 승인 2026-08-27,
  `EditorAssetBrowser.tsx`의 "내레이션" 단추 → `Dialog`).
- 리다이렉트로 실제 편집기(`EditorWorkbenchRoute`)가 열리므로, 옛 화면에는
  없던 편집기 전용 API(세션 단건 조회·재생 매니페스트·유진 대화
  이어받기·출력 변형·전환 추천·유진 선호·작업 목록·현재 미리보기 요청)를
  이 시험의 fake API에 새로 채워야 했다 — 값은 전부 빈/기본값이라 이
  시험이 실제로 지키려는 것(목소리 등록·업로드·후보 생성·청취 승인·
  새로고침 유지)과는 무관하다.

**검증**: 위 아홉 파일을 개별 실행 후, 마지막에 전체 E2E 스위트를 두 번
(fix 도중 1회 + 완료 후 1회) 돌렸다. **최종: 48개 전부 통과, 0 skip**
(직전 status quo였던 29 passed / 19 failed에서 전부 회복).

```
cwd: apps/web
command: node ./e2e/run-isolated.mjs --reporter=list
결과: 48 passed (1.6m), verified playwright-snapshot-manifest.json
commit: 515779e21 (backend 변경, e2e 무관), 이번 세션 변경은 미커밋 상태에서 실행
```

## INVEST-03 — 성능 gate 초과 원인

FIX-02 검증 중 자연히 재현됐다: median **116.9ms**(표본 122.3/137.8/104.9/
103.5/116.9), 기준 92ms·허용 20%(=110.4ms) 초과 → `regression: true`.
`browser_version`은 `149.0.7827.55`로 baseline(2026-07-23 채집, 같은 버전)과
**정확히 일치** — 브라우저 버전 차이는 원인이 아니다.

이 컴퓨터에서 `git worktree list`가 **30개 이상의 동시 worktree**(다른
에이전트 세션들)를 보여 준다 — CPU/GPU 경합이 강하게 의심되는 잡음
요인이다. 임계값을 올리거나 재시도로 더 좋은 숫자를 얻으려 하지 않았다.

**판정: 재현됨, 원인 미확정.** 코드 회귀인지 기계 부하 잡음인지 이번
세션에서는 가를 수 없다 — 유휴 상태의 같은 기계(또는 비교 가능한 부하
상태)에서 다시 재는 것이 필요하다. 기준 보정은 하지 않았다.

## INVEST-04 — 목록 썸네일 404

`artifacts/system-audit-2026-09-09-2348/browser-readonly-B.json`을 읽었다:
`/`과 `/projects` 화면에서 각 2회씩 `/api/projects/{project}/assets/{asset}/thumbnail`
404(총 4회, 데모 프로젝트 "여름 여행 영상" 카드).

코드 추적(합성 자산으로 **실행** 재현은 시간상 못 함, 아래 스포( )은
직접 실행하지 않고 코드 읽기만으로 확인한 것임을 밝힌다):

- `ProjectWorkspaceSummaryResponse.thumbnail_url`은 자산 metadata에
  `thumbnail_uri`가 **있을 때만** 채워진다(`routers/projects.py:358`) —
  즉 프런트가 404를 낸 요청을 보냈다는 것은 등록 당시 썸네일 생성이
  성공해 metadata에 기록됐다는 뜻이다.
- 영상(B-roll) 썸네일은 등록 시 1회, best-effort로 만든다
  (`local_pipeline.py`의 `_try_generate_broll_thumbnail`, ffmpeg 실패는
  조용히 삼킨다).
- 캐시 파일은 `<project_root>/derived/thumbnails/{asset_id}.jpg`
  (`local_project_store.py:1403`)이고, 이 경로는 "원본에서 다시 만들 수
  있는 파생물"이라는 이유로 §10.16 정리 규칙 대상이라고 코드 주석이
  명시한다.
- **가장 유력한 설명**: 등록 당시 썸네일 생성은 성공해 metadata에
  `thumbnail_uri`가 남았는데, 이후 어떤 정리(§10.16 규칙에 따른 파생물
  청소)가 캐시 파일만 지우고 metadata는 안 건드려서 참조가 끊겼다 —
  "삭제/없음의 정상 fallback"이 아니라 **metadata와 파일이 어긋난 상태**다.
- `get_asset_thumbnail`(`routers/assets.py:608`)은 2026-09-17에 **이미지**
  자산에 한해 파일이 없으면 즉석 재생성하는 fallback을 추가했다(주석: "실제
  프로젝트에서 이미지 자산 썸네일이 그냥 404였다"). **이 fallback은 영상
  자산에는 없다** — 09-17 수정이 이미지만 고치고 영상은 비대칭으로
  남겨진 것으로 보인다.
- 프런트 쪽도 반쪽이다: 프로젝트 카드 `<img src={summary.thumbnail_url}>`
  (`AppRouter.tsx:662`)에 `onError` 대체 처리가 없다 — 404가 나면 깨진
  이미지 아이콘이 그대로 보인다.

**판정: 의심 확인(코드 추적 기반), 실행 재현은 못 함.** 운영 자료를
삭제·재생성하지 않았고 합성 자산으로도 아직 실행 재현은 안 했다 — 다음
세션에 넘긴다(`task_0373d077`로 스폰함, `spawn_task` 결과 참고). Minor로
예상했던 것과 달리, 09-17 수정과 비교하면 **비대칭 수정 누락**이라는
구체적 원인까지는 확인했다.

## VERIFIED-01 — 인계 중복 재수정 제외

`test_handoff_entry_point.py`가 전체 pytest에 포함돼 돌았다. **1차 전체
실행에서 이 파일이 실제로 실패했다** — 그런데 원인은 인계 중복이 아니라
**이번 세션이 만든 새 인계 문서 자신의 형식 오류**였다: "아직 없음" 자리
표시 문구도 `**대체됨:**` 글자를 담고 있어서, `_newest_handoff()`의 단순
부분 문자열 검사(`_SUPERSEDED not in text`)가 이 문서를 "이미 대체됨"으로
잘못 읽었다. 게다가 전체 실행이 41분 걸리는 동안 **다른 세션이 별도로
`2026-09-18-transcript-panel-text-delete.ko.md`를 커밋**해 들어와 "최신"
자리를 다시 다퉜다. 자리 표시 문구를 지우고(살아있는 문서는 `대체됨` 줄
자체가 없어야 한다 — 다른 정상 문서들이 그렇다) 그 문서에 내 문서를
가리키는 `대체됨` 줄을 추가해 체인을 바로잡았다. `tests/test_handoff_entry_point.py`
단독 재실행으로 5개 전부 통과 확인함. **이건 "인계 중복" 그 자체(VERIFIED-01이
막으려던 결함)가 재발한 게 아니라, 이번 세션이 새 문서를 쓰면서 만든
별개의 새 실수였다** — VERIFIED-01의 판정("재발 안 하면 재수정 안 함")은
그대로 유효하다.

## 검증 실행 기록

| 검증 | cwd | 시작/종료 | commit(dirty) | exit | 결과 |
|---|---|---|---|---|---|
| E2E 개별 파일(9개, 여러 회) | `apps/web` | 22:0x대(반복) | 515779e21(e2e dirty) | 0 | 각 파일 수정 후 개별 통과 확인, 로그는 turn 내 보존 |
| E2E 전체(1차, 중간 확인) | `apps/web` | - | 515779e21(e2e dirty) | 0 | 47 passed / 1 failed(exact-preview:335, 그 자리에서 마저 고침) |
| E2E 전체(2차, 최종) | `apps/web` | - | 515779e21(e2e dirty) | 0 | **48 passed / 0 failed** |
| frontend 전체 vitest | `apps/web` | 21:32~21:33 | 04d9af569(당시 e2e 변경 전) | 0 | 139 files, **1752 passed** |
| frontend tsc --noEmit | `apps/web` | 22:02 | 515779e21(e2e dirty) | 0 | 에러 0건 |
| backend 전체 pytest(1차, 경로 문제) | 루트 | 22:02~22:03 | 04d9af569 | 1 | basetemp 경로가 너무 길어 무더기 오탐(아래 주 참고). 결과 근거로 안 씀 |
| backend 전체 pytest(2차, 최종) | 루트 | 22:09:45~22:50:24(41분18초) | 515779e21(e2e·docs dirty) | 1 | **5147 passed, 56 skipped, 1 xfailed, 3 failed** |
| ↳ 실패 1: `test_handoff_entry_point.py::test_entry_map_points_at_the_newest_handoff` | 루트 | 재실행 22:5x | d47c48700(병합 후) | 0 | 원인 규명 후 문서 형식 고침, **단독 재실행 5 passed** |
| ↳ 실패 2·3: `test_owner_ready_script.py`의 smoke timeout/continues 시험 2건 | 루트 | 재실행 22:5x | d47c48700 | 0 | 격리 재실행 **2 passed** — 41분 전체 실행 중 기계 부하(동시 worktree 30개 이상)로 생긴 일시적 timeout으로 판단. 코드 변경 없음 |

**최종 판정: 이 저장소의 backend 전체 pytest는 현재 HEAD(`d47c48700`, 이
세션의 e2e·docs 변경 적용 전 기준)에서 실질적으로 전부 통과한다** — 41분
전체 실행에서 나온 3건 실패는 (a) 이번 세션 자신의 문서 형식 실수 1건
(고쳐서 확인함), (b) 기계 부하로 인한 일시적 timeout 2건(격리 재실행으로
확인함)이었고, **제품 코드의 회귀는 하나도 없었다.** 다만 문서 형식 수정 뒤
**41분짜리 전체 스위트를 처음부터 다시 통째로 돌리지는 않았다** — 개별
재현으로 원인을 확인하는 선에서 끝냈다(시간 대비 근거 확보 트레이드오프,
아래 "남은 것"에 남긴다).

(주: 최초 backend 전체 실행은 basetemp를 세션 scratchpad의 매우 긴 경로로
줬다가 Windows `MAX_PATH`(260자) 제한에 걸려 `test_api.py`의 tmp_path
기반 시험들이 무더기로 `[WinError 206] 파일 이름이나 확장자가 너무
깁니다`로 실패했다 — **이건 제품 결함이 아니라 이번 세션이 고른 임시
경로의 문제**였다. `--basetemp`를 짧은 경로(`D:/vbpt`)로 바꿔 다시
돌렸다. 이 사고 자체가 `videobox-pytest-runs-on-windows-product-runs-on-linux`
메모가 말하는 것과 같은 종류다.)

## 남은 것 / 사용자 판단이 필요한 것

- **실사용 브라우저 끝까지(격리 Postgres+파일)**: 이번 세션에서는 하지
  않았다. E2E는 fake-API-server를 쓰는 실제 빌드+실제 브라우저 조작이지만,
  운영 스택(컨테이너, 실 DB)을 새로 띄우지는 않았다 — `scripts/owner-ready.ps1`
  기동 자체가 이번 위임 범위 밖이라 보고, 차단으로 남긴다.
- **INVEST-03**: 유휴 기계에서 재측정 필요.
- **INVEST-04**: 합성 자산으로 실행 재현 + 영상 썸네일 즉석 재생성/프런트
  `onError` 대체 추가는 후속 세션 몫(`task_0373d077`).
- **INVEST-02의 "미리보기 안전성" 커버리지 공백**: 2026-09-01 직접 적용
  전환 이후, "미리보기가 세션을 안 바꾼다"는 안전 성질을 지키던 시험이
  깔끔한 지시 시나리오에서는 더 이상 걸리지 않는다(자동 적용이 미리보기
  단계를 건너뛴다). 유진이 스스로 해석 못 해 사람이 수동으로 편집안을
  검토해야 하는 경로(모호한 지시, 적용 실패 등)에서 이 성질을 다시 잡는
  시험이 필요할 수 있다 — 범위 밖으로 남긴다.
- **backend 전체 pytest 재확인**: 문서 형식 수정(VERIFIED-01 절 참고) 뒤
  41분짜리 전체 스위트를 처음부터 다시 돌리지 않았다. 고친 3건 각각은
  단독/격리 재실행으로 통과를 확인했지만, "전체를 한 번에 다시 돌려도
  정말 다른 실패가 안 섞이는가"는 이번 세션에서 최종 확인하지 못했다 —
  다음 세션이 여유가 있으면 한 번 더 통째로 돌려 보는 것을 권한다.
- **다중 세션 인계 문서 경합**: 이번 세션 도중 다른 세션이 최소 두 번
  `docs/handoffs/`에 새 문서를 커밋해 "최신" 자리를 갱신했고, 그중 한 번은
  내 결과 보고 직전에 겹쳐 `test_handoff_entry_point.py`를 실제로 깨뜨렸다
  (위 VERIFIED-01 절). 여러 세션이 동시에 이 저장소에 인계 문서를 쓰는
  한 이 경합은 구조적으로 남는다 — 커밋 직전에 항상 `test_handoff_entry_point.py`를
  마지막으로 한 번 더 돌려 체인이 여전히 맞는지 확인하는 습관이 필요하다.

## 재사용 원칙

- 재사용 후보: 기존 `ensureDockOpen` 패턴(`editor-workbench.spec.mjs`)을
  그대로 본떠 `ensureYujinOpen`을 만들었다. 다른 시험이 이미 쓰던 fixture
  구조(manifest/editingSession 빌더)를 새 mock에도 그대로 재사용했다.
- 실제 반영: `apps/web/e2e/*.spec.mjs` 아홉 파일의 fixture·locator·
  주석만 고쳤다. 프런트/백엔드 **소스 코드는 한 줄도 바꾸지 않았다** —
  전부 승인된 화면 변경을 테스트가 못 따라간 것이었다.
- 제외: INVEST-04(영상 썸네일 fallback·프런트 onError)는 확인까지만 하고
  수정은 다음 세션(`task_0373d077`)에 넘겼다 — 다른 세션이 같은 코드
  영역(core-engine)을 동시에 만지고 있어서 이번에 손대면 충돌 위험이
  있었고, 실행 재현이 아직 없어 추측으로 고치지 않기 위해서였다.
- 경계 보존: `UI 구조`·`Google Sheets/Drive`·provider 하드코딩 반입 없음.
  다른 세션이 작업 중이던 `composition_plan.py`·`output_variants.py`·
  관련 테스트는 건드리지 않았고 커밋에도 포함하지 않는다.
