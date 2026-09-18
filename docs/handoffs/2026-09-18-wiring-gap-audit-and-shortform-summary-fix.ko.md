# task_ -- 유진 배선 누락 전수 조사 + 숏폼 완료 문구 누락 고침

owner 지시: 오늘 앞선 세션이 `resolve_variant_conflict`가 Hermes 자율 루프
체계에만 배선되고 화면 채팅 체계엔 없던 결함을 고쳤는데
(`docs/handoffs/2026-09-18-variant-conflict-resolution-actually-wired-to-chat.ko.md`),
**같은 종류의 배선 누락이 또 있는지 전수 조사**하라는 지시였다. "다 고쳐라"가
아니라 "다시 깊게 조사해서 어디에 또 있는지 찾아라"였다.

## 한 일

1. **네 표면을 코드로 직접 세어 교차 대조했다** -- 화면 명령
   (`editorCommandPort.ts` + `OutputsPage.tsx`), A(직접 편집 채팅, 21개 의도),
   B(Hermes 창작 제안, 8 kind·11 action), SKILL.md 계약 문서. 전체 결과는
   `docs/surveys/2026-09-18-wiring-gap-full-audit.ko.md`에 남겼다 -- 이 조사의
   핵심 산출물이다.
2. **좁고 명백한 결함 1건을 직접 고쳤다** -- 아래.
3. 나머지 9건은 판단이 필요하다고 보고 고치지 않았다(survey §4에 우선순위·
   비용 추정과 함께 남김).

## 고친 것 -- 숏폼 넷의 완료 한 줄 요약이 빠져 있었다

**증상**: A(직접 편집 채팅)의 21개 의도 중 숏폼 넷(`create_short_form`,
`remake_short_form`, `unfold_short_form`, `render_short_form`)은 백엔드
(스키마·프롬프트·적용기)가 전부 정상이라 실제로 잘 적용되는데,
`apps/web/src/features/editor/workbench/yujinEditingSummary.ts`의
`yujinEditingOperationSummary`에는 이 넷이 없어서 owner에게 보여주는 완료
한 줄이 `"편집 항목을 바꿔요."`(의미 없는 기본 문구)로 떨어지고 있었다. 이
파일 머리말이 스스로 "명령을 늘릴 때마다 여기를 같이 늘려야 한다"고 경고한
바로 그 함정이다. 말한 편집이 확인 클릭 없이 바로 적용되는 제품(2026-09-01
결정)에서 이 한 줄이 "무엇이 바뀌었는지 알려 주는 유일한 자리"이므로, 숏폼을
채팅으로 만들어도 owner는 성공했는지 이 문구만으로는 알 수 없었다.

**고침**: `yujinEditingOperationSummary`에 4개 분기 추가.
- `create_short_form` → "숏폼을 새로 만들어요."
- `remake_short_form` → "숏폼 장면을 다시 골라요."
- `unfold_short_form` → "숏폼을 편집본으로 펼쳐요."
- `render_short_form` → "숏폼을 완성본으로 뽑아요."

## 검증

### RED
`yujinEditingSummary.test.ts`에 새 테스트("숏폼 넷도 제 이름으로 말한다")를
먼저 추가하고 돌려서 실패를 봤다: `기대 "숏폼을 새로 만들어요." / 실제
"편집 항목을 바꿔요."`.

### GREEN / focused / broader
- `npx vitest run src/features/editor/workbench/yujinEditingSummary.test.ts`
  -- 10건 통과(새 케이스 1개 포함).
- `npx vitest run src/features/editor` -- **71 files, 961 tests, 전부 통과.**
- `npx tsc --noEmit` -- 에러 0건.

### 역방향 -- 하지 못했다 (남은 것)
순수 문자열 매핑 함수이고 입력은 이미 검증된 pydantic 모델이 주는 고정된
모양(넷 다 파라미터 없이 `intent`뿐)이라 편차 여지가 거의 없다고 판단했지만,
**실제 브라우저에서 "숏폼 만들어 줘"를 채팅으로 시켜 화면 문구를 눈으로
확인하지는 않았다.** 이번 audit 범위가 넓어 컨테이너 재빌드까지는 안 갔다.
다음에 숏폼 관련 화면을 만질 일이 있으면 한 번 확인해 보는 것을 권한다.

## 조사에서 확인한 것 -- 09-11 조사 이후 이미 해결된 항목

`docs/surveys/2026-09-11-yujin-command-gap.ko.md`가 "가장 값싼 구멍"으로 지목한
것 -- `output_variant`/`set_crop` 등 11개 action이 `config/hermes/yujin/
skills/videobox-creator/SKILL.md`에 0건이라던 문제 -- 는 **현재는 11개 전부
문서화돼 있어 해결된 상태**임을 확인했다(언제 고쳐졌는지는 git blame을 안 봐서
모른다). 09-11 문서의 §2·§4 첫 줄은 낡았다 -- 새 survey가 갱신했다.

## 남은 것 (판단 필요, owner 몫) -- survey §4 요약

우선순위 순으로: (1) 완성본 만들기를 채팅으로, (2) 가로·세로 전체 변형
렌더하기를 채팅으로, (3) 자막 색·외곽선·배경·정렬을 A에도, (4) 트랙
숨김/음소거, (5) 장면 분할/합치기, (6) 검토 승인/CapCut 내보내기/공유 링크
(외부 게시 성격이라 owner 판단 특히 필요), (7) 도형 오버레이, (8) TTS 후보
적용/지우기, (9) 자막 번역/더빙 시작(의도적 비동기 통로라 설계 판단 필요).
비용·근거는 survey 문서 §4 표에 있다.

## 재사용 원칙

- 재사용 후보: `resolve_variant_conflict`가 최근 겪은 것과 같은 패턴이라
  그 조사 방법(네 표면을 코드로 직접 세기)을 그대로 따랐다. 새 시험 하나는
  기존 파일의 기존 패턴(다른 intent 케이스들과 같은 `summary()` 헬퍼)을
  그대로 재사용했다.
- 실제 반영: `yujinEditingSummary.ts`에 분기 4개, `yujinEditingSummary.test.ts`에
  케이스 1개(숏폼 넷 4가지 검증), survey 문서 1개, 이 handoff 1개.
- 제외: survey §4의 9건은 전부 새 도메인 모델·스키마·적용기·프롬프트가
  필요한 중간 이상 비용의 작업이거나 owner의 제품 판단(외부 게시 성격,
  비동기 통로 설계)이 필요해 이번 범위에서 뺐다.
- 경계 보존: `UI 구조`·`Google Sheets/Drive`·provider 하드코딩 반입 없음.
  다른 세션이 작업 중인 `packages/core-engine/src/videobox_core_engine/
  composition_plan.py`, `tests/test_clip_placement.py`의 커밋 안 된 변경은
  건드리지 않았고 커밋에도 포함하지 않았다.

## 커밋·푸시

커밋했다(내 변경 파일만: `apps/web/src/features/editor/workbench/
yujinEditingSummary.ts`, `yujinEditingSummary.test.ts`,
`docs/surveys/2026-09-18-wiring-gap-full-audit.ko.md`, 이 handoff,
`CLAUDE.md`). 푸시는 안 했다 -- 코디네이터가 이어받는다(지시사항).
