# Task 11 편집 작업판 시각 승인 기록

<!-- editor-workbench-approval: {"manifest_sha256":"5b6f51149308822b231700342bc1fd120a6667f0f170e1c4ca928cf09089baa6","status":"approved"} -->

- 상태: `approved`
- 결정: 2026-07-22 사용자가 다섯 viewport의 정적, 읽기 전용 workbench 시안을 명시 승인했다. 승인 뒤 current runtime으로 스냅샷을 다시 생성해 tracked PNG byte가 바뀌지 않음을 확인했고, manifest의 이전 placeholder label과 stale PNG SHA-256을 실제 화면/현재 artifact로 바로잡았다. 이 승인으로 Task 11의 두 번째 시각 승인 gate를 충족한다.
- 범위 제외: Task 12 정확 미리보기, Task 13 재생·audition, Task 14 geometry mutation, Task 20 실제 유진 추천.
- 승인 입력: 각 viewport의 패널 밀도, 미리보기 자리, 작은 화면 drawer, 유진/Inspector dock을 검토한 명시적 승인.

## 2026-08-15 스냅샷 재승인

owner가 Playwright 스냅샷 5장의 재생성을 명시 승인했다.

배경: 재생성해 보니 `1920×1080`뿐 아니라 `1440×900`·`1280×800`·`390×844`·`768×1024`까지
**5장 전부** sha256이 달랐다. 뒤 네 개는 같은 날 적용한 `min-width:1500px` 수정이 닿지
않는 크기이므로, **그 이전부터 스냅샷이 코드보다 낡아 있었다.**

- 갱신 대상: `apps/web/e2e/snapshots/editor-workbench-*.png` 5장과
  `playwright-snapshot-manifest.json`의 해당 `bytes`/`sha256`
- 위 `<!-- editor-workbench-approval -->` marker는 **건드리지 않았다.** 그 값은
  `docs/prototypes/2026-07-20-editor-workbench/manifest.json`의 digest이고 이번 변경과
  무관하다(`tests/test_editor_workbench_artifacts.py:27-30`).
- 이 스냅샷은 pixel 비교 게이트가 아니다. `VIDEOBOX_WRITE_PLAYWRIGHT_SNAPSHOTS=1`일
  때만 기록되고(`e2e/support/fixed-clock.mjs:29`), manifest는 무결성만 확인한다.

**이 재승인의 범위는 "기록을 현재 코드와 맞춘다"까지다.** 스냅샷은 E2E fixture 상태
(미리보기 없음)를 담고 있어 실제 편집 결과물의 화질·타이밍 승인과는 다르다.
owner의 실제 시청 승인은 여전히 남아 있다.

## 2026-08-15 두 번째 재승인 — 대시보드 UX 개편 이후

owner가 `docs/superpowers/plans/2026-08-15-videobox-dashboard-ux-recovery.md`
Task 1~6 완료 뒤 스냅샷 재생성을 다시 명시 승인했다.

배경: 위 첫 재승인 이후 같은 날 세션에서 편집 작업판 레이아웃이 여러 번 더
바뀌었다(출력 변형 접기 기본값, 소스 확인을 dock으로 이동, 자막 안내 통합, 편집기
기본 시작 상태). 그 결과 `editor-workbench-*.png` 5장이 다시 낡았고, 이번에는
`ProductShell.tsx`도 두 번 바뀌어(홈 문구 중복 제거, 사이드바 구획 라벨)
`product-shell-*.png` 5장도 함께 낡았다 — **총 10장 전부** sha256이 달랐다.

- 갱신 대상: `editor-workbench-*.png` 5장 + `product-shell-*.png` 5장,
  `playwright-snapshot-manifest.json`의 해당 `bytes`/`sha256` 10줄
- `<!-- editor-workbench-approval -->` marker는 이번에도 건드리지 않았다(첫 재승인과
  같은 이유 — 프로토타입 매니페스트 digest이고 무관).
- 재생성 후 `npm --prefix apps/web run test:e2e` 42개 전부 통과, manifest 무결성
  검증(`verify-snapshot-manifest.mjs`) 통과를 확인했다.

이번에도 범위는 "기록을 현재 코드와 맞춘다"까지다. owner의 실제 시청·승인은
여전히 별도이고 완료되지 않았다.
