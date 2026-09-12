# 숏폼 만들기·다시 만들기·펼치기·내보내기가 채팅으로 다 된다 — 답변 문구 버그의 진짜 원인을 찾았다 (2026-09-13 새벽)

앞 인계(`2026-09-12-yujin-chat-wiring-done-render-still-open.ko.md`)를 잇는다.
그 인계가 남긴 "다음은 렌더"를 이번에 끝냈고, R3(실제 채팅창 확인)도 이번엔
GPU가 비어서 끝까지 했다. 그 과정에서 훨씬 중요한 걸 하나 찾았다 — **화면에
뜨는 유진의 대답 문구는, 무엇을 실행할지 결정하는 코드와 완전히 다른 별도의
LLM 호출이 만든다.** 계획서는
`docs/superpowers/plans/2026-09-12-a-short-that-looks-like-a-short.md` —
"4. 렌더"와 "6. 실물 채팅 확인" 절을 이번에 갱신했다.

## 1. 렌더("내보내줘") 배선 — 끝냄, 실제로 mp4가 나오는 것까지 확인

`render_short_form` 의도를 새로 얹었다(파라미터 없음 — "지금 걸린 숏폼
하나"를 화면 단추와 같은 함수로 내보낸다).

- `yujin_editing_proposals.py`에 `RenderShortFormOperation` 추가.
- `yujin_editing_proposal_adapter.py` — 있어야 쓸 수 있는 넷째 숏폼 의도로 분류.
- `yujin_editing_proposal_service.py` — 스키마·프롬프트에 추가.
- `routers/director_proposals.py`의 `_apply_short_form_editing_intent`에 분기
  추가 — **변형본을 안 바꾼다**(렌더는 output_variant를 짓거나 고치는 일이
  아니다). `orchestrator.start_variant_renders` + 새로 뽑은
  `launch_pending_variant_render_workers`를 그대로 불러 렌더 잡만 시작시키고
  "숏폼을 만들고 있어요. 출력 화면에서 확인해 주세요."를 동기로 돌려준다.
- **같은 로직 두 자리 함정을 미리 막았다**: 워커 스레드를 켜는 로직이
  `routers/outputs.py`(화면 단추)와 `routers/director_proposals.py`(이번에
  얹는 채팅) 두 곳에 거의 같은 모양으로 생기게 생겨서,
  `orchestration.py`에 `launch_pending_variant_render_workers` 공용 메서드로
  먼저 뽑고 둘 다 그것만 부르게 했다.
- 렌더는 output_variant를 안 바꾸므로 `apply_director_variant_proposal_
  transaction`으로 소진할 대상이 없다 — 대신 렌더 잡 자체가 같은
  `variant_revision`에 대해 이미 CAS로 idempotent해서(화면 단추도 이
  재사용에 기댄다) 제안을 따로 소진하지 않아도 두 번 눌러도 안전하다.

**실물 확인(가장 강한 증거).** 깨끗한 프로젝트("사진 브이로그 실기 0907",
과거 완성본이 있어 실제 자산이 멀쩡한 프로젝트)에서 실제 웹 화면 채팅에
직접 타이핑했다: "숏폼 만들어줘" → "숏폼 내보내줘". Job API로 직접 조회해
**진짜 완성본 mp4가 두 번 성공한 것을 확인했다**(`final_render_job_014`/
`016`, 둘 다 `status: succeeded`, 8초, 1080×1920). 처음 골랐던 프로젝트
("역방향 실측 2026-09-12 숏폼")는 예전 세션들이 하도 많이 건드려서 변형본에
`unresolved_variant_conflicts`(pre-existing, `master_changed_while_locked`)가
남아 있어 렌더가 정상적으로 거절됐다 — 이건 결함이 아니라
`output_variants.py`의 기존 안전장치가 제대로 작동한 것이다.

## 2. 답변 문구 버그 — 두 번 잘못 고치고서야 진짜 원인을 찾았다

R3를 하다가 "숏폼 다시 만들어줘"의 답변이 55초짜리 엉뚱한 대본을 써버리는
것을 봤다. **처음엔 이걸 `yujin_editing_proposal_service.py`의
`_short_form_catalogue`(reply_text 안내가 부족하다고) 문제로 오진하고
두 번 고쳤다**(`b5f3013b9`, `fcf35544e`) — 첫 수정 뒤 화면 문구가
"..."로 짧아졌고, 렌더에 대해서는 "저는 실행 못 해요, 단추를 누르세요"로
더 심해졌다.

**둘 다 헛짚었다.** 코드를 다시 추적해 보니, 화면에 뜨는 "유진: ..." 문구는
`_editing_prompt`가 만드는 게 아니라 **완전히 별도의 LLM 호출**이 만든다:

```
sendDirectorMessage -> POST .../director/conversations/{id}/messages
  -> submit_conversation_message (routers/director_proposals.py)
  -> YujinLocalConversationService.reply(...) (yujin_local_conversation.py)
```

이 호출은 사용자 문장만 보고 **무엇이 실제로 실행될지 전혀 모르는 채**
자기 나름의 대답을 짓는다. `createYujinEditingProposal`(operations를
결정하고 실제로 적용하는 그 경로)은 **별개의 후속 호출**이다 — 둘이
같은 결정을 공유하지 않는다.

**진짜 원인을 찾았다.** `yujin_local_conversation.py`의
`_YUJIN_SYSTEM_PROMPT`에 이 두 문장이 있다:
1. "CapCut이나 렌더러를 직접 조작... [안 한다]" — `render_short_form`이
   생기기 전에는 맞았지만 이제 아니다.
2. "편집이 실제로 반영되려면 사람이 화면에서 직접 승인해야 하며, 대화 중
   '네'는 승인이 아니다" — `2026-09-01-yujin-chat-applies-edits-directly.
   ko.md` 결정과 정면으로 어긋난다. 직접 편집 의도(세그먼트 편집 16개 +
   숏폼 4개)는 이미 자동 적용된다. (다만 화면의 자료 추천 카드는 지금도
   "적용" 단추가 필요해서, 단순 삭제가 아니라 **어느 흐름인지 구분**해서
   고쳐야 한다 — 그래서 이번 세션엔 손 안 댔다.)

이번 세션엔 **안 고쳤다** — 화면 전체 대화(기존 16개 편집 의도 포함)에
쓰이는 범용 프롬프트라 섣불리 고치면 다른 곳에서 새 회귀가 날 수 있어서,
제대로 된 진단만 남기고 별도 task로 큐에 올렸다(`task_935fadb7`). 이전에
잘못 짚은 task(`task_68dbf7aa`)는 지웠다.

**중요:** 실제 편집/렌더 동작(operations) 자체는 이번 버그와 무관하게
매번 정확했다 — 문제는 오직 화면에 보이는 **말**뿐이다. 대표님이 화면에서
직접 확인하시면, 편집·렌더는 실제로 잘 되는데 유진이 그걸 부정하는 말을
하는 것으로 보일 것이다.

## 3. 검증

- `tests/test_yujin_editing_proposal_adapter.py` — render_short_form 단위
  시험 3건 추가(총 14건).
- `tests/test_yujin_editing_short_form.py` — 렌더 성공·실패 실제 엔드포인트
  시험 2건 추가(총 7건, 렌더 시작 메서드만 가짜로 세움 — 진짜 ffmpeg는
  실물 확인에서만 돌렸다).
- `tests/test_final_render_idempotency.py` — 새 공용 메서드
  `launch_pending_variant_render_workers` 단위 시험 추가, 기존 라우터 시험을
  거기 맞게 고침(총 16건).
- **전체 backend pytest 단독 실행**(48분): 5121 passed / 56 skipped / 1
  failed. 실패한 1건(`test_owner_ready_script.py`, 다른 마커 케이스)은
  단독 재실행하면 통과 — 기존에 기록된 "전체 실행에서만 기계 상태로 흔들리는
  시험" 패턴과 같다고 판단(이번 변경과 무관한 파일).
- 컨테이너를 세 번 재빌드하며 실제 웹 화면에서 직접 타이핑해 확인했다
  (R3 + 렌더 실물 확인 + 답변 문구 버그 재현·오진 확인).

## 4. 다음 세션이 먼저 할 일

1. `task_935fadb7`부터 본다 — `yujin_local_conversation.py`의
   `_YUJIN_SYSTEM_PROMPT` 두 문장을 사실과 맞게 고친다(직접 편집은 자동
   적용, 자료 추천 카드만 단추 필요). 고치기 전에 task 설명의 "할 일"
   4단계를 그대로 따를 것 — 범용 프롬프트라 다른 흐름 회귀에 주의.
2. 완성본(마스터) 렌더 자원 오류(별도 task, 세그먼트 94개 프로젝트) —
   여전히 안 풀림. R1(md5 재확인)이 여기 막혀 있다.
3. CapCut R2(blur 실물 확인) — 여전히 구조적으로 막혀 있음(앞 인계 참고).

## 5. 커밋

- `ffb8d5926` feat: 유진 채팅으로 숏폼 만들기·다시 만들기·펼치기
- `2a25e390a` docs: 배선 완료 반영
- `b5f3013b9` fix: (오진) 숏폼 답변이 대본을 지어 쓰던 것
- `8a626557` docs: R3 닫음 기록
- `5f014692` feat: 유진 채팅에서 "숏폼 내보내줘"(렌더)
- `fcf35544` fix: (오진, 더 나빠짐) 렌더 답변의 거짓 부정
- (이 인계 + 계획서 갱신은 별도 `docs:` 커밋으로 뒤따른다)
