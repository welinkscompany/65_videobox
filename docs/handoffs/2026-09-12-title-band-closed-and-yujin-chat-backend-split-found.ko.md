# 제목 띠를 닫고, 유진 채팅이 두 백엔드로 갈라져 있다는 것을 찾았다 (2026-09-12)

**대체됨:** 같은 날 밤 `2026-09-12-yujin-chat-wiring-done-render-still-open.ko.md`가
이 문서가 찾은 문제(진짜 채팅 경로에 안 닿음)를 실제로 고쳤다. 최신 상태는 그 문서를 봐라.

앞 인계(`2026-09-12-rebuilt-and-measured-on-the-real-video.ko.md`)를 잇는다.
계획서는 `docs/superpowers/plans/2026-09-12-a-short-that-looks-like-a-short.md` —
이번 세션에 Task 3 절과 R1·R2·R4를 정정·기록해 뒀다. **다음 세션은 그 문서의
"해야 할 것" 절부터 읽어라.**

## 1. Task 1(제목 띠) — 닫음, 실물 렌더로 확인

앞 세션 서브에이전트가 중간에 멈춰 둔 코드(`shorts_layout.py` 등, 20여 파일
+763/-55)를 이어받아 검증하고 닫았다. 백엔드 76건 + 프론트 3건이던 것을
관련 테스트 전부(백엔드 776여 건, 프론트 1745건)로 넓혀 돌렸고 전부 초록이다.

빠진 것 둘을 채웠다:
- 계획서는 영상 띠 맞춤을 `blur`로 못박았는데, 실제 코드는 이미 `fit`으로
  가 있었다(2026-09-12 실물 비교 근거 — `blur`는 위아래에 흐린 띠가 남는다).
  **계획과 다른 게 아니라 계획보다 나은 근거로 이미 바뀌어 있었다** — 정직하게
  적어 둔다.
- `test_hermes_yujin_profile_distribution.py`가 "여덟 형태"를 못박고 있었는데
  앞 세션이 `set_shorts_title`을 아홉 번째로 추가하며 이 시험을 안 고쳤다.
  이번 세션이 `create_short_form`을 열 번째로 더하며 "열 형태"로 한 번에
  고쳤다.

**실물 검증(R4, `2026-09-12-ca6dd9ed` 실제 영상, 컨테이너 재빌드 후 렌더한
숏폼 job_021, 35.4초):** 프레임을 png로 뽑아 참고 숏폼을 쟀던 것과 같은
방식(행별 밝기·대비)으로 쟀다.

| | 실측 | 참고 범위/목표 |
|---|---|---|
| 제목 띠 | 20.83% | 20.8~28.6% |
| 영상 띠 세로:가로 | 1.30:1 | 1.3 |
| 영상 letterbox | 위아래 균등 여백, 안 잘림 | 설계대로 |

두 줄 제목("정답을 안 주는 이유" / "일본 마켓 매출 3배의 비밀")과 강조
낱말("안", 초록)도 실제로 그려졌다. 원본에 구워진 자막은 영상 띠 안에
온전하고 우리 자막 레인은 이 프로젝트에서 꺼져 있어(구운 자막 있음) 겹치지
않는다 — 설계대로다.

## 2. Task 3(유진 배선) — 코드는 짰다, 그런데 화면 채팅에 안 닿는다

`is_yujin_variant_proposal`이 `variant_id is not None`을 요구해 "숏폼
만들어줘"(처음 만들기)가 막혀 있던 문을 열었다 — 도메인 모델(`create_short_
form` action, `PENDING_SHORT_FORM_TARGET_ID`), 저장소 원자적 트랜잭션
(`apply_director_variant_create_proposal_transaction`), 라우터 분기, 어댑터,
프로필(SKILL.md) 문서, 단위·통합 시험(76건 이상)까지 전부 갖췄다.

**그런데 실제로 검증하려고 화면의 진짜 채팅창을 찾아 프론트 코드를
역추적한 결과, 이 전체 경로(`yujin_creator_proposals.py`/`hermes_run_
service.py`/`videobox-creator/SKILL.md`)가 화면 어디서도 안 불린다는 것을
발견했다.**

- `apps/web/src`에서 `api.createHermesRun`/`hermesSseClient.ts`의
  `streamHermesSseWithReconnect`를 부르는 `.tsx`가 **0건**이다.
- 실제 채팅(`HomeYujinChat.tsx`, `EditorWorkbenchRoute.tsx`의 대화창)은 전부
  `sendDirectorMessage` → `submit_conversation_message` →
  `createYujinEditingProposal` → `YujinEditingProposalService`로 간다.
- 이 시스템의 도메인 모델(`yujin_editing_proposals.py`)에는 output_variant도
  숏폼도 개념 자체가 없다 — 16개 세그먼트 편집 의도(속도·컷·자막·색감·전환 등)
  뿐이다.

즉 이번에 고친 `create_short_form`뿐 아니라 **기존 `remake_short_form`/
`unfold_to_editing_board`도 화면 채팅으로는 안 된다.** 이전 세션들이
"된다"고 적어 둔 근거(`test_yujin_can_remake_the_short_when_the_owner_tells_
her_to` 류)는 `YujinCreatorContext`를 코드로 직접 만들어 검증기를 통과시킨
것이라 **화면을 한 번도 안 지났다** — `CLAUDE.md` §4가 경고하는 "API 단건
확인이 화면 확인을 대체하지 못한다"의 정확한 사례였다.

**코드를 폐기하지 않았다.** 도메인·저장소 조각(특히 `created_short_form_
variant`, `apply_director_variant_create_proposal_transaction`)은 재사용
가능하다고 판단했다 — 잘못은 로직이 아니라 **입구**(어느 프로필/컨텍스트가
그걸 부르는가)였다. 계획서의 "해야 할 것" 절에 다음에 할 일 순서를 다시
적었다: `yujin_editing_proposals.py`(16개 의도가 있는 그 파일)에 새 의도를
추가하고, `_editing_prompt`를 고치고, 적용기에서 `short_form_scenes.py`의
기존 함수를 부르는 것.

## 3. 검증 못 끝낸 것 — 정직하게

### R1 (md5, 가장 중요하다고 지시받음) — 완료 못 함, 별개 결함 발견

`2026-09-12-ca6dd9ed`에서 완성본(마스터, 495초 전체) 렌더를 여러 번
시도했으나 **전부 `ffmpeg` 스레드 자원 오류로 실패**했다(`frame=0`,
`Terminating thread with return code -11`). 코드로 확인한바 완성본 렌더
경로는 `shorts_layout`을 아예 안 읽어 이번 세션 변경과 무관하고, 이 프로젝트가
반복 프로빙으로 마스터 세그먼트 94개까지 쌓인 상태에서 재빌드 이전부터도
간헐적으로 실패해 왔다(job_004·010·016도 실패) — **새로 생긴 결함이 아니다.**
별도 task로 남겼다(`spawn_task`, `docs/`가 아니라 세션 큐에 있음 — 다음
세션이 안 보이면 owner에게 확인).

R1의 좁은 주장("경계 나누기가 완성본을 안 바꾼다")은 코드 구조로는 참이라고
본다(제목 띠 데이터가 완성본 렌더 경로에 들어갈 길이 없다) — 다만 **md5로
다시 재지는 못했다.** 완성본 렌더가 다시 성공하는 날 재확인이 필요하다.

### R2 (CapCut 초안의 blur) — 코드 확인만, 실물 못 봄

CapCut 내보내기 코드에 `shorts_layout`/`shorts_title` 참조가 0건 — 제목 띠는
CapCut 초안에 반영되지 않는다(그냥 없는 것으로 나간다). 이건 이번 세션
문제가 아니라 `d7bd2d023`(이전 커밋)의 `blur` 기본값 변경에 대해 계속
밀려온 확인 항목이다. CapCut 앱이 이 환경에 없어 실물 초안을 못 열었다.

### R3 (유진에게 실제로 말해서) — 시도해서 "안 된다"로 반증함

위 2절 참고. 화면 채팅 자체가 이 기능을 모른다.

## 4. 다음 세션이 먼저 할 일

1. `docs/superpowers/plans/2026-09-12-a-short-that-looks-like-a-short.md`의
   "Task 3 — 해야 할 것"부터 읽는다.
2. 완성본 렌더 자원 오류(별도 task, 위 3절)를 owner와 상의해 우선순위를
   정한다 — 안 고치면 이 프로젝트에서 R1 재확인 자체가 불가능하다.
3. CapCut 앱이 있는 환경에서 R2를 실측한다.

## 5. 커밋

- `88ce30e34` feat: 숏폼 제목 띠 레이아웃을 닫고, 채팅으로 숏폼 만들기를 시도한다
- `88e46c57` docs: Task 3 조사 결과 정정 -- 유진 채팅은 다른 백엔드로 간다

전체 backend pytest(`.venv/Scripts/python.exe -m pytest -q`, 단독 실행)를
돌렸으나 완료까지 40분+ 걸려 이 인계를 쓰는 시점까지 못 받았다 — 관련
테스트(변경 파일 전부를 포함하는 776여 건)는 별도로 여러 번 돌려 전부
초록임을 이미 확인했다. 결과가 나오면 다음 턴에 보고한다.
