# 유진 명령 표면 실측 — 화면이 되는데 유진은 안 되는 것

작성: 2026-09-11. 근거는 전부 파일:줄로 달았다. 대표님 상시 지시
("전부 다 유진이한테 명령하면 실행되도록 배선 연결이 다 되어야 되")에 대한
**계획을 세우기 전의 실측**이다. 추측한 항목은 그렇게 표시했다.

## 0. 먼저 — 유진은 시스템이 **셋**이다

이걸 모르면 아래 표를 잘못 읽는다.

| 시스템 | 어디서 | 프롬프트가 사는 곳 | 적용 방식 |
|---|---|---|---|
| **A. 직접 편집 대화** | 편집기 채팅 → `interpretAndApplySpokenEdit` (`apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx:1903`) | `yujin_editing_proposal_service.py`의 `_editing_prompt` (코드 안 문자열) | **바로 적용**(2026-09-01 승인). 되돌리기가 지킨다 |
| **B. Director/Creator 대화** | 같은 전송 단추가 **동시에** 부른다 → `submitDirectorMessage` (`:1790`) → Hermes 컨테이너 | `config/hermes/yujin/SOUL.md` + `skills/videobox-{editor,creator}/SKILL.md` | **후보만.** 사람이 화면에서 적용 |
| **C. 자료 정리 대화** | 편집기 밖, 자료 가져오기 | `routers/footage_organizer.py:541` | 후보만 |

메시지 한 번이 A와 B를 **동시에** 부른다.

## 1. 유진이 지금 할 수 있는 것

- **A: 편집 의도 16개** — 배속·트림·포함제외·순서·자막글·자막글꼴·색감·사진움직임·전환·
  손떨림/노이즈·소리정리·확대위치기울이기·오버레이 얹기/빼기·미디어 배치/해제.
  셋(스키마·적용기·프롬프트) 다 있다.
- **B: 창작 제안 8종** — `broll`·`bgm`·`sfx`·`caption`·`voice`·`overlay`·`output_check`·
  **`output_variant`**.
- **C: 자료 정리 6개** — 장면분할·처리선택·품질제외·유사합치기·세로선택·목표길이.

## 2. 가장 값싼 구멍: `output_variant`

스키마도 있고(`yujin_creator_proposals.py:462`) 적용기도 라우터에 배선돼
있는데(`yujin_creator_proposal_adapter.py:72` ← `director_proposals.py:1025`),
**유진에게 "이런 게 있다"고 말해 주는 문장이 한 군데도 없다.**
`config/hermes/yujin/skills/videobox-creator/SKILL.md`에 `output_variant`·
`set_crop`·`set_focal`·`set_caption_layout`·`set_safe_area`·`correct_audio`
문자열이 **0건**이다.

모델이 배울 방법이 없으니 능력이 있어도 안 고른다. 이 저장소가 전에 겪은
패턴이다 — 안내문을 안 고치면 할 수 있어도 안 한다.

## 3. 가장 큰 구멍: 출력 화면에 유진이 **없다**

`apps/web/src/app/OutputsPage.tsx`에 `Yujin`/`Director`/`유진` 문자열이 **0건**이다.
완성본 만들기·변형 렌더·CapCut 내보내기·검토 승인이 전부 이 화면에 있는데,
유진이 뜨는 자리조차 없다. 스키마를 아무리 고쳐도 진입점이 없으면 무의미하다.

## 4. 대조표 — 없는 것만

| 화면 동작 | 근거 | 상태 |
|---|---|---|
| 변형본 크롭/포컬/자막배치/안전영역/오디오 | `EditorWorkbenchRoute.tsx:1306` | **의도·적용기 있음, 프로필에 없음** |
| 세로 하이라이트 만들기 | `EditorWorkbenchRoute.tsx:1348` | **없음** |
| 가로·세로 변형 렌더하기 | `OutputsPage.tsx:664` | **없음** |
| 완성본 만들기 | `OutputsPage.tsx:953` | **없음** |
| 완성본 승인/반려 | `OutputsPage.tsx:898` | **없음** |
| CapCut 내보내기 | `OutputsPage.tsx:996` | **없음** |
| 공유 링크 발급 | `OutputsPage.tsx:914` | **없음** |
| 검토 승인 | `api.ts` | **없음** |
| 장면 분할 / 합치기 | `editorCommandPort.ts:42,43` | **없음** |
| 도형·화살표·아이콘 오버레이 | `editorCommandPort.ts:176` | **없음** |
| 트랙 숨김/음소거 | `editorCommandPort.ts:49` | **없음** |
| 자막 번역 / 더빙 | `api.ts` | **없음** |
| TTS 후보 지우기 | `editorCommandPort.ts:56` | **없음** |
| 자막 색·외곽선·배경·정렬 | `port.setCaptionStyle` | B에만 있음(A엔 글꼴·크기뿐) |
| 내려받기 | 별도 API 없음 | **명령 대상 아님** — 파일이 만들어진 뒤 브라우저가 하는 일 |

## 5. 새 능력을 유진에게 더하는 절차

- **A(직접 편집)에 더하려면**: `yujin_editing_proposals.py`에 Operation 추가 →
  `yujin_editing_proposal_service.py`의 `_EDITING_OPERATION_SCHEMA`와 `_editing_prompt`
  → `editing_session.py`의 `_apply_yujin_editing_operations`에 적용기.
- **B(Director/Creator)에 노출하려면**: `config/hermes/yujin/skills/videobox-creator/SKILL.md`에
  문장 추가가 **핵심**. `tests/test_hermes_yujin_profile_distribution.py`가 정확한
  부분 문자열을 고정하고 있어 같이 갱신해야 하고, 실행 중인 컨테이너에 반영하려면
  `scripts/install-hermes-yujin-profile.ps1`을 다시 돌린다.

## 6. 확인하지 못한 것 (추측으로 쓰지 마라)

- Hermes가 `videobox-editor`와 `videobox-creator` 스킬 중 **어느 쪽으로 라우팅하는지**는
  이 저장소 밖이라 확정 못 했다. 다만 **둘 다에 `output_variant`가 없다**는 사실은
  라우팅과 무관하게 유효하다.
- `horizontal`/`vertical_full` 변형본이 정확히 어느 백엔드 코드에서 기본 생성되는지.
- `yujin_profile_contract.py`/`yujin_agent_package_contract.py`(SHA-256 고정 offline 계약)를
  실제로 부르는 동적 경로가 있는지 — grep으로는 시험 말고 없었지만 죽었다고 단언하지 않는다.
