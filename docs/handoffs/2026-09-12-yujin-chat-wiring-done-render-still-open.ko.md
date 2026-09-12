# 유진 채팅으로 숏폼 만들기·다시 만들기·펼치기가 실제로 된다 (2026-09-12 밤)

앞 인계(`2026-09-12-title-band-closed-and-yujin-chat-backend-split-found.ko.md`)를
잇는다. 그 인계가 찾아낸 문제 — "코드는 다 있는데 실제 화면 채팅은 완전히 다른
백엔드(`yujin_editing_proposals.py`)를 쓰고 있어서 안 닿는다" — 를 이번 세션에
고쳤다. 계획서는 `docs/superpowers/plans/2026-09-12-a-short-that-looks-like-a-short.md`
— "### 해야 할 것" 절을 이번에 갱신해 뒀다. **다음 세션은 "4. 렌더" 항목부터
시작하면 된다.**

## 1. 무엇을 했는가

**진짜 화면 채팅 경로**(`HomeYujinChat.tsx`/`EditorWorkbenchRoute.tsx` →
`sendDirectorMessage` → `createYujinEditingProposal` →
`YujinEditingProposalService`)에 `create_short_form`/`remake_short_form`/
`unfold_short_form` 세 의도를 새로 얹었다.

- `packages/domain-models/.../yujin_editing_proposals.py` — 세 의도를 discriminated
  union에 추가.
- `yujin_editing_proposal_adapter.py` — 검증기에 분기 추가(숏폼 의도는 다른 의도와
  못 섞고, 만들기는 이미 있으면 거절, 다시 만들기/펼치기는 없으면 거절).
- `yujin_editing_proposal_service.py`(`_editing_prompt`) — 프롬프트에 세 의도
  설명과, 지금 숏폼이 있는지 없는지에 따라 달라지는 안내문(`_short_form_
  catalogue`)을 추가. **이 파일이 유진이 실제로 읽는 프롬프트다** — 앞 세션이
  고쳤던 `videobox-creator/SKILL.md`는 화면 어디서도 안 불리는 죽은 문서였다.
- `routers/director_proposals.py` — 적용기(`apply_yujin_editing_proposal_route`)에
  숏폼 세 의도 분기(`_apply_short_form_editing_intent`)를 추가. 세션 문서를 고치는
  `update_editing_session` 대신 `output_variant`(별개 자원)를 직접 만들고/바꾸는
  기존 저장소 함수(`created_short_form_variant`/`remade_short_form_variant`/
  `orchestrator.unfold_short_form_editing_session`)를 그대로 부른다 — **화면의
  단추가 부르는 것과 같은 함수**다.
- `short_form_scenes.py`에 `current_short_form_variant(...)` 공용 함수를 새로
  만들어 "지금 숏폼이 있는가" 판정을 한 곳으로 모았다 — 전에는 `hermes_run_
  service.py`에 같은 판정이 두 벌 있었다.

## 2. 검증

- `tests/test_yujin_editing_proposal_adapter.py`에 검증기 단위 시험 5건 추가.
- `tests/test_yujin_editing_short_form.py`(새 파일) — **실제 엔드포인트**
  (`POST .../yujin-editing-proposals` → `POST .../apply`)를 그대로 두드리는 통합
  시험 5건. `YujinCreatorContext`를 손으로 만들어 검증기만 통과시키는 식(전 세션이
  걸렸던 함정)이 아니라, 화면이 밟는 것과 같은 두 홉짜리 경로를 그대로 밟는다.
- 관련 시험 247건 별도 실행 — 전부 초록(3분 5초).
- **전체 backend pytest 단독 실행**(`.venv/Scripts/python.exe -m pytest`, 48분):
  5117 passed, 1 failed, 56 skipped. 실패한 1건(`test_owner_ready_script.py::
  test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure`)은 이번
  변경과 무관한 PowerShell 하위 프로세스 타임아웃 시험으로, 기존 메모
  (`videobox-smoke-timeout-test-fails-by-machine-state.md`)가 이미 "기계 상태로
  실패한다"고 적어 둔 그 시험이다 — 코드 변경이 아니라 이 컴퓨터의 프로세스 정리
  타이밍 문제로 본다.

## 3. R3(실제 채팅창에서 직접 타이핑) — 시도했으나 GPU 경합으로 미완주

밤 10시부터 다른 프로젝트가 같은 GPU의 qwen 모델을 쓰고 있어(대표님이 직접
설명해 주심 — 버그 아님) 화면 채팅에서 로컬 LLM 응답이 매번 시간 초과됐다.
서버 로그로 요청이 새 코드 경로(`_apply_short_form_editing_intent`)까지 정확히
도달하는 것은 확인했지만, 답까지 받는 것은 못 봤다. **다음에 열 때 `lms ps`로
qwen이 유휴인지 먼저 확인하고 마저 확인할 것.**

## 4. 렌더("내보내줘") — 아직 시작 안 함

계획서 4번 항목. **화면이 쓰는 같은 자리(`POST /api/projects/{id}/variant-renders`)를
그대로 쓰고, 채팅 안에 세 번째 진행률 표시 방식을 만들지 않는다** — apply 응답은
"만들고 있어요, 출력 화면에서 확인해 주세요" 정도로 렌더 잡만 시작시키고, 폴링은
기존 출력 화면 폴링에 맡기는 안을 먼저 검토할 것. 상세는 계획서 문서와 별도
task(`숏폼 유진 배선 -- 렌더`)에 있다.

## 5. 새로 발견해 큐에만 넣어 둔 것 (이번 세션 범위 밖)

- 로컬 LLM 제공자가 실패하면 `local_only_blocked: <예외 원문>`이 사용자 화면
  채팅에 그대로 샌다 — 내부 오류 문자열 노출. 이번 세션이 만든 버그는 아니고
  기존 버그를 발견만 함.
- 완성본(마스터) 렌더가 세그먼트 94개 누적된 이 테스트 프로젝트에서 간헐적으로
  `ffmpeg` 스레드 자원 오류로 실패 — 앞 인계가 이미 별도 task로 기록해 뒀고,
  R1(md5 재확인)이 여기 막혀 있다. 이번 세션도 재확인 시도했으나 여전히 막혀
  있어 못 풀었다.
- CapCut R2(blur 실물 확인): 데스크탑 초안(`com.lveditor.draft`)과 CapCut 웹은
  아예 다른 저장 구조라서, 웹으로는 우리가 만든 실제 초안을 열어 볼 방법이
  구조적으로 없다는 것을 확인했다. `Wbrowser`(대표님의 CDP 자동화 도구)로 CapCut
  웹의 "새로 만들기"까지는 가봤지만 그 다음이 OS 파일 선택창이라 텍스트 기반
  자동화로는 못 넘는다. 로그인은 대표님이 직접 하셨고 나는 손대지 않았다.

## 6. 커밋

- `ffb8d5926` feat: 유진 채팅으로 숏폼 만들기·다시 만들기·펼치기 -- 진짜 화면 경로에
- (이 인계 + 계획서 갱신은 별도 `docs:` 커밋으로 뒤따른다)

## 7. 다음 세션이 먼저 할 일

1. `lms ps`로 GPU가 비었는지 보고 R3(실제 채팅창 타이핑)를 마저 확인한다.
2. 계획서 "4. 렌더" 항목을 시작한다 — 새 폴링/진행률 방식을 만들지 말 것.
3. 완성본 렌더 자원 오류(별도 task)를 owner와 상의해 우선순위를 정한다 — 안
   고치면 R1 재확인 자체가 계속 막혀 있다.
