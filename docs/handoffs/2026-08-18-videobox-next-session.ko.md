# 다음 세션은 여기서 시작한다

**대체됨:** `docs/handoffs/2026-08-18-videobox-capcut-close-and-one-icon-launch.ko.md`

이 문서가 남긴 A·B·C 중 A와 C는 닫혔고 B는 절반 진행됐다. **현재 상태는 위 문서를 봐라.**
아래는 그때의 기록으로 남긴다.

- 작성: 2026-08-17
- 직전 세션: 캡컷 벤치마킹 (`83261f4e5`, `f7cb56939`)
- **읽는 순서:** 이 문서 → `docs/decisions/2026-08-17-editor-capcut-layout-approval.ko.md`
  → `docs/handoffs/2026-08-17-videobox-first-use-walkthrough.ko.md`

## 지금 상태 — 전부 초록, 트리 깨끗

| 게이트 | 결과 |
|---|---|
| 전체 pytest (**단독**) | 3,599 passed · 53 skipped · 실패 0 |
| `npm test` | 84 파일 · 1,033 passed |
| `npm run test:e2e` / editor-workbench | 46 + 10 passed |

**시작 전에 직접 확인하라.** 위 숫자는 그때의 것이다.

## 할 일 A — 왼쪽 재료 패널 기본 펴기 (승인 있음, 가장 가깝다)

owner가 승인했고(`decisions/2026-08-17-editor-capcut-layout-approval.ko.md`)
**세 번 시도해 세 번 되돌렸다.** 조사는 끝났으니 다시 하지 마라.

**이미 확인된 것 (그대로 쓰면 된다):**

- 기본값은 **두 곳**이다. 한쪽만 바꾸면 다른 쪽이 이겨서 화면에 닿지 않는다.
  - `apps/web/src/features/editor/workbench/editorUiState.ts` (실제로 쓰이는 쪽)
  - `apps/web/src/features/editor/workbench/editorWorkbenchLayout.ts`
- 저장 키 세대(`editorUiGeneration = "v2"`)는 **이미 올려 두었다.** 기존 사용자에게도
  새 기본값이 한 번 적용된다.
- 단위 테스트 13개는 아래 헬퍼 하나로 전부 통과한다(확인함, 1,033 초록).

```ts
// apps/web/src/features/editor/workbench/editor-workbench.test.tsx
function openMaterialDock(): void {
  if (screen.queryByRole("complementary", { name: "자산과 대본" })) return;
  fireEvent.click(screen.getByRole("button", { name: "자산과 대본" }));
}
```
그리고 `fireEvent.click(screen.getByRole("button", { name: "자산과 대본" }));` 13곳을
`openMaterialDock();`으로 바꾼다. 기본값 테스트 3개(`editorUiState.test.ts`,
`editorWorkbenchLayout.test.ts` 2곳)도 새 기본값으로 갱신한다.

**남은 것은 e2e다. 여기서 세 번째 시도가 막혔다.**

같은 조건부 클릭을 e2e에 넣었더니 **2건에서 3건으로 늘었다.** 클릭 문제가 아니다 --
`editor-workbench.spec.mjs:117`은 두 도크를 펴 `desktop-both`를 만든 뒤 도크 폭
유지를 본다. 기본값이 바뀌면 **몇 개가 열려 있느냐에 따라 layout mode가 통째로
달라지고** 폭·스냅샷이 함께 움직인다.

**그래서 이렇게 하라:** 그 spec들이 지키려는 게 무엇인지부터 읽어라.
`:117`이 지키는 것은 "**드래그한 도크 폭이 새로고침 뒤에도 남는가**"이지
`desktop-both`가 아니다. `desktop-both`는 그 상황을 만드는 수단이다. 새 기본값에서도
같은 것을 지키도록 다시 써라. 나머지 2건도 값이 아니라 **의도**부터 확인하라.

마지막으로 편집 작업판 스냅샷 5장 재생성 — **owner 확인 필요**(`2026-08-15` 절차).

## 할 일 B — 미리보기/타임라인 비율 재정의

캡컷은 아래 절반을 타임라인이 쓴다. 우리는 타임라인 높이를 늘렸지만
**1500px 위에서는 거의 못 늘렸다.**

원인: 1440에서는 compact 블록이 타임라인을 `4rem`으로 눌러 미리보기가 크다. 1920에서
타임라인을 키우면 늘어난 화면 높이(+180px)보다 타임라인 증가분이 커져 **미리보기가
되레 작아진다.** `apps/web/e2e/exact-preview.spec.mjs:94`가 정확히 그걸 막는다.

**함께 열어야 하는 것 둘:** 위 e2e 가드와 `docs/decisions/2026-07-20-...`(2026-07-22에
미리보기를 8.5%→20.8%로 키운 작업). 값 하나 바꾸는 일이 아니라 **비율 정책을 다시
정하는 일**이므로 owner 판단이 필요하다.

## 할 일 C — 데스크톱 껍데기

아이콘 하나로 켜고, 파일을 네이티브로 고른다. **안쪽 화면은 그대로 쓴다.**

`docs/handoffs/2026-08-17-videobox-first-use-walkthrough.ko.md`의 결론:
*"위 문제 중 웹 때문인 것은 없다. 웹이라서 생기는 진짜 불편은 따로 있다 -- 도커를
띄우고 주소를 쳐야 켜지는 것, 파일 경로를 타이핑해야 하는 것."* C는 **그 둘만** 푼다.

새 런타임·빌드·배포 경로가 붙는 큰 작업이다. 시작 전에 범위를 owner와 맞춰라.

## 캡컷 대비 남은 차이 (직접 세어 본 것)

| | 상태 |
|---|---|
| 열면 바로 편집판 / 빈 편집판 / 컷 도구 / 재생 위치 선 / 단축키 / 끌어다 놓기 | 됨 |
| 왼쪽 재료 패널 항상 보이기 | **A** |
| 타임라인이 아래 절반 | **B** |
| 아이콘 하나로 켜기 | **C** |
| 미리보기 구간 반복·프레임 이동 | 미착수 |

## 잊지 말 것

- **전체 pytest는 단독으로** 돌린다. 같이 돌리면 무관한 테스트가 거짓 실패한다.
- `ProductShell.tsx`를 고치면 `docs/oss/editor-ui-source-map.json`의
  `normalized_sha256` **두 곳**을 갱신한다(백엔드 스위트만 잡는다).
- 컨테이너는 `scripts/owner-ready.ps1`로만 다룬다.
- **화면에서 실제로 눌러 보기 전에는 됐다고 하지 마라.** 이번 세션에도 단위 테스트가
  전부 초록인 채로 컷편집이 막혀 있었다.
