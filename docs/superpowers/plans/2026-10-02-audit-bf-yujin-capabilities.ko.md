# 유진에게 화면 기능 전부 열기 (묶음 B~F) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 화면에서 되는데 유진은 못 하던 기능(분할·붙이기·되돌리기·배속 전 범위·트랙 숨김/소리 끄기, 완성본·캡컷 초안·미리보기 링크·업로드 승인 **요청**, 설명 카드·표·도형·자막 모양·저장한 포맷, 자막 번역·언어·더빙·TTS 교체·받아쓰기 캡션·부분 다시 만들기, 그 밖의 남은 빈칸)을 유진 편집 채팅으로도 쓸 수 있게 한다. 각 기능은 화면이 쓰는 **같은 함수·같은 라우트**로 간다.

**Architecture:** 화면 채팅은 `POST .../yujin-editing-proposals`(의도 판단) → `POST .../apply`(적용) 한 길로만 간다. 새 기능마다 이 길의 여덟 겹(의도 모델 · JSON 스키마 · 안내문 · 맥락 · 검증기 · 적용기 · 답장 문장 · 화면 한 줄)을 같이 넓힌다. 적용기는 두 갈래다 — **세션 편집형**(A형: 한 번의 되돌리기 단위로 묶임, `_apply_yujin_editing_operations`)과 **단독 실행형**(B형: 화면과 같은 orchestrator 함수를 각각 부름, `_apply_standalone_intent`). 오래 걸리는 일(완성본·캡컷·번역·더빙·받아쓰기·부분 재생성)은 서버가 job만 걸고 돌아오고, 화면은 이미 있는 `pollJobUntilTerminal` 폴링으로 유진 패널에 "맡은 일" 줄을 띄운다.

**Tech Stack:** Python 3.12 · FastAPI · pydantic v2(strict) · pytest / React 18 + TypeScript · vitest + Testing Library / 로컬 LLM(LM Studio, structured output)

**Spec:** docs/superpowers/2026-10-02-audit-follow-up-plan.ko.md + docs/decisions/2026-10-02-audit-follow-up-decisions.ko.md

## Global Constraints

1. **세션 시작 체크리스트를 먼저 한다**(`CLAUDE.md` §0): `CLAUDE.md` → `docs/development-fast-path.ko.md` §10 → `docs/decisions/`(가장 나중 것부터, 최소 `2026-10-02-audit-follow-up-decisions.ko.md`) → `git status --short`, `git log --oneline -5`, `git worktree list`, `git diff --check`. 작업은 메인 체크아웃 `main`에서 한다.
2. **경계(바뀌지 않는 것)** — 결정 문서 그대로:
   - **영구 삭제는 유진에게 열지 않는다.** 보관(되돌릴 수 있음)까지만. 자료실 `trash`, 프로젝트 삭제, 대화 삭제 라우트는 의도로 만들지 않는다.
   - **사람 게이트 셋(제목 선택·대본 확정·업로드)은 유진에게 열지 않는다.** 업로드는 **승인 요청**(`request-upload-approval`)까지만. `founder-approval-decisions`·결재 결정 기록 라우트는 의도로 만들지 않는다.
   - TTS 교체는 **이미 들어 보고 승인된 후보만** 고른다(`operator_review_status == "approved"`). 듣기 승인 자체(`listening-review`)는 열지 않는다.
   - 팔레트·배치는 이 계획에서 건드리지 않는다. 화면에 새로 생기는 것은 유진 패널의 상태 한 줄(`유진이 맡은 일`)뿐이다.
3. **애매한 확인 문장은 여전히 되묻는다.** `_YUJIN_SYSTEM_PROMPT`(`packages/core-engine/src/videobox_core_engine/yujin_local_conversation.py:70-73`)의 "그걸로/그거/응/네 → 되물어라" 문장을 지우거나 약하게 바꾸지 않는다. 묶음을 닫을 때마다 실기에서 "응 그걸로 해줘"가 편집안을 만들지 않는지 잰다.
4. **백엔드 시험**: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider <file>::<test>`. 맨 `pytest`·시스템 Python 결과는 근거가 아니다. RED/GREEN 단계에서는 **시험 1개만** 돌린다. 전체 pytest(약 40~50분)는 Task 22에서 **혼자** 돌리고 `--ignore=tests/test_mcp_server.py`를 붙인다(수집 에러, 메모리 "맨 pytest는 0건 실행된다").
5. **웹 시험**: 반드시 `apps/web`에서 돈다 — `cd apps/web && npx vitest run <file>`. 타입 검사 `cd apps/web && npx tsc --noEmit`. 빌드 `npm --prefix apps/web run build`.
6. **알려진 기존 실패(건드리지 않는다)**: `apps/web/src/features/editor/workbench/editor-workbench.test.tsx`의 "gives the material dock back the same way, without needing a second click", `tests/test_owner_ready_script.py::test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure`. 결함으로 보고하기 전에 이전 커밋(`git stash`가 아니라 `git worktree add`로 만든 임시 트리)에서 같은 실패가 나는지 먼저 본다.
7. **컨테이너**: 재빌드·재시작은 PowerShell에서 `.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild`만 쓴다. 맨 `docker compose` 금지. 화면은 http://127.0.0.1:5173, 재빌드 뒤 브라우저 Ctrl+F5 한 번.
8. **화면 문구(§10.13)**: 명사형 이름표, 필요한 곳만 짧은 해요체. `provider`·`runtime`·`model`·`job`·`revision`·`pipeline`·`시스템`·`모델`·`파이프라인` 등을 화면 글자에 쓰지 않는다(`apps/web/src/user-copy-policy.test.ts`가 지킨다). 유진 안내문(모델이 읽는 프롬프트)은 화면 문구가 아니므로 intent 이름 등 영어 식별자를 써도 된다.
9. **`ProductShell.tsx`는 이 계획에서 고치지 않는다**(SHA-256 고정, `docs/oss/editor-ui-source-map.json`). 만약 고치게 되면 두 곳의 `normalized_sha256`을 `.venv/Scripts/python.exe -c "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('apps/web/src/app/ProductShell.tsx').read_bytes()).hexdigest())"`로 갱신하고 `tests/test_editor_ui_source_provenance.py`를 돌린다.
10. **새 단추를 만들지 않는다.** 이 계획은 화면 단추를 추가하지 않으므로 `apps/web/src/task22-parity-owners.test.ts` 허용 목록은 바뀌지 않아야 한다. 바뀌어야 한다면 멈추고 보고한다.
11. **Host/Origin 검사가 전역이다**(`services/api/src/videobox_api/csrf_guard.py`). 시험은 `TestClient`(호스트 `testserver`)만 쓴다. `videobox.test` 같은 가짜 호스트는 400이 난다.
12. **"같은 로직이 두 자리에"를 만들지 않는다.** 화면 라우트에 있던 본문을 유진 쪽에서도 써야 하면 **함수로 뽑아 두 곳이 같이 부르게** 한다(완성본 워커 시작, 캡컷 워커 시작, 업로드 승인 요청, 포맷 적용). 복사하지 않는다.
13. **허용값을 넓히면 세 층(엔진·API 스키마·유진 의도)**을 같이 보고, 넓힌 **끝값**(0.25, 4.0)으로 끝까지 밟는다.
14. **유진 실기는 새 편집본에서** 한다(메모리 "유진 시험은 새 세션에서"). Task 0이 만드는 `scripts/owner-path/ask_yujin_capabilities.py`가 매 지시마다 새 편집본을 연다.
15. **유진이 "없다/못 한다"고 하면 로그부터**: `docker logs videobox-api --since 10m 2>&1 | Select-String "유진의 편집 제안을 검증이 막았습니다"`로 거절 사유를 본다(`director_proposals.py:614-617`이 남긴다).
16. **GPU 경합 먼저**: 지연을 재기 전에 PowerShell에서 `lms ps`. 모델이 둘 이상 올라가 있으면 그 사실을 기록한다. **35b 모델은 내리지 않는다**(다른 프로젝트가 쓴다).
17. **조각마다 검증 넷(고정)**: 갭(이 문서 Step 대조, 안 한 것을 적는다) · 역방향(컨테이너 재빌드 후 브라우저) · 동작(렌더는 파일·픽셀, 소리는 음량으로 잰다) · 배선(`git grep`으로 실제 부르는 자리를 센다). 각 Task 끝의 "검증 넷" Step이 그것이다.
18. **커밋은 Task마다.** 메시지는 한국어, 마지막 줄 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. 확인과 푸시를 한 명령에 묶지 않는다. 푸시는 묶음이 닫히는 Task(7·12·16·20·21·22)에서 검증 결과를 본 뒤 **정확히** `git push origin main`(force 금지, 다른 브랜치·옵션 금지). **도구 권한이 이 푸시를 막으면 우회하지 않는다**(다른 명령·다른 셸·`--no-verify` 등 금지) — 멈추고 owner에게 "`D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`에서 `git push origin main`을 직접 실행하시거나, 권한 허용 규칙 `Bash(git push origin main)`을 추가해 주세요"라고 알린 뒤 다음 Task로 넘어가지 않고 기다린다.
19. 이 계획의 줄 번호는 2026-10-02 `main`(`ca39f2a7f`) 기준이다. 앞 Task가 같은 파일을 고치면 줄이 밀린다 — **줄 번호가 아니라 각 Step에 적은 "기준 글귀"로 찾아 고친다.**
20. **단독 실행형(B형)은 한 편집안을 한 번만 실행한다.** 세션 편집형은 적용이 세션 판(`session_revision`)을 올려서 같은 편집안을 두 번 적용하면 두 번째가 409로 막힌다. 단독 실행형(완성본·캡컷 초안·미리보기 링크·업로드 승인 요청·번역·더빙·받아쓰기·부분 재생성 …)은 판을 안 올리므로 그 장치가 없다 — 두 번 적용하면 링크 둘·승인 요청 둘·렌더 둘이 생긴다. 그래서 Task 4가 만드는 `store.claim_director_proposal_for_standalone_apply`로 **실행 전에** 편집안을 원자적으로 `applied`로 바꾸고(`ready`일 때만), 이미 소진된 편집안은 409 `editing_proposal_already_applied`로 돌려보낸다. MCP `ask_yujin`은 409 중 `editing_proposal_needs_refresh`일 때만 다시 시도한다(Task 4). 새 단독 실행형 갈래는 이 장치 **안에서만** 부른다 — `_apply_standalone_intent`를 거치지 않는 단독 실행 경로를 만들지 않는다.
21. **오래 걸리는 일은 적용 라우트가 기다리지 않는다**(프록시 330초 벽). 완성본·캡컷 초안·번역·더빙·받아쓰기·부분 재생성은 job만 걸고 `{"status": "..._started", "job_id": ...}`로 **즉시** 돌아오고, 화면은 Task 8의 `followYujinWork`(공용 `pollJobUntilTerminal`)로 `유진이 맡은 일` 줄을 띄운다. 적용 라우트 안에서 `join()`·폴링·`time.sleep`을 하지 않는다. 동기 응답으로 남는 것은 실측 30초 이하인 것뿐이다(F7 장면 그림 약 24초 — 330초 벽 안이고, 그동안은 `commitTimelineMutation`이 이미 띄우는 저장 상태 줄 `변경 내용을 저장하고 있어요.`가 기다림 표시다).

## Review Focus

행복한 경로 시험이 덮지 못하는, 실제로 터질 가능성이 큰 입력 다섯. 각각 소유 Task에 시험이 들어간다.

1. **단독 의도를 다른 편집과 섞은 제안**("방금 거 되돌리고 3번 장면 빼줘" → `undo_last_edit` + `set_cut_action`). 반쯤 적용되면 안 되고 생성 단계에서 `operation_must_be_alone`으로 막혀야 한다. → Task 2(`split_segment` 섞기), Task 4(`undo_last_edit` 섞기), Task 9(`render_final_video` 섞기).
2. **장면 가장자리·뺀 장면에서 나누기/붙이기**(`at_sec_in_scene=0.1`, 길이-0.1, 첫 장면 붙이기, 뺀 장면 붙이기). 적용 단계 422("적용하지 못했어요")가 아니라 생성 단계에서 이유 있는 거절. → Task 2, Task 3.
3. **배속 끝값과 문자열**: `rate=0.25`/`4.0` 통과, `4.5`·`0`·`"0.5배"` 거절, 0.5초 장면에 `4.0` → 0.2초 미만이 되는 조합은 생성 단계에서 `scene_speed_makes_scene_too_short`. → Task 5.
4. **업로드 승인 요청의 실패 모양**: 완성본이 없거나 낡았거나(`final_render_not_current`), 권리를 모르는 자산이 있으면(`asset_rights_unconfirmed`) 결재함에 아무것도 안 올라가고, 유진 답장은 "승인됐어요/업로드했어요"라고 말하지 않는다. → Task 11.
5. **트랙 상태 병합과 되돌리기**: 자막 트랙 음소거·내레이션 숨김 같은 뜻 없는 조합은 거절, 배경 음악만 끄면 이미 숨긴 영상 트랙 상태가 그대로 남아야 하고(덮어쓰기 금지), 그 한 번을 되돌리면 이전 상태로 돌아와야 한다(세션 전역 값이 `mutate`에서 버려지는 함정 — 이미 열린 `set_caption_font`의 맨 위 `caption_style`도 지금 버려지고 있다). → Task 6(Step 0이 기존 결함을 먼저 재현).

(검토에서 더함) 6. **같은 편집안 두 번 적용**(대화상자 `적용` 연타, MCP 재시도, 네트워크 재전송). 판을 안 올리는 단독 실행형은 지금 장치로는 두 번 실행된다(미리보기 링크 둘·승인 요청 둘·렌더 둘). → Task 4(편집안 소진 + MCP 재시도 좁히기, 시험 둘), Task 12(실물에서 두 번 적용).

---

## 0. Yujin 기능 하나를 여는 표준 절차

이 절은 **모든 Task가 따르는 절차**다. 아래 기존 의도 하나(`set_scene_speed` — 세션 편집형, `render_short_form` — 단독 실행형의 선례)를 처음부터 끝까지 따라간 결과다. 줄 번호는 `ca39f2a7f` 기준.

### 0.1 요청 한 번이 지나는 길

```
[화면] YujinPanel 입력 → EditorWorkbenchRoute.sendDirectorMessage (EditorWorkbenchRoute.tsx:2045-2074)
   ├─ ① 답장: submitDirectorMessage → POST /director/conversations/{id}/messages
   │     → YujinLocalConversationService.reply  (_YUJIN_SYSTEM_PROMPT, yujin_local_conversation.py:46-84)
   │     ※ 답장은 적용 **전에** 만들어진다. 그래서 답장은 실제 결과를 모른다.
   └─ ② 판단+적용: interpretAndApplySpokenEdit (EditorWorkbenchRoute.tsx:2119-2147)
         → api.createYujinEditingProposal (api.ts:2247-2248)
         → POST /api/projects/{p}/editing-sessions/{s}/yujin-editing-proposals
              director_proposals.py:453-632  create_yujin_editing_proposal
              ├ YujinEditingContext 조립 (director_proposals.py:479-595)
              ├ YujinEditingProposalService.create (yujin_editing_proposal_service.py:662-673)
              │    prompt = _editing_prompt(...)            (같은 파일 535-659)
              │    schema = _editing_response_schema(...)   (같은 파일 86-105, 의도 목록 39-83)
              └ interpret_yujin_editing_request → _validate_current_targets (yujin_editing_proposal_adapter.py:157-361)
         → applyEditingProposalNow (EditorWorkbenchRoute.tsx:2080-2108)
              preflight → POST .../yujin-editing-proposals/{id}/apply
              director_proposals.py:693-740  apply_yujin_editing_proposal_route
              ├ 숏폼 넷 → _apply_short_form_editing_intent (742-823)     ← 단독 실행형의 선례
              ├ 변형본 충돌 → _apply_variant_conflict_resolution_from_chat (825-871)
              └ 나머지 → apply_yujin_editing_proposal (editing_session.py:1365-1385)
                           → _apply_yujin_editing_operations (editing_session.py:1142-1348)  ← 세션 편집형
         → 완료 목록 한 줄: editingProposalCompletionEntry → yujinEditingOperationSummary (yujinEditingSummary.ts:44-107)
[MCP] services/mcp/src/videobox_mcp/tools.py:73-180 ask_yujin → 같은 두 라우트를 그대로 부른다. 단 지금은 apply의 **모든 409**를 다시 시도한다(`_ask_yujin_once`의 `if exc.status_code != 409`) — Task 4가 `editing_proposal_needs_refresh`일 때만 다시 시도하게 좁힌다(안 좁히면 단독 실행형의 다른 409 뒤에 새 편집안을 만들어 한 번 더 실행한다)
```

**주의 — 화면 채팅은 Hermes 프로필을 읽지 않는다.** `config/hermes/yujin/SOUL.md`·`skills/videobox-editor/SKILL.md`는 9119 Hermes 경로용이고 `tests/test_hermes_yujin_profile_distribution.py`가 내용을 고정한다. 화면 채팅의 "프로필 안내문"은 **`_editing_prompt`(의도 판단)**와 **`_YUJIN_SYSTEM_PROMPT`(답장)** 둘이다. 이 계획은 Hermes 프로필 파일을 고치지 않는다.

### 0.2 여덟 겹 체크리스트 (새 의도 하나마다)

| # | 겹 | 파일·자리 | 할 일 |
|---|---|---|---|
| 1 | 의도 모델 | `packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py` — 클래스는 `RenderShortFormOperation`(326-336) 아래, 유니언 `YujinEditingOperation`(339-362), `__all__`(379-404) | `_StrictFrozenModel`(장면 무관) 또는 `_SegmentOperation`(장면 하나) 상속, `intent: Literal["..."]`. 목록 값의 원본이 core-engine에 있으면 `str`로 받고 검증기에서 대조(색감·전환과 같은 규칙). 유니언과 `__all__`에 넣는다. |
| 2 | JSON 스키마 | `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py:39-83` `_EDITING_OPERATION_SCHEMA["oneOf"]` | 같은 이름·같은 필드로 한 줄. `additionalProperties: False`, 말한 것만 싣게 `required`는 최소로. |
| 3 | 안내문 | 같은 파일 `_editing_prompt`(535-659): (a) 허용 intent 문장(575-595) — `"resolve_variant_conflict(변형본 충돌을` 줄 **바로 앞**에 `"새_intent(뜻 -- \"창작자가 할 말\"이 이것이다), "` 한 줄, (b) 목록·지금 값 문단 — `_..._catalogue(context)` 함수를 만들고 `f"{_variant_conflict_catalogue(context)} "`(623) 다음 줄에 붙인다 | **목록과 지금 값은 한 쌍**(메모리 "목록과 현재값은 한 쌍"). 창작자가 실제로 할 말 → 값 매핑을 적는다. 거절 예시에 지원 기능을 쓰지 않는다. |
| 4 | 맥락 | `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py:73-141` `YujinEditingContext`(필드 추가, **기본값 필수**), 조립은 `services/api/src/videobox_api/routers/director_proposals.py:479-595` — `image_overlays_by_segment=_image_overlays_by_segment(session),`(574) 다음 줄에 키워드 추가 | 안내문이 쓰는 값과 검증기가 쓰는 값을 같은 필드에서 읽는다. |
| 5 | 검증기 | 같은 adapter `_validate_current_targets`(210-361) | 지어낸 값·지금 상태에서 불가능한 값을 **생성 단계**에서 이유 코드로 막는다. 혼자여야 하는 의도는 `MUST_BE_ALONE_INTENTS`(Task 2가 만든다)에 넣는다. |
| 6 | 적용기 | **A형(세션 편집형)**: `editing_session.py` `_apply_yujin_editing_operations`(1142-1348)에 `elif isinstance(...)` 한 갈래 — 화면 라우트가 부르는 **같은 core 함수**를 부른다. 세션 전역 값(`track_states`, `caption_style`)을 바꾸면 `apply_yujin_editing_proposal`(1365-1385)의 `mutate`가 그 열쇠도 옮기게 한다. **B형(단독 실행형)**: `STANDALONE_INTENTS`(Task 4가 만든다)에 넣고 `director_proposals.py`의 `_apply_standalone_intent`(Task 4가 만든다)에 갈래 하나 — 화면 라우트가 부르는 **같은 orchestrator 함수**를 부른다. 편집안 소진(`claim_director_proposal_for_standalone_apply`)은 적용 라우트가 `_apply_standalone_intent`를 부르기 **전에** 한 번 한다(Global Constraint 20) — 갈래마다 따로 하지 않는다. 오래 걸리면 job만 걸고 즉시 돌아온다(Global Constraint 21). | 화면 라우트 본문을 복사하지 않는다(Global Constraint 12). |
| 7 | 답장 문장 | `yujin_local_conversation.py:56-61` | 새로 연 일이 "실행한다고 답해도 거짓이 아닌" 목록에 들어가는지 본다. 사람 게이트는 "요청까지만, 승인은 대표님이"를 못박는다. 되묻기 문장(70-73)은 그대로. |
| 8 | 화면 한 줄 | `apps/web/src/features/editor/workbench/yujinEditingSummary.ts:44-107` | 의도마다 한 줄(`편집 항목을 바꿔요.`로 떨어지면 안 된다). B형 결과가 `notice`·job을 돌려주면 Task 8의 `yujinApplyOutcome`가 읽는다. |

선택: `director_proposals.py:1402-1412` `_editing_follow_ups`에 이어 할 질문 셋(없어도 된다).

### 0.3 시험 네 겹 (모든 Task가 같은 모양)

1. **의도 파싱+검증 RED** — `interpret_yujin_editing_request(response, context)`가 통과/이유 코드로 거절하는지(순수 함수, 빠름).
2. **적용기 RED** — A형은 `_apply_yujin_editing_operations` 또는 API 두 라우트를 지나는 시험, B형은 반드시 **API 두 라우트**(`tests/yujin_chat_fakes.py`의 `create_and_apply`)를 지나는 시험. orchestrator의 무거운 함수(렌더 시작 등)만 `monkeypatch`.
3. **안내문 존재 RED** — `_editing_prompt(instruction=..., context=...)` 결과에 새 intent 이름과 창작자 말 예시가 있는지.
4. **화면 한 줄 RED** — `yujinEditingSummary.test.ts`.

그리고 묶음이 닫힐 때 **새 편집본 실기**(Task 0의 스크립트)와 **브라우저 실기**.

### 0.4 바뀐 기존 결정 하나

`packages/core-engine/src/videobox_core_engine/editing_session.py:35-36`과 `tests/test_ripple_speed_range.py:12-14`는 "유진 스키마는 안 넓힌다(1·1.5·2만)"고 적고 있다. **2026-10-02 owner 결정("전부 연다", 묶음 B3 "배속 0.25~4.0 전체")이 이것을 바꿨다.** 옛 규칙은 `docs/decisions/`의 승인 기록이 아니라 커밋 `beaf88105`(2026-09-04 `속도`를 캡컷과 같게)에서 코드 주석으로만 생긴 구현자 판단이다(2026-10-02 `docs/decisions/` 전체 grep — `2026-09-04-capcut-shell-with-my-assets.ko.md`는 화면 배속만 넓히라고 했고 유진 범위는 말하지 않는다). 그래도 **주석만 조용히 고치지 않는다** — Task 5 Step 7이 `docs/decisions/2026-10-02-audit-follow-up-decisions.ko.md` 끝에 "바뀐 옛 규칙" 덧붙임을 먼저 쓰고, 두 주석은 그 덧붙임을 가리키게 고친다.

---

## 작업 순서 한눈에

| Task | 묶음 | 내용 | 적용기 형 |
|---|---|---|---|
| 0 | — | 착수 확인, 실기·지연 측정 스크립트, 기준선 | — |
| 1 | — | 공용 시험 도구 `tests/yujin_chat_fakes.py` | — |
| 2 | B1 | `split_segment` + 장면 길이 맥락 + "혼자" 규칙 | A |
| 3 | B1 | `merge_with_previous` | A |
| 4 | B2 | `undo_last_edit` / `redo_last_edit` + 단독 실행형 길 + **한 번만 실행(편집안 소진)** + MCP 재시도 좁히기 | B |
| 5 | B3 | 배속 0.25~4.0 (세 층) | A |
| 6 | B4 | `set_track_state` + `mutate`가 세션 전역 값을 옮김 | A |
| 7 | B | 묶음 B 닫기: 답장 문장·실기·지연·푸시 | — |
| 8 | C0 | 서버가 건 일을 화면이 지켜보는 길(`yujinApplyOutcome`·`yujinBackgroundWork`·`session_master_outputs`) | — |
| 9 | C1 | `render_final_video` | B |
| 10 | C2 | `export_capcut_draft`, `create_preview_link` | B |
| 11 | C3 | `request_upload_approval`(요청까지만) | B |
| 12 | C | 묶음 C 닫기 | — |
| 13 | D1 | 설명 카드·표·도형 (얹기/빼기 여섯) | A |
| 14 | D2 | `set_caption_style` + `caption_style`도 옮김 | A |
| 15 | D3 | `apply_format_template` | B |
| 16 | D | 묶음 D 닫기 | — |
| 17 | E1 | `translate_captions`, `set_caption_language` | B |
| 18 | E2 | `dub_narration` | B |
| 19 | E3 | `set_tts_replacement`/`clear_tts_replacement`, `captions_from_transcript`, `regenerate_part` | B |
| 20 | E | 묶음 E 닫기 | — |
| 21 | F | 남은 빈칸 다시 세기 + 후보별 열기 | A/B |
| 22 | — | 프롬프트 크기·지연 최종 측정, 전체 검증, 인계 | — |
| 23 | — | **조건부**: 지연이 1.5배를 넘었을 때만 — 두 단계 판단(묶음 고르기 → 그 묶음 안내문만) 시험 구현·측정 | — |

---

### Task 0: 착수 확인과 측정 기준선

**Files:**
- Create: `scripts/owner-path/ask_yujin_capabilities.py`
- Create: `scripts/measure_yujin_prompt_size.py`
- Read only: `scripts/owner-path/drive.py:1-25`(`BASE`, `call`), `scripts/owner-path/ask_yujin_about_photos.py:1-80`(선례)

**Interfaces:**
- Consumes: `drive.call(method: str, path: str, body: dict | None = None, *, timeout: float = 300.0) -> tuple[int, dict]`; `GET /api/projects/{p}/jobs` → `{"jobs": [...]}`; `POST /api/projects/{p}/editing-sessions` body `{"timeline_job_id": str}` → 201 세션; `POST .../yujin-editing-proposals` body `{"instruction": str}`; `videobox_core_engine.yujin_editing_proposal_service._editing_prompt(*, instruction: str, context: YujinEditingContext) -> str`
- Produces: `python scripts/owner-path/ask_yujin_capabilities.py <project_id> <bundle>` (bundle ∈ `baseline`,`B`,`C`,`D`,`E`,`F`) — 지시마다 새 편집본, 고른 의도·통과 여부·걸린 초·중앙값 출력, 종료 코드 0/1. `python scripts/measure_yujin_prompt_size.py` — 40장면 맥락에서 프롬프트 글자 수 한 줄 출력.

- [ ] **Step 1: 세션 시작 체크리스트**

```powershell
git status --short; git log --oneline -5; git worktree list; git diff --check
```
기대: `?? .anchor/` 외에 변경 없음, 맨 위 커밋 `ca39f2a7f`(또는 그 뒤 묶음 A 커밋들). 묶음 A가 이미 들어왔으면 `git log --oneline -15`에서 `PATCH .../filename`(자료실 이름 바꾸기) 커밋이 있는지 적어 둔다(Task 21에서 쓴다).

- [ ] **Step 2: 실기 스크립트를 만든다**

`scripts/owner-path/ask_yujin_capabilities.py`:

```python
"""묶음별로 유진에게 말을 시켜 보고, 고른 의도와 걸린 시간을 잰다 — 실기.

**새 편집본에서 시킨다.** 앞 요청이 편집본 상태를 바꿔 같은 이유로 두 번 틀렸다
(메모리 "유진 시험은 새 세션에서"). 지시마다 그 프로젝트의 최신 타임라인 작업에서
편집본을 새로 연다.

**편집안만 만들고 적용하지 않는다.** 완성본 렌더·업로드 승인 요청 같은 일은 이
스크립트에서 일어나지 않는다 -- 적용은 브라우저 실기에서 사람이 본다.

쓰는 법: python scripts/owner-path/ask_yujin_capabilities.py <project_id> <bundle>
bundle: baseline | B | C | D | E | F
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from drive import call  # noqa: E402

#: 편집안이 없어야 맞는 경우("" = proposal 없음, 되묻기·거절).
NO_PROPOSAL = ""

#: (이름, 시킬 말, 통과로 보는 intent 집합). 집합에 NO_PROPOSAL이 있으면 편집안이 없어도 통과.
BUNDLES: dict[str, list[tuple[str, str, set[str]]]] = {
    "baseline": [
        ("배속(기존)", "2번 장면 두 배 빠르게 해줘", {"set_scene_speed"}),
        ("자르기(기존)", "1번 장면 앞부분 1초 잘라줘", {"set_segment_bounds"}),
        ("되묻기", "응 그걸로 해줘", {NO_PROPOSAL}),
    ],
    "B": [
        ("나누기", "2번 장면 2초에서 나눠줘", {"split_segment"}),
        ("붙이기", "3번 장면을 앞 장면이랑 붙여줘", {"merge_with_previous"}),
        ("느리게", "2번 장면 느리게 해줘", {"set_scene_speed"}),
        ("아주 빠르게", "1번 장면 네 배 빠르게 해줘", {"set_scene_speed"}),
        ("트랙 소리", "배경 음악 트랙 소리 꺼줘", {"set_track_state"}),
        ("트랙 숨기기", "자막 트랙 숨겨줘", {"set_track_state"}),
        ("되돌리기(없음)", "방금 거 되돌려줘", {"undo_last_edit", NO_PROPOSAL}),
        ("되묻기", "응 그걸로 해줘", {NO_PROPOSAL}),
    ],
    "C": [
        ("완성본", "완성본 만들어줘", {"render_final_video"}),
        ("캡컷", "캡컷 초안으로 내보내줘", {"export_capcut_draft"}),
        ("링크", "미리보기 링크 만들어줘", {"create_preview_link", NO_PROPOSAL}),
        ("승인 요청", "유튜브 업로드 승인 요청 올려줘. 내일 오전에 올릴 예정이야", {"request_upload_approval", NO_PROPOSAL}),
        ("승인은 못 함", "업로드 승인해줘", {"request_upload_approval", NO_PROPOSAL}),
        ("되묻기", "응 그걸로 해줘", {NO_PROPOSAL}),
    ],
    "D": [
        ("설명 카드", "2번 장면에 '핵심: 재고 회전율' 설명 카드 띄워줘", {"set_explanation_card"}),
        ("표", "3번 장면에 가격 비교 표 넣어줘. 항목은 A사 3만원, B사 4만원", {"set_table_overlay"}),
        ("도형", "1번 장면 오른쪽 위에 화살표 표시 작게 넣어줘", {"set_shape_overlay"}),
        ("자막 색", "자막 노란색으로 바꿔줘", {"set_caption_style"}),
        ("자막 위치", "자막 화면 위쪽으로 올려줘", {"set_caption_style"}),
        ("포맷", "저번에 저장한 포맷 입혀줘", {"apply_format_template", NO_PROPOSAL}),
        ("되묻기", "응 그걸로 해줘", {NO_PROPOSAL}),
    ],
    "E": [
        ("번역", "자막 영어로 번역해줘", {"translate_captions"}),
        ("언어", "자막 원래 한국어로 돌려줘", {"set_caption_language"}),
        ("더빙", "영어 목소리로 더빙해줘", {"dub_narration", NO_PROPOSAL}),
        ("받아쓰기", "말 받아써서 캡션 만들어줘", {"captions_from_transcript", NO_PROPOSAL}),
        ("부분 다시", "2번 장면 영상만 다시 골라줘", {"regenerate_part", "apply_media", NO_PROPOSAL}),
        ("되묻기", "응 그걸로 해줘", {NO_PROPOSAL}),
    ],
    "F": [
        ("보관", "이 프로젝트 보관해줘", {"archive_project"}),
        ("삭제는 못 함", "이 프로젝트 영구 삭제해줘", {NO_PROPOSAL}),
        ("이름", "프로젝트 이름을 '셀러 교육 3편'으로 바꿔줘", {"rename_project"}),
        ("되묻기", "응 그걸로 해줘", {NO_PROPOSAL}),
    ],
}


def latest_timeline_job_id(project_id: str) -> str | None:
    code, body = call("GET", f"/api/projects/{project_id}/jobs")
    if code != 200:
        print(f"!! 작업 목록을 못 읽었다: {code}")
        return None
    jobs = [
        job for job in body.get("jobs") or []
        if job.get("job_type") == "timeline_build" and job.get("status") == "succeeded"
    ]
    if not jobs:
        return None
    jobs.sort(key=lambda job: (str(job.get("finished_at") or ""), str(job.get("started_at") or ""), str(job.get("job_id"))))
    return str(jobs[-1]["job_id"])


def fresh_session(project_id: str, timeline_job_id: str) -> str | None:
    code, body = call("POST", f"/api/projects/{project_id}/editing-sessions", {"timeline_job_id": timeline_job_id})
    if code != 201:
        print(f"!! 새 편집본을 못 열었다: {code} {json.dumps(body, ensure_ascii=False)[:200]}")
        return None
    return str(body.get("session_id") or "")


def main() -> int:
    if len(sys.argv) < 3 or sys.argv[2] not in BUNDLES:
        print(f"쓰는 법: {sys.argv[0]} <project_id> <{'|'.join(BUNDLES)}>")
        return 2
    project_id, bundle = sys.argv[1], sys.argv[2]
    timeline_job_id = latest_timeline_job_id(project_id)
    if timeline_job_id is None:
        print("!! 이 프로젝트에 끝난 타임라인 작업이 없다 -- 장면이 있는 프로젝트를 골라라")
        return 1
    failures = 0
    seconds: list[float] = []
    for label, instruction, allowed in BUNDLES[bundle]:
        session_id = fresh_session(project_id, timeline_job_id)
        if not session_id:
            failures += 1
            continue
        started = time.perf_counter()
        code, body = call(
            "POST",
            f"/api/projects/{project_id}/editing-sessions/{session_id}/yujin-editing-proposals",
            {"instruction": instruction},
            timeout=600.0,
        )
        elapsed = time.perf_counter() - started
        seconds.append(elapsed)
        operations = ((body.get("diff") or {}).get("operations")) or []
        intents = [str(item.get("intent") or "") for item in operations] or [NO_PROPOSAL]
        passed = code in (200, 201) and all(intent in allowed for intent in intents)
        if not passed:
            failures += 1
        print(f"{'  ' if passed else '!!'} {label} ({elapsed:.1f}초)")
        print(f"     시킨 말: {instruction}")
        print(f"     응답 {code}, 고른 것: {intents}")
        print(f"     유진: {str(body.get('reply_text') or body.get('detail') or '')[:160]}")
        if operations:
            print(f"     첫 편집: {json.dumps(operations[0], ensure_ascii=False)[:240]}")
        print()
    if seconds:
        print(f"걸린 시간: 중앙값 {statistics.median(seconds):.1f}초, 최대 {max(seconds):.1f}초 ({len(seconds)}건)")
    total = len(BUNDLES[bundle])
    print(f"{total - failures}/{total} 통과")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 프롬프트 크기 측정 스크립트를 만든다**

`scripts/measure_yujin_prompt_size.py`:

```python
"""유진 편집 판단 프롬프트가 얼마나 긴지 잰다 -- 묶음마다 늘어나는 안내문의 비용.

실제 대본은 243문단이지만 자막 목록은 40개에서 잘린다(`_CAPTION_CATALOGUE_LIMIT`).
그래서 40장면짜리 맥락으로 잰다. 숫자만 비교한다(묶음 전후).
"""
from __future__ import annotations

import sys
from pathlib import Path

# 패키지가 venv에 설치돼 있지 않다 -- `tests/conftest.py:13-28`과 같은 길을 직접 붙인다.
ROOT = Path(__file__).resolve().parents[1]
for relative in (
    "packages/domain-models/src", "packages/storage-abstractions/src", "packages/provider-interfaces/src",
    "packages/timeline-schema/src", "packages/core-engine/src",
):
    sys.path.insert(0, str(ROOT / relative))

from videobox_core_engine.yujin_editing_proposal_adapter import YujinEditingContext  # noqa: E402
from videobox_core_engine.yujin_editing_proposal_service import _editing_prompt  # noqa: E402


def main() -> int:
    segment_ids = tuple(f"seg-{index:03d}" for index in range(1, 41))
    context = YujinEditingContext(
        session_id="measure",
        session_revision=7,
        segment_ids=segment_ids,
        captions=tuple((segment_id, f"{segment_id} 자막 문장 하나입니다") for segment_id in segment_ids),
        segment_ids_with_broll=segment_ids[:20],
    )
    prompt = _editing_prompt(instruction="2번 장면 두 배 빠르게 해줘", context=context)
    print(f"프롬프트 글자 수: {len(prompt)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run: `.venv/Scripts/python.exe scripts/measure_yujin_prompt_size.py`
Expected: `프롬프트 글자 수: <숫자>` 한 줄. 이 숫자를 **기준선 A**로 적어 둔다.

- [ ] **Step 4: GPU 상태와 지연 기준선을 잰다**

PowerShell:
```powershell
lms ps
.\scripts\owner-ready.ps1 -Mode Check
```
화면(http://127.0.0.1:5173)에서 장면이 있는 프로젝트 하나를 골라 주소창의 `project_id`를 적는다(owner 실제 영상 프로젝트, 예: `노마드루이스` 채널 B-roll 프로젝트). 그 다음:
```powershell
.venv/Scripts/python.exe scripts/owner-path/ask_yujin_capabilities.py <project_id> baseline
```
Expected: `3/3 통과`와 `걸린 시간: 중앙값 N초`. `lms ps` 출력(올라간 모델 수)과 중앙값을 **기준선 B**로 적는다. 모델이 둘 이상이면 "GPU 경합 상태"라고 같이 적는다(35b를 내리지 않는다).

- [ ] **Step 5: 커밋**

```bash
git add scripts/owner-path/ask_yujin_capabilities.py scripts/measure_yujin_prompt_size.py
git commit -m "chore: 유진 기능 실기·프롬프트 크기 측정 스크립트(묶음 B~F 기준선용)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 1: 공용 시험 도구 — 화면이 쓰는 두 라우트를 지나는 가짜 유진

**Files:**
- Create: `tests/yujin_chat_fakes.py`
- Create: `tests/test_yujin_chat_fakes.py`
- Read only: `tests/test_yujin_editing_short_form.py:30-95`(일반화할 선례 `_EditingChatProvider`, `_plain_session_project`, `_create_and_apply`), `tests/test_api_output_variants.py:35-40`(`_offline_app`)

**Interfaces:**
- Consumes: `test_api_output_variants._offline_app(tmp_path: Path, *, name: str = ..., provider: object | None = None) -> FastAPI`; `videobox_provider_interfaces.llm.{LLMProviderError, LLMTaskType, StructuredLLMRequest, StructuredLLMResponse}`
- Produces:
  - `ScriptedEditingProvider(operations: list[dict] | None, reply_text: str = "처리했어요.")` — `.prompts: list[str]`, `.complete_structured(request)`; `operations=None`이면 proposal 없는 답(되묻기).
  - `DEFAULT_SEGMENTS: tuple[dict, ...]` — `seg-hook`(0~3) · `seg-middle`(3~20) · `seg-close`(20~24)
  - `plain_session_project(tmp_path, provider, *, segments=DEFAULT_SEGMENTS, extra_session=None) -> tuple[app, client, project_id, session]`
  - `propose(client, project_id, session_id, instruction) -> dict`
  - `create_and_apply(client, project_id, session, instruction) -> httpx.Response`
  - `current_session(client, project_id, session_id) -> dict`

- [ ] **Step 1: 실패하는 시험을 쓴다**

`tests/test_yujin_chat_fakes.py`:

```python
"""공용 가짜 유진이 화면이 쓰는 두 라우트를 실제로 지나는지 -- 도구 자체의 시험."""
from __future__ import annotations

from pathlib import Path

from yujin_chat_fakes import ScriptedEditingProvider, create_and_apply, current_session, plain_session_project, propose


def test_scripted_provider_drives_the_real_chat_routes(tmp_path: Path) -> None:
    provider = ScriptedEditingProvider(operations=[{"intent": "set_cut_action", "segment_id": "seg-close", "action": "exclude"}])
    app, client, project_id, session = plain_session_project(tmp_path, provider)

    response = create_and_apply(client, project_id, session, "3번 장면 빼줘")

    assert response.status_code == 200, response.text
    after = current_session(client, project_id, session["session_id"])
    assert [item["cut_action"] for item in after["segments"]][-1] == "remove"
    # 프롬프트가 실제로 모델 쪽에 닿았다 -- 화면 경로를 지났다는 증거.
    assert "현재 revision: 1" in provider.prompts[0]


def test_no_operations_means_yujin_asked_back(tmp_path: Path) -> None:
    provider = ScriptedEditingProvider(operations=None, reply_text="어느 장면일까요?")
    app, client, project_id, session = plain_session_project(tmp_path, provider)

    body = propose(client, project_id, session["session_id"], "응 그걸로 해줘")

    assert body["status"] == "clarification"
    assert body["proposal"] is None
```

- [ ] **Step 2: 돌려서 실패를 본다**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_chat_fakes.py::test_scripted_provider_drives_the_real_chat_routes`
Expected: FAIL — `ModuleNotFoundError: No module named 'yujin_chat_fakes'`

- [ ] **Step 3: 도구를 만든다**

`tests/yujin_chat_fakes.py`:

```python
"""유진 편집 채팅 시험 도구 -- **화면이 실제로 쓰는 문**을 지난다.

`/yujin-editing-proposals`(판단) -> `/apply`(적용). `test_yujin_editing_short_form.py`의
`_EditingChatProvider`를 일반화했다: 의도 하나가 아니라 operations 목록을 그대로 돌려준다.
core 함수를 직접 부르는 시험은 화면 경로의 증거가 되지 못한다(그 파일 머리말).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from test_api_output_variants import _offline_app
from videobox_provider_interfaces.llm import (
    LLMProviderError,
    LLMTaskType,
    StructuredLLMRequest,
    StructuredLLMResponse,
)

DEFAULT_SEGMENTS: tuple[dict[str, Any], ...] = (
    {"segment_id": "seg-hook", "caption_text": "이것만 보세요", "start_sec": 0.0, "end_sec": 3.0},
    {"segment_id": "seg-middle", "caption_text": "중간 설명", "start_sec": 3.0, "end_sec": 20.0},
    {"segment_id": "seg-close", "caption_text": "결론입니다", "start_sec": 20.0, "end_sec": 24.0},
)


@dataclass
class ScriptedEditingProvider:
    """편집 판단(`YUJIN_CONVERSATION`)에만 답하는 가짜 유진.

    `operations`가 `None`이면 편집안 없이 되묻는다. 시험이 중간에 `operations`를
    바꿔 같은 앱에서 두 번째 요청을 보낼 수 있다(되돌리기 시험이 그렇게 쓴다).
    `base_session_revision`은 프롬프트의 `현재 revision: N.`에서 그대로 읽는다.
    """

    operations: list[dict[str, Any]] | None
    reply_text: str = "처리했어요."
    prompts: list[str] = field(default_factory=list)

    def complete_structured(self, request: StructuredLLMRequest) -> StructuredLLMResponse:
        if request.task_type != LLMTaskType.YUJIN_CONVERSATION:
            raise LLMProviderError(provider_name="local_qwen", message="only the editing chat is scripted here")
        self.prompts.append(request.prompt)
        revision = 1
        marker = "현재 revision: "
        if marker in request.prompt:
            revision = int(request.prompt.split(marker, 1)[1].split(".", 1)[0].strip())
        output_data: dict[str, Any] = {
            "schema_version": "videobox.yujin-editing-response.v1",
            "reply_text": self.reply_text,
            "proposal": None if self.operations is None else {
                "proposal_id": "scripted",
                "base_session_revision": revision,
                "operations": [dict(item) for item in self.operations],
            },
        }
        return StructuredLLMResponse(
            provider_name="local_qwen", model_name="Qwen3-32B",
            output_data=output_data, raw_text="{}", metadata={},
        )


def plain_session_project(
    tmp_path: Path,
    provider: object,
    *,
    segments: tuple[dict[str, Any], ...] = DEFAULT_SEGMENTS,
    extra_session: dict[str, Any] | None = None,
):
    app = _offline_app(tmp_path, provider=provider)
    client = TestClient(app)
    project = client.post("/api/projects", json={"name": "유진 채팅 시험"}).json()
    payload: dict[str, Any] = {"segments": [dict(item) for item in segments], "history": [], **(extra_session or {})}
    session = app.state.store.save_editing_session(
        project_id=project["project_id"], timeline_id="timeline-source", session_payload=payload,
    )
    return app, client, project["project_id"], session


def propose(client: TestClient, project_id: str, session_id: str, instruction: str) -> dict[str, Any]:
    return client.post(
        f"/api/projects/{project_id}/editing-sessions/{session_id}/yujin-editing-proposals",
        json={"instruction": instruction},
    ).json()


def create_and_apply(client: TestClient, project_id: str, session: dict[str, Any], instruction: str):
    root = f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
    proposal = propose(client, project_id, session["session_id"], instruction)
    assert "proposal_id" in proposal, proposal
    return client.post(
        f"{root}/yujin-editing-proposals/{proposal['proposal_id']}/apply",
        json={"expected_revision": int(proposal["base_session_revision"])},
    )


def current_session(client: TestClient, project_id: str, session_id: str) -> dict[str, Any]:
    response = client.get(f"/api/projects/{project_id}/editing-sessions/{session_id}")
    assert response.status_code == 200, response.text
    return response.json()
```

- [ ] **Step 4: 통과를 본다**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_chat_fakes.py`
Expected: `2 passed`. (`set_cut_action` exclude가 `cut_action: "remove"`로 저장되는지는 `editing_session.py:1176-1181`이 정한다.)

- [ ] **Step 5: 커밋**

```bash
git add tests/yujin_chat_fakes.py tests/test_yujin_chat_fakes.py
git commit -m "test: 유진 편집 채팅 공용 가짜(화면이 쓰는 두 라우트를 지난다)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task 2: B1 — 장면 나누기(`split_segment`) + 장면 길이 맥락 + "혼자" 규칙

화면 `POST .../segments/{segment_id}/split`(`services/api/src/videobox_api/routers/editing_session.py:362-372`)이 부르는 core 함수 `split_segment`(`packages/core-engine/src/videobox_core_engine/editing_session.py:646-650`)를 그대로 쓴다. 세션 편집형(A형)이라 유진 편집 한 번 = 되돌리기 한 칸.

**Files:**
- Modify: `packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py:326-404` (클래스 추가·유니언·`__all__`)
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py:58-70`(상수), `:73-141`(맥락 필드), `:210-361`(검증)
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py:39-83`(스키마), `:535-659`(안내문)
- Modify: `packages/core-engine/src/videobox_core_engine/editing_session.py:1142-1348`(적용기)
- Modify: `services/api/src/videobox_api/routers/director_proposals.py:479-595`(맥락 조립)
- Modify: `apps/web/src/features/editor/workbench/yujinEditingSummary.ts:99-106`, `apps/web/src/features/editor/workbench/yujinEditingSummary.test.ts`
- Create: `tests/test_yujin_editing_basics.py`

**Interfaces:**
- Consumes: `split_segment(*, session: dict, segment_id: str, split_sec: float) -> dict`(판 전체 시각), `_segment_index(*, session, segment_id) -> int`(`editing_session.py:128-132`), `MIN_SEGMENT_DURATION_SEC = 0.2`(`editing_session.py:24`)
- Produces: `SplitSegmentOperation(segment_id: str, intent: Literal["split_segment"], at_sec_in_scene: float>0)`; `YujinEditingContext.segment_durations: tuple[tuple[str, float], ...] = ()`, `.excluded_segment_ids: tuple[str, ...] = ()`; adapter 공개 상수 `MUST_BE_ALONE_INTENTS: frozenset[str]`, `STANDALONE_INTENTS: frozenset[str]`; 거절 이유 `operation_must_be_alone`, `split_point_too_close_to_edge`, `split_segment_excluded`, `split_segment_duration_unknown`

- [ ] **Step 1: 실패하는 시험을 쓴다**

`tests/test_yujin_editing_basics.py`:

```python
"""묶음 B -- 유진 편집 기본기(나누기·붙이기·되돌리기·배속·트랙). owner 결정 2026-10-02 "전부 연다".

시험 네 겹(계획서 §0.3): 파싱+검증, 적용(화면 경로), 안내문, (화면 한 줄은 vitest).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from videobox_core_engine.yujin_editing_proposal_adapter import YujinEditingContext, interpret_yujin_editing_request
from videobox_core_engine.yujin_editing_proposal_service import _editing_prompt
from yujin_chat_fakes import ScriptedEditingProvider, create_and_apply, current_session, plain_session_project

_IDS = ("seg-hook", "seg-middle", "seg-close")
_DURATIONS = (("seg-hook", 3.0), ("seg-middle", 17.0), ("seg-close", 4.0))


def _response(*operations: dict, revision: int = 3) -> dict:
    return {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "편집안을 만들었어요.",
        "proposal": {"proposal_id": "p", "base_session_revision": revision, "operations": list(operations)},
    }


def _context(**extra: object) -> YujinEditingContext:
    return YujinEditingContext(
        session_id="s", session_revision=3, segment_ids=_IDS, segment_durations=_DURATIONS, **extra,  # type: ignore[arg-type]
    )


# --- 나누기 -------------------------------------------------------------------

def test_split_point_must_leave_room_on_both_sides() -> None:
    inside = interpret_yujin_editing_request(
        _response({"intent": "split_segment", "segment_id": "seg-middle", "at_sec_in_scene": 2.0}), _context()
    )
    near_start = interpret_yujin_editing_request(
        _response({"intent": "split_segment", "segment_id": "seg-middle", "at_sec_in_scene": 0.1}), _context()
    )
    near_end = interpret_yujin_editing_request(
        _response({"intent": "split_segment", "segment_id": "seg-hook", "at_sec_in_scene": 2.9}), _context()
    )

    assert inside.status == "candidate_only"
    assert near_start.reason == "split_point_too_close_to_edge"
    assert near_end.reason == "split_point_too_close_to_edge"


def test_split_is_refused_on_a_removed_scene() -> None:
    result = interpret_yujin_editing_request(
        _response({"intent": "split_segment", "segment_id": "seg-close", "at_sec_in_scene": 1.0}),
        _context(excluded_segment_ids=("seg-close",)),
    )
    assert result.reason == "split_segment_excluded"


def test_split_mixed_with_another_edit_is_refused_before_anything_applies() -> None:
    """Review Focus 1: 나누면 오른쪽 조각 id가 새로 생긴다 -- 섞으면 무엇을 가리키는지 흔들린다."""
    mixed = interpret_yujin_editing_request(
        _response(
            {"intent": "split_segment", "segment_id": "seg-middle", "at_sec_in_scene": 2.0},
            {"intent": "set_cut_action", "segment_id": "seg-hook", "action": "exclude"},
        ),
        _context(),
    )
    assert mixed.reason == "operation_must_be_alone"


def test_yujin_splits_a_scene_from_the_real_chat(tmp_path: Path) -> None:
    provider = ScriptedEditingProvider(operations=[{"intent": "split_segment", "segment_id": "seg-middle", "at_sec_in_scene": 2.0}])
    app, client, project_id, session = plain_session_project(tmp_path, provider)

    response = create_and_apply(client, project_id, session, "2번 장면 2초에서 나눠줘")

    assert response.status_code == 200, response.text
    after = current_session(client, project_id, session["session_id"])
    assert [item["segment_id"] for item in after["segments"]] == ["seg-hook", "seg-middle", "seg-middle__split_2", "seg-close"]
    # 장면 시작(3.0)부터 2초 -- 판 전체 5.0초에서 나뉜다.
    assert after["segments"][1]["end_sec"] == pytest.approx(5.0)
    assert after["segments"][2]["start_sec"] == pytest.approx(5.0)
    # 유진 편집 한 번은 되돌리기 한 칸이다(안전장치는 되돌리기, 2026-09-01 결정).
    assert after["undo_count"] == 1


def test_the_prompt_tells_yujin_how_to_split_and_how_long_each_scene_is() -> None:
    prompt = _editing_prompt(instruction="2번 장면 2초에서 나눠줘", context=_context())

    assert "split_segment" in prompt
    assert "at_sec_in_scene" in prompt
    assert "2번 장면=seg-middle(17.0초)" in prompt
```

- [ ] **Step 2: 하나만 돌려 실패를 본다**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_basics.py::test_split_point_must_leave_room_on_both_sides`
Expected: FAIL — `TypeError: YujinEditingContext.__init__() got an unexpected keyword argument 'segment_durations'`

- [ ] **Step 3: 의도 모델 (겹 1)**

`yujin_editing_proposals.py` — `RenderShortFormOperation` 클래스 끝(`    intent: Literal["render_short_form"]`, 336행) **다음**, `YujinEditingOperation = Annotated[` **앞**에 넣는다:

```python
class SplitSegmentOperation(_SegmentOperation):
    """장면 하나를 둘로 나눈다 -- 화면 `나누기`(`POST .../segments/{id}/split`)와 같은 core 함수.

    `at_sec_in_scene`은 **그 장면 시작부터** 잰 초다. 판 전체 시각을 받으면 모델이 앞
    장면들 길이를 더해야 하는데, 번호를 세는 일조차 틀렸다(2026-09-02 실측) -- 덧셈은
    적용기가 한다.

    **혼자여야 한다.** 나누면 오른쪽 조각 id(`{id}__split_N`)가 새로 생겨, 같은 제안 안의
    다른 편집이 가리킬 자리가 흔들린다(검증기의 `MUST_BE_ALONE_INTENTS`).
    """

    intent: Literal["split_segment"]
    at_sec_in_scene: float = Field(gt=0, allow_inf_nan=False)
```

유니언 — 기준 글귀

```python
    | RenderShortFormOperation
    | ResolveVariantConflictOperation,
```

를 다음으로 바꾼다:

```python
    | RenderShortFormOperation
    | SplitSegmentOperation
    | ResolveVariantConflictOperation,
```

`__all__` — `"SetSegmentBoundsOperation",` 다음 줄에 `"SplitSegmentOperation",`를 넣는다.

- [ ] **Step 4: 맥락·상수·검증 (겹 4·5)**

`yujin_editing_proposal_adapter.py`

(a) import — `from videobox_core_engine.transitions import TRANSITION_CATALOG` 다음 줄에:

```python
from videobox_core_engine.editing_session import MIN_SEGMENT_DURATION_SEC
```

(`editing_session.py`는 이 adapter를 import하지 않으므로 순환이 없다 — 2026-10-02 `git grep` 확인.) 도메인 import 목록(`from videobox_domain_models.yujin_editing_proposals import (`)에 `SplitSegmentOperation,`을 `SetSoundCleanupOperation,` 다음에 넣는다.

(b) 상수 — `_MAX_PAYLOAD_BYTES = 32_768` **바로 앞**에:

```python
#: 세션 편집 한 덩이(`apply_yujin_editing_proposal`)로 가지 않고, 화면과 같은 orchestrator
#: 함수로 **각각** 가는 의도(계획서 §0.2 B형). 전부 혼자여야 한다. 적용 라우트
#: (`director_proposals.py`의 `_apply_standalone_intent`)가 이 집합으로 가른다.
STANDALONE_INTENTS: frozenset[str] = frozenset()

#: 혼자서만 실을 수 있는 의도. 나누기·붙이기는 장면 id를 바꾸고, 단독 실행형은
#: 세션 편집 한 덩이에 섞일 수 없다 -- 숏폼 넷의 `short_form_operation_must_be_alone`과
#: 같은 규칙이다.
MUST_BE_ALONE_INTENTS: frozenset[str] = frozenset({"split_segment"}) | STANDALONE_INTENTS
```

(c) 맥락 필드 — `YujinEditingContext`의 마지막 필드 `    variant_conflicts: tuple[tuple[str, str, str], ...] = ()`(141행) 다음에:

```python
    #: 장면별 **지금 보이는 길이**(초). 나누기 자리가 장면 안인지 검증기가 보고, 안내문은
    #: `2번 장면=seg(17.0초)`로 보여 준다 -- 길이를 모르면 "2초에서 나눠줘"가 끝을 넘는지 모른다.
    segment_durations: tuple[tuple[str, float], ...] = ()
    #: 완성본에서 뺀 장면(`cut_action == "remove"`). 나누기·붙이기를 그 장면에 걸지 않는다.
    excluded_segment_ids: tuple[str, ...] = ()
```

(d) "혼자" 규칙 — `_validate_current_targets` 안, 기준 글귀

```python
    current_variant_conflicts = set(
        (variant_id, field) for variant_id, _kind, field in context.variant_conflicts
    )
```

**바로 다음**에:

```python
    if len(proposal.operations) != 1 and any(
        operation.intent in MUST_BE_ALONE_INTENTS for operation in proposal.operations
    ):
        return "operation_must_be_alone"
```

(e) 장면 무관 의도의 열쇠 — 같은 함수, `elif isinstance(operation, SetCaptionFontOperation):` 갈래의 마지막 줄 `            key = (operation.intent, "all")` 다음, `        else:` **앞**에:

```python
        elif not hasattr(operation, "segment_id"):
            # 편집본 전체에 거는 새 의도들(되돌리기·트랙·완성본·자막 모양 …). 장면 번호가 없다.
            key = (operation.intent, "all")
```

(f) 나누기 검사 — 같은 함수의 `        if isinstance(operation, SetSceneTransitionOperation):` **앞**(`operation_targets.add(key)` 다음)에:

```python
        if isinstance(operation, SplitSegmentOperation):
            reason = _split_point_problem(operation, context)
            if reason is not None:
                return reason
```

(g) 도우미 — `def _rejected(reason: str)` **앞**에:

```python
def _split_point_problem(operation: SplitSegmentOperation, context: YujinEditingContext) -> str | None:
    """나눌 자리가 장면 안쪽인지. 엔진(`_split_one_segment_in_place`)도 막지만 거기까지
    가면 창작자는 "적용하지 못했어요"만 본다 -- 같은 규칙을 생성 단계에서 이유와 함께 막는다."""
    if operation.segment_id in set(context.excluded_segment_ids):
        return "split_segment_excluded"
    duration = dict(context.segment_durations).get(operation.segment_id)
    if duration is None:
        return "split_segment_duration_unknown"
    if (
        operation.at_sec_in_scene < MIN_SEGMENT_DURATION_SEC
        or duration - operation.at_sec_in_scene < MIN_SEGMENT_DURATION_SEC
    ):
        return "split_point_too_close_to_edge"
    return None
```

- [ ] **Step 5: 맥락 조립 (겹 4, API)**

`director_proposals.py` — 기준 글귀 `            image_overlays_by_segment=_image_overlays_by_segment(session),` **다음 줄**에:

```python
            # 장면 길이와 뺀 장면. 나누기·붙이기가 어디까지 되는지 유진과 검증기가 같은 값으로 본다.
            segment_durations=tuple(
                (str(item["segment_id"]), float(item.get("end_sec") or 0.0) - float(item.get("start_sec") or 0.0))
                for item in session.get("segments", [])
                if isinstance(item, dict) and item.get("segment_id")
            ),
            excluded_segment_ids=tuple(
                str(item["segment_id"])
                for item in session.get("segments", [])
                if isinstance(item, dict) and item.get("segment_id")
                and str(item.get("cut_action") or "keep") == "remove"
            ),
```

- [ ] **Step 6: 적용기 (겹 6, A형)**

`editing_session.py` `_apply_yujin_editing_operations` — 함수 안 import 목록에 `SplitSegmentOperation,`을 더하고, 기준 글귀

```python
        else:
            raise ValueError("editing_proposal_operation_not_supported")
    return working
```

의 `else:` **앞**에:

```python
        elif isinstance(operation, SplitSegmentOperation):
            # 화면 `나누기`와 **같은 함수**다. 장면 안 초를 판 시각으로 바꾸는 덧셈만 여기서 한다.
            index = _segment_index(session=working, segment_id=operation.segment_id)
            start_sec = float(working["segments"][index]["start_sec"])
            working = split_segment(
                session=working, segment_id=operation.segment_id,
                split_sec=start_sec + float(operation.at_sec_in_scene),
            )
```

- [ ] **Step 7: 스키마와 안내문 (겹 2·3)**

`yujin_editing_proposal_service.py`

(a) 스키마 — `_EDITING_OPERATION_SCHEMA`의 `resolve_variant_conflict` 줄(81행, `{"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "resolve_variant_conflict"}`로 시작) **다음 줄**에:

```python
        # 묶음 B(2026-10-02). 나누기는 **장면 시작부터** 잰 초다 -- 판 전체 시각이 아니다.
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "split_segment"}, "segment_id": {"type": "string"}, "at_sec_in_scene": {"type": "number", "exclusiveMinimum": 0}}, "required": ["intent", "segment_id", "at_sec_in_scene"]},
```

(b) 장면 목록에 길이 — `_editing_prompt`의 기준 글귀

```python
        f"현재 장면: {', '.join(f'{index}번 장면={segment_id}' for index, segment_id in enumerate(context.segment_ids, start=1))}. "
```

를 다음으로 바꾼다:

```python
        f"현재 장면: {', '.join(f'{index}번 장면={segment_id}' + (f'({durations[segment_id]:.1f}초)' if segment_id in durations else '') for index, segment_id in enumerate(context.segment_ids, start=1))}. "
```

그리고 `_editing_prompt` 본문 첫 줄(`    success_example = {`) **앞**에:

```python
    durations = dict(context.segment_durations)
```

(c) 허용 intent 문장 — 기준 글귀 `        "resolve_variant_conflict(변형본 충돌을 마스터 기준으로 맞추거나 지금 값을 그대로 둔다 -- "` **앞 줄**에:

```python
        "split_segment(장면 하나를 둘로 나눈다 -- \"3번 장면 2초에서 나눠줘\"가 이것이다), "
```

(d) 목록 문단 — `def _editing_prompt(` **앞**에 함수를 만든다:

```python
def _split_merge_catalogue(context: YujinEditingContext) -> str:
    """나누기(묶음 B1). 장면 길이는 위 `현재 장면` 목록에 있다 -- 여기서는 규칙만 말한다."""
    excluded = ", ".join(context.excluded_segment_ids) or "없음"
    return (
        "장면 나누기는 split_segment다 -- at_sec_in_scene은 **그 장면 시작부터** 잰 초다"
        "(판 전체 시각이 아니다). '3번 장면 2초에서 나눠줘'는 3번 장면의 segment_id와 "
        "at_sec_in_scene=2. 장면 양 끝에서 0.2초 안쪽은 못 나눈다. "
        "나누기는 **한 번에 하나만, 다른 편집과 섞지 않고** 싣는다. "
        f"완성본에서 뺀 장면(나누기·붙이기 불가): {excluded}."
    )
```

그리고 `_editing_prompt` 안 기준 글귀 `        f"{_variant_conflict_catalogue(context)} "` **다음 줄**에:

```python
        f"{_split_merge_catalogue(context)} "
```

- [ ] **Step 8: 화면 한 줄 (겹 8)**

`yujinEditingSummary.ts` — 기준 글귀 `  return "편집 항목을 바꿔요.";` **앞**에:

```ts
  // 묶음 B(2026-10-02): 화면에서 되던 편집 기본기를 유진에게도 열었다.
  if (operation.intent === "split_segment") return "장면을 둘로 나눠요.";
```

`yujinEditingSummary.test.ts` — 마지막 `});`(describe 닫기) **앞**에:

```ts
  it("나누기를 말한다", () => {
    expect(summary({ intent: "split_segment", segment_id: "s1", at_sec_in_scene: 2 })).toBe("장면을 둘로 나눠요.");
  });
```

- [ ] **Step 9: 통과를 본다**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_basics.py`
Expected: `5 passed`

Run: `cd apps/web && npx vitest run src/features/editor/workbench/yujinEditingSummary.test.ts`
Expected: all passed

- [ ] **Step 10: 넓은 검증 (이 Task가 건드린 이웃)**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_proposal_adapter.py tests/test_yujin_editing_command_evaluation.py tests/test_yujin_caption_font.py tests/test_yujin_editing_short_form.py tests/test_editor_timeline_mutations.py`
Expected: 전부 통과. 기존 시험이 `1번 장면=scene-1` 같은 글귀를 찾으면 여전히 들어 있다(길이는 그 뒤 괄호로 붙고, 맥락에 길이가 없으면 아예 안 붙는다).

- [ ] **Step 11: 검증 넷과 커밋**

갭: 이 Task는 나누기만 연다(붙이기는 Task 3). 배선: `git grep -n "split_segment" -- packages services apps/web/src` → 의도 모델·스키마·안내문·검증기·적용기·화면 한 줄 자리가 다 나와야 한다. 역방향·동작은 Task 7에서 묶음으로 한다.

```bash
git add packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py packages/core-engine/src/videobox_core_engine/editing_session.py services/api/src/videobox_api/routers/director_proposals.py apps/web/src/features/editor/workbench/yujinEditingSummary.ts apps/web/src/features/editor/workbench/yujinEditingSummary.test.ts tests/test_yujin_editing_basics.py
git commit -m "feat(yujin): 말로 장면 나누기 -- 화면 나누기와 같은 함수, 장면 길이 맥락, 혼자 규칙

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: B1 — 앞 장면과 붙이기(`merge_with_previous`)

화면 `POST .../segments/merge`(`routers/editing_session.py:374-384`)가 부르는 `merge_adjacent_segments`(`packages/core-engine/src/videobox_core_engine/editing_session.py:752-802`)를 그대로 쓴다. 화면 이름이 `앞과 붙이기`라서 의도도 "이 장면을 **앞** 장면에 붙인다"로 둔다(장면 둘을 받으면 모델이 순서를 뒤집어 보낼 수 있다).

**Files:**
- Modify: `packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py`(Task 2의 `SplitSegmentOperation` 다음)
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py`(`MUST_BE_ALONE_INTENTS`, 검사)
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py`(스키마·안내문)
- Modify: `packages/core-engine/src/videobox_core_engine/editing_session.py`(적용기)
- Modify: `apps/web/src/features/editor/workbench/yujinEditingSummary.ts`, `.test.ts`
- Modify: `tests/test_yujin_editing_basics.py`

**Interfaces:**
- Consumes: `merge_adjacent_segments(*, session, left_segment_id: str, right_segment_id: str) -> dict` — 인접·맞닿음·같은 non-remove `cut_action`만 받는다.
- Produces: `MergeWithPreviousOperation(segment_id: str, intent: Literal["merge_with_previous"])`; 거절 이유 `merge_needs_a_previous_scene`, `merge_scene_excluded`

- [ ] **Step 1: 실패하는 시험을 더한다** — `tests/test_yujin_editing_basics.py` 끝에:

```python
# --- 붙이기 -------------------------------------------------------------------

def test_merging_needs_a_previous_scene_that_is_not_removed() -> None:
    first = interpret_yujin_editing_request(_response({"intent": "merge_with_previous", "segment_id": "seg-hook"}), _context())
    removed_previous = interpret_yujin_editing_request(
        _response({"intent": "merge_with_previous", "segment_id": "seg-close"}),
        _context(excluded_segment_ids=("seg-middle",)),
    )
    fine = interpret_yujin_editing_request(_response({"intent": "merge_with_previous", "segment_id": "seg-close"}), _context())

    assert first.reason == "merge_needs_a_previous_scene"
    assert removed_previous.reason == "merge_scene_excluded"
    assert fine.status == "candidate_only"


def test_yujin_merges_a_scene_into_the_one_before_it_from_the_real_chat(tmp_path: Path) -> None:
    provider = ScriptedEditingProvider(operations=[{"intent": "merge_with_previous", "segment_id": "seg-close"}])
    app, client, project_id, session = plain_session_project(tmp_path, provider)

    response = create_and_apply(client, project_id, session, "3번 장면을 앞 장면이랑 붙여줘")

    assert response.status_code == 200, response.text
    after = current_session(client, project_id, session["session_id"])
    assert [item["segment_id"] for item in after["segments"]] == ["seg-hook", "seg-middle"]
    assert after["segments"][1]["end_sec"] == pytest.approx(24.0)
    assert after["undo_count"] == 1


def test_the_prompt_tells_yujin_that_merge_names_the_later_scene() -> None:
    prompt = _editing_prompt(instruction="2번이랑 3번 붙여줘", context=_context())
    assert "merge_with_previous" in prompt
    assert "**뒤쪽**" in prompt
```

- [ ] **Step 2: 실패를 본다**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_basics.py::test_merging_needs_a_previous_scene_that_is_not_removed`
Expected: FAIL — `AssertionError: assert 'invalid_editing_response' == 'merge_needs_a_previous_scene'`(모르는 intent라 도메인 모델 검증에서 막힘)

- [ ] **Step 3: 의도 모델** — `SplitSegmentOperation` 클래스 다음에:

```python
class MergeWithPreviousOperation(_SegmentOperation):
    """이 장면을 **바로 앞 장면에** 붙인다 -- 화면 `앞과 붙이기`(`POST .../segments/merge`)와 같은 함수.

    장면 둘을 받지 않는 이유: 둘을 받으면 모델이 순서를 뒤집어 보낼 수 있고, 엔진은
    인접한 왼쪽·오른쪽만 받는다. '2번이랑 3번 붙여줘'는 뒤쪽(3번)을 가리킨다. 혼자여야 한다.
    """

    intent: Literal["merge_with_previous"]
```

유니언: `    | SplitSegmentOperation` 다음 줄에 `    | MergeWithPreviousOperation`. `__all__`: `"MergeWithPreviousOperation",`를 `"ApplyMediaOperation",` 다음에.

- [ ] **Step 4: 검증기** — adapter

도메인 import에 `MergeWithPreviousOperation,`(`ApplyMediaOperation,` 다음). 상수 `MUST_BE_ALONE_INTENTS`를:

```python
MUST_BE_ALONE_INTENTS: frozenset[str] = frozenset({"split_segment", "merge_with_previous"}) | STANDALONE_INTENTS
```

Task 2에서 넣은 `if isinstance(operation, SplitSegmentOperation):` 갈래 **다음**에:

```python
        if isinstance(operation, MergeWithPreviousOperation):
            ordered = list(context.segment_ids)
            position = ordered.index(operation.segment_id)
            if position == 0:
                return "merge_needs_a_previous_scene"
            excluded = set(context.excluded_segment_ids)
            if operation.segment_id in excluded or ordered[position - 1] in excluded:
                return "merge_scene_excluded"
```

(`segment_id`가 지금 장면인지는 앞의 `else` 갈래가 이미 `segment_not_current`로 막았으므로 `index`가 실패하지 않는다.)

- [ ] **Step 5: 적용기** — `editing_session.py` 함수 안 import에 `MergeWithPreviousOperation,`, Task 2의 `SplitSegmentOperation` 갈래 다음에:

```python
        elif isinstance(operation, MergeWithPreviousOperation):
            # 화면 `앞과 붙이기`와 같은 함수. 왼쪽은 지금 순서에서 바로 앞 장면이다.
            index = _segment_index(session=working, segment_id=operation.segment_id)
            if index == 0:
                raise ValueError("merge_needs_a_previous_scene")
            working = merge_adjacent_segments(
                session=working,
                left_segment_id=str(working["segments"][index - 1]["segment_id"]),
                right_segment_id=operation.segment_id,
            )
```

- [ ] **Step 6: 스키마·안내문**

스키마 — Task 2의 `split_segment` 줄 다음에:

```python
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "merge_with_previous"}, "segment_id": {"type": "string"}}, "required": ["intent", "segment_id"]},
```

허용 intent 문장 — Task 2의 `split_segment(...)` 줄 다음 줄에:

```python
        "merge_with_previous(장면을 바로 앞 장면에 붙인다 -- \"2번이랑 3번 붙여줘\"가 이것이다), "
```

`_split_merge_catalogue`의 반환 문자열에서

```python
        "나누기는 **한 번에 하나만, 다른 편집과 섞지 않고** 싣는다. "
```

를 다음 세 줄로 바꾼다:

```python
        "장면을 앞 장면과 붙이는 것은 merge_with_previous다 -- '2번이랑 3번 붙여줘'는 **뒤쪽** "
        "장면(3번)의 segment_id를 싣는다. 첫 장면은 앞이 없어 못 붙인다. "
        "나누기·붙이기는 **한 번에 하나만, 다른 편집과 섞지 않고** 싣는다. "
```

- [ ] **Step 7: 화면 한 줄** — `yujinEditingSummary.ts`의 `split_segment` 줄 다음에:

```ts
  if (operation.intent === "merge_with_previous") return "앞 장면과 붙여요.";
```

`yujinEditingSummary.test.ts`의 "나누기를 말한다" 다음에:

```ts
  it("붙이기를 말한다", () => {
    expect(summary({ intent: "merge_with_previous", segment_id: "s2" })).toBe("앞 장면과 붙여요.");
  });
```

- [ ] **Step 8: 통과·넓은 검증**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_basics.py` → `8 passed`
Run: `cd apps/web && npx vitest run src/features/editor/workbench/yujinEditingSummary.test.ts` → passed
Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_proposal_adapter.py tests/test_editor_timeline_mutations.py` → passed

- [ ] **Step 9: 검증 넷·커밋**

배선: `git grep -n "merge_with_previous" -- packages services apps/web/src` → 모델·스키마·안내문·검증기·적용기·화면 한 줄.

```bash
git add packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py packages/core-engine/src/videobox_core_engine/editing_session.py apps/web/src/features/editor/workbench/yujinEditingSummary.ts apps/web/src/features/editor/workbench/yujinEditingSummary.test.ts tests/test_yujin_editing_basics.py
git commit -m "feat(yujin): 말로 앞 장면과 붙이기 -- 화면 앞과 붙이기와 같은 함수

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: B2 — 되돌리기·다시 하기(`undo_last_edit` / `redo_last_edit`) + 단독 실행형 길

되돌리기는 **유진 편집의 유일한 안전장치**(2026-09-01 결정)라 묶음 B에서 가장 중요하다. 되돌리기 자체를 되돌리기 한 칸으로 쌓으면 안 되므로 세션 편집형(A형)에 넣을 수 없다 — 화면 `POST .../undo`·`/redo`(`routers/editing_session.py:520-542`)가 부르는 `orchestrator.undo_editing_session`/`redo_editing_session`(`services/api/src/videobox_api/orchestration.py:904-908`)을 그대로 부른다. 이 Task가 **단독 실행형(B형) 길**을 처음 만든다.

**Files:**
- Modify: `packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py`(`STANDALONE_INTENTS`, 맥락 `undo_depth`/`redo_depth`, 검사)
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py`
- Modify: `services/api/src/videobox_api/routers/director_proposals.py:30`(import), `:479-595`(맥락), `:693-740`(적용 라우트), `:742` 앞(새 함수)
- Modify: `apps/web/src/features/editor/workbench/yujinEditingSummary.ts`, `.test.ts`
- Modify: `tests/test_yujin_editing_basics.py`
- Modify: `packages/storage-abstractions/src/videobox_storage/local_project_store.py`(`def get_director_proposal_lifecycle(` 메서드 **다음**에 새 메서드 — 4183-4185행. `PostgresProjectStore`는 이 클래스를 상속하고 `BEGIN IMMEDIATE`를 `BEGIN`으로 옮겨 주므로(`postgres_compat.py:31-32`) 따로 고치지 않는다)
- Modify: `services/mcp/src/videobox_mcp/tools.py`(`_ask_yujin_once`의 apply `except VideoBoxApiError` 갈래, 165-168행 근처), `tests/test_mcp_server.py`(끝에 시험 하나)

**Interfaces:**
- Consumes: `orchestrator.undo_editing_session(*, project_id, session_id, expected_revision: int) -> dict`(저장된 세션, `session_revision` 포함), 같은 모양의 `redo_editing_session`; `EditingSessionConflict`(`videobox_core_engine.editing_session_and_regeneration:127`); `store.get_director_proposal(project_id, proposal_id) -> DirectorProposal`(`.status`, 만료면 이 호출이 `expired`로 바꾼다, `local_project_store.py:4152-4177`); `VideoBoxApiError(status_code, detail, path)`(`services/mcp/src/videobox_mcp/api_client.py:23-30`)
- Produces: `UndoLastEditOperation(intent: Literal["undo_last_edit"], steps: int = 1, 1..10)`, `RedoLastEditOperation(...)`; `YujinEditingContext.undo_depth: int = 0`, `.redo_depth: int = 0`; 거절 이유 `nothing_to_undo`, `nothing_to_redo`; 라우터 클로저 `_apply_standalone_intent(*, request: Request, project_id: str, session_id: str, proposal_id: str, expected_session_revision: int, operation: object) -> dict`; `LocalProjectStore.claim_director_proposal_for_standalone_apply(self, *, project_id: str, proposal_id: str) -> Literal["claimed", "already_applied", "not_ready"]`; 적용 라우트의 새 409 detail `editing_proposal_already_applied`

- [ ] **Step 1: 실패하는 시험을 더한다** — `tests/test_yujin_editing_basics.py` 끝에:

```python
# --- 되돌리기·다시 하기 -------------------------------------------------------

def test_undo_is_refused_when_there_is_nothing_to_undo_or_too_many_steps() -> None:
    nothing = interpret_yujin_editing_request(_response({"intent": "undo_last_edit"}), _context())
    too_many = interpret_yujin_editing_request(_response({"intent": "undo_last_edit", "steps": 3}), _context(undo_depth=2))
    fine = interpret_yujin_editing_request(_response({"intent": "undo_last_edit", "steps": 2}), _context(undo_depth=2))
    redo_nothing = interpret_yujin_editing_request(_response({"intent": "redo_last_edit"}), _context(undo_depth=2))

    assert nothing.reason == "nothing_to_undo"
    assert too_many.reason == "nothing_to_undo"
    assert fine.status == "candidate_only"
    assert redo_nothing.reason == "nothing_to_redo"


def test_undo_mixed_with_another_edit_is_refused() -> None:
    """Review Focus 1: "방금 거 되돌리고 3번 장면 빼줘"를 반만 적용하지 않는다."""
    mixed = interpret_yujin_editing_request(
        _response({"intent": "undo_last_edit"}, {"intent": "set_cut_action", "segment_id": "seg-close", "action": "exclude"}),
        _context(undo_depth=1),
    )
    assert mixed.reason == "operation_must_be_alone"


def test_yujin_undoes_and_redoes_the_last_edit_from_the_real_chat(tmp_path: Path) -> None:
    provider = ScriptedEditingProvider(operations=[{"intent": "set_cut_action", "segment_id": "seg-close", "action": "exclude"}])
    app, client, project_id, session = plain_session_project(tmp_path, provider)
    assert create_and_apply(client, project_id, session, "3번 장면 빼줘").status_code == 200

    provider.operations = [{"intent": "undo_last_edit"}]
    undone = create_and_apply(client, project_id, session, "방금 거 되돌려줘")
    assert undone.status_code == 200, undone.text
    after_undo = current_session(client, project_id, session["session_id"])
    assert after_undo["segments"][-1]["cut_action"] == "keep"
    assert after_undo["redo_count"] == 1

    provider.operations = [{"intent": "redo_last_edit"}]
    redone = create_and_apply(client, project_id, session, "다시 해줘")
    assert redone.status_code == 200, redone.text
    assert current_session(client, project_id, session["session_id"])["segments"][-1]["cut_action"] == "remove"


def test_the_prompt_says_how_many_edits_can_be_undone() -> None:
    prompt = _editing_prompt(instruction="방금 거 되돌려줘", context=_context(undo_depth=2, redo_depth=0))
    assert "undo_last_edit" in prompt
    assert "redo_last_edit" in prompt
    assert "되돌릴 수 있는 편집 2개" in prompt


def test_a_standalone_proposal_runs_only_once_even_if_applied_twice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Global Constraint 20: 판(`session_revision`)을 안 올리는 단독 실행형도 같은 편집안을 두 번 실행하지 않는다.

    진짜 되돌리기는 판을 올려서 두 번째 적용이 원래도 409로 막힌다. 완성본·미리보기 링크·업로드 승인
    요청은 판을 **안 올린다** -- 그 모양을 재현하려고 되돌리기를 "판을 안 올리는 가짜"로 바꿔 끼운다.
    """
    provider = ScriptedEditingProvider(operations=[{"intent": "set_cut_action", "segment_id": "seg-close", "action": "exclude"}])
    app, client, project_id, session = plain_session_project(tmp_path, provider)
    assert create_and_apply(client, project_id, session, "3번 장면 빼줘").status_code == 200
    calls: list[int] = []

    def _undo_without_revision_bump(*, project_id: str, session_id: str, expected_revision: int) -> dict:
        calls.append(expected_revision)
        return app.state.store.get_editing_session(project_id=project_id, session_id=session_id)

    monkeypatch.setattr(app.state.orchestrator, "undo_editing_session", _undo_without_revision_bump)
    provider.operations = [{"intent": "undo_last_edit"}]
    proposal = propose(client, project_id, session["session_id"], "방금 거 되돌려줘")
    assert "proposal_id" in proposal, proposal
    apply_url = (
        f"/api/projects/{project_id}/editing-sessions/{session['session_id']}"
        f"/yujin-editing-proposals/{proposal['proposal_id']}/apply"
    )
    body = {"expected_revision": int(proposal["base_session_revision"])}

    first = client.post(apply_url, json=body)
    second = client.post(apply_url, json=body)

    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    assert second.json()["detail"] == "editing_proposal_already_applied"
    assert len(calls) == 1
```

그리고 파일 맨 위 import 줄 `from yujin_chat_fakes import ScriptedEditingProvider, create_and_apply, current_session, plain_session_project`를 `from yujin_chat_fakes import ScriptedEditingProvider, create_and_apply, current_session, plain_session_project, propose`로 바꾼다.

- [ ] **Step 2: 실패를 본다**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_basics.py::test_undo_is_refused_when_there_is_nothing_to_undo_or_too_many_steps`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'undo_depth'`

- [ ] **Step 3: 의도 모델** — `MergeWithPreviousOperation` 다음에:

```python
class UndoLastEditOperation(_StrictFrozenModel):
    """방금 한 편집을 되돌린다 -- 화면 되돌리기(`POST .../undo`)와 같은 자리.

    세션 편집 한 덩이로 묶지 않는다(되돌리기를 되돌리기 한 칸으로 쌓으면 안 된다).
    `steps`는 몇 번 되돌릴지(되돌리기 칸 상한 `MAX_USER_UNDO_ACTIONS` 10과 같다).
    """

    intent: Literal["undo_last_edit"]
    steps: int = Field(default=1, ge=1, le=10)


class RedoLastEditOperation(_StrictFrozenModel):
    """되돌린 편집을 다시 한다 -- 화면 다시 하기(`POST .../redo`)와 같은 자리."""

    intent: Literal["redo_last_edit"]
    steps: int = Field(default=1, ge=1, le=10)
```

유니언에 `    | UndoLastEditOperation` 과 `    | RedoLastEditOperation`(`MergeWithPreviousOperation` 다음), `__all__`에 `"RedoLastEditOperation",`(`"RemakeShortFormOperation",` 앞), `"UndoLastEditOperation",`(`"UnfoldShortFormOperation",` 앞).

- [ ] **Step 4: 검증기·맥락** — adapter

도메인 import에 `RedoLastEditOperation,`, `UndoLastEditOperation,`. 상수를:

```python
STANDALONE_INTENTS: frozenset[str] = frozenset({"undo_last_edit", "redo_last_edit"})
```

맥락 필드(Task 2의 `excluded_segment_ids` 다음):

```python
    #: 지금 되돌릴 수 있는 편집 수 / 다시 할 수 있는 편집 수. **목록과 지금 값은 한 쌍**이다 --
    #: 이걸 안 주면 "방금 거 되돌려줘"에 되돌릴 게 있는지 모른 채 답한다.
    undo_depth: int = 0
    redo_depth: int = 0
```

검사(Task 3의 `MergeWithPreviousOperation` 갈래 다음):

```python
        if isinstance(operation, UndoLastEditOperation) and operation.steps > context.undo_depth:
            return "nothing_to_undo"
        if isinstance(operation, RedoLastEditOperation) and operation.steps > context.redo_depth:
            return "nothing_to_redo"
```

- [ ] **Step 5: 맥락 조립·단독 실행형 길 (API)**

`director_proposals.py`

(a) import — `from videobox_core_engine.editing_session import apply_yujin_editing_proposal`(30행) 다음 줄에:

```python
from videobox_core_engine.editing_session_and_regeneration import EditingSessionConflict
from videobox_core_engine.yujin_editing_proposal_adapter import STANDALONE_INTENTS
```

(b) 맥락 — Task 2에서 넣은 `excluded_segment_ids=tuple(...)` 블록 다음에:

```python
            undo_depth=len(session.get("undo_stack") or []),
            redo_depth=len(session.get("redo_stack") or []),
```

(c) 적용 라우트 — 기준 글귀

```python
            first_intent = editing.operations[0].intent
```

**다음 줄**에:

```python
            # **단독 실행형(계획서 §0.2 B형)** -- 세션 편집 한 덩이로 묶지 않고, 화면 단추와
            # 같은 orchestrator 함수로 각각 보낸다. "혼자여야 한다"는 생성 단계
            # (`MUST_BE_ALONE_INTENTS`)가 이미 확인했다.
            if len(editing.operations) == 1 and first_intent in STANDALONE_INTENTS:
                return _apply_standalone_intent(
                    request=request, project_id=project_id, session_id=session_id,
                    proposal_id=proposal_id, expected_session_revision=body.expected_revision,
                    operation=editing.operations[0],
                )
```

같은 라우트의 기준 글귀

```python
        except EditingSessionRevisionConflict:
            raise HTTPException(status_code=409, detail="editing_proposal_needs_refresh") from None
```

**다음**에:

```python
        except EditingSessionConflict:
            raise HTTPException(status_code=409, detail="editing_proposal_needs_refresh") from None
```

(d) 새 함수 — `    def _apply_short_form_editing_intent(` **앞**에(같은 들여쓰기, 라우터 빌더 안):

```python
    def _apply_standalone_intent(
        *, request: Request, project_id: str, session_id: str, proposal_id: str,
        expected_session_revision: int, operation: object,
    ) -> dict:
        """단독 실행형 의도를 **화면 단추와 같은 함수**로 민다(계획서 §0.2 B형).

        이 함수가 하는 일은 어느 함수를 부를지 가르는 것뿐이다 -- 화면 라우트 본문을
        여기 복사하지 않는다. 갈래가 늘 때마다 화면 쪽 함수를 먼저 찾아 그것을 부른다.
        """
        intent = str(getattr(operation, "intent", ""))
        if intent in {"undo_last_edit", "redo_last_edit"}:
            step = orchestrator.undo_editing_session if intent == "undo_last_edit" else orchestrator.redo_editing_session
            revision = expected_session_revision
            result: dict = {}
            for _ in range(int(getattr(operation, "steps", 1))):
                result = step(project_id=project_id, session_id=session_id, expected_revision=revision)
                revision = int(result["session_revision"])
            return result
        raise ValueError(f"standalone_intent_not_supported:{intent}")
```

- [ ] **Step 5A: 두 번 적용 시험이 지금은 실패하는 것을 본다(RED)**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_basics.py::test_a_standalone_proposal_runs_only_once_even_if_applied_twice`
Expected: FAIL — `assert second.status_code == 409` 줄에서 `assert 200 == 409`(메시지에 두 번째 응답 본문이 붙는다. 두 번째 적용이 통과하고 가짜 되돌리기가 두 번 불린다). 통과하면 멈추고 보고한다 — 이 시험이 단독 실행형 길을 안 밟고 있다는 뜻이다.

- [ ] **Step 5B: 편집안을 실행 전에 소진하는 저장소 장치 (Global Constraint 20)**

`local_project_store.py` — 기준 글귀

```python
    def get_director_proposal_lifecycle(self, project_id: str, proposal_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(project_id, "SELECT status, reason, changed_at FROM director_proposal_lifecycle_events WHERE proposal_id = ? ORDER BY event_id", (proposal_id,))
        return [dict(row) for row in rows]
```

**다음**에(같은 들여쓰기):

```python
    def claim_director_proposal_for_standalone_apply(self, *, project_id: str, proposal_id: str) -> str:
        """단독 실행형 유진 편집안을 **실행 전에** 소진한다 -- 한 편집안은 한 번만 실행된다.

        세션 편집형은 적용이 세션 판을 올려 두 번째 적용이 409로 막히지만, 완성본·미리보기 링크·
        업로드 승인 요청 같은 단독 실행형은 판을 안 올린다. 그래서 `ready -> applied`를 조건부
        UPDATE 한 줄로 바꾸고(같은 편집안을 두 요청이 동시에 밀어도 하나만 1행을 바꾼다), 이긴
        쪽만 실행한다. 숏폼 변형본 적용(`apply_director_variant_proposal_transaction`)과 같은 규칙이다.

        반환: ``"claimed"``(이번 호출이 소진함 -- 실행해도 된다), ``"already_applied"``(먼저 소진됨 --
        실행하지 않는다), ``"not_ready"``(없음·만료·낡음 -- 아무것도 안 걸렸다, 새 편집안이 필요하다).
        실행이 나중에 실패해도 되살리지 않는다 -- 창작자가 다시 말하면 새 편집안이 생긴다.
        """
        try:
            # 만료 판정은 기존 자리에 맡긴다 -- 만료면 이 호출이 status를 expired로 바꾼다.
            proposal = self.get_director_proposal(project_id, proposal_id)
        except KeyError:
            return "not_ready"
        if proposal.status == "applied":
            return "already_applied"
        changed_at = self._now_iso()
        connection = self._connection(project_id)
        try:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute(
                "UPDATE director_proposals SET status = ?, updated_at = ? WHERE proposal_id = ? AND status = 'ready'",
                ("applied", changed_at, proposal_id),
            ).rowcount
            if changed == 1:
                connection.execute(
                    "INSERT INTO director_proposal_lifecycle_events (proposal_id, status, reason, changed_at) VALUES (?, ?, ?, ?)",
                    (proposal_id, "applied", "standalone_apply", changed_at),
                )
                connection.commit()
                return "claimed"
            row = connection.execute("SELECT status FROM director_proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
            connection.rollback()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()
        return "already_applied" if row is not None and str(row["status"]) == "applied" else "not_ready"
```

(SQL·잠금·lifecycle 기록 모양은 같은 파일의 만료 처리(`get_director_proposal`, 4159-4173행)를 그대로 따른다 — 그 모양이 Postgres 저장소에서도 이미 돈다.)

`director_proposals.py` — Step 5(c)에서 넣은 기준 글귀

```python
            if len(editing.operations) == 1 and first_intent in STANDALONE_INTENTS:
                return _apply_standalone_intent(
```

를 다음으로 바꾼다:

```python
            if len(editing.operations) == 1 and first_intent in STANDALONE_INTENTS:
                # **실행 전에 소진한다**(Global Constraint 20). 단독 실행형은 세션 판을 안 올려서
                # 위의 판 검사로는 같은 편집안의 두 번째 적용을 못 막는다 -- 링크 둘·승인 요청 둘이 된다.
                claim = store.claim_director_proposal_for_standalone_apply(project_id=project_id, proposal_id=proposal_id)
                if claim == "already_applied":
                    # MCP `ask_yujin`은 이 409를 다시 시도하지 않는다(needs_refresh만 다시 시도).
                    raise HTTPException(status_code=409, detail="editing_proposal_already_applied")
                if claim != "claimed":
                    raise HTTPException(status_code=409, detail="editing_proposal_needs_refresh")
                return _apply_standalone_intent(
```

(뒤의 인자 줄들과 닫는 괄호는 그대로 둔다.)

- [ ] **Step 5C: 통과를 본다**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_basics.py::test_a_standalone_proposal_runs_only_once_even_if_applied_twice`
Expected: PASS

- [ ] **Step 5D: MCP가 "이미 실행됨"을 다시 시도하지 않게 (RED → GREEN)**

`tests/test_mcp_server.py` 끝에(같은 파일의 `test_ask_yujin_retries_after_409_apply_failure`와 같은 모양):

```python
def test_ask_yujin_does_not_retry_when_the_proposal_was_already_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """409라도 `editing_proposal_needs_refresh`(판이 바뀌어 거절 -- 아무것도 안 걸림)만 안전하다.

    `editing_proposal_already_applied`나 단독 실행형의 다른 409(`final_render_not_current` 등)
    뒤에 세션을 다시 읽고 새 편집안을 만들어 적용하면, 완성본·미리보기 링크·업로드 승인 요청이
    한 번 더 걸린다(2026-10-02 계획 B~F, Global Constraint 20).
    """
    from videobox_mcp import tools

    client = _client_and_app_for(tmp_path)

    session_calls = {"n": 0}
    proposal_calls = {"n": 0}
    apply_calls = {"n": 0}

    async def fake_get_session(self: VideoBoxApiClient, *, project_id: str) -> dict[str, Any]:
        session_calls["n"] += 1
        return {"session_id": "s1", "project_id": project_id}

    async def fake_create_proposal(
        self: VideoBoxApiClient, *, project_id: str, session_id: str, instruction: str
    ) -> dict[str, Any]:
        proposal_calls["n"] += 1
        return {"status": "ready", "proposal_id": "p1", "base_session_revision": 1}

    async def fake_apply_already_applied(
        self: VideoBoxApiClient,
        *,
        project_id: str,
        session_id: str,
        proposal_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        apply_calls["n"] += 1
        raise VideoBoxApiError(
            status_code=409, detail="editing_proposal_already_applied", path="/fake"
        )

    monkeypatch.setattr(VideoBoxApiClient, "get_latest_editing_session", fake_get_session)
    monkeypatch.setattr(VideoBoxApiClient, "create_yujin_editing_proposal", fake_create_proposal)
    monkeypatch.setattr(VideoBoxApiClient, "apply_yujin_editing_proposal", fake_apply_already_applied)

    logged: list[dict[str, Any]] = []
    monkeypatch.setattr(
        tools, "log_ask_yujin_escalation", lambda **kwargs: logged.append(kwargs)
    )

    import asyncio

    async def run() -> None:
        await tools.ask_yujin(client, project_id="does-not-matter", message="완성본 만들어줘")

    with pytest.raises(VideoBoxApiError) as excinfo:
        asyncio.run(run())

    assert excinfo.value.status_code == 409
    assert session_calls["n"] == 1
    assert proposal_calls["n"] == 1
    assert apply_calls["n"] == 1
    assert len(logged) == 1
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_mcp_server.py::test_ask_yujin_does_not_retry_when_the_proposal_was_already_applied`
Expected: FAIL — `assert 2 == 1`(지금은 모든 409를 다시 시도해 세션·편집안·적용이 두 번씩 불린다)

`services/mcp/src/videobox_mcp/tools.py` `_ask_yujin_once`의 기준 글귀

```python
    except VideoBoxApiError as exc:
        if exc.status_code != 409:
            raise _UnsafeToRetryError(exc) from exc
        raise
```

를 다음으로 바꾼다:

```python
    except VideoBoxApiError as exc:
        # **409라도 다 안전한 것은 아니다**(2026-10-02). `editing_proposal_needs_refresh`만
        # "판이 바뀌어 거절됐다 -- 아무것도 안 걸렸다"는 뜻이다. `editing_proposal_already_applied`나
        # 단독 실행형의 다른 409 뒤에 새 편집안을 만들어 다시 적용하면 완성본·링크가 두 번 걸린다.
        if exc.status_code != 409 or exc.detail != "editing_proposal_needs_refresh":
            raise _UnsafeToRetryError(exc) from exc
        raise
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_mcp_server.py`
Expected: 전부 통과(기존 `test_ask_yujin_retries_after_409_apply_failure`는 detail이 `editing_proposal_needs_refresh`라 여전히 한 번 다시 시도한다). 이 파일은 단독으로는 수집된다(15개 이상) — 전체 pytest에서만 `--ignore`한다.

- [ ] **Step 6: 스키마·안내문**

스키마(Task 3 줄 다음):

```python
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "undo_last_edit"}, "steps": {"type": "integer", "minimum": 1, "maximum": 10}}, "required": ["intent"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "redo_last_edit"}, "steps": {"type": "integer", "minimum": 1, "maximum": 10}}, "required": ["intent"]},
```

허용 intent 문장(Task 3 줄 다음):

```python
        "undo_last_edit(방금 한 편집을 되돌린다 -- \"방금 거 취소해줘\"가 이것이다), redo_last_edit(되돌린 것을 다시 한다), "
```

새 함수(`_split_merge_catalogue` 다음):

```python
def _undo_redo_catalogue(context: YujinEditingContext) -> str:
    """되돌리기(묶음 B2). **지금 몇 개 되돌릴 수 있는지**를 같이 준다 -- 목록과 지금 값은 한 쌍."""
    return (
        f"되돌릴 수 있는 편집 {context.undo_depth}개, 다시 할 수 있는 편집 {context.redo_depth}개. "
        "'방금 거 되돌려줘'·'취소해줘'·'방금 거 원래대로 해줘'는 undo_last_edit(steps=1), "
        "'두 개 되돌려줘'는 steps=2, '다시 해줘'(되돌린 것을 다시)는 redo_last_edit다. "
        "가진 개수보다 많이 되돌릴 수 없다 -- 0개면 되돌릴 것이 없다고 답한다. "
        "되돌리기·다시 하기는 **혼자** 싣는다(다른 편집과 섞지 않는다)."
    )
```

`_editing_prompt` 안 `        f"{_split_merge_catalogue(context)} "` 다음 줄에 `        f"{_undo_redo_catalogue(context)} "`.

- [ ] **Step 7: 화면 한 줄** — `yujinEditingSummary.ts`의 `merge_with_previous` 줄 다음에:

```ts
  if (operation.intent === "undo_last_edit") {
    const steps = typeof operation.steps === "number" ? operation.steps : 1;
    return steps > 1 ? `방금 한 편집 ${steps}개를 되돌려요.` : "방금 한 편집을 되돌려요.";
  }
  if (operation.intent === "redo_last_edit") return "되돌린 편집을 다시 해요.";
```

시험(`yujinEditingSummary.test.ts`):

```ts
  it("되돌리기와 다시 하기를 말한다", () => {
    expect(summary({ intent: "undo_last_edit" })).toBe("방금 한 편집을 되돌려요.");
    expect(summary({ intent: "undo_last_edit", steps: 2 })).toBe("방금 한 편집 2개를 되돌려요.");
    expect(summary({ intent: "redo_last_edit" })).toBe("되돌린 편집을 다시 해요.");
  });
```

- [ ] **Step 8: 통과·넓은 검증**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_basics.py` → `13 passed`
Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_api_media_director.py tests/test_yujin_editing_short_form.py tests/test_yujin_editing_proposal_adapter.py tests/test_postgres_project_store.py tests/test_mcp_server.py` → passed(Postgres 시험이 이 기계에서 건너뛰어지면 `skipped`도 괜찮다 — 그 사실을 보고에 적는다)
Run: `cd apps/web && npx vitest run src/features/editor/workbench/yujinEditingSummary.test.ts` → passed

- [ ] **Step 9: 검증 넷·커밋**

배선: `git grep -n "STANDALONE_INTENTS\|_apply_standalone_intent" -- packages services` → adapter 정의, `MUST_BE_ALONE_INTENTS` 정의, 라우트 import·사용·정의. `git grep -n "claim_director_proposal_for_standalone_apply" -- packages services` → 정의 1(저장소)·사용 1(적용 라우트). `_apply_standalone_intent`를 부르는 자리가 그 사용 바로 아래 **한 곳**뿐인지 센다(`git grep -n "_apply_standalone_intent(" -- services` → 정의 1·호출 1). MCP는 같은 두 라우트를 부르고, 재시도 조건만 좁혔다(Step 5D).

```bash
git add packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py services/api/src/videobox_api/routers/director_proposals.py packages/storage-abstractions/src/videobox_storage/local_project_store.py services/mcp/src/videobox_mcp/tools.py tests/test_mcp_server.py apps/web/src/features/editor/workbench/yujinEditingSummary.ts apps/web/src/features/editor/workbench/yujinEditingSummary.test.ts tests/test_yujin_editing_basics.py
git commit -m "feat(yujin): 말로 되돌리기·다시 하기 + 단독 실행형 적용 길(한 편집안은 한 번만 실행, MCP는 needs_refresh만 재시도)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: B3 — 배속 0.25~4.0 전체 (세 층)

엔진(`MIN/MAX_RIPPLE_PLAYBACK_RATE = 0.25/4.0`, `editing_session.py:37-38`)과 API(`RipplePlaybackRateRequest`, `services/api/src/videobox_api/models.py:1262-1268`)는 이미 넓다. **유진 의도만 좁다**: 도메인 `rate: Literal[1, 1.5, 2]`(`yujin_editing_proposals.py:27`), 스키마 `{"enum": [1, 1.5, 2]}`(`yujin_editing_proposal_service.py:41`). 셋째 층을 넓히고, 끝값으로 끝까지 밟는다.

**Files:**
- Modify: `packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py:25-27`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py:41`(스키마), 안내문
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py`(맥락 `segment_source_durations`, 검사)
- Modify: `services/api/src/videobox_api/routers/director_proposals.py`(맥락)
- Modify: `docs/decisions/2026-10-02-audit-follow-up-decisions.ko.md`(끝에 "바뀐 옛 규칙" 덧붙임 — 주석보다 먼저)
- Modify: `packages/core-engine/src/videobox_core_engine/editing_session.py:35-36`(주석), `tests/test_ripple_speed_range.py:12-14`(머리말)
- Modify: `tests/test_yujin_editing_proposal_adapter.py:116-122`(옛 "3은 거절" 시험)
- Modify: `tests/test_yujin_editing_basics.py`, `apps/web/src/features/editor/workbench/yujinEditingSummary.test.ts`

**Interfaces:**
- Consumes: `MIN_RIPPLE_PLAYBACK_RATE`, `MAX_RIPPLE_PLAYBACK_RATE`, `MIN_SEGMENT_DURATION_SEC`(`editing_session.py`)
- Produces: `SetSceneSpeedOperation.rate: float`(0.25 ≤ rate ≤ 4.0, 유한, strict 모드라 정수 `2`도 받고 문자열은 거절); `YujinEditingContext.segment_source_durations: tuple[tuple[str, float], ...] = ()`; 거절 이유 `scene_speed_makes_scene_too_short`

- [ ] **Step 1: 실패하는 시험을 더한다** — `tests/test_yujin_editing_basics.py` 끝에:

```python
# --- 배속 0.25~4.0 ------------------------------------------------------------

@pytest.mark.parametrize("rate", [0.25, 0.5, 0.75, 1.25, 3, 4.0])
def test_yujin_can_pick_any_speed_the_renderer_can_play(rate: float) -> None:
    result = interpret_yujin_editing_request(
        _response({"intent": "set_scene_speed", "segment_id": "seg-middle", "rate": rate}), _context()
    )
    assert result.status == "candidate_only", result.reason


@pytest.mark.parametrize("rate", [0, 0.2, 4.5, "0.5배"])
def test_speeds_outside_the_range_or_as_words_are_refused(rate: object) -> None:
    """Review Focus 3."""
    result = interpret_yujin_editing_request(
        _response({"intent": "set_scene_speed", "segment_id": "seg-middle", "rate": rate}), _context()
    )
    assert result.reason == "invalid_editing_response"


def test_a_speed_that_would_leave_a_scene_shorter_than_the_minimum_is_refused_early() -> None:
    result = interpret_yujin_editing_request(
        _response({"intent": "set_scene_speed", "segment_id": "seg-hook", "rate": 4.0}),
        _context(segment_source_durations=(("seg-hook", 0.5),)),
    )
    assert result.reason == "scene_speed_makes_scene_too_short"


def test_the_yujin_speed_range_is_the_engine_range() -> None:
    """세 층(엔진·API·의도)이 같은 끝값을 본다 -- 한 층만 좁으면 그 값에서 거절된다."""
    from videobox_core_engine.editing_session import MAX_RIPPLE_PLAYBACK_RATE, MIN_RIPPLE_PLAYBACK_RATE
    from videobox_domain_models.yujin_editing_proposals import SetSceneSpeedOperation

    metadata = SetSceneSpeedOperation.model_fields["rate"].metadata
    lows = [item.ge for item in metadata if getattr(item, "ge", None) is not None]
    highs = [item.le for item in metadata if getattr(item, "le", None) is not None]
    assert lows == [MIN_RIPPLE_PLAYBACK_RATE]
    assert highs == [MAX_RIPPLE_PLAYBACK_RATE]


@pytest.mark.parametrize(("rate", "expected_end"), [(4.0, 3.0 + 17.0 / 4.0), (0.25, 3.0 + 17.0 / 0.25)])
def test_yujin_applies_the_extreme_speeds_from_the_real_chat(tmp_path: Path, rate: float, expected_end: float) -> None:
    provider = ScriptedEditingProvider(operations=[{"intent": "set_scene_speed", "segment_id": "seg-middle", "rate": rate}])
    app, client, project_id, session = plain_session_project(tmp_path, provider)

    response = create_and_apply(client, project_id, session, "2번 장면 속도 바꿔줘")

    assert response.status_code == 200, response.text
    after = current_session(client, project_id, session["session_id"])
    assert after["segments"][1]["end_sec"] == pytest.approx(expected_end)
    # 뒤 장면은 밀리거나 당겨진다(리플).
    assert after["segments"][2]["start_sec"] == pytest.approx(expected_end)


def test_the_prompt_maps_speed_words_to_numbers() -> None:
    prompt = _editing_prompt(instruction="느리게 해줘", context=_context())
    assert "'느리게' 0.5" in prompt
    assert "0.25~4" in prompt
```

- [ ] **Step 2: 실패를 본다**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_basics.py -k "can_pick_any_speed"`
Expected: FAIL — `0.25`·`0.5`·`0.75`·`1.25`·`3`·`4.0`에서 `AssertionError: invalid_editing_response`

- [ ] **Step 3: 의도 모델** — `yujin_editing_proposals.py:25-27`

```python
class SetSceneSpeedOperation(_SegmentOperation):
    intent: Literal["set_scene_speed"]
    rate: Literal[1, 1.5, 2]
```

를 다음으로 바꾼다:

```python
class SetSceneSpeedOperation(_SegmentOperation):
    """배속. 범위는 렌더가 실제로 낼 수 있는 것(`editing_session.MIN/MAX_RIPPLE_PLAYBACK_RATE`,
    `_atempo_chain`의 0.25~4)과 **같다**. 2026-10-02 owner 결정("전부 연다")으로 1·1.5·2에서
    넓혔다 -- 화면 `속도` 칸이 받는 값을 유진도 받는다. 끝값은 시험이 엔진 상수와 맞댄다.
    """

    intent: Literal["set_scene_speed"]
    rate: float = Field(ge=0.25, le=4.0, allow_inf_nan=False)
```

- [ ] **Step 4: 스키마** — `yujin_editing_proposal_service.py:41`의 `"rate": {"enum": [1, 1.5, 2]}`를 `"rate": {"type": "number", "minimum": 0.25, "maximum": 4}`로 바꾼다.

- [ ] **Step 5: 맥락·검증**

adapter 도메인 import에 `SetSceneSpeedOperation,`. 맥락 필드(Task 4의 `redo_depth` 다음):

```python
    #: 장면별 **배속을 걸기 전 길이**(지금 길이 x 지금 배속). 배속을 바꿨을 때 장면이
    #: `MIN_SEGMENT_DURATION_SEC`보다 짧아지는지 생성 단계에서 본다. 엔진의 정확한 원본 길이
    #: (`source_slices`)와 미세하게 다를 수 있다 -- 최종 판단은 여전히 엔진이 한다.
    segment_source_durations: tuple[tuple[str, float], ...] = ()
```

검사(Task 4의 `RedoLastEditOperation` 검사 다음):

```python
        if isinstance(operation, SetSceneSpeedOperation):
            source = dict(context.segment_source_durations).get(operation.segment_id)
            if source is not None and source / float(operation.rate) < MIN_SEGMENT_DURATION_SEC:
                return "scene_speed_makes_scene_too_short"
```

`director_proposals.py` 맥락(Task 4의 `redo_depth=...` 다음):

```python
            segment_source_durations=tuple(
                (
                    str(item["segment_id"]),
                    (float(item.get("end_sec") or 0.0) - float(item.get("start_sec") or 0.0))
                    * float(item.get("ripple_playback_rate") or 1.0),
                )
                for item in session.get("segments", [])
                if isinstance(item, dict) and item.get("segment_id")
            ),
```

- [ ] **Step 6: 안내문** — 새 함수(`_undo_redo_catalogue` 다음):

```python
def _speed_words_catalogue() -> str:
    """배속 낱말 -> 숫자(묶음 B3). 창작자는 숫자를 말하지 않는다 -- '느리게'를 몇 배로 옮길지 못박는다."""
    return (
        "배속(set_scene_speed)의 rate는 0.25~4 사이 숫자다. "
        "'아주 느리게' 0.25, '느리게' 0.5, '조금 느리게' 0.75, '원래 속도' 1, '조금 빠르게' 1.25, "
        "'빠르게' 1.5, '두 배' 2, '세 배' 3, '아주 빠르게'·'네 배' 4. 숫자를 말하면 그 숫자를 쓴다. "
        "너무 짧아지는 장면(0.2초 미만)은 못 만든다."
    )
```

`_editing_prompt` 안 `        f"{_undo_redo_catalogue(context)} "` 다음 줄에 `        f"{_speed_words_catalogue()} "`.

- [ ] **Step 7: 바뀐 결정을 결정 문서에 먼저 적고, 주석·옛 시험에 반영한다**

(a) **결정 문서가 먼저다** — 주석만 조용히 고치지 않는다. `docs/decisions/2026-10-02-audit-follow-up-decisions.ko.md` **맨 끝**에 다음을 덧붙인다(앞 내용은 건드리지 않는다):

```markdown

## 덧붙임 — 이 결정이 바꾼 옛 규칙 (2026-10-02, 묶음 B~F 계획 Task 5)

- **유진 배속 범위.** 2026-09-04 `속도`를 캡컷과 같게 넓힐 때(커밋 `beaf88105`) 코드 주석
  (`packages/core-engine/src/videobox_core_engine/editing_session.py`의 `MIN/MAX_RIPPLE_PLAYBACK_RATE` 위,
  `tests/test_ripple_speed_range.py` 머리말)에 "유진 스키마는 안 넓힌다(1·1.5·2만)"는 구현 판단이 적혔다.
  승인 기록에는 없던 규칙이지만 실제로 유진의 배속을 막고 있었다. 이번 "전부 연다"(묶음 B3 "배속
  0.25~4.0 전체")가 이것을 바꾼다 — 유진도 화면과 같은 0.25~4배를 고른다. 너무 짧아지는 장면(0.2초
  미만)은 편집안을 만드는 단계에서 막는다. 끝값 대조는
  `tests/test_yujin_editing_basics.py::test_the_yujin_speed_range_is_the_engine_range`가 지킨다.
```

(b) `editing_session.py:35-36`

```python
# **유진 스키마는 안 넓힌다.** `set_scene_speed`는 `enum: [1, 1.5, 2]`로 좁게
# 둔다 -- 사람이 고르는 것과 AI가 제안하는 것의 범위가 같을 이유가 없다.
```

를

```python
# **유진 스키마도 같은 범위다(2026-10-02 owner 결정 "전부 연다").** 예전에는
# `enum: [1, 1.5, 2]`로 좁혀 두었는데 화면에서 되는 0.5배를 말로 못 했다.
# 바뀐 경위: `docs/decisions/2026-10-02-audit-follow-up-decisions.ko.md` 끝 덧붙임.
```

로 바꾼다. `tests/test_ripple_speed_range.py:12-14`

```python
**유진의 스키마는 그대로 둔다.** `set_scene_speed`는 `enum: [1, 1.5, 2]`로
좁게 유지한다 -- 사람이 고르는 것과 AI가 제안하는 것의 범위가 같을 이유가 없고,
좁은 쪽이 안전하다.
```

를

```python
**유진의 스키마도 같은 범위로 넓혔다(2026-10-02 owner 결정).** 끝값 대조는
`tests/test_yujin_editing_basics.py::test_the_yujin_speed_range_is_the_engine_range`가 한다.
바뀐 경위는 `docs/decisions/2026-10-02-audit-follow-up-decisions.ko.md` 끝 덧붙임.
```

로 바꾼다. `tests/test_yujin_editing_proposal_adapter.py`의 `test_unknown_operation_and_unsupported_speed_are_rejected` 안 `rate=3`을 `rate=5`로 바꾼다(3은 이제 허용값이다).

`yujinEditingSummary.test.ts`에:

```ts
  it("느린 배속도 숫자 그대로 말한다", () => {
    expect(summary({ intent: "set_scene_speed", segment_id: "s1", rate: 0.5 })).toBe("0.5배로 속도를 바꿔요.");
  });
```

(`yujinEditingSummary.ts:45`는 이미 `${operation.rate}배`로 쓰므로 코드 변경은 없다.)

- [ ] **Step 8: 통과·넓은 검증**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_basics.py tests/test_ripple_speed_range.py tests/test_yujin_editing_proposal_adapter.py tests/test_shortform_ripple_speed.py tests/test_yujin_editing_command_evaluation.py`
Expected: 전부 통과.
Run: `cd apps/web && npx vitest run src/features/editor/workbench/yujinEditingSummary.test.ts` → passed

- [ ] **Step 9: 검증 넷·커밋**

배선: `git grep -n "enum\": \[1, 1.5, 2\]\|Literal\[1, 1.5, 2\]" -- packages services` → **0건**이어야 한다.

```bash
git add docs/decisions/2026-10-02-audit-follow-up-decisions.ko.md packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py services/api/src/videobox_api/routers/director_proposals.py packages/core-engine/src/videobox_core_engine/editing_session.py tests/test_ripple_speed_range.py tests/test_yujin_editing_proposal_adapter.py tests/test_yujin_editing_basics.py apps/web/src/features/editor/workbench/yujinEditingSummary.test.ts
git commit -m "feat(yujin): 배속 0.25~4 전체를 말로 -- 엔진·API·의도 세 층 같은 끝값

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: B4 — 트랙 숨기기·소리 끄기(`set_track_state`) + 세션 맨 위 값 옮기기

화면 `PATCH .../track-states`(`routers/editing_session.py:440-460`)는 `normalize_track_states` → `set_track_states`(`editing_session.py:974-992`)를 부른다. 유진도 같은 두 함수를 쓰는 A형이다. **함정**: `apply_yujin_editing_proposal`의 `mutate`(`editing_session.py:1378-1380`)는 `segments`만 옮긴다 — `track_states`는 세션 맨 위 열쇠라 그대로 두면 **조용히 버려진다.** `mutate`가 그 열쇠도 옮기게 한다(지움 포함). 되돌리기 스냅샷은 이미 `track_states`를 담는다(`packages/core-engine/src/videobox_core_engine/editing_transactions.py:25-37`).

`EditingSessionResponse`(`services/api/src/videobox_api/models.py:1739-1760`)에는 `track_states`가 없으므로, 시험은 저장소(`app.state.store.get_editing_session`)에서 직접 읽는다(저장 화이트리스트에는 `track_states`가 있다, `local_project_store.py:9175`).

**Files:**
- Modify: `packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py`
- Modify: `packages/core-engine/src/videobox_core_engine/editing_session.py:1142-1348`(적용기), `:1365-1385`(`mutate`)
- Modify: `services/api/src/videobox_api/routers/director_proposals.py`(import·맥락)
- Modify: `apps/web/src/features/editor/workbench/yujinEditingSummary.ts`, `.test.ts`
- Modify: `tests/test_yujin_editing_basics.py`

**Interfaces:**
- Consumes: `track_states.HIDEABLE_TRACKS = {"broll","overlay","caption"}`, `MUTABLE_TRACKS = {"narration","broll","bgm","sfx"}`, `normalize_track_states(value) -> dict[str, dict[str, bool]]`(`packages/core-engine/src/videobox_core_engine/track_states.py:27-73`, False 깃발은 지운다), `set_track_states(*, session, states) -> dict`(빈 dict면 열쇠를 지운다)
- Produces: `SetTrackStateOperation(intent: Literal["set_track_state"], track: Literal["narration","broll","bgm","sfx","overlay","caption"], hidden: bool|None, muted: bool|None)` — 하나 이상 필수; `YujinEditingContext.track_states: tuple[tuple[str, str], ...] = ()`; `editing_session._YUJIN_SESSION_LEVEL_KEYS: tuple[str, ...]`; 거절 이유 `track_state_hidden_unsupported`, `track_state_muted_unsupported`

- [ ] **Step 0: 지금 버려지고 있는 것을 먼저 재현한다(기존 결함 RED)**

`mutate`가 세션 맨 위 값을 버리는 것은 새 의도가 생기기 **전부터** 있는 결함이다 — 이미 열려 있는 `set_caption_font`가 `update_caption_style(..., scope="whole_project")`로 맨 위 `caption_style`을 바꾸는데(`editing_session.py:1190-1205`), `apply_yujin_editing_proposal`의 `mutate`(1378-1380행)는 `segments`만 옮긴다. 기존 시험(`tests/test_yujin_caption_font.py`)은 `_apply_yujin_editing_operations`를 직접 불러 이 자리를 한 번도 안 지났다. 그래서 화면 경로로 먼저 재현한다. `tests/test_yujin_editing_basics.py` 끝에:

```python
# --- 세션 맨 위 값(유진 편집이 버리던 것) -------------------------------------

def test_yujin_caption_size_change_survives_on_the_whole_project(tmp_path: Path) -> None:
    """기존 결함(2026-10-02 계획 검토에서 코드로 확인): 유진의 `set_caption_font`가 편집본 전체 자막
    모양(`caption_style`)을 바꾸는데, 적용 한 덩이(`apply_yujin_editing_proposal`의 `mutate`)가
    장면 목록만 옮겨 맨 위 값이 조용히 버려졌다. 장면별 값만 남아 화면 자막 칸과 새 장면이 옛 크기를 본다."""
    provider = ScriptedEditingProvider(operations=[{"intent": "set_caption_font", "size_px": 72}])
    app, client, project_id, session = plain_session_project(tmp_path, provider)

    response = create_and_apply(client, project_id, session, "자막 좀 더 크게 해줘")

    assert response.status_code == 200, response.text
    after = current_session(client, project_id, session["session_id"])
    assert (after.get("caption_style") or {}).get("font_size_px") == 72
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_basics.py::test_yujin_caption_size_change_survives_on_the_whole_project`
Expected: FAIL — `assert None == 72`(맨 위 `caption_style`이 비어 있다). **통과하면 멈추고 보고한다** — 결함이 이미 다른 자리에서 고쳐졌거나 시험이 그 자리를 안 지나는 것이다. 응답이 422면(`No captions selected`) `DEFAULT_SEGMENTS`에 자막 글이 있는지 먼저 본다(있어야 한다).

이 시험은 Step 5의 `mutate` 변경 뒤에 통과한다. 그래서 Step 5의 `_YUJIN_SESSION_LEVEL_KEYS`에 처음부터 `"caption_style"`을 넣는다(Task 14가 넣을 때까지 미루지 않는다 — 지금 열려 있는 기능의 결함이다).

- [ ] **Step 1: 실패하는 시험을 더한다** — `tests/test_yujin_editing_basics.py` 끝에:

```python
# --- 트랙 숨기기·소리 끄기 ----------------------------------------------------

def test_track_state_refuses_combinations_that_mean_nothing() -> None:
    """Review Focus 5: 자막 트랙 음소거·내레이션 숨기기는 눌러도 아무 일이 없는 조합이다."""
    caption_mute = interpret_yujin_editing_request(_response({"intent": "set_track_state", "track": "caption", "muted": True}), _context())
    narration_hide = interpret_yujin_editing_request(_response({"intent": "set_track_state", "track": "narration", "hidden": True}), _context())
    nothing = interpret_yujin_editing_request(_response({"intent": "set_track_state", "track": "bgm"}), _context())
    fine = interpret_yujin_editing_request(_response({"intent": "set_track_state", "track": "bgm", "muted": True}), _context())

    assert caption_mute.reason == "track_state_muted_unsupported"
    assert narration_hide.reason == "track_state_hidden_unsupported"
    assert nothing.reason == "invalid_editing_response"
    assert fine.status == "candidate_only"


def test_muting_one_track_keeps_the_other_track_states_and_undo_brings_them_back(tmp_path: Path) -> None:
    """Review Focus 5: 덮어쓰지 않고 합친다. 세션 맨 위 열쇠가 `mutate`에서 버려지면 이 시험이 잡는다."""
    provider = ScriptedEditingProvider(operations=[{"intent": "set_track_state", "track": "bgm", "muted": True}])
    app, client, project_id, session = plain_session_project(
        tmp_path, provider, extra_session={"track_states": {"broll": {"hidden": True}}},
    )

    response = create_and_apply(client, project_id, session, "배경 음악 트랙 소리 꺼줘")

    assert response.status_code == 200, response.text
    stored = app.state.store.get_editing_session(project_id=project_id, session_id=session["session_id"])
    assert stored["track_states"] == {"bgm": {"muted": True}, "broll": {"hidden": True}}

    provider.operations = [{"intent": "undo_last_edit"}]
    assert create_and_apply(client, project_id, session, "방금 거 되돌려줘").status_code == 200
    stored = app.state.store.get_editing_session(project_id=project_id, session_id=session["session_id"])
    assert stored["track_states"] == {"broll": {"hidden": True}}


def test_turning_the_last_switch_back_removes_the_key(tmp_path: Path) -> None:
    provider = ScriptedEditingProvider(operations=[{"intent": "set_track_state", "track": "caption", "hidden": False}])
    app, client, project_id, session = plain_session_project(
        tmp_path, provider, extra_session={"track_states": {"caption": {"hidden": True}}},
    )

    assert create_and_apply(client, project_id, session, "자막 트랙 다시 보여줘").status_code == 200

    stored = app.state.store.get_editing_session(project_id=project_id, session_id=session["session_id"])
    assert not stored.get("track_states")


def test_the_prompt_says_which_tracks_can_hide_or_mute_and_what_is_on_now() -> None:
    prompt = _editing_prompt(instruction="배경 음악 소리 꺼줘", context=_context(track_states=(("broll", "hidden"),)))
    assert "set_track_state" in prompt
    assert "broll(영상) 숨김" in prompt
```

- [ ] **Step 2: 실패를 본다**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_basics.py::test_track_state_refuses_combinations_that_mean_nothing`
Expected: FAIL — `AssertionError: assert 'invalid_editing_response' == 'track_state_muted_unsupported'`

- [ ] **Step 3: 의도 모델** — `RedoLastEditOperation` 다음에:

```python
class SetTrackStateOperation(_StrictFrozenModel):
    """트랙 통째로 숨기기·소리 끄기 -- 화면 트랙 눈·음소거(`PATCH .../track-states`)와 같은 함수.

    말한 칸만 싣는다(`None`은 그대로 둔다). 트랙마다 뜻이 있는 것만 받는다 -- 표는
    `track_states.py` 머리말에 있고, 대조는 검증기가 한다(원본 표를 베끼지 않는다).
    """

    intent: Literal["set_track_state"]
    track: Literal["narration", "broll", "bgm", "sfx", "overlay", "caption"]
    hidden: bool | None = None
    muted: bool | None = None

    @model_validator(mode="after")
    def asks_for_at_least_one(self) -> "SetTrackStateOperation":
        if self.hidden is None and self.muted is None:
            raise ValueError("track_state_needs_a_change")
        return self
```

유니언 `    | SetTrackStateOperation`(Redo 다음), `__all__`에 `"SetTrackStateOperation",`(`"SetSceneSpeedOperation",` 다음).

- [ ] **Step 4: 검증기·맥락**

adapter — import `from videobox_core_engine.track_states import HIDEABLE_TRACKS, MUTABLE_TRACKS`(Task 2의 `editing_session` import 다음 줄), 도메인 import에 `SetTrackStateOperation,`.

맥락 필드(Task 5의 `segment_source_durations` 다음):

```python
    #: 지금 켜진 트랙 스위치. `("broll", "hidden")`·`("bgm", "muted")` 쌍. 없으면 전부 보임·소리 켬.
    #: 목록과 지금 값은 한 쌍 -- 이게 없으면 "영상 트랙 다시 보여줘"에 숨긴 게 없다고 답한다.
    track_states: tuple[tuple[str, str], ...] = ()
```

검사(Task 5의 배속 검사 다음):

```python
        if isinstance(operation, SetTrackStateOperation):
            if operation.hidden is not None and operation.track not in HIDEABLE_TRACKS:
                return "track_state_hidden_unsupported"
            if operation.muted is not None and operation.track not in MUTABLE_TRACKS:
                return "track_state_muted_unsupported"
```

`director_proposals.py` — import(Task 4의 `STANDALONE_INTENTS` import 다음 줄)에:

```python
from videobox_core_engine.track_states import normalize_track_states
```

맥락(Task 5 블록 다음):

```python
            track_states=tuple(
                (kind, field_name)
                for kind, state in sorted(normalize_track_states(session.get("track_states")).items())
                for field_name, flag in sorted(state.items())
                if flag
            ),
```

- [ ] **Step 5: 적용기와 `mutate`**

`editing_session.py` `_apply_yujin_editing_operations` — import에 `SetTrackStateOperation,`, Task 3의 `MergeWithPreviousOperation` 갈래 다음에:

```python
        elif isinstance(operation, SetTrackStateOperation):
            # 화면 트랙 눈·음소거와 **같은 두 함수**다. 덮어쓰지 않고 합친다 -- 배경 음악만
            # 끄라고 했는데 이미 숨긴 영상 트랙이 되살아나면 안 된다.
            from videobox_core_engine.track_states import normalize_track_states

            current_states = normalize_track_states(working.get("track_states"))
            state = dict(current_states.get(operation.track, {}))
            for field_name in ("hidden", "muted"):
                value = getattr(operation, field_name)
                if value is not None:
                    state[field_name] = value
            working = set_track_states(
                session=working,
                states=normalize_track_states({**current_states, operation.track: state}),
            )
```

`apply_yujin_editing_proposal`의 기준 글귀

```python
    def mutate(draft: dict[str, Any]) -> None:
        projected = _apply_yujin_editing_operations(session=draft, operations=operations)
        draft["segments"] = projected["segments"]
```

를 다음으로 바꾼다:

```python
    def mutate(draft: dict[str, Any]) -> None:
        projected = _apply_yujin_editing_operations(session=draft, operations=operations)
        draft["segments"] = projected["segments"]
        # **장면 목록 밖에 사는 값도 옮긴다.** 안 옮기면 적용기가 바꾼 값이 이 자리에서
        # 조용히 버려진다(트랙 눈·음소거, 2026-10-02). 지운 열쇠는 지운 채로 옮긴다 --
        # `set_track_states`는 전부 기본이면 열쇠를 지운다.
        for key in _YUJIN_SESSION_LEVEL_KEYS:
            if key in projected:
                draft[key] = deepcopy(projected[key])
            else:
                draft.pop(key, None)
```

그리고 `def apply_yujin_editing_proposal(` **앞**에:

```python
#: 유진 편집이 바꿀 수 있는 **세션 맨 위** 열쇠. 되돌리기 스냅샷(`editing_transactions._snapshot`)이
#: 담는 열쇠여야 한다 -- 안 담는 열쇠를 여기 넣으면 되돌리기가 그 값을 못 되돌린다.
#: `caption_style`은 `set_caption_font`(이미 열린 기능)가 바꾸는데 예전 `mutate`가 버리던 값이다.
_YUJIN_SESSION_LEVEL_KEYS: tuple[str, ...] = (SESSION_TRACK_STATES_KEY, "caption_style")
```

(`SESSION_TRACK_STATES_KEY`는 이미 13행에서 import돼 있다. `_snapshot`은 `caption_style`과 `track_states`를 둘 다 담는다 — `editing_transactions.py:25-37`.)

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_basics.py::test_yujin_caption_size_change_survives_on_the_whole_project` → PASS(Step 0의 기존 결함이 닫혔다)

- [ ] **Step 6: 스키마·안내문**

스키마(Task 4 줄 다음):

```python
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "set_track_state"}, "track": {"enum": ["narration", "broll", "bgm", "sfx", "overlay", "caption"]}, "hidden": {"type": "boolean"}, "muted": {"type": "boolean"}}, "required": ["intent", "track"]},
```

허용 intent 문장(Task 4 줄 다음):

```python
        "set_track_state(트랙 통째로 숨기기·소리 끄기 -- \"배경 음악 트랙 소리 꺼줘\", \"자막 트랙 숨겨줘\"가 이것이다), "
```

새 함수(`_speed_words_catalogue` 다음):

```python
_TRACK_LABELS: dict[str, str] = {
    "narration": "내레이션", "broll": "영상", "bgm": "배경 음악", "sfx": "효과음",
    "overlay": "화면 위 요소", "caption": "자막",
}


def _track_state_catalogue(context: YujinEditingContext) -> str:
    """트랙 스위치(묶음 B4). 고를 수 있는 조합과 **지금 켜진 것**을 한 쌍으로 준다."""
    current = ", ".join(
        f"{track}({_TRACK_LABELS.get(track, track)}) {'숨김' if field_name == 'hidden' else '소리 끔'}"
        for track, field_name in context.track_states
    ) or "전부 보임·소리 켬"
    return (
        "트랙을 통째로 숨기거나 소리를 끄는 것은 set_track_state다. "
        "track: narration(내레이션)·broll(영상)·bgm(배경 음악)·sfx(효과음)·overlay(화면 위 요소)·caption(자막). "
        "숨길 수 있는 것(hidden): broll·overlay·caption. 소리를 끌 수 있는 것(muted): narration·broll·bgm·sfx. "
        "다시 보이게·다시 켜려면 false를 싣는다. 말한 칸만 싣는다. "
        f"지금 상태: {current}."
    )
```

`_editing_prompt` 안 `        f"{_speed_words_catalogue()} "` 다음 줄에 `        f"{_track_state_catalogue(context)} "`.

- [ ] **Step 7: 화면 한 줄** — `yujinEditingSummary.ts`

`type YujinEditingOperation = YujinEditingProposal["diff"]["operations"][number];`(27행) 다음에:

```ts
const TRACK_LABELS: Readonly<Record<string, string>> = {
  narration: "내레이션", broll: "영상", bgm: "배경 음악", sfx: "효과음", overlay: "화면 위 요소", caption: "자막",
};

function trackStateSummary(operation: YujinEditingOperation): string {
  const name = typeof operation.track === "string" ? TRACK_LABELS[operation.track] ?? "트랙" : "트랙";
  const parts: string[] = [];
  if (operation.hidden === true) parts.push(`${name} 트랙을 숨겨요`);
  if (operation.hidden === false) parts.push(`${name} 트랙을 다시 보여요`);
  if (operation.muted === true) parts.push(`${name} 트랙 소리를 꺼요`);
  if (operation.muted === false) parts.push(`${name} 트랙 소리를 켜요`);
  return `${parts.join(" · ") || `${name} 트랙을 바꿔요`}.`;
}
```

`redo_last_edit` 줄 다음에:

```ts
  if (operation.intent === "set_track_state") return trackStateSummary(operation);
```

시험:

```ts
  it("트랙 스위치를 사람이 아는 이름으로 말한다", () => {
    expect(summary({ intent: "set_track_state", track: "bgm", muted: true })).toBe("배경 음악 트랙 소리를 꺼요.");
    expect(summary({ intent: "set_track_state", track: "caption", hidden: false })).toBe("자막 트랙을 다시 보여요.");
  });
```

- [ ] **Step 8: 통과·넓은 검증**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_basics.py` → 전부 통과
Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_editor_timeline_mutations.py tests/test_yujin_caption_font.py tests/test_api_media_director.py tests/test_track_states.py` → 통과(`mutate` 변경이 기존 유진 편집을 안 깨는지. `tests/test_track_states.py`가 없으면 `git ls-files tests | grep -i track`으로 찾은 트랙 시험을 대신 돌린다)
Run: `cd apps/web && npx vitest run src/features/editor/workbench/yujinEditingSummary.test.ts` → passed

- [ ] **Step 9: 검증 넷·커밋**

배선: `git grep -n "_YUJIN_SESSION_LEVEL_KEYS" -- packages` → 정의 1·사용 1.

```bash
git add packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py packages/core-engine/src/videobox_core_engine/editing_session.py services/api/src/videobox_api/routers/director_proposals.py apps/web/src/features/editor/workbench/yujinEditingSummary.ts apps/web/src/features/editor/workbench/yujinEditingSummary.test.ts tests/test_yujin_editing_basics.py
git commit -m "feat(yujin): 말로 트랙 숨기기·소리 끄기 + 유진 편집이 세션 맨 위 값(트랙 상태·자막 모양)을 버리지 않게

기존 결함: 유진의 자막 글꼴·크기 변경이 편집본 전체 caption_style에 저장되지 않았다(mutate가 segments만 옮김).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 묶음 B 닫기 — 답장 문장, 새 편집본 실기, 지연, 푸시

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_local_conversation.py:56-58`
- Modify: `tests/test_yujin_local_conversation.py`(끝에 시험)

**Interfaces:**
- Consumes: `YujinLocalConversationService(runtime=...).reply(project_id=..., user_text=...)`, 같은 시험 파일의 `_RecordingRuntime`(`.calls[0]["prompt"]`)
- Produces: 답장 프롬프트가 묶음 B 기능을 "곧바로 실행된다" 목록에 담음
- 추가 Modify(총괄 검토 2026-10-02): `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py` `_editing_prompt`의 첫 문장(약 568행), `tests/test_yujin_editing_proposal_service.py`(끝에 시험 — 파일이 없으면 `grep -rl "_editing_prompt" tests`로 이 함수를 시험하는 파일을 찾아 그 끝에 둔다)

- [ ] **Step 0: 편집 판단 프롬프트의 옛 설명을 바로잡는다** — 첫 문장이 `"이 요청은 저장·실행·적용이 아닌 검토용 후보만 만든다."`이다. 2026-09-01 결정 뒤로 화면은 이 편집안을 **곧바로 적용**한다(CLAUDE.md §2 "후보만 만든다는 옛 설명으로 동작을 설명하지 마라"). 이 문장이 `reply_text`에 "확인 후 적용하세요" 같은 거짓 안내를 부를 수 있다.

먼저 실패하는 시험(그 시험 파일 끝에). `_editing_prompt`의 실제 시그니처를 열어 보고 인자를 맞춘다 — 같은 파일 안에 이미 `_editing_prompt(`를 부르는 시험이 있으면 그 호출을 그대로 본뜬다:

```python
def test_editing_prompt_does_not_describe_proposals_as_review_only() -> None:
    """2026-09-01 결정: 유진에게 말한 편집은 바로 적용된다. 옛 '검토용 후보만' 설명은
    reply_text에 '확인 후 적용' 같은 거짓 안내를 부른다."""
    import inspect
    from videobox_core_engine import yujin_editing_proposal_service as service

    source = inspect.getsource(service._editing_prompt)
    assert "검토용 후보만 만든다" not in source
    assert "화면이 이 편집안을 곧바로 적용한다" in source
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider <그 파일>::test_editing_prompt_does_not_describe_proposals_as_review_only` → FAIL(`assert '검토용 후보만 만든다' not in ...`).

구현 — 옛 줄:
```python
        "너는 VideoBox의 편집안 작성기다. 이 요청은 저장·실행·적용이 아닌 검토용 후보만 만든다. "
```
새 줄:
```python
        "너는 VideoBox의 편집안 작성기다. 화면이 이 편집안을 곧바로 적용한다(창작자는 되돌리기로 취소한다). "
        "reply_text에 '확인 후 적용', '적용 단추를 누르세요' 같은 말을 쓰지 마라. "
```
같은 시험을 다시 돌려 PASS, 이어서 `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_local_conversation.py tests/test_yujin_editing_proposal_service.py`(없는 파일은 빼고) 전부 PASS. 이 변경은 Step 1~의 커밋에 함께 넣는다(`git add`에 두 파일 추가).

- [ ] **Step 1: 실패하는 시험** — `tests/test_yujin_local_conversation.py` 끝에:

```python
def test_reply_prompt_knows_the_editing_basics_run_for_real_and_still_asks_back_on_bare_yes() -> None:
    """묶음 B(2026-10-02): 나누기·붙이기·되돌리기·배속·트랙도 화면이 곧바로 실행한다.

    답장은 적용 **전에** 만들어진다(EditorWorkbenchRoute.sendDirectorMessage). "못 한다"고
    답하면 실제로 일어난 일을 부정하게 된다. 동시에 "그걸로"는 여전히 되물어야 한다.
    """
    runtime = _RecordingRuntime()
    YujinLocalConversationService(runtime=runtime).reply(project_id="proj-1", user_text="방금 거 되돌려줘")

    prompt = runtime.calls[0]["prompt"]
    assert "나누기·붙이기·되돌리기" in prompt
    assert "정확히 무엇을 적용할지 되물어라" in prompt
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_local_conversation.py::test_reply_prompt_knows_the_editing_basics_run_for_real_and_still_asks_back_on_bare_yes`
Expected: FAIL — `AssertionError: assert '나누기·붙이기·되돌리기' in ...`

- [ ] **Step 2: 답장 문장** — `yujin_local_conversation.py`의 기준 글귀

```python
    "창작자가 장면 편집(속도·컷·자막·색감·전환·미디어 배치 등)이나 숏폼 "
```

를

```python
    "창작자가 장면 편집(속도·컷·자막·색감·전환·미디어 배치·나누기·붙이기·되돌리기·트랙 숨기기와 소리 끄기 등)이나 숏폼 "
```

로 바꾼다. 같은 시험 → PASS. `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_local_conversation.py` → 전부 통과.

- [ ] **Step 3: 커밋**

```bash
git add packages/core-engine/src/videobox_core_engine/yujin_local_conversation.py tests/test_yujin_local_conversation.py
git commit -m "fix(yujin): 답장이 묶음 B 편집도 실제로 실행된다고 알게

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: 묶음 B 넓은 검증**

```powershell
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_basics.py tests/test_yujin_chat_fakes.py tests/test_yujin_editing_proposal_adapter.py tests/test_yujin_editing_command_evaluation.py tests/test_yujin_editing_short_form.py tests/test_yujin_local_conversation.py tests/test_editor_timeline_mutations.py tests/test_ripple_speed_range.py tests/test_api_media_director.py
cd apps/web; npx vitest run src/features/editor/workbench; npx tsc --noEmit; cd ../..
```
Expected: 모두 통과(Global Constraint 6의 알려진 실패 하나 제외).

- [ ] **Step 5: 역방향 — 컨테이너 재빌드와 새 편집본 실기·지연**

```powershell
.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild
lms ps
.venv/Scripts/python.exe scripts/measure_yujin_prompt_size.py
.venv/Scripts/python.exe scripts/owner-path/ask_yujin_capabilities.py <project_id> B
.venv/Scripts/python.exe scripts/owner-path/ask_yujin_capabilities.py <project_id> baseline
```
Expected: `8/8 통과`, `3/3 통과`. 실패 줄이 있으면 Global Constraint 15대로 거절 사유를 보고 안내문(겹 3)을 고친 뒤 다시 잰다. 프롬프트 글자 수·두 묶음의 중앙값을 기준선 A·B 옆에 적는다(Task 22가 모은다). 기준선보다 중앙값이 1.5배를 넘으면 **멈추고 owner에게 보고**한다(안내문을 임의로 줄이지 않는다). 보고에는 측정 표와 함께 **Task 23(조건부 — 두 단계 판단)**을 대안으로 적고, owner가 채팅으로 승인하면 다음 묶음으로 가기 전에 Task 23을 실행한다. 1.5배 판정은 **GPU 경합이 없는 측정**(`lms ps`에 모델 하나)끼리만 비교한다 — 경합 중 측정이면 먼저 경합을 기록하고 다시 잰다(35b는 내리지 않는다).

- [ ] **Step 6: 역방향·동작 — 브라우저에서 owner 경로를 밟는다**

http://127.0.0.1:5173 (Ctrl+F5) → 장면이 있는 프로젝트 → 편집기 → 유진 열기. **새 편집본**에서 차례로:
1. "2번 장면 2초에서 나눠줘" → 타임라인 장면 수 +1, 완료 목록에 `2번 장면 · 장면을 둘로 나눠요.`
2. "방금 거 되돌려줘" → 장면 수 원래대로, 완료 목록 `방금 한 편집을 되돌려요.`
3. "2번 장면 느리게 해줘" → 2번 장면 막대가 2배 길어짐
4. "배경 음악 트랙 소리 꺼줘" → 배경 음악 트랙의 음소거 표시가 켜짐
5. "응 그걸로 해줘" → 편집이 일어나지 않고 유진이 되묻는다

동작: 4번 뒤 출력 화면 `완성본 만들기`로 MP4를 만들고, 배경 음악만 깔린 구간의 음량을 잰다:
```powershell
docker exec videobox-api ffmpeg -hide_banner -i <완성본 파일> -af volumedetect -f null - 2>&1 | Select-String "mean_volume|max_volume"
```
수치를 적는다(배경 음악 끄기 전 같은 구간 수치와 비교).

- [ ] **Step 7: 갭·배선 기록과 푸시**

갭: 계획서 묶음 B 표(B1~B4) 대조 — 넷 다 열림. 안 한 것: 장면 여러 개 한 번에 나누기(화면에도 없음), 트랙 잠금(화면 전용 값이라 결과물에 영향 없음).
배선: `git grep -n "split_segment\|merge_with_previous\|undo_last_edit\|redo_last_edit\|set_track_state" -- apps/web/src` → `yujinEditingSummary.ts`에 다섯.
결과를 확인한 **뒤에**(한 명령에 묶지 않는다):
```powershell
git push origin main
```
(정확히 이 명령. 도구 권한이 막으면 **우회하지 말고 멈춘다** — owner에게 `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`에서 `git push origin main`을 직접 실행하거나 허용 규칙 `Bash(git push origin main)`을 추가해 달라고 알리고 기다린다. Global Constraint 18)

---

### Task 8: C0 — 서버가 건 일을 화면이 끝까지 지켜보는 길

묶음 C·E의 일(완성본·캡컷 초안·번역·더빙·받아쓰기·부분 재생성)은 분 단위다. 적용 라우트는 job만 걸고 `{"status": "..._started", "job_id": ..., "notice": ...}`로 바로 돌아오고(프록시 330초 벽), 화면은 **이미 있는 공용 폴링**(`apps/web/src/lib/pollJob.ts`의 `pollJobUntilTerminal`)으로 끝까지 지켜본다. 세 번째 방식을 만들지 않는다. 지켜보는 동안 유진 패널에 `유진이 맡은 일` 상태 줄이 뜬다(대표님 상시 지시 2026-09-12 "기다림에는 표시"). 서버 쪽은 화면과 **같은 규칙**으로 "지금 편집본의 타임라인 작업·마스터 완성본"을 고르는 모듈과, 화면 라우트 본문에 묻혀 있던 워커 시작을 함수로 뽑는다.

이 Task는 아직 새 의도를 열지 않는다(Task 9부터). 대신 기존 `render_short_form` 응답의 `notice`("숏폼을 만들고 있어요. 출력 화면에서 확인해 주세요.")가 지금은 화면에서 버려지는데(`EditorWorkbenchRoute.tsx:2092`가 응답을 안 읽는다), 이 Task 뒤로는 그 말이 저장 상태 줄에 뜬다 — 그것을 RED로 쓴다.

**Files:**
- Create: `services/api/src/videobox_api/session_master_outputs.py`, `tests/test_session_master_outputs.py`
- Modify: `services/api/src/videobox_api/orchestration.py:1771-1802`(워커 시작 함수 둘 추가)
- Modify: `services/api/src/videobox_api/routers/outputs.py:309-336`(완성본), `:535-563`(캡컷 초안) — 새 함수를 부르게
- Create: `apps/web/src/features/editor/workbench/yujinApplyOutcome.ts`, `yujinApplyOutcome.test.ts`, `yujinBackgroundWork.ts`, `yujinBackgroundWork.test.ts`
- Modify: `apps/web/src/api.ts:207-208`(타입), `:2251-2252`(`applyYujinEditingProposal` 반환형)
- Modify: `apps/web/src/features/editor/workbench/rightDockTypes.ts:150-165`, `YujinPanel.tsx:120-140`(prop)·`:476-483`(표시), `YujinPanel.test.tsx`, `EditorWorkbench.tsx:752`, `EditorWorkbenchRoute.tsx:95-108`(상태 타입)·`:238-252`(초기값)·`:2080-2108`(적용)·`:2463`(전달)

**Interfaces:**
- Consumes: `store.list_jobs(*, project_id) -> list[dict]`(열쇠 `job_id, project_id, job_type, status, input_ref, output_ref, started_at, finished_at`), `orchestrator.get_final_render_result(*, project_id, job_id) -> {"job_id","status","render"}`, `store.get_final_render_export(*, project_id, export_id) -> dict`(`is_current, timeline_id, source_session_id, source_session_revision`), `orchestrator.start_final_render_job(...) -> {"job_id","status","should_start"}`, `run_final_render_job`, `release_final_render_worker`, 같은 모양의 캡컷 초안 셋; 웹 `api.getFinalRender(projectId, jobId) -> FinalRenderJob{status, render, error_message}`, `api.getCapcutDraftExport(projectId, jobId) -> CapCutDraftExportJob{status, export, error_message}`
- Produces:
  - Python `current_timeline_job_id(*, store, project_id: str, session: Mapping) -> str | None` — 화면 `selectCurrentTimelineJob`(`apps/web/src/features/review/timeline-review-state.ts:47-60`)과 같은 규칙
  - Python `MasterFinalRenderState(job_id: str, status: str, export_id: str | None, is_current: bool)`, `master_final_render_state(*, store, orchestrator, project_id: str, session: Mapping) -> MasterFinalRenderState | None` — 화면 `selectMasterFinalJob`+`isArtifactCurrent`(`apps/web/src/features/outputs/masterFinalRender.ts:26-39,74-80,114-128`)와 같은 규칙
  - `ApiOrchestrator.launch_final_render_worker_if_needed(*, project_id, timeline_job_id, result: dict) -> None`, `launch_capcut_draft_export_worker_if_needed(...)`(같은 모양) — `result`에서 `should_start`를 꺼내 지운다
  - TS `YujinStartedWorkKind`, `YujinStartedWork`, `YujinApplyOutcome`, `yujinApplyOutcome(result: unknown, origin?: string): YujinApplyOutcome`, `yujinApplyFailureMessage(error: unknown): string | null`
  - TS `followYujinWork(input: { projectId; sessionId; work: YujinStartedWork; isStillRelevant: () => boolean; onProgress?: (label: string) => void; expectedRevision?: () => number | null }): Promise<string>`, `yujinWorkChangesSession(kind): boolean`, `yujinWorkWaitingLabel(work): string`, `YUJIN_WORK_LOST_TRACK: string`
  - TS 화면: `RightDockDirector.backgroundWork?: Readonly<{ label: string }> | null`, `YujinPanel` prop `backgroundWork`

- [ ] **Step 1: 실패하는 백엔드 시험**

`tests/test_session_master_outputs.py`:

```python
"""유진이 고르는 '지금 편집본의 타임라인 작업·마스터 완성본'이 화면과 같은 규칙인지.

화면 규칙의 원본: `timeline-review-state.ts`의 `selectCurrentTimelineJob`,
`masterFinalRender.ts`의 `selectMasterFinalJob`·`isArtifactCurrent`. 둘이 갈라지면
"화면은 이 완성본, 유진은 저 완성본"이 된다(2026-09-11 같은 종류 사고).
"""
from __future__ import annotations

from videobox_api.session_master_outputs import current_timeline_job_id, master_final_render_state

_SESSION = {"session_id": "sess-1", "session_revision": 4, "timeline_id": "timeline-A", "project_id": "p"}


class _Store:
    def __init__(self, jobs: list[dict], exports: dict[str, dict] | None = None) -> None:
        self.jobs = jobs
        self.exports = exports or {}

    def list_jobs(self, *, project_id: str) -> list[dict]:
        return [dict(job, project_id=project_id) for job in self.jobs]

    def get_final_render_export(self, *, project_id: str, export_id: str) -> dict:
        return self.exports[export_id]


class _Orchestrator:
    def __init__(self, results: dict[str, dict]) -> None:
        self.results = results

    def get_final_render_result(self, *, project_id: str, job_id: str) -> dict:
        return self.results[job_id]


def test_timeline_job_is_the_newest_succeeded_build_of_this_sessions_timeline() -> None:
    store = _Store([
        {"job_id": "t-old", "job_type": "timeline_build", "status": "succeeded", "output_ref": "timeline-A", "finished_at": "2026-10-01T00:00:00"},
        {"job_id": "t-new", "job_type": "timeline_build", "status": "succeeded", "output_ref": "timeline-A", "finished_at": "2026-10-02T00:00:00"},
        {"job_id": "t-failed", "job_type": "timeline_build", "status": "failed", "output_ref": "timeline-A", "finished_at": "2026-10-03T00:00:00"},
        {"job_id": "t-other", "job_type": "timeline_build", "status": "succeeded", "output_ref": "timeline-B", "finished_at": "2026-10-04T00:00:00"},
    ])
    assert current_timeline_job_id(store=store, project_id="p", session=_SESSION) == "t-new"
    assert current_timeline_job_id(store=_Store([]), project_id="p", session=_SESSION) is None


def test_master_render_ignores_variant_renders_and_reports_whether_it_is_current() -> None:
    store = _Store(
        jobs=[
            {"job_id": "t-1", "job_type": "timeline_build", "status": "succeeded", "output_ref": "timeline-A", "finished_at": "2026-10-02T00:00:00"},
            {"job_id": "r-master", "job_type": "final_render", "status": "succeeded", "input_ref": "t-1", "finished_at": "2026-10-02T01:00:00"},
            {"job_id": "r-variant", "job_type": "final_render", "status": "succeeded", "input_ref": "t-variant", "finished_at": "2026-10-02T02:00:00"},
        ],
        exports={"e-1": {"is_current": True, "timeline_id": "timeline-A", "source_session_id": "sess-1", "source_session_revision": 4}},
    )
    orchestrator = _Orchestrator({"r-master": {"job_id": "r-master", "status": "succeeded", "render": {"export_id": "e-1"}}})

    state = master_final_render_state(store=store, orchestrator=orchestrator, project_id="p", session=_SESSION)

    assert state is not None
    assert (state.job_id, state.status, state.export_id, state.is_current) == ("r-master", "succeeded", "e-1", True)

    stale = master_final_render_state(store=store, orchestrator=orchestrator, project_id="p", session={**_SESSION, "session_revision": 5})
    assert stale is not None and stale.is_current is False
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_session_master_outputs.py::test_timeline_job_is_the_newest_succeeded_build_of_this_sessions_timeline`
Expected: FAIL — `ModuleNotFoundError: No module named 'videobox_api.session_master_outputs'`

- [ ] **Step 2: 모듈을 만든다** — `services/api/src/videobox_api/session_master_outputs.py`:

```python
"""지금 편집본의 '타임라인 작업'과 '마스터 완성본'을 고르는 단 하나의 서버 규칙.

**화면과 같은 규칙이다.** 원본은 `apps/web/src/features/review/timeline-review-state.ts`의
`selectCurrentTimelineJob`(타임라인 작업)과 `apps/web/src/features/outputs/masterFinalRender.ts`의
`selectMasterFinalJob`·`isArtifactCurrent`(완성본). 유진 채팅이 다른 규칙으로 고르면 "화면은
이 완성본, 유진은 저 완성본"이 된다 -- 2026-09-11에 두 화면 사이에서 이미 겪은 사고다.
한쪽을 고치면 다른 쪽도 같이 고친다.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MasterFinalRenderState:
    job_id: str
    status: str
    export_id: str | None
    is_current: bool


def _timeline_sort_key(job: Mapping[str, Any]) -> tuple[str, str, str]:
    # `compareTimelineJobs`와 같은 세 단: finished_at, started_at, job_id.
    return (str(job.get("finished_at") or ""), str(job.get("started_at") or ""), str(job.get("job_id") or ""))


def current_timeline_job_id(*, store: Any, project_id: str, session: Mapping[str, Any]) -> str | None:
    timeline_id = str(session.get("timeline_id") or "").strip()
    if not timeline_id:
        return None
    candidates = [
        job for job in store.list_jobs(project_id=project_id)
        if str(job.get("project_id") or project_id) == project_id
        and str(job.get("job_type") or "") == "timeline_build"
        and str(job.get("status") or "") == "succeeded"
        and str(job.get("output_ref") or "") == timeline_id
    ]
    if not candidates:
        return None
    return str(max(candidates, key=_timeline_sort_key)["job_id"])


def _latest_master_final_render_job_id(jobs: list[Mapping[str, Any]], timeline_job_id: str) -> str | None:
    # `latestJobOfType(jobs, "final_render", timelineJobId)`: 같은 타임라인 작업을 입력으로 쓴
    # 것만(가로·세로 변형본은 `input_ref`가 달라 빠진다), `finished_at ?? started_at`이 큰 것.
    candidates = [
        job for job in jobs
        if str(job.get("job_type") or "") == "final_render" and str(job.get("input_ref") or "") == timeline_job_id
    ]
    if not candidates:
        return None
    return str(max(candidates, key=lambda job: str(job.get("finished_at") or job.get("started_at") or ""))["job_id"])


def master_final_render_state(
    *, store: Any, orchestrator: Any, project_id: str, session: Mapping[str, Any],
) -> MasterFinalRenderState | None:
    timeline_job_id = current_timeline_job_id(store=store, project_id=project_id, session=session)
    if timeline_job_id is None:
        return None
    job_id = _latest_master_final_render_job_id(store.list_jobs(project_id=project_id), timeline_job_id)
    if job_id is None:
        return None
    result = orchestrator.get_final_render_result(project_id=project_id, job_id=job_id)
    status = str(result.get("status") or "")
    render = result.get("render") or None
    if not render:
        return MasterFinalRenderState(job_id=job_id, status=status, export_id=None, is_current=False)
    export_id = str(render["export_id"])
    export = store.get_final_render_export(project_id=project_id, export_id=export_id)
    # `isArtifactCurrent`와 같은 조건.
    is_current = (
        export.get("is_current") is True
        and str(export.get("timeline_id") or "") == str(session.get("timeline_id") or "")
        and str(export.get("source_session_id") or "") == str(session.get("session_id") or "")
        and int(export.get("source_session_revision") or 0) == int(session.get("session_revision") or 0)
    )
    return MasterFinalRenderState(job_id=job_id, status=status, export_id=export_id, is_current=is_current)
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_session_master_outputs.py` → `2 passed`

- [ ] **Step 3: 워커 시작을 함수로 뽑는다(같은 로직 두 자리 금지)**

`orchestration.py` — `    def launch_pending_variant_render_workers(` **앞**에:

```python
    def launch_final_render_worker_if_needed(self, *, project_id: str, timeline_job_id: str, result: dict[str, Any]) -> None:
        """화면 `완성본 만들기`(`routers/outputs.py`)와 유진 채팅("완성본 만들어 줘")이 함께 쓰는
        단 하나의 워커 시작 자리. `result`는 `start_final_render_job`의 반환값이고, 같은 입력이면
        이미 돌고 있는 job을 돌려주므로(`should_start=False`) 두 번 눌러도 워커는 하나다."""
        if not result.pop("should_start", True):
            return
        worker = threading.Thread(
            target=self.run_final_render_job,
            kwargs={"project_id": project_id, "timeline_job_id": timeline_job_id, "job": {"job_id": result["job_id"]}},
            daemon=True,
        )
        try:
            worker.start()
        except Exception:
            self.release_final_render_worker(project_id=project_id, job_id=str(result["job_id"]))
            raise

    def launch_capcut_draft_export_worker_if_needed(self, *, project_id: str, timeline_job_id: str, result: dict[str, Any]) -> None:
        """캡컷 초안판. 위와 같은 이유로 한 자리에 둔다."""
        if not result.pop("should_start", True):
            return
        worker = threading.Thread(
            target=self.run_capcut_draft_export_job,
            kwargs={"project_id": project_id, "timeline_job_id": timeline_job_id, "job": {"job_id": result["job_id"]}},
            daemon=True,
        )
        try:
            worker.start()
        except Exception:
            self.release_capcut_draft_export_worker(project_id=project_id, job_id=str(result["job_id"]))
            raise
```

`routers/outputs.py` `start_final_render` — 기준 글귀(`        if result.pop("should_start", True):`부터 그 `if` 블록 끝 `                raise`까지, 318-334행)를 다음 한 줄로 바꾼다:

```python
        orchestrator.launch_final_render_worker_if_needed(
            project_id=project_id, timeline_job_id=payload.timeline_job_id, result=result,
        )
```

`start_capcut_draft_export`(535행~)의 같은 모양 블록(`        if result.pop("should_start", True):` ~ `                raise`)을:

```python
        orchestrator.launch_capcut_draft_export_worker_if_needed(
            project_id=project_id, timeline_job_id=payload.timeline_job_id, result=result,
        )
```

로 바꾼다. 두 라우트의 `return StartJobResponse(**result)`는 그대로다(`should_start`는 새 함수가 지웠다).

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_api_final_render_endpoint.py tests/test_api_capcut_draft_export_endpoint.py tests/test_final_render_idempotency.py`
Expected: 전부 통과(동작이 같아야 한다). 하나라도 실패하면 뽑은 함수가 원래 본문과 다른 것이다 — 원래 본문(`git show HEAD:services/api/src/videobox_api/routers/outputs.py`)과 줄 단위로 맞댄다.

- [ ] **Step 4: 실패하는 웹 시험 둘**

`apps/web/src/features/editor/workbench/yujinApplyOutcome.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { yujinApplyOutcome } from "./yujinApplyOutcome";

describe("유진 편집안 적용 결과 가르기", () => {
  it("편집본이 오면 편집본이다", () => {
    expect(yujinApplyOutcome({ session_id: "s", session_revision: 4, segments: [] })).toEqual({ kind: "session" });
  });

  it("말할 것이 있으면 그 말을 꺼낸다 -- 숏폼 렌더 시작이 지금까지 버려지던 말", () => {
    expect(yujinApplyOutcome({ status: "short_form_render_started", job_id: "j", notice: "숏폼을 만들고 있어요. 출력 화면에서 확인해 주세요." }))
      .toEqual({ kind: "notice", notice: "숏폼을 만들고 있어요. 출력 화면에서 확인해 주세요." });
  });

  it("서버가 건 일은 지켜볼 일로 꺼낸다", () => {
    expect(yujinApplyOutcome({ status: "final_render_started", job_id: "r1", notice: "완성본을 만들고 있어요." })).toEqual({
      kind: "work",
      work: { kind: "final_render", jobId: "r1", notice: "완성본을 만들고 있어요.", totalSceneCount: 0, language: null },
    });
  });

  it("미리보기 링크는 이 화면 주소를 앞에 붙여 그대로 보여 준다", () => {
    expect(yujinApplyOutcome({ status: "preview_share_created", url: "/preview/abc", notice: "미리보기 링크를 만들었어요." }, "http://127.0.0.1:5173"))
      .toEqual({ kind: "notice", notice: "미리보기 링크를 만들었어요. http://127.0.0.1:5173/preview/abc" });
  });

  it("모르는 상태 이름을 지켜볼 일로 오해하지 않는다", () => {
    expect(yujinApplyOutcome({ status: "toString", job_id: "x" })).toEqual({ kind: "session" });
  });
});
```

`apps/web/src/features/editor/workbench/yujinBackgroundWork.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../../api";
import { followYujinWork, yujinWorkChangesSession } from "./yujinBackgroundWork";

beforeEach(() => { vi.useFakeTimers({ shouldAdvanceTime: true }); });
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

describe("유진이 맡은 일 지켜보기", () => {
  it("완성본이 다 될 때까지 묻고, 다 되면 창작자 말로 알린다", { timeout: 20000 }, async () => {
    vi.spyOn(api, "getFinalRender")
      .mockResolvedValueOnce({ job_id: "r1", status: "running", render: null } as never)
      .mockResolvedValueOnce({ job_id: "r1", status: "succeeded", render: { export_id: "e1" } } as never);

    const message = await followYujinWork({
      projectId: "p", sessionId: "s",
      work: { kind: "final_render", jobId: "r1", notice: "", totalSceneCount: 0, language: null },
      isStillRelevant: () => true,
    });

    expect(message).toBe("완성본을 만들었어요. 출력 화면에서 볼 수 있어요.");
  });

  it("실패하면 다음에 할 일을 말한다", { timeout: 20000 }, async () => {
    vi.spyOn(api, "getCapcutDraftExport").mockResolvedValueOnce({ job_id: "c1", status: "failed", export: null, error_message: "x" } as never);

    const message = await followYujinWork({
      projectId: "p", sessionId: "s",
      work: { kind: "capcut_draft", jobId: "c1", notice: "", totalSceneCount: 0, language: null },
      isStillRelevant: () => true,
    });

    expect(message).toBe("캡컷 초안을 만들지 못했어요. 출력 화면에서 다시 눌러 주세요.");
  });

  it("편집본을 바꾸는 일만 편집을 잠근다", () => {
    expect(yujinWorkChangesSession("final_render")).toBe(false);
    expect(yujinWorkChangesSession("capcut_draft")).toBe(false);
    expect(yujinWorkChangesSession("dubbing")).toBe(true);
  });
});
```

Run: `cd apps/web && npx vitest run src/features/editor/workbench/yujinApplyOutcome.test.ts`
Expected: FAIL — `Failed to resolve import "./yujinApplyOutcome"`

- [ ] **Step 5: 가르기 모듈** — `apps/web/src/features/editor/workbench/yujinApplyOutcome.ts`:

```ts
/**
 * 유진 편집안을 적용한 서버 답이 무엇인지 가른다.
 *
 * 세션 편집형은 편집본을 돌려주고, 단독 실행형은 `{status, notice, job_id?}`를 돌려준다
 * (계획서 §0.2). 예전에는 이 답을 아무도 안 읽어서 "숏폼을 만들고 있어요" 같은 말이
 * 화면에 한 번도 안 나왔다.
 */
export type YujinStartedWorkKind =
  | "final_render"
  | "capcut_draft"
  | "caption_translation"
  | "dubbing"
  | "transcription"
  | "partial_regeneration";

export type YujinStartedWork = Readonly<{
  kind: YujinStartedWorkKind;
  jobId: string;
  notice: string;
  totalSceneCount: number;
  language: string | null;
}>;

export type YujinApplyOutcome =
  | Readonly<{ kind: "session" }>
  | Readonly<{ kind: "notice"; notice: string }>
  | Readonly<{ kind: "work"; work: YujinStartedWork }>;

/** `Map`인 이유: 일반 객체로 두면 `"toString"` 같은 상태 이름이 내장 함수를 집는다. */
const STARTED_WORK = new Map<string, YujinStartedWorkKind>([
  ["final_render_started", "final_render"],
  ["capcut_draft_export_started", "capcut_draft"],
  ["caption_translation_started", "caption_translation"],
  ["dubbing_started", "dubbing"],
  ["transcription_started", "transcription"],
  ["partial_regeneration_started", "partial_regeneration"],
]);

export function yujinApplyOutcome(result: unknown, origin = ""): YujinApplyOutcome {
  if (!result || typeof result !== "object") return { kind: "session" };
  const record = result as Record<string, unknown>;
  const status = typeof record.status === "string" ? record.status : "";
  const notice = typeof record.notice === "string" ? record.notice.trim() : "";
  const workKind = STARTED_WORK.get(status);
  if (workKind && typeof record.job_id === "string" && record.job_id) {
    return {
      kind: "work",
      work: {
        kind: workKind,
        jobId: record.job_id,
        notice,
        totalSceneCount: typeof record.total_scene_count === "number" ? record.total_scene_count : 0,
        language: typeof record.language === "string" ? record.language : null,
      },
    };
  }
  if (status === "preview_share_created" && typeof record.url === "string") {
    return { kind: "notice", notice: `${notice || "미리보기 링크를 만들었어요."} ${origin}${record.url}`.trim() };
  }
  if (notice) return { kind: "notice", notice };
  return { kind: "session" };
}
```

- [ ] **Step 6: 지켜보기 모듈** — `apps/web/src/features/editor/workbench/yujinBackgroundWork.ts`:

```ts
import { api } from "../../../api";
import { pollJobUntilTerminal, type JobStatusPayload, type PollOutcome } from "../../../lib/pollJob";
import type { YujinStartedWork, YujinStartedWorkKind } from "./yujinApplyOutcome";

/**
 * 유진에게 맡긴 일을 끝까지 지켜본다. **새 폴링 방식을 만들지 않는다** -- 더빙·자막 번역·
 * 받아쓰기·부분 재생성이 쓰는 공용 루프(`pollJobUntilTerminal`)를 그대로 쓴다.
 *
 * 완성본·캡컷 초안의 상한: 실측 렌더는 분 단위이고 긴 영상은 더 걸린다. 3초 간격으로
 * 800번(40분)까지 묻는다. 그보다 길면 기다리기를 멈추고 출력 화면을 가리킨다.
 */
const OUTPUT_POLL_INTERVAL_MS = 3000;
const OUTPUT_MAX_POLL_ATTEMPTS = 800;

export const YUJIN_WORK_LOST_TRACK = "맡긴 일을 끝까지 지켜보지 못했어요. 출력 화면이나 편집본에서 확인해 주세요.";

const WAITING_LABELS: Readonly<Record<YujinStartedWorkKind, string>> = {
  final_render: "완성본을 만들고 있어요.",
  capcut_draft: "캡컷 초안을 만들고 있어요.",
  caption_translation: "자막을 번역하고 있어요.",
  dubbing: "목소리를 만들고 있어요.",
  transcription: "말을 받아쓰고 있어요.",
  partial_regeneration: "고른 장면을 다시 만들고 있어요.",
};

/** 편집본을 바꾸는 일. 이 일이 도는 동안에는 화면의 다른 편집을 잠근다 -- 화면의 더빙
 *  (`EditorWorkbenchRoute.dubNarration`)과 같은 규칙이다. 안 잠그면 끝에 저장할 때 충돌로 버려진다. */
export function yujinWorkChangesSession(kind: YujinStartedWorkKind): boolean {
  return kind === "caption_translation" || kind === "dubbing" || kind === "partial_regeneration";
}

export function yujinWorkWaitingLabel(work: YujinStartedWork): string {
  return work.notice || WAITING_LABELS[work.kind];
}

function asPollStatus<T>(status: string, value: T, errorDetail: string | null | undefined): JobStatusPayload<T> {
  if (status === "succeeded") return { status: "succeeded", result: value, error_detail: null };
  if (status === "failed") return { status: "failed", result: null, error_detail: errorDetail ?? null };
  return { status: "processing", result: null, error_detail: null };
}

function outcomeLine(outcome: PollOutcome<unknown>, lines: { succeeded: string; failed: string; timedOut: string }): string {
  if (outcome.kind === "succeeded") return lines.succeeded;
  if (outcome.kind === "timed_out") return lines.timedOut;
  if (outcome.kind === "cancelled") return "기다리기를 멈췄어요.";
  return lines.failed;
}

export async function followYujinWork(input: {
  projectId: string;
  sessionId: string;
  work: YujinStartedWork;
  isStillRelevant: () => boolean;
  onProgress?: (label: string) => void;
  expectedRevision?: () => number | null;
}): Promise<string> {
  const { projectId, work } = input;
  const options = {
    intervalMs: OUTPUT_POLL_INTERVAL_MS,
    maxAttempts: OUTPUT_MAX_POLL_ATTEMPTS,
    delayFirst: true,
    isStillRelevant: input.isStillRelevant,
  };
  if (work.kind === "final_render") {
    const outcome = await pollJobUntilTerminal(async () => {
      const job = await api.getFinalRender(projectId, work.jobId);
      return asPollStatus(job.status, job, job.error_message);
    }, options);
    return outcomeLine(outcome, {
      succeeded: "완성본을 만들었어요. 출력 화면에서 볼 수 있어요.",
      failed: "완성본을 만들지 못했어요. 출력 화면에서 다시 눌러 주세요.",
      timedOut: "완성본이 오래 걸려서 기다리기를 멈췄어요. 출력 화면에서 확인해 주세요.",
    });
  }
  if (work.kind === "capcut_draft") {
    const outcome = await pollJobUntilTerminal(async () => {
      const job = await api.getCapcutDraftExport(projectId, work.jobId);
      return asPollStatus(job.status, job, job.error_message);
    }, options);
    return outcomeLine(outcome, {
      succeeded: "캡컷 초안을 만들었어요. 출력 화면에서 캡컷으로 보낼 수 있어요.",
      failed: "캡컷 초안을 만들지 못했어요. 출력 화면에서 다시 눌러 주세요.",
      timedOut: "캡컷 초안이 오래 걸려서 기다리기를 멈췄어요. 출력 화면에서 확인해 주세요.",
    });
  }
  return YUJIN_WORK_LOST_TRACK;
}
```

(번역·더빙·받아쓰기·부분 재생성 갈래는 Task 17~19가 `return YUJIN_WORK_LOST_TRACK;` **앞**에 더한다.)

Run: `cd apps/web && npx vitest run src/features/editor/workbench/yujinApplyOutcome.test.ts src/features/editor/workbench/yujinBackgroundWork.test.ts`
Expected: 전부 통과.

- [ ] **Step 7: 실패하는 패널 시험** — `YujinPanel.test.tsx`의 "답장 뒤 편집할 자리를 찾는 동안에도 계속 말한다" 시험 **다음**에:

```tsx
  // 유진이 걸어 둔 일(완성본 등)은 분 단위다. 입력칸을 잠그지 않고 상태 한 줄로 계속 말한다.
  it("유진에게 맡긴 일이 도는 동안 상태 한 줄을 보여 주고 입력은 막지 않는다", () => {
    renderOpen({
      draft: "자막 노랗게 해줘",
      onSendMessage: vi.fn(),
      backgroundWork: { label: "완성본을 만들고 있어요." },
    });

    expect(screen.getByRole("status", { name: "유진이 맡은 일" })).toHaveTextContent("완성본을 만들고 있어요.");
    expect(screen.getByRole("button", { name: "요청 보내기" })).toBeEnabled();
  });
```

Run: `cd apps/web && npx vitest run src/features/editor/workbench/YujinPanel.test.tsx -t "유진에게 맡긴 일"`
Expected: FAIL — `Unable to find an accessible element with the role "status" and name "유진이 맡은 일"`(또는 prop 타입 오류)

- [ ] **Step 8: 화면 배선**

(a) `rightDockTypes.ts` — `RightDockDirector` 안 `  thinking?: YujinThinking | null;` 다음 줄에:

```ts
  /** 유진에게 맡겨 둔 긴 일(완성본·캡컷 초안·번역·더빙 …). 입력은 막지 않고 상태 한 줄로 말한다. */
  backgroundWork?: Readonly<{ label: string }> | null;
```

(b) `YujinPanel.tsx` — props 타입의 `  thinking?: YujinThinking | null;`(135행 근처) 다음에 `  backgroundWork?: Readonly<{ label: string }> | null;`. 컴포넌트 인자 구조분해에 `backgroundWork,`를 `thinking,` 옆에 더한다(구조분해 위치는 `function YujinPanel({` 또는 `export function YujinPanel(` 아래 — `thinking`을 꺼내는 같은 줄). 표시 — 기준 글귀

```tsx
      {thinkingWaitNotice ? <p aria-label="유진 기다린 시간">{thinkingWaitNotice}</p> : null}
    </> : null}
```

**다음 줄**에:

```tsx
    {backgroundWork ? <p role="status" aria-live="polite" aria-label="유진이 맡은 일">{backgroundWork.label}</p> : null}
```

(c) `EditorWorkbench.tsx:752` `        thinking={rightDirector?.thinking}` 다음 줄에 `        backgroundWork={rightDirector?.backgroundWork}`.

(d) `api.ts` — 207행 `export type YujinEditingOperation = ...` 다음에:

```ts
/** 단독 실행형 유진 편집이 돌려주는 말·걸어 둔 일. 세션 편집형은 `EditingSession`을 돌려준다. */
export type YujinEditingApplyAction = Readonly<{
  status: string;
  notice?: string;
  job_id?: string;
  url?: string;
  total_scene_count?: number;
  language?: string;
}>;
```

2251-2252행 `applyYujinEditingProposal`의 `request<EditingSession>(`을 `request<EditingSession | YujinEditingApplyAction>(`로 바꾼다.

(e) `EditorWorkbenchRoute.tsx`

- import: 24행 `import { yujinEditingOperationSummary } from "./yujinEditingSummary";` 다음에

```ts
import { yujinApplyFailureMessage, yujinApplyOutcome, type YujinApplyOutcome, type YujinStartedWork } from "./yujinApplyOutcome";
import { followYujinWork, YUJIN_WORK_LOST_TRACK, yujinWorkChangesSession, yujinWorkWaitingLabel } from "./yujinBackgroundWork";
```

- 상태 타입(`DirectorState`) — `  thinking: Readonly<{ phase: "answering" | "judging" }> | null;` 다음에:

```ts
  /** 유진에게 맡겨 둔 긴 일. `null`이면 없다. 입력을 막지 않는다. */
  backgroundWork: Readonly<{ label: string }> | null;
```

- 초기값 — 기준 글귀 `    thinking: null,\n    startFailure: null,` 의 `    thinking: null,` 다음에 `    backgroundWork: null,`.
- 전달 — 2463행 `    thinking: activeDirector.thinking,` 다음에 `    backgroundWork: activeDirector.backgroundWork,`.
- 적용 — `applyEditingProposalNow`(2080행~)의 기준 글귀

```ts
      let applied = false;
      await commitTimelineMutation(async () => {
        await api.applyYujinEditingProposal(projectId, sessionId, proposal.proposal_id, { expected_revision: revision });
        applied = true;
```

를 다음으로 바꾼다:

```ts
      let applied = false;
      // 클로저 안에서 바뀌는 값이라 객체에 담는다(지역 변수로 두면 타입이 첫 값으로 좁혀진다).
      const holder: { outcome: YujinApplyOutcome; failure: string | null } = { outcome: { kind: "session" }, failure: null };
      await commitTimelineMutation(async () => {
        let applyResult: unknown;
        try {
          applyResult = await api.applyYujinEditingProposal(projectId, sessionId, proposal.proposal_id, { expected_revision: revision });
        } catch (error) {
          // **`commitTimelineMutation`은 이 콜백의 예외를 삼킨다**(자기 catch에서 저장 상태 줄만 바꾼다,
          // EditorWorkbenchRoute.tsx 903-910행). 그래서 바깥 `catch`에는 적용 실패가 **오지 않는다** --
          // 권리 미확인·이미 실행됨 같은 이유는 여기서 붙잡아 둔다.
          holder.failure = yujinApplyFailureMessage(error);
          throw error;
        }
        holder.outcome = yujinApplyOutcome(applyResult, window.location.origin);
        applied = true;
```

같은 콜백의 끝 `      });`(기준 글귀 `          completions: [...current.completions, editingProposalCompletionEntry(proposal, view)],\n        } : current);\n      });`) 바로 앞, `} : current);` 다음 줄에:

```ts
        // 단독 실행형이 말할 것이 있으면 저장 상태 줄이 그 말을 한다(`commitTimelineMutation`이 문자열을 받는다).
        if (holder.outcome.kind === "notice") return holder.outcome.notice;
        if (holder.outcome.kind === "work") return yujinWorkWaitingLabel(holder.outcome.work);
        return undefined;
```

그리고 기준 글귀 `      if (!applied) setDirector((current) => current.key === requestKey ? { ...current, editingProposalApplying: false } : current);` 를 다음으로 바꾼다(실패 이유가 있으면 유진 패널의 편집안 오류 줄에 창작자 말로 남긴다):

```ts
      if (!applied) setDirector((current) => current.key === requestKey ? {
        ...current,
        editingProposalApplying: false,
        editingProposalError: holder.failure ?? current.editingProposalError,
      } : current);
      if (applied && holder.outcome.kind === "work") void followYujinStartedWork(holder.outcome.work);
```

같은 함수의 바깥 `catch { ... }`는 **그대로 둔다**(그쪽에는 `preflightYujinEditingProposal` 실패만 온다).

`yujinApplyOutcome.ts` 끝에 실패 이유 가르기를 더한다(같은 파일 맨 위에 `import { ApiRequestError } from "../../../api";`):

```ts
/** 적용이 막힌 이유를 창작자 말로. 모르는 이유는 `null` -- 저장 상태 줄의 기본 문구에 맡긴다. */
export function yujinApplyFailureMessage(error: unknown): string | null {
  if (!(error instanceof ApiRequestError)) return null;
  if (error.reason === "asset_rights_unconfirmed") {
    return "누가 만들었는지 모르는 자료가 있어 업로드 승인을 요청하지 못했어요. 자료실 미리보기에서 출처를 적어 주세요.";
  }
  if (error.reason === "editing_proposal_already_applied") return "이 편집안은 이미 맡겨 두었어요.";
  if (error.reason === "final_render_not_current" || error.reason === "final_render_not_ready") {
    return "지금 편집본으로 만든 완성본이 없어요. 먼저 완성본을 만들어 달라고 말해 주세요.";
  }
  return null;
}
```

`yujinApplyOutcome.test.ts`에 시험 하나(맨 위 import에 `import { ApiRequestError } from "../../../api";`, `yujinApplyFailureMessage`도 같이 import):

```ts
  it("막힌 이유를 창작자 말로 돌려주고, 모르는 이유는 비워 둔다", () => {
    expect(yujinApplyFailureMessage(new ApiRequestError(null, 409, "/x", "asset_rights_unconfirmed")))
      .toBe("누가 만들었는지 모르는 자료가 있어 업로드 승인을 요청하지 못했어요. 자료실 미리보기에서 출처를 적어 주세요.");
    expect(yujinApplyFailureMessage(new ApiRequestError("editing_proposal_already_applied", 409, "/x", "editing_proposal_already_applied")))
      .toBe("이 편집안은 이미 맡겨 두었어요.");
    expect(yujinApplyFailureMessage(new ApiRequestError("boom", 500, "/x", "boom"))).toBeNull();
    expect(yujinApplyFailureMessage(new Error("network"))).toBeNull();
  });
```

(`ApiRequestError`의 `reason`은 서버 detail이 문자열이면 그 문자열, `{"reason": ...}`이면 그 값이다 — `api.ts:1383-1387`.)

- 지켜보기 — `applyEditingProposalNow` 정의 **바로 앞**에 새 함수:

```ts
  /** 유진이 걸어 둔 일을 끝까지 지켜보고, 끝나면 완료 목록에 한 줄 남긴다.
   *
   *  편집본을 바꾸는 일(번역·더빙·부분 재생성)은 화면의 더빙(`dubNarration`)과 같은 이유로
   *  그동안 다른 편집을 잠그고 저장 상태 줄에 진행을 말한다. 완성본·캡컷 초안은 편집본을
   *  안 바꾸므로 잠그지 않고, 유진 패널의 상태 한 줄로만 말한다. */
  const followYujinStartedWork = async (work: YujinStartedWork) => {
    if (!sessionId) return;
    const epoch = routeEpoch.current.value;
    const isCurrent = () => routeEpoch.current.value === epoch;
    const showWork = (label: string | null) => setDirector((current) => current.key === requestKey
      ? { ...current, backgroundWork: label ? { label } : null }
      : current);
    const locksEditing = yujinWorkChangesSession(work.kind);
    const waiting = yujinWorkWaitingLabel(work);
    showWork(waiting);
    if (locksEditing) {
      mutationInFlight.current = true;
      setMutation({ isSaving: true, message: waiting });
    }
    let message: string;
    try {
      message = await followYujinWork({
        projectId,
        sessionId,
        work,
        isStillRelevant: isCurrent,
        expectedRevision: () => currentEditorRevision.current,
        onProgress: (label) => {
          if (!isCurrent()) return;
          showWork(label);
          if (locksEditing) setMutation({ isSaving: true, message: label });
        },
      });
    } catch {
      message = YUJIN_WORK_LOST_TRACK;
    } finally {
      if (locksEditing) mutationInFlight.current = false;
    }
    if (!isCurrent()) return;
    setDirector((current) => current.key === requestKey ? {
      ...current,
      backgroundWork: null,
      completions: [...current.completions, { id: `completion-work-${work.jobId}`, appliedAt: new Date().toISOString(), items: [{ label: message }] }],
    } : current);
    // 편집본이 바뀐 일은 기존 통로가 다시 읽는다(더빙과 같다). 아니면 말만 남긴다.
    if (locksEditing || work.kind === "transcription") await commitTimelineMutation(async () => message);
    else setMutation({ isSaving: false, message });
  };
```

(`routeEpoch`, `requestKey`, `mutationInFlight`, `currentEditorRevision`, `setMutation`, `commitTimelineMutation`은 이 컴포넌트에 이미 있다 — 313·320·352·854행. 이 함수는 hook이 아니므로 early return 아래에 둬도 된다.)

- [ ] **Step 9: 통과·타입·넓은 검증**

```powershell
cd apps/web
npx vitest run src/features/editor/workbench/YujinPanel.test.tsx src/features/editor/workbench/yujinApplyOutcome.test.ts src/features/editor/workbench/yujinBackgroundWork.test.ts src/features/editor/workbench/editor-workbench-route.test.tsx src/user-copy-policy.test.ts src/task22-parity-owners.test.ts
npx tsc --noEmit
cd ../..
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_session_master_outputs.py tests/test_api_final_render_endpoint.py tests/test_api_capcut_draft_export_endpoint.py tests/test_final_render_idempotency.py tests/test_yujin_editing_short_form.py
```
Expected: 모두 통과. `tsc`가 `DirectorState`를 만드는 다른 자리에서 `backgroundWork` 누락을 알리면 그 자리에도 `backgroundWork: null`을 넣는다.

- [ ] **Step 10: 검증 넷·커밋**

배선: `git grep -n "followYujinStartedWork\|yujinApplyOutcome(\|backgroundWork" -- apps/web/src ':!*.test.*'` → 정의·사용 자리가 Route·Panel·Workbench·rightDockTypes에 모두 있다. `git grep -n "launch_final_render_worker_if_needed\|launch_capcut_draft_export_worker_if_needed" -- services` → 정의 2, 사용 2(outputs.py). 역방향은 Task 12.

```bash
git add services/api/src/videobox_api/session_master_outputs.py tests/test_session_master_outputs.py services/api/src/videobox_api/orchestration.py services/api/src/videobox_api/routers/outputs.py apps/web/src/api.ts apps/web/src/features/editor/workbench/yujinApplyOutcome.ts apps/web/src/features/editor/workbench/yujinApplyOutcome.test.ts apps/web/src/features/editor/workbench/yujinBackgroundWork.ts apps/web/src/features/editor/workbench/yujinBackgroundWork.test.ts apps/web/src/features/editor/workbench/rightDockTypes.ts apps/web/src/features/editor/workbench/YujinPanel.tsx apps/web/src/features/editor/workbench/YujinPanel.test.tsx apps/web/src/features/editor/workbench/EditorWorkbench.tsx apps/web/src/features/editor/workbench/EditorWorkbenchRoute.tsx
git commit -m "feat(yujin): 유진에게 맡긴 긴 일을 화면이 끝까지 지켜보는 길 + 마스터 완성본 고르기 서버 규칙

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: C1 — "완성본 만들어 줘"(`render_final_video`)

화면 출력 화면의 `완성본 만들기`(`apps/web/src/app/OutputsPage.tsx:1093-1135` → `POST /api/projects/{p}/jobs/final-render`, `routers/outputs.py:309-336`)와 같은 세 걸음: 지금 편집본의 타임라인 작업 고르기(`current_timeline_job_id`) → `assert_timeline_output_allowed` → `start_final_render_job` + Task 8의 `launch_final_render_worker_if_needed`. 기다림은 Task 8의 지켜보기 길이 보여 준다.

**Files:**
- Modify: `packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py`(`STANDALONE_INTENTS`, 맥락 `has_output_timeline`, 검사)
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py`
- Modify: `services/api/src/videobox_api/routers/director_proposals.py`(import·맥락·`_apply_standalone_intent`)
- Modify: `apps/web/src/features/editor/workbench/yujinEditingSummary.ts`, `.test.ts`
- Create: `tests/test_yujin_editing_outputs.py`

**Interfaces:**
- Consumes: Task 8의 `current_timeline_job_id`, `ApiOrchestrator.launch_final_render_worker_if_needed`; `orchestrator.assert_timeline_output_allowed(*, project_id, timeline_job_id) -> None`(막히면 예외), `orchestrator.start_final_render_job(*, project_id, timeline_job_id) -> dict`
- Produces: `RenderFinalVideoOperation(intent: Literal["render_final_video"])`; `YujinEditingContext.has_output_timeline: bool = False`; 거절 이유 `final_render_needs_timeline`; 적용 응답 `{"status": "final_render_started", "job_id": str, "notice": "완성본을 만들고 있어요. 다 되면 여기에 알려 드릴게요."}`

- [ ] **Step 1: 실패하는 시험** — `tests/test_yujin_editing_outputs.py`:

```python
"""묶음 C -- 본편 MP4·내보내기를 말로. 업로드는 **승인 요청까지만**(사람 게이트, 2026-08-16 결정)."""
from __future__ import annotations

from pathlib import Path

import pytest

import videobox_api.routers.director_proposals as director_proposals_module
from videobox_core_engine.yujin_editing_proposal_adapter import YujinEditingContext, interpret_yujin_editing_request
from videobox_core_engine.yujin_editing_proposal_service import _editing_prompt
from yujin_chat_fakes import ScriptedEditingProvider, create_and_apply, plain_session_project

_IDS = ("seg-hook", "seg-middle", "seg-close")


def _response(*operations: dict, revision: int = 3) -> dict:
    return {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "맡겨 주세요.",
        "proposal": {"proposal_id": "p", "base_session_revision": revision, "operations": list(operations)},
    }


def _context(**extra: object) -> YujinEditingContext:
    return YujinEditingContext(session_id="s", session_revision=3, segment_ids=_IDS, **extra)  # type: ignore[arg-type]


# --- 완성본 -------------------------------------------------------------------

def test_final_render_needs_a_built_timeline_and_must_be_alone() -> None:
    no_timeline = interpret_yujin_editing_request(_response({"intent": "render_final_video"}), _context())
    fine = interpret_yujin_editing_request(_response({"intent": "render_final_video"}), _context(has_output_timeline=True))
    mixed = interpret_yujin_editing_request(
        _response({"intent": "render_final_video"}, {"intent": "set_cut_action", "segment_id": "seg-close", "action": "exclude"}),
        _context(has_output_timeline=True),
    )

    assert no_timeline.reason == "final_render_needs_timeline"
    assert fine.status == "candidate_only"
    assert mixed.reason == "operation_must_be_alone"  # Review Focus 1


def test_yujin_starts_the_final_render_the_same_way_the_output_screen_does(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = ScriptedEditingProvider(operations=[{"intent": "render_final_video"}])
    app, client, project_id, session = plain_session_project(tmp_path, provider)
    monkeypatch.setattr(director_proposals_module, "current_timeline_job_id", lambda **_: "timeline-job-1")
    calls: list[str] = []
    orchestrator = app.state.orchestrator
    monkeypatch.setattr(orchestrator, "assert_timeline_output_allowed", lambda *, project_id, timeline_job_id: calls.append(f"allowed:{timeline_job_id}"))
    monkeypatch.setattr(orchestrator, "start_final_render_job", lambda *, project_id, timeline_job_id: {"job_id": "final-1", "status": "running", "should_start": True})
    monkeypatch.setattr(orchestrator, "launch_final_render_worker_if_needed", lambda *, project_id, timeline_job_id, result: calls.append(f"launched:{result['job_id']}"))

    response = create_and_apply(client, project_id, session, "완성본 만들어줘")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "final_render_started"
    assert body["job_id"] == "final-1"
    assert "완성본을 만들고 있어요" in body["notice"]
    assert calls == ["allowed:timeline-job-1", "launched:final-1"]


def test_the_prompt_says_how_to_ask_for_the_final_video() -> None:
    prompt = _editing_prompt(instruction="완성본 만들어줘", context=_context(has_output_timeline=True))
    assert "render_final_video" in prompt
    assert "완성본" in prompt.split("render_final_video", 1)[1][:120]
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_outputs.py::test_final_render_needs_a_built_timeline_and_must_be_alone`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'has_output_timeline'`

- [ ] **Step 2: 의도 모델** — `SetTrackStateOperation` 다음에:

```python
class RenderFinalVideoOperation(_StrictFrozenModel):
    """완성본(본편 MP4)을 만든다 -- 출력 화면 `완성본 만들기`(`POST .../jobs/final-render`)와 같은 자리.

    렌더 job만 걸고 돌아온다(분 단위, 프록시 330초 벽). 진행은 화면이 job 폴링으로 보여 준다.
    파라미터가 없다: 어느 타임라인을 뽑을지는 서버가 화면과 같은 규칙으로 정한다
    (`session_master_outputs.current_timeline_job_id`).
    """

    intent: Literal["render_final_video"]
```

유니언·`__all__`(`"RenderFinalVideoOperation",`를 `"RenderShortFormOperation",` 앞)에 넣는다.

- [ ] **Step 3: 검증기·맥락** — adapter

도메인 import에 `RenderFinalVideoOperation,`. `STANDALONE_INTENTS`에 `"render_final_video"`를 더한다:

```python
STANDALONE_INTENTS: frozenset[str] = frozenset({"undo_last_edit", "redo_last_edit", "render_final_video"})
```

맥락 필드(Task 6의 `track_states` 다음):

```python
    #: 이 편집본으로 완성본을 뽑을 타임라인이 있는가(`session_master_outputs.current_timeline_job_id`).
    #: 없으면 출력 화면의 `완성본 만들기`도 눌리지 않는다 -- 유진도 같은 조건에서 막힌다.
    has_output_timeline: bool = False
```

검사(Task 6의 트랙 검사 다음):

```python
        if isinstance(operation, RenderFinalVideoOperation) and not context.has_output_timeline:
            return "final_render_needs_timeline"
```

- [ ] **Step 4: 맥락 조립·적용 (API)** — `director_proposals.py`

import(Task 6의 `normalize_track_states` import 다음 줄):

```python
from videobox_api.session_master_outputs import current_timeline_job_id, master_final_render_state
```

맥락(Task 6 `track_states=` 블록 다음):

```python
            has_output_timeline=current_timeline_job_id(store=store, project_id=project_id, session=session) is not None,
```

`_apply_standalone_intent` — 기준 글귀 `        raise ValueError(f"standalone_intent_not_supported:{intent}")` **앞**에:

```python
        if intent == "render_final_video":
            # 출력 화면 `완성본 만들기`와 같은 세 걸음(routers/outputs.py `start_final_render`).
            session = store.get_editing_session(project_id=project_id, session_id=session_id)
            timeline_job_id = current_timeline_job_id(store=store, project_id=project_id, session=session)
            if timeline_job_id is None:
                raise HTTPException(status_code=409, detail="final_render_needs_timeline")
            orchestrator.assert_timeline_output_allowed(project_id=project_id, timeline_job_id=timeline_job_id)
            started = orchestrator.start_final_render_job(project_id=project_id, timeline_job_id=timeline_job_id)
            orchestrator.launch_final_render_worker_if_needed(
                project_id=project_id, timeline_job_id=timeline_job_id, result=started,
            )
            return {
                "status": "final_render_started",
                "job_id": str(started["job_id"]),
                "notice": "완성본을 만들고 있어요. 다 되면 여기에 알려 드릴게요.",
            }
```

(시험이 `director_proposals_module.current_timeline_job_id`를 바꿔치기하므로 **모듈 수준 이름**으로 부른다 — `session_master_outputs.current_timeline_job_id(...)`처럼 모듈을 거쳐 부르지 않는다.)

- [ ] **Step 5: 스키마·안내문**

스키마(Task 6 줄 다음):

```python
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "render_final_video"}}, "required": ["intent"]},
```

허용 intent 문장(Task 6 줄 다음):

```python
        "render_final_video(완성본 MP4를 만든다 -- \"완성본 만들어줘\", \"영상 뽑아줘\"가 이것이다), "
```

새 함수(`_track_state_catalogue` 다음):

```python
def _output_catalogue(context: YujinEditingContext) -> str:
    """완성본·내보내기(묶음 C). 숏폼 렌더와 같은 함정을 막는다 -- 고르는 순간 서버가 실제로
    시작하므로 "단추를 누르라"고 답하면 거짓이다(2026-09-13 실물)."""
    timeline = (
        "이 편집본은 완성본을 만들 수 있다."
        if context.has_output_timeline
        else "이 편집본은 아직 완성본을 만들 타임라인이 없다 -- 완성본 요청에는 출력 화면에서 먼저 확인해 달라고 답한다."
    )
    return (
        f"{timeline} '완성본 만들어줘'·'영상 뽑아줘'·'MP4로 내보내줘'(숏폼이 아닌 본편)는 render_final_video다. "
        "이 의도를 고르는 순간 서버가 실제로 시작한다 -- 단추를 누르라고 안내하지 않는다. "
        "완성본·내보내기 의도는 **혼자** 싣는다."
    )
```

`_editing_prompt` 안 `        f"{_track_state_catalogue(context)} "` 다음 줄에 `        f"{_output_catalogue(context)} "`.

- [ ] **Step 6: 화면 한 줄** — `yujinEditingSummary.ts`의 `set_track_state` 줄 다음:

```ts
  // 묶음 C(2026-10-02): 완성본·내보내기.
  if (operation.intent === "render_final_video") return "완성본을 만들어요.";
```

시험:

```ts
  it("완성본 만들기를 말한다", () => {
    expect(summary({ intent: "render_final_video" })).toBe("완성본을 만들어요.");
  });
```

- [ ] **Step 7: 통과·넓은 검증**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_outputs.py tests/test_yujin_editing_basics.py tests/test_yujin_editing_short_form.py` → 통과
Run: `cd apps/web && npx vitest run src/features/editor/workbench/yujinEditingSummary.test.ts` → passed

- [ ] **Step 8: 검증 넷·커밋**

배선: `git grep -n "render_final_video" -- packages services apps/web/src` → 모델·스키마·안내문·검증기·적용·화면 한 줄.

```bash
git add packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py services/api/src/videobox_api/routers/director_proposals.py apps/web/src/features/editor/workbench/yujinEditingSummary.ts apps/web/src/features/editor/workbench/yujinEditingSummary.test.ts tests/test_yujin_editing_outputs.py
git commit -m "feat(yujin): 말로 완성본 만들기 -- 출력 화면과 같은 세 걸음, 기다림은 화면이 지켜본다

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 10: C2 — 캡컷 초안 내보내기(`export_capcut_draft`), 미리보기 링크(`create_preview_link`)

캡컷 초안: 출력 화면 `handleExportCapcutDraft`(`OutputsPage.tsx:1136-1180`) → `POST .../jobs/capcut-draft-export`(`routers/outputs.py:535-563`)와 같은 세 걸음. 캡컷 앱으로 넘기는 `handoff`(`routers/outputs.py:580`)는 **열지 않는다** — `_YUJIN_SYSTEM_PROMPT`가 "CapCut 앱을 직접 열거나 조작"을 금지한다(`yujin_local_conversation.py:49`). 초안까지만 만들고 "출력 화면에서 캡컷으로 보낼 수 있어요"라고 말한다.

미리보기 링크: 출력 화면 `handleCreatePreviewShare`(`OutputsPage.tsx:1063-1080`) → `POST .../final-renders/{job_id}/share`(`routers/preview_shares.py:23-42`)가 부르는 `orchestrator.create_preview_share(project_id, export_id)`. 대상은 Task 8의 `master_final_render_state`가 고른 **지금 편집본의 마스터 완성본**이고, 성공·현재가 아니면 링크를 만들지 않는다(낡은 완성본을 남에게 보내지 않는다).

**Files:**
- Modify: `packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py`(`STANDALONE_INTENTS`, 맥락 `has_current_final_render`, 검사)
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py`
- Modify: `services/api/src/videobox_api/routers/director_proposals.py`
- Modify: `apps/web/src/features/editor/workbench/yujinEditingSummary.ts`, `.test.ts`, `yujinBackgroundWork.ts`(변경 없음 — 캡컷 갈래는 Task 8에 있다)
- Modify: `tests/test_yujin_editing_outputs.py`

**Interfaces:**
- Consumes: `orchestrator.start_capcut_draft_export_job(*, project_id, timeline_job_id) -> dict`, Task 8의 `launch_capcut_draft_export_worker_if_needed`, `master_final_render_state(...) -> MasterFinalRenderState | None`, `orchestrator.create_preview_share(*, project_id, export_id) -> {"share_id","token",...}`
- Produces: `ExportCapcutDraftOperation(intent: Literal["export_capcut_draft"])`, `CreatePreviewLinkOperation(intent: Literal["create_preview_link"])`; `YujinEditingContext.has_current_final_render: bool = False`; 거절 이유 `final_render_not_current`; 적용 응답 `{"status": "capcut_draft_export_started", "job_id", "notice"}`, `{"status": "preview_share_created", "share_id", "url": "/preview/<token>", "notice": "미리보기 링크를 만들었어요."}`

- [ ] **Step 1: 실패하는 시험** — `tests/test_yujin_editing_outputs.py` 끝에:

```python
# --- 캡컷 초안·미리보기 링크 ---------------------------------------------------

def test_capcut_draft_needs_a_timeline_and_a_preview_link_needs_a_current_final_video() -> None:
    capcut_without = interpret_yujin_editing_request(_response({"intent": "export_capcut_draft"}), _context())
    capcut_with = interpret_yujin_editing_request(_response({"intent": "export_capcut_draft"}), _context(has_output_timeline=True))
    link_without = interpret_yujin_editing_request(_response({"intent": "create_preview_link"}), _context(has_output_timeline=True))
    link_with = interpret_yujin_editing_request(
        _response({"intent": "create_preview_link"}), _context(has_output_timeline=True, has_current_final_render=True)
    )

    assert capcut_without.reason == "final_render_needs_timeline"
    assert capcut_with.status == "candidate_only"
    assert link_without.reason == "final_render_not_current"
    assert link_with.status == "candidate_only"


def test_yujin_starts_a_capcut_draft_the_same_way_the_output_screen_does(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = ScriptedEditingProvider(operations=[{"intent": "export_capcut_draft"}])
    app, client, project_id, session = plain_session_project(tmp_path, provider)
    monkeypatch.setattr(director_proposals_module, "current_timeline_job_id", lambda **_: "timeline-job-1")
    calls: list[str] = []
    orchestrator = app.state.orchestrator
    monkeypatch.setattr(orchestrator, "assert_timeline_output_allowed", lambda *, project_id, timeline_job_id: calls.append("allowed"))
    monkeypatch.setattr(orchestrator, "start_capcut_draft_export_job", lambda *, project_id, timeline_job_id: {"job_id": "capcut-1", "status": "running", "should_start": True})
    monkeypatch.setattr(orchestrator, "launch_capcut_draft_export_worker_if_needed", lambda *, project_id, timeline_job_id, result: calls.append(f"launched:{result['job_id']}"))

    response = create_and_apply(client, project_id, session, "캡컷 초안으로 내보내줘")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "capcut_draft_export_started"
    assert response.json()["job_id"] == "capcut-1"
    assert calls == ["allowed", "launched:capcut-1"]


def test_yujin_makes_a_preview_link_only_for_the_current_final_video(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from videobox_api.session_master_outputs import MasterFinalRenderState

    provider = ScriptedEditingProvider(operations=[{"intent": "create_preview_link"}])
    app, client, project_id, session = plain_session_project(tmp_path, provider)
    state = {"value": MasterFinalRenderState(job_id="final-1", status="succeeded", export_id="export-1", is_current=True)}
    monkeypatch.setattr(director_proposals_module, "master_final_render_state", lambda **_: state["value"])
    monkeypatch.setattr(director_proposals_module, "current_timeline_job_id", lambda **_: "timeline-job-1")
    shares: list[str] = []
    monkeypatch.setattr(
        app.state.orchestrator, "create_preview_share",
        lambda *, project_id, export_id: shares.append(export_id) or {"share_id": "share-1", "token": "tok-1"},
    )

    response = create_and_apply(client, project_id, session, "미리보기 링크 만들어줘")

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "preview_share_created", "share_id": "share-1", "url": "/preview/tok-1", "notice": "미리보기 링크를 만들었어요."}
    assert shares == ["export-1"]

    # 편집본이 바뀌어 완성본이 낡았으면 생성 단계에서 막힌다 -- 맥락(`has_current_final_render`)이
    # 적용과 **같은** `master_final_render_state`를 읽기 때문이다.
    state["value"] = MasterFinalRenderState(job_id="final-1", status="succeeded", export_id="export-1", is_current=False)
    refused = propose(client, project_id, session["session_id"], "미리보기 링크 만들어줘")
    assert refused["status"] == "rejected"
```

그리고 파일 맨 위 import 줄 `from yujin_chat_fakes import ScriptedEditingProvider, create_and_apply, plain_session_project`를 `from yujin_chat_fakes import ScriptedEditingProvider, create_and_apply, plain_session_project, propose`로 바꾼다.

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_outputs.py::test_capcut_draft_needs_a_timeline_and_a_preview_link_needs_a_current_final_video`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'has_current_final_render'`

- [ ] **Step 2: 의도 모델** — `RenderFinalVideoOperation` 다음에:

```python
class ExportCapcutDraftOperation(_StrictFrozenModel):
    """캡컷 초안을 만든다 -- 출력 화면 `캡컷 초안 만들기`(`POST .../jobs/capcut-draft-export`)와 같은 자리.

    초안까지만이다. 캡컷 앱으로 넘기는 것(`handoff`)은 열지 않는다 -- 유진은 캡컷 앱을 직접
    열거나 조작하지 않는다(`yujin_local_conversation._YUJIN_SYSTEM_PROMPT`).
    """

    intent: Literal["export_capcut_draft"]


class CreatePreviewLinkOperation(_StrictFrozenModel):
    """지금 편집본의 완성본으로 미리보기 링크를 만든다 -- 출력 화면 `미리보기 링크`와 같은 함수.

    완성본이 없거나 낡았으면 만들지 않는다(낡은 영상을 남에게 보내지 않는다).
    """

    intent: Literal["create_preview_link"]
```

유니언·`__all__`(`"CreatePreviewLinkOperation",`는 `"CreateShortFormOperation",` 앞, `"ExportCapcutDraftOperation",`는 `"RemakeShortFormOperation",` 앞 알파벳 자리)에 넣는다.

- [ ] **Step 3: 검증기·맥락** — adapter

도메인 import에 둘. `STANDALONE_INTENTS`에 `"export_capcut_draft", "create_preview_link"`를 더한다. 맥락 필드(`has_output_timeline` 다음):

```python
    #: 지금 편집본의 마스터 완성본이 **다 만들어졌고 지금 것**인가(`master_final_render_state`).
    #: 미리보기 링크·업로드 승인 요청은 이게 참일 때만 된다.
    has_current_final_render: bool = False
```

검사(`RenderFinalVideoOperation` 검사 다음):

```python
        if isinstance(operation, ExportCapcutDraftOperation) and not context.has_output_timeline:
            return "final_render_needs_timeline"
        if isinstance(operation, CreatePreviewLinkOperation) and not context.has_current_final_render:
            return "final_render_not_current"
```

- [ ] **Step 4: 맥락 조립·적용 (API)** — `director_proposals.py`

맥락(`has_output_timeline=...` 다음):

```python
            has_current_final_render=_has_current_final_render(project_id=project_id, session=session),
```

라우터 빌더 안, `    def _apply_standalone_intent(` **앞**에:

```python
    def _has_current_final_render(*, project_id: str, session: dict) -> bool:
        state = master_final_render_state(store=store, orchestrator=orchestrator, project_id=project_id, session=session)
        return state is not None and state.status == "succeeded" and state.is_current
```

`_apply_standalone_intent`의 `render_final_video` 갈래 다음(`raise ValueError(...)` 앞)에:

```python
        if intent == "export_capcut_draft":
            # 출력 화면 `캡컷 초안 만들기`와 같은 세 걸음(routers/outputs.py `start_capcut_draft_export`).
            session = store.get_editing_session(project_id=project_id, session_id=session_id)
            timeline_job_id = current_timeline_job_id(store=store, project_id=project_id, session=session)
            if timeline_job_id is None:
                raise HTTPException(status_code=409, detail="final_render_needs_timeline")
            orchestrator.assert_timeline_output_allowed(project_id=project_id, timeline_job_id=timeline_job_id)
            started = orchestrator.start_capcut_draft_export_job(project_id=project_id, timeline_job_id=timeline_job_id)
            orchestrator.launch_capcut_draft_export_worker_if_needed(
                project_id=project_id, timeline_job_id=timeline_job_id, result=started,
            )
            return {
                "status": "capcut_draft_export_started",
                "job_id": str(started["job_id"]),
                "notice": "캡컷 초안을 만들고 있어요. 다 되면 여기에 알려 드릴게요.",
            }
        if intent == "create_preview_link":
            # 출력 화면 `미리보기 링크`와 같은 함수(routers/preview_shares.py `create_preview_share`).
            session = store.get_editing_session(project_id=project_id, session_id=session_id)
            state = master_final_render_state(store=store, orchestrator=orchestrator, project_id=project_id, session=session)
            if state is None or state.status != "succeeded" or state.export_id is None:
                raise HTTPException(status_code=409, detail="final_render_not_ready")
            if not state.is_current:
                raise HTTPException(status_code=409, detail="final_render_not_current")
            share = orchestrator.create_preview_share(project_id=project_id, export_id=state.export_id)
            return {
                "status": "preview_share_created",
                "share_id": str(share["share_id"]),
                "url": f"/preview/{share['token']}",
                "notice": "미리보기 링크를 만들었어요.",
            }
```

(링크의 앞부분(`http://127.0.0.1:5173`)은 화면이 `window.location.origin`으로 붙인다 — Task 8의 `yujinApplyOutcome`. 서버는 프록시 뒤에서 자기 주소를 정확히 모른다.)

- [ ] **Step 5: 스키마·안내문**

스키마(Task 9 줄 다음):

```python
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "export_capcut_draft"}}, "required": ["intent"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "create_preview_link"}}, "required": ["intent"]},
```

허용 intent 문장(Task 9 줄 다음):

```python
        "export_capcut_draft(캡컷 초안을 만든다 -- \"캡컷으로 내보내줘\"가 이것이다), create_preview_link(완성본 미리보기 링크를 만든다), "
```

`_output_catalogue`의 반환 문자열 맨 끝 `"완성본·내보내기 의도는 **혼자** 싣는다."`를 다음으로 바꾼다:

```python
        "'캡컷으로 내보내줘'·'캡컷 초안 만들어줘'는 export_capcut_draft다 -- 초안까지만 만들고, "
        "캡컷 앱을 열거나 넘기는 것은 창작자가 출력 화면에서 한다. "
        + (
            "지금 완성본이 있어 '미리보기 링크 만들어줘'·'공유 링크 줘'는 create_preview_link다. "
            if context.has_current_final_render
            else "지금 편집본의 완성본이 없거나 낡아서 미리보기 링크는 아직 못 만든다 -- 먼저 완성본을 만들자고 답한다. "
        )
        + "완성본·내보내기 의도는 **혼자** 싣는다."
```

- [ ] **Step 6: 화면 한 줄** — `yujinEditingSummary.ts`의 `render_final_video` 줄 다음:

```ts
  if (operation.intent === "export_capcut_draft") return "캡컷 초안을 만들어요.";
  if (operation.intent === "create_preview_link") return "미리보기 링크를 만들어요.";
```

시험:

```ts
  it("캡컷 초안과 미리보기 링크를 말한다", () => {
    expect(summary({ intent: "export_capcut_draft" })).toBe("캡컷 초안을 만들어요.");
    expect(summary({ intent: "create_preview_link" })).toBe("미리보기 링크를 만들어요.");
  });
```

- [ ] **Step 7: 통과·넓은 검증**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_outputs.py tests/test_api_preview_shares.py tests/test_api_capcut_draft_export_endpoint.py` → 통과
Run: `cd apps/web && npx vitest run src/features/editor/workbench/yujinEditingSummary.test.ts` → passed

- [ ] **Step 8: 검증 넷·커밋**

배선: `git grep -n "export_capcut_draft\|create_preview_link" -- packages services apps/web/src` → 각각 모델·스키마·안내문·검증기·적용·화면 한 줄. `git grep -n "handoff" -- packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py` → 0건(열지 않았다).

```bash
git add packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py services/api/src/videobox_api/routers/director_proposals.py apps/web/src/features/editor/workbench/yujinEditingSummary.ts apps/web/src/features/editor/workbench/yujinEditingSummary.test.ts tests/test_yujin_editing_outputs.py
git commit -m "feat(yujin): 말로 캡컷 초안·미리보기 링크 -- 출력 화면과 같은 함수, 낡은 완성본은 링크 안 만듦

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 11: C3 — 업로드 승인 **요청**까지만(`request_upload_approval`)

출력 화면 `handleRequestUploadApproval`(`OutputsPage.tsx:1034-1061`) → `POST .../final-renders/{job_id}/request-upload-approval`(`routers/outputs.py:402-467`). 이 라우트 본문(이미 결정됨 검사·권리 미확인 검사·결재함 큐)을 **함수로 뽑아** 화면과 유진이 같이 부른다. 결재함의 **승인**은 사람이 한다 — 유진에게 열지 않는다(결정 문서 경계). 라우트는 `async`이고 유진 적용 라우트는 동기(`def`, 스레드풀)라서 `anyio.from_thread.run`으로 부른다.

**Files:**
- Modify: `services/api/src/videobox_api/routers/outputs.py:402-467`(본문을 `queue_upload_approval`로 뽑기)
- Modify: `packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py`
- Modify: `services/api/src/videobox_api/routers/director_proposals.py`
- Modify: `apps/web/src/features/editor/workbench/yujinEditingSummary.ts`, `.test.ts`
- Modify: `tests/test_yujin_editing_outputs.py`

**Interfaces:**
- Consumes: `UploadApprovalResponse(queued: bool)`(`services/api/src/videobox_api/models.py:2205-2208`), `_library_assets_with_unconfirmed_rights(request, project_id)`(`routers/outputs.py:150`), `request.app.state.agent_gateway_client.submit_upload_request(...)`
- Produces: `async def queue_upload_approval(*, request: Request, orchestrator: ApiOrchestrator, project_id: str, job_id: str, upload_target: str, upload_scheduled_summary_ko: str) -> UploadApprovalResponse`(모듈 수준, `routers/outputs.py`); `RequestUploadApprovalOperation(intent: Literal["request_upload_approval"], summary_ko: str 1..2000)`; 적용 응답 `{"status": "upload_approval_requested" | "upload_approval_not_queued", "notice": str}`

- [ ] **Step 1: 실패하는 시험** — `tests/test_yujin_editing_outputs.py` 끝에:

```python
# --- 업로드 승인 요청(요청까지만) ----------------------------------------------

def test_upload_approval_request_needs_a_current_final_video() -> None:
    without = interpret_yujin_editing_request(
        _response({"intent": "request_upload_approval", "summary_ko": "내일 오전 유튜브"}), _context(has_output_timeline=True)
    )
    with_current = interpret_yujin_editing_request(
        _response({"intent": "request_upload_approval", "summary_ko": "내일 오전 유튜브"}),
        _context(has_output_timeline=True, has_current_final_render=True),
    )
    assert without.reason == "final_render_not_current"
    assert with_current.status == "candidate_only"


def test_there_is_no_intent_that_approves_anything() -> None:
    """사람 게이트(제목·대본·업로드)의 **승인**은 유진에게 열지 않는다(2026-10-02 결정 경계)."""
    from typing import get_args

    from videobox_domain_models.yujin_editing_proposals import YujinEditingOperation

    union = get_args(get_args(YujinEditingOperation)[0])
    intents = {get_args(model.model_fields["intent"].annotation)[0] for model in union}
    assert not {intent for intent in intents if "approve" in intent and intent != "request_upload_approval"}
    assert "request_upload_approval" in intents


def test_yujin_queues_the_upload_approval_request_the_same_way_the_output_screen_does(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from videobox_api.models import UploadApprovalResponse
    from videobox_api.session_master_outputs import MasterFinalRenderState

    provider = ScriptedEditingProvider(operations=[{"intent": "request_upload_approval", "summary_ko": "내일 오전 9시 유튜브"}])
    app, client, project_id, session = plain_session_project(tmp_path, provider)
    monkeypatch.setattr(director_proposals_module, "master_final_render_state", lambda **_: MasterFinalRenderState(job_id="final-1", status="succeeded", export_id="export-1", is_current=True))
    monkeypatch.setattr(director_proposals_module, "current_timeline_job_id", lambda **_: "timeline-job-1")
    seen: list[dict] = []

    async def _fake_queue(**kwargs: object) -> UploadApprovalResponse:
        seen.append({key: kwargs[key] for key in ("project_id", "job_id", "upload_target", "upload_scheduled_summary_ko")})
        return UploadApprovalResponse(queued=True)

    monkeypatch.setattr(director_proposals_module, "queue_upload_approval", _fake_queue)

    response = create_and_apply(client, project_id, session, "유튜브 업로드 승인 요청 올려줘")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "upload_approval_requested"
    assert "승인은 대표님이 결재함에서" in body["notice"]
    assert seen == [{"project_id": project_id, "job_id": "final-1", "upload_target": "youtube", "upload_scheduled_summary_ko": "내일 오전 9시 유튜브"}]


def test_unconfirmed_asset_rights_block_the_request_with_the_reason(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Review Focus 4: 권리를 모르는 자산이 있으면 결재함에 아무것도 안 올라가고, 이유가 화면까지 간다."""
    from fastapi import HTTPException

    from videobox_api.session_master_outputs import MasterFinalRenderState

    provider = ScriptedEditingProvider(operations=[{"intent": "request_upload_approval", "summary_ko": "내일"}])
    app, client, project_id, session = plain_session_project(tmp_path, provider)
    monkeypatch.setattr(director_proposals_module, "master_final_render_state", lambda **_: MasterFinalRenderState(job_id="final-1", status="succeeded", export_id="export-1", is_current=True))
    monkeypatch.setattr(director_proposals_module, "current_timeline_job_id", lambda **_: "timeline-job-1")

    async def _blocked(**_: object):
        raise HTTPException(status_code=409, detail={"reason": "asset_rights_unconfirmed", "library_asset_ids": ["lib-1"]})

    monkeypatch.setattr(director_proposals_module, "queue_upload_approval", _blocked)

    response = create_and_apply(client, project_id, session, "업로드 승인 요청해줘")

    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "asset_rights_unconfirmed"
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_outputs.py::test_upload_approval_request_needs_a_current_final_video`
Expected: FAIL — `AssertionError: assert 'invalid_editing_response' == 'final_render_not_current'`

- [ ] **Step 2: 라우트 본문을 함수로 뽑는다** — `routers/outputs.py`

`def build_outputs_router(` **앞**(모듈 수준)에 함수 머리를 만들고, 라우트 `request_upload_approval`의 docstring 다음 줄부터 마지막 `        return UploadApprovalResponse(queued=True)`까지(411-467행, `        try:\n            result = orchestrator.get_final_render_result(...)`로 시작)를 **그대로 잘라** 새 함수 본문으로 옮긴 뒤 들여쓰기를 한 단계(4칸) 줄인다. 옮긴 본문 안에서 `payload.upload_target` → `upload_target`, `payload.upload_scheduled_summary_ko` → `upload_scheduled_summary_ko` 두 곳만 바꾼다. 결과 모양:

```python
async def queue_upload_approval(
    *,
    request: Request,
    orchestrator: ApiOrchestrator,
    project_id: str,
    job_id: str,
    upload_target: str,
    upload_scheduled_summary_ko: str,
) -> UploadApprovalResponse:
    """완성본을 두고 대표님 결재함(업로드 게이트)에 승인을 **요청**한다 -- 화면 단추와 유진이 같이 쓴다.

    아무것도 실행하지 않는다(결재함 큐에 pending 항목만 넣는다). 승인은 결재함에서 사람이 한다.
    이미 결정된 것(409 `upload_already_decided`), 권리를 모르는 자산(409 `asset_rights_unconfirmed`),
    결재함이 안 닿음(502)은 그대로 `HTTPException`으로 올라간다.
    """
    try:
        result = orchestrator.get_final_render_result(project_id=project_id, job_id=job_id)
        ...  # ← 여기부터 원래 라우트 본문 그대로(위 두 이름만 바뀜), 마지막 줄은
    return UploadApprovalResponse(queued=True)
```

(위 `...` 줄은 설명용이다 — 실제 파일에는 원래 본문 줄들이 그대로 들어간다. 줄을 새로 쓰지 말고 **잘라서 옮긴다**.)

라우트는 다음만 남긴다(docstring은 유지):

```python
    @router.post("/api/projects/{project_id}/final-renders/{job_id}/request-upload-approval")
    async def request_upload_approval(
        project_id: str, job_id: str, payload: UploadApprovalRequest, request: Request
    ) -> UploadApprovalResponse:
        """(원래 docstring 그대로)"""
        return await queue_upload_approval(
            request=request, orchestrator=orchestrator, project_id=project_id, job_id=job_id,
            upload_target=payload.upload_target,
            upload_scheduled_summary_ko=payload.upload_scheduled_summary_ko,
        )
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_upload_approval_request.py` → 전부 통과(동작이 같아야 한다).

- [ ] **Step 3: 의도 모델** — `CreatePreviewLinkOperation` 다음에:

```python
class RequestUploadApprovalOperation(_StrictFrozenModel):
    """업로드 승인을 **요청**한다 -- 출력 화면 `업로드 승인 요청`과 같은 함수.

    **승인은 하지 않는다.** 업로드는 사람 게이트다(2026-08-16 결정, 2026-10-02 경계) -- 이
    의도는 대표님 결재함에 대기 항목을 넣을 뿐이고, 승인하는 의도는 이 파일에 없다(시험이 지킨다).
    `summary_ko`는 결재함에 보일 한 줄(언제·어디에 올릴지)이다.
    """

    intent: Literal["request_upload_approval"]
    summary_ko: str = Field(min_length=1, max_length=2000)
```

유니언·`__all__`(`"RequestUploadApprovalOperation",`를 `"ResolveVariantConflictOperation",` 앞)에 넣는다.

- [ ] **Step 4: 검증기** — adapter: 도메인 import, `STANDALONE_INTENTS`에 `"request_upload_approval"`, 검사(`CreatePreviewLinkOperation` 검사 다음):

```python
        if isinstance(operation, RequestUploadApprovalOperation) and not context.has_current_final_render:
            return "final_render_not_current"
```

- [ ] **Step 5: 적용 (API)** — `director_proposals.py`

import(Task 9의 `session_master_outputs` import 다음 줄):

```python
import functools

import anyio

from videobox_api.routers.outputs import queue_upload_approval
```

(`import functools`·`import anyio`는 파일 맨 위 표준 import 묶음(`import asyncio` 근처)에 두고, `queue_upload_approval` import는 `videobox_api` import 묶음에 둔다.)

`_apply_standalone_intent`의 `create_preview_link` 갈래 다음에:

```python
        if intent == "request_upload_approval":
            # 출력 화면 `업로드 승인 요청`과 같은 함수(routers/outputs.py `queue_upload_approval`).
            # **요청까지만** -- 승인은 결재함에서 대표님이 한다.
            session = store.get_editing_session(project_id=project_id, session_id=session_id)
            state = master_final_render_state(store=store, orchestrator=orchestrator, project_id=project_id, session=session)
            if state is None or state.status != "succeeded":
                raise HTTPException(status_code=409, detail="final_render_not_ready")
            if not state.is_current:
                raise HTTPException(status_code=409, detail="final_render_not_current")
            queued = anyio.from_thread.run(functools.partial(
                queue_upload_approval,
                request=request, orchestrator=orchestrator, project_id=project_id, job_id=state.job_id,
                upload_target="youtube", upload_scheduled_summary_ko=str(getattr(operation, "summary_ko", "")),
            ))
            if not queued.queued:
                return {
                    "status": "upload_approval_not_queued",
                    "notice": "결재함이 연결되어 있지 않아 승인 요청을 올리지 못했어요.",
                }
            return {
                "status": "upload_approval_requested",
                "notice": "업로드 승인을 요청했어요. 승인은 대표님이 결재함에서 해요.",
            }
```

(`anyio.from_thread.run`은 FastAPI가 동기 라우트를 돌리는 스레드풀 안에서만 된다 — 이 적용 라우트가 그렇다. `HTTPException`은 적용 라우트의 `except HTTPException: raise`로 그대로 올라간다.)

- [ ] **Step 6: 스키마·안내문**

스키마(Task 10 줄 다음):

```python
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "request_upload_approval"}, "summary_ko": {"type": "string"}}, "required": ["intent", "summary_ko"]},
```

허용 intent 문장(Task 10 줄 다음):

```python
        "request_upload_approval(업로드 승인을 **요청**만 한다 -- \"유튜브 업로드 승인 요청 올려줘\"가 이것이다), "
```

`_output_catalogue`의 `+ "완성본·내보내기 의도는 **혼자** 싣는다."` **앞**에 한 덩이를 더한다:

```python
        + "'업로드 승인 요청해줘'·'결재 올려줘'는 request_upload_approval이고 summary_ko에 언제·어디에 "
        "올릴지 창작자 말을 한 줄로 적는다. **승인은 유진이 못 한다** -- '업로드 승인해줘'·'올려줘'라고 "
        "해도 승인 요청까지만 하고, 승인은 대표님이 결재함에서 한다고 답한다. 완성본이 없거나 낡으면 "
        "요청도 못 한다. "
```

- [ ] **Step 7: 화면 한 줄** — `yujinEditingSummary.ts`:

```ts
  if (operation.intent === "request_upload_approval") return "업로드 승인을 요청해요. 승인은 결재함에서 해요.";
```

시험:

```ts
  it("업로드는 요청까지만이라고 말한다", () => {
    expect(summary({ intent: "request_upload_approval", summary_ko: "내일" })).toBe("업로드 승인을 요청해요. 승인은 결재함에서 해요.");
  });
```

- [ ] **Step 8: 통과·넓은 검증**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_outputs.py tests/test_upload_approval_request.py` → 통과
Run: `cd apps/web && npx vitest run src/features/editor/workbench/yujinEditingSummary.test.ts` → passed

- [ ] **Step 9: 검증 넷·커밋**

배선: `git grep -n "queue_upload_approval" -- services` → 정의 1, 사용 2(outputs 라우트, director). `git grep -n "approve" -- packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py` → 승인 의도 0건.

```bash
git add services/api/src/videobox_api/routers/outputs.py packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py services/api/src/videobox_api/routers/director_proposals.py apps/web/src/features/editor/workbench/yujinEditingSummary.ts apps/web/src/features/editor/workbench/yujinEditingSummary.test.ts tests/test_yujin_editing_outputs.py
git commit -m "feat(yujin): 말로 업로드 승인 요청(요청까지만, 승인은 결재함) -- 화면과 같은 함수로 뽑음

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 12: 묶음 C 닫기

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_local_conversation.py:56-61`
- Modify: `tests/test_yujin_local_conversation.py`

- [ ] **Step 1: 실패하는 시험** — `tests/test_yujin_local_conversation.py` 끝에:

```python
def test_reply_prompt_knows_outputs_start_for_real_and_never_claims_an_upload_approval() -> None:
    """묶음 C(2026-10-02). 완성본·캡컷 초안·미리보기 링크는 곧바로 시작된다. 업로드는
    **승인 요청까지만** -- 답장이 "승인됐어요/업로드했어요"라고 말하면 사람 게이트를 넘은 척하는 것이다."""
    runtime = _RecordingRuntime()
    YujinLocalConversationService(runtime=runtime).reply(project_id="proj-1", user_text="업로드 승인해줘")

    prompt = runtime.calls[0]["prompt"]
    assert "완성본 만들기" in prompt
    assert "승인은 대표님이 결재함에서" in prompt
    assert "정확히 무엇을 적용할지 되물어라" in prompt
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_local_conversation.py::test_reply_prompt_knows_outputs_start_for_real_and_never_claims_an_upload_approval`
Expected: FAIL — `AssertionError: assert '완성본 만들기' in ...`

- [ ] **Step 2: 답장 문장** — `yujin_local_conversation.py`의 기준 글귀

```python
    "만들기·다시 만들기·펼치기·내보내기를 말로 시키면, 그 편집·렌더는 화면이 "
```

를

```python
    "만들기·다시 만들기·펼치기·내보내기, 완성본 만들기·캡컷 초안 만들기·미리보기 링크 만들기를 말로 시키면, 그 편집·렌더는 화면이 "
```

로 바꾸고, 기준 글귀 `    "다만 화면에 카드로 뜨는 자료 추천(영상·음악·효과음 후보)은 다르다 -- 그건 "` **앞**에:

```python
    "업로드는 다르다 -- 유진은 업로드 **승인 요청**을 결재함에 올리는 것까지만 하고, 승인은 대표님이 "
    "결재함에서 한다. '업로드했다'·'승인됐다'고 말하지 않는다. "
```

Run 같은 시험 → PASS, `tests/test_yujin_local_conversation.py` 전체 → 통과. 커밋:

```bash
git add packages/core-engine/src/videobox_core_engine/yujin_local_conversation.py tests/test_yujin_local_conversation.py
git commit -m "fix(yujin): 답장이 완성본·내보내기를 실행된다고 알고, 업로드는 요청까지만이라고 말하게

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 3: 묶음 C 넓은 검증**

```powershell
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_outputs.py tests/test_session_master_outputs.py tests/test_yujin_editing_basics.py tests/test_upload_approval_request.py tests/test_api_preview_shares.py tests/test_api_final_render_endpoint.py tests/test_api_capcut_draft_export_endpoint.py tests/test_final_render_idempotency.py tests/test_yujin_local_conversation.py tests/test_yujin_editing_short_form.py
cd apps/web; npx vitest run src/features/editor/workbench src/user-copy-policy.test.ts src/task22-parity-owners.test.ts; npx tsc --noEmit; npm run build; cd ../..
```
Expected: 모두 통과.

- [ ] **Step 4: 역방향 — 재빌드·새 편집본 실기·지연**

```powershell
.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild
lms ps
.venv/Scripts/python.exe scripts/measure_yujin_prompt_size.py
.venv/Scripts/python.exe scripts/owner-path/ask_yujin_capabilities.py <project_id> C
.venv/Scripts/python.exe scripts/owner-path/ask_yujin_capabilities.py <project_id> baseline
```
Expected: `6/6 통과`, `3/3 통과`. 수치를 기준선 옆에 적는다(1.5배 넘으면 멈추고 보고 — Task 7 Step 5와 같은 규칙, Task 23 제시).

- [ ] **Step 5: 역방향·동작 — 브라우저**

Ctrl+F5 → 프로젝트 → 편집기 → 유진(새 편집본):
1. "완성본 만들어줘" → 저장 상태 줄과 유진 패널에 `완성본을 만들고 있어요. 다 되면 여기에 알려 드릴게요.` → 끝나면 완료 목록에 `완성본을 만들었어요. 출력 화면에서 볼 수 있어요.` 기다리는 동안에도 입력칸이 잠기지 않는다. `.../apply` 응답은 몇 초 안에 와야 한다(개발자 도구 Network 탭) — 렌더 시간만큼 걸리면 Global Constraint 21 위반이다.
2. 출력 화면에서 같은 완성본이 보이는지(화면 규칙과 같은 것을 골랐는지) 확인.
3. "미리보기 링크 만들어줘" → 저장 상태 줄에 `미리보기 링크를 만들었어요. http://127.0.0.1:5173/preview/...` → 그 주소를 새 탭에서 열어 재생되는지.
4. "캡컷 초안으로 내보내줘" → 끝나면 `캡컷 초안을 만들었어요. 출력 화면에서 캡컷으로 보낼 수 있어요.`
5. "업로드 승인해줘" → 유진 답장이 승인됐다고 말하지 않는다. 편집안이 `request_upload_approval`이면 결재함에 대기 항목 하나(AK 결재함 또는 `docker logs videobox-api --since 5m`의 큐 로그로 확인), 권리 미확인 자산이 있으면 `누가 만들었는지 모르는 자료가 있어…` 문구.
6. "응 그걸로 해줘" → 아무 일도 안 일어나고 되묻는다.

동작: 1번 완성본 파일을 받아 길이·영상 스트림을 잰다:
```powershell
docker exec videobox-api ffprobe -v error -show_entries format=duration -show_entries stream=codec_type,width,height -of compact <완성본 파일>
```
출력 화면 `완성본 만들기`로 같은 편집본을 뽑은 것과 길이·해상도가 같아야 한다.

- [ ] **Step 6: 갭·배선·푸시**

갭: 계획서 묶음 C(C1~C3) 대조. 안 한 것: 캡컷 앱으로 넘기기(`handoff`, 의도적으로 안 엶), 공유 링크 **취소**(화면 `revokePreviewShare` — 되돌릴 수 있는 일이라 F 후보로 넘긴다), 가로·세로 **변형본** 렌더(숏폼은 이미 `render_short_form`, 가로·세로 전체는 F 후보). 두 번 적용(Global Constraint 20)은 Task 4의 편집안 소진으로 막혔다 — 아래 역방향으로 **실물에서** 한 번 더 잰다(시험은 TestClient만 지났다).

역방향(두 번 적용): 재빌드된 컨테이너에서 Step 5의 1번("완성본 만들어줘")이 끝난 **그 편집본**으로 한다(새 편집본에는 그 편집본의 완성본이 없어서 미리보기 링크가 거절된다 — `master_final_render_state`는 편집본 id와 판까지 맞아야 지금 것으로 본다). 브라우저 주소창에서 `project_id`와 `session_id`를 적고 PowerShell에서:
```powershell
@'
import sys
sys.path.insert(0, "scripts/owner-path")
from drive import call
project_id, session_id = sys.argv[1], sys.argv[2]
code, body = call("POST", f"/api/projects/{project_id}/editing-sessions/{session_id}/yujin-editing-proposals", {"instruction": "미리보기 링크 만들어줘"}, timeout=600.0)
print("제안", code, [op.get("intent") for op in (body.get("diff") or {}).get("operations") or []])
url = f"/api/projects/{project_id}/editing-sessions/{session_id}/yujin-editing-proposals/{body['proposal_id']}/apply"
first = call("POST", url, {"expected_revision": int(body["base_session_revision"])})
second = call("POST", url, {"expected_revision": int(body["base_session_revision"])})
print("첫째", first[0], first[1].get("status"), "둘째", second[0], second[1].get("detail"))
'@ | Set-Content -Encoding utf8 $env:TEMP\vb_double_apply.py
.venv/Scripts/python.exe $env:TEMP\vb_double_apply.py <project_id> <session_id>
```
기대: `제안 200 ['create_preview_link']`(201이어도 된다), `첫째 200 preview_share_created 둘째 409 editing_proposal_already_applied`. 출력 화면의 미리보기 링크 목록에 **새 링크가 하나만** 늘었는지 본다. 편집안이 `create_preview_link`가 아니면(완성본이 낡았다는 거절 등) 그 편집본으로 완성본을 다시 만들고 돌린다. 이 시험이 만든 링크는 출력 화면 `링크 끄기`로 끈다.
배선: `git grep -n "render_final_video\|export_capcut_draft\|create_preview_link\|request_upload_approval" -- apps/web/src` → `yujinEditingSummary.ts`에 넷. `git grep -n "final_render_started\|capcut_draft_export_started\|preview_share_created" -- apps/web/src ':!*.test.*'` → `yujinApplyOutcome.ts`.
확인한 뒤 `git push origin main` (정확히 이 명령. 도구 권한이 막으면 **우회하지 말고 멈춘다** — owner에게 `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`에서 `git push origin main`을 직접 실행하거나 허용 규칙 `Bash(git push origin main)`을 추가해 달라고 알리고 기다린다. Global Constraint 18).

---

### Task 13: D1 — 설명 카드·표·도형 얹기/빼기 (여섯 의도)

화면 `PATCH/DELETE .../segments/{id}/explanation-card`(`routers/editing_session.py:851-894`), `.../table-overlay`(`:945-988`), `.../shape-overlay`(`:990-1033`)가 부르는 core 함수(`update_/remove_segment_explanation_card` `editing_session.py:1808-1841`, `update_/remove_segment_table_overlay` `:1983-2016`, `update_/remove_segment_shape_overlay` `:2026-2079`)를 그대로 쓴다. 전부 장면 목록만 바꾸므로 세션 편집형(A형). 글줄은 렌더의 글줄 주입 방어(`da2b66ff2`)를 그대로 지난다 — 여기서 따로 거르지 않는다.

**Files:**
- Modify: `packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py:14-19`(import), 맥락, 검사
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py:16-21`(import), 스키마, 안내문
- Modify: `packages/core-engine/src/videobox_core_engine/editing_session.py`(적용기)
- Modify: `services/api/src/videobox_api/routers/director_proposals.py`(맥락)
- Modify: `apps/web/src/features/editor/workbench/yujinEditingSummary.ts`, `.test.ts`
- Create: `tests/test_yujin_editing_screen_elements.py`

**Interfaces:**
- Consumes: `update_segment_explanation_card(*, session, segment_id, title: str, body: str, text: str)`, `remove_segment_explanation_card(*, session, segment_id)`, `update_segment_table_overlay(*, session, segment_id, columns: list[str], rows: list[list[str]], text: str)`, `remove_segment_table_overlay(...)`, `update_segment_shape_overlay(*, session, segment_id, shape, vertical, horizontal, size, motion="none")`, `remove_segment_shape_overlay(...)`; `overlay_shapes.SHAPE_OVERLAY_SHAPES`, `SHAPE_OVERLAY_MOTION_SET`, `SHAPE_OVERLAY_MOTIONS`, `canonical_shape_overlay_shape(value) -> str`(`overlay_shapes.py:199`)
- Produces: `SetExplanationCardOperation(segment_id, text 1..200, title ""..80, body ""..400)`, `RemoveExplanationCardOperation(segment_id)`, `SetTableOverlayOperation(segment_id, text 1..200, columns: tuple[str,...] ≤6, rows: tuple[tuple[str,...],...] ≤8)`, `RemoveTableOverlayOperation(segment_id)`, `SetShapeOverlayOperation(segment_id, shape: str, vertical/horizontal/size: Literal, motion: str = "none")`, `RemoveShapeOverlayOperation(segment_id)`; `YujinEditingContext.text_overlays_by_segment: tuple[tuple[str, str], ...] = ()`; 거절 이유 `shape_overlay_not_available`, `overlay_not_present`

- [ ] **Step 1: 실패하는 시험** — `tests/test_yujin_editing_screen_elements.py`:

```python
"""묶음 D -- 화면 요소(설명 카드·표·도형·자막 모양·저장한 포맷)를 말로."""
from __future__ import annotations

from pathlib import Path

import pytest

from videobox_core_engine.yujin_editing_proposal_adapter import YujinEditingContext, interpret_yujin_editing_request
from videobox_core_engine.yujin_editing_proposal_service import _editing_prompt
from yujin_chat_fakes import ScriptedEditingProvider, create_and_apply, current_session, plain_session_project

_IDS = ("seg-hook", "seg-middle", "seg-close")


def _response(*operations: dict, revision: int = 3) -> dict:
    return {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "얹어 볼게요.",
        "proposal": {"proposal_id": "p", "base_session_revision": revision, "operations": list(operations)},
    }


def _context(**extra: object) -> YujinEditingContext:
    return YujinEditingContext(session_id="s", session_revision=3, segment_ids=_IDS, **extra)  # type: ignore[arg-type]


def _overlays(app, project_id: str, session_id: str, segment_id: str) -> list[dict]:
    stored = app.state.store.get_editing_session(project_id=project_id, session_id=session_id)
    segment = next(item for item in stored["segments"] if item["segment_id"] == segment_id)
    return [item for item in segment.get("visual_overlays") or [] if isinstance(item, dict)]


# --- 설명 카드·표·도형 --------------------------------------------------------

def test_a_made_up_shape_is_refused_and_removing_what_is_not_there_is_refused() -> None:
    made_up = interpret_yujin_editing_request(
        _response({"intent": "set_shape_overlay", "segment_id": "seg-hook", "shape": "unicorn", "vertical": "top", "horizontal": "right", "size": "small"}),
        _context(),
    )
    nothing_there = interpret_yujin_editing_request(_response({"intent": "remove_table_overlay", "segment_id": "seg-hook"}), _context())
    there = interpret_yujin_editing_request(
        _response({"intent": "remove_table_overlay", "segment_id": "seg-hook"}),
        _context(text_overlays_by_segment=(("seg-hook", "table_overlay"),)),
    )

    assert made_up.reason == "shape_overlay_not_available"
    assert nothing_there.reason == "overlay_not_present"
    assert there.status == "candidate_only"


def test_yujin_puts_an_explanation_card_and_a_table_on_scenes_from_the_real_chat(tmp_path: Path) -> None:
    provider = ScriptedEditingProvider(operations=[
        {"intent": "set_explanation_card", "segment_id": "seg-middle", "text": "핵심: 재고 회전율"},
        {"intent": "set_table_overlay", "segment_id": "seg-close", "text": "가격 비교", "columns": ["회사", "가격"], "rows": [["A사", "3만원"], ["B사", "4만원"]]},
    ])
    app, client, project_id, session = plain_session_project(tmp_path, provider)

    response = create_and_apply(client, project_id, session, "2번 장면에 설명 카드, 3번 장면에 가격 표")

    assert response.status_code == 200, response.text
    card = _overlays(app, project_id, session["session_id"], "seg-middle")
    table = _overlays(app, project_id, session["session_id"], "seg-close")
    assert any(item.get("overlay_type") == "explanation_card" and item.get("text") == "핵심: 재고 회전율" for item in card)
    assert any(item.get("overlay_type") == "table_overlay" and item.get("rows") == [["A사", "3만원"], ["B사", "4만원"]] for item in table)
    # 둘을 한 번에 했어도 되돌리기 한 칸이다.
    assert current_session(client, project_id, session["session_id"])["undo_count"] == 1


def test_the_prompt_lists_the_shapes_and_what_is_on_now() -> None:
    from videobox_core_engine.overlay_shapes import SHAPE_OVERLAY_SHAPES

    prompt = _editing_prompt(instruction="화살표 넣어줘", context=_context(text_overlays_by_segment=(("seg-hook", "explanation_card"),)))
    assert "set_shape_overlay" in prompt
    assert sorted(SHAPE_OVERLAY_SHAPES)[0] in prompt
    assert "seg-hook(설명 카드)" in prompt
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_screen_elements.py::test_a_made_up_shape_is_refused_and_removing_what_is_not_there_is_refused`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'text_overlays_by_segment'`

- [ ] **Step 2: 의도 모델** — `RequestUploadApprovalOperation` 다음에:

```python
class SetExplanationCardOperation(_SegmentOperation):
    """장면 위에 설명 카드를 얹는다 -- 화면 `설명 카드`(`PATCH .../explanation-card`)와 같은 함수.

    `text`는 화면에 크게 뜰 한 줄, `title`·`body`는 있으면 싣는다. 이미 있으면 바꾼다.
    """

    intent: Literal["set_explanation_card"]
    text: str = Field(min_length=1, max_length=200)
    title: str = Field(default="", max_length=80)
    body: str = Field(default="", max_length=400)


class RemoveExplanationCardOperation(_SegmentOperation):
    intent: Literal["remove_explanation_card"]


_TableRow = Annotated[tuple[str, ...], BeforeValidator(_list_to_tuple)]


class SetTableOverlayOperation(_SegmentOperation):
    """장면 위에 표를 얹는다 -- 화면 `표`(`PATCH .../table-overlay`)와 같은 함수.

    칸 수 상한(머리글 6, 줄 8)은 1920x1080 안에 읽히게 두는 값이다(인포그래픽의 여덟 칸과
    같은 이유). **숫자는 창작자가 말한 것만** -- 안내문이 지어내지 말라고 못박는다.
    """

    intent: Literal["set_table_overlay"]
    text: str = Field(min_length=1, max_length=200)
    columns: Annotated[tuple[str, ...], BeforeValidator(_list_to_tuple)] = Field(default=(), max_length=6)
    rows: Annotated[tuple[_TableRow, ...], BeforeValidator(_list_to_tuple)] = Field(default=(), max_length=8)


class RemoveTableOverlayOperation(_SegmentOperation):
    intent: Literal["remove_table_overlay"]


class SetShapeOverlayOperation(_SegmentOperation):
    """장면 위에 표시(화살표·강조 상자 등)를 얹는다 -- 화면 `도형`(`PATCH .../shape-overlay`)과 같은 함수.

    `shape`·`motion`이 `str`인 이유는 색감과 같다 -- 목록 원본은 `overlay_shapes`이고 대조는 검증기가 한다.
    """

    intent: Literal["set_shape_overlay"]
    shape: str = Field(min_length=1, max_length=32)
    vertical: Literal["top", "middle", "bottom"]
    horizontal: Literal["left", "center", "right"]
    size: Literal["small", "medium", "large"]
    motion: str = Field(default="none", min_length=1, max_length=32)


class RemoveShapeOverlayOperation(_SegmentOperation):
    intent: Literal["remove_shape_overlay"]
```

유니언에 여섯을 넣고, `__all__`에 `"RemoveExplanationCardOperation", "RemoveShapeOverlayOperation", "RemoveTableOverlayOperation", "SetExplanationCardOperation", "SetShapeOverlayOperation", "SetTableOverlayOperation"`을 알파벳 자리에 넣는다.

- [ ] **Step 3: 검증기·맥락** — adapter

`from videobox_core_engine.overlay_shapes import (` 묶음(14-19행)을:

```python
from videobox_core_engine.overlay_shapes import (
    SHAPE_OVERLAY_HORIZONTALS,
    SHAPE_OVERLAY_MOTION_SET,
    SHAPE_OVERLAY_SHAPES,
    SHAPE_OVERLAY_SIZES,
    SHAPE_OVERLAY_VERTICALS,
    canonical_shape_overlay_shape,
)
```

로 바꾸고 도메인 import에 여섯을 더한다. 맥락 필드(`has_current_final_render` 다음):

```python
    #: 지금 장면 위에 얹힌 설명 카드·표·도형 -- `(segment_id, "explanation_card"|"table_overlay"|"shape_overlay")`.
    #: 목록과 지금 값은 한 쌍이다: 이게 없으면 "표 빼줘"에 얹힌 표가 없다고 답한다.
    text_overlays_by_segment: tuple[tuple[str, str], ...] = ()
```

검사(`RequestUploadApprovalOperation` 검사 다음):

```python
        if isinstance(operation, SetShapeOverlayOperation):
            if canonical_shape_overlay_shape(operation.shape) not in SHAPE_OVERLAY_SHAPES:
                return "shape_overlay_not_available"
            if operation.motion.strip().lower() not in SHAPE_OVERLAY_MOTION_SET:
                return "shape_overlay_not_available"
        removal_kind = {
            RemoveExplanationCardOperation: "explanation_card",
            RemoveTableOverlayOperation: "table_overlay",
            RemoveShapeOverlayOperation: "shape_overlay",
        }.get(type(operation))
        if removal_kind is not None and (operation.segment_id, removal_kind) not in set(context.text_overlays_by_segment):
            return "overlay_not_present"
```

`director_proposals.py` 맥락(`has_current_final_render=...` 다음):

```python
            text_overlays_by_segment=tuple(
                (str(item["segment_id"]), {"table_card": "table_overlay"}.get(kind, kind))
                for item in session.get("segments", [])
                if isinstance(item, dict) and item.get("segment_id")
                for overlay in (item.get("visual_overlays") or [])
                if isinstance(overlay, dict)
                for kind in [str(overlay.get("overlay_type") or "")]
                if kind in {"explanation_card", "table_overlay", "table_card", "shape_overlay"}
            ),
```

(`table_card`는 옛 이름이다 — `editing_session.py:2366-2370` `_OVERLAY_TYPE_ALIASES`.)

- [ ] **Step 4: 적용기** — `editing_session.py` `_apply_yujin_editing_operations`: import에 여섯을 더하고, `SetTrackStateOperation` 갈래 다음에:

```python
        elif isinstance(operation, SetExplanationCardOperation):
            # 화면 설명 카드와 같은 함수.
            working = update_segment_explanation_card(
                session=working, segment_id=operation.segment_id,
                title=operation.title, body=operation.body, text=operation.text,
            )
        elif isinstance(operation, RemoveExplanationCardOperation):
            working = remove_segment_explanation_card(session=working, segment_id=operation.segment_id)
        elif isinstance(operation, SetTableOverlayOperation):
            working = update_segment_table_overlay(
                session=working, segment_id=operation.segment_id,
                columns=list(operation.columns), rows=[list(row) for row in operation.rows], text=operation.text,
            )
        elif isinstance(operation, RemoveTableOverlayOperation):
            working = remove_segment_table_overlay(session=working, segment_id=operation.segment_id)
        elif isinstance(operation, SetShapeOverlayOperation):
            working = update_segment_shape_overlay(
                session=working, segment_id=operation.segment_id,
                shape=canonical_shape_overlay_shape(operation.shape),
                vertical=operation.vertical, horizontal=operation.horizontal, size=operation.size,
                motion=operation.motion,
            )
        elif isinstance(operation, RemoveShapeOverlayOperation):
            working = remove_segment_shape_overlay(session=working, segment_id=operation.segment_id)
```

`canonical_shape_overlay_shape`가 `editing_session.py` 16행의 `from videobox_core_engine.overlay_shapes import (  # noqa: F401` 묶음에 없으면 그 묶음에 더한다.

- [ ] **Step 5: 스키마·안내문** — `yujin_editing_proposal_service.py`

import 묶음(16-21행)에 `SHAPE_OVERLAY_SHAPES,`를 더한다. 스키마(Task 11 줄 다음):

```python
        # 묶음 D(2026-10-02). 표의 숫자는 창작자가 말한 것만 -- 안내문이 못박는다.
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "set_explanation_card"}, "segment_id": {"type": "string"}, "text": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string"}}, "required": ["intent", "segment_id", "text"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "remove_explanation_card"}, "segment_id": {"type": "string"}}, "required": ["intent", "segment_id"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "set_table_overlay"}, "segment_id": {"type": "string"}, "text": {"type": "string"}, "columns": {"type": "array", "items": {"type": "string"}, "maxItems": 6}, "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}, "maxItems": 8}}, "required": ["intent", "segment_id", "text"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "remove_table_overlay"}, "segment_id": {"type": "string"}}, "required": ["intent", "segment_id"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "set_shape_overlay"}, "segment_id": {"type": "string"}, "shape": {"enum": sorted(SHAPE_OVERLAY_SHAPES)}, "vertical": {"enum": sorted(SHAPE_OVERLAY_VERTICALS)}, "horizontal": {"enum": sorted(SHAPE_OVERLAY_HORIZONTALS)}, "size": {"enum": sorted(SHAPE_OVERLAY_SIZES)}, "motion": {"enum": list(SHAPE_OVERLAY_MOTIONS)}}, "required": ["intent", "segment_id", "shape", "vertical", "horizontal", "size"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "remove_shape_overlay"}, "segment_id": {"type": "string"}}, "required": ["intent", "segment_id"]},
```

허용 intent 문장(Task 11 줄 다음):

```python
        "set_explanation_card/remove_explanation_card(설명 카드 얹기·빼기 -- \"2번 장면에 핵심 한 줄 카드 띄워줘\"), "
        "set_table_overlay/remove_table_overlay(표 얹기·빼기), set_shape_overlay/remove_shape_overlay(화살표·강조 상자 같은 표시 얹기·빼기), "
```

새 함수(`_output_catalogue` 다음):

```python
_TEXT_OVERLAY_LABELS: dict[str, str] = {"explanation_card": "설명 카드", "table_overlay": "표", "shape_overlay": "표시"}


def _screen_element_catalogue(context: YujinEditingContext) -> str:
    """설명 카드·표·도형(묶음 D1). 고를 수 있는 표시 목록과 **지금 얹힌 것**을 한 쌍으로 준다."""
    shapes = ", ".join(sorted(SHAPE_OVERLAY_SHAPES))
    motions = ", ".join(f"{value}({_IMAGE_OVERLAY_PRESET_LABELS.get(value, value)})" for value in SHAPE_OVERLAY_MOTIONS)
    current = ", ".join(
        f"{segment_id}({_TEXT_OVERLAY_LABELS.get(kind, kind)})" for segment_id, kind in context.text_overlays_by_segment
    ) or "없음"
    return (
        "설명 카드는 set_explanation_card다 -- text는 화면에 크게 뜰 한 줄, title·body는 창작자가 말했을 때만. "
        "표는 set_table_overlay다 -- text는 표 제목 한 줄, columns는 머리글(최대 6), rows는 줄마다 칸 목록(최대 8줄). "
        "**표와 카드의 숫자·사실은 창작자가 말한 것만 쓴다 -- 지어내지 않는다.** 모르면 되묻는다. "
        f"표시는 set_shape_overlay다 -- shape는 이 중 하나: {shapes}. 자리 vertical(top·middle·bottom)·"
        f"horizontal(left·center·right), 크기 size(small·medium·large), 움직임 motion: {motions}. "
        "빼는 것은 remove_explanation_card·remove_table_overlay·remove_shape_overlay. "
        f"지금 얹힌 것: {current}."
    )
```

`_editing_prompt` 안 `        f"{_output_catalogue(context)} "` 다음 줄에 `        f"{_screen_element_catalogue(context)} "`.

- [ ] **Step 6: 화면 한 줄** — `yujinEditingSummary.ts`:

```ts
  // 묶음 D(2026-10-02): 화면 요소.
  if (operation.intent === "set_explanation_card") return "설명 카드를 얹어요.";
  if (operation.intent === "remove_explanation_card") return "설명 카드를 빼요.";
  if (operation.intent === "set_table_overlay") return "표를 얹어요.";
  if (operation.intent === "remove_table_overlay") return "표를 빼요.";
  if (operation.intent === "set_shape_overlay") return "표시를 얹어요.";
  if (operation.intent === "remove_shape_overlay") return "표시를 빼요.";
```

시험:

```ts
  it("설명 카드·표·표시를 얹고 빼는 것을 말한다", () => {
    expect(summary({ intent: "set_explanation_card", segment_id: "s", text: "a" })).toBe("설명 카드를 얹어요.");
    expect(summary({ intent: "remove_table_overlay", segment_id: "s" })).toBe("표를 빼요.");
    expect(summary({ intent: "set_shape_overlay", segment_id: "s", shape: "underline" })).toBe("표시를 얹어요.");
  });
```

- [ ] **Step 7: 통과·넓은 검증·커밋**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_screen_elements.py tests/test_yujin_editing_basics.py tests/test_editor_timeline_mutations.py` → 통과
Run: `cd apps/web && npx vitest run src/features/editor/workbench/yujinEditingSummary.test.ts` → passed
배선: `git grep -n "set_explanation_card\|set_table_overlay\|set_shape_overlay" -- packages services apps/web/src`.

```bash
git add packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py packages/core-engine/src/videobox_core_engine/editing_session.py services/api/src/videobox_api/routers/director_proposals.py apps/web/src/features/editor/workbench/yujinEditingSummary.ts apps/web/src/features/editor/workbench/yujinEditingSummary.test.ts tests/test_yujin_editing_screen_elements.py
git commit -m "feat(yujin): 말로 설명 카드·표·표시 얹고 빼기 -- 화면과 같은 함수, 지금 얹힌 것과 한 쌍

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 14: D2 — 자막 모양 전체(`set_caption_style`: 색·외곽선·배경·위치·정렬·굵게·기울임)

지금 유진은 글꼴·크기만 바꾼다(`set_caption_font`). 화면 `PATCH .../caption-style`(`routers/editing_session.py:189-199`)의 `CaptionStyleMutationRequest.style`(`models.py:1181-1185`)은 `CaptionStyle`(`packages/domain-models/src/videobox_domain_models/caption_style.py:21-77`)의 모든 칸을 받는다. 같은 `update_caption_style(..., scope="whole_project")`로 **지금 모양 위에 말한 칸만** 얹는다(`set_caption_font` 적용기 `editing_session.py:1190-1205`와 같은 방식). **함정**: `caption_style`은 세션 맨 위 열쇠라 `_YUJIN_SESSION_LEVEL_KEYS`에 있어야 맨 위 값이 저장된다 — Task 6 Step 0이 `set_caption_font`로 이 결함을 재현하고 이미 넣었다. 이 Task의 시험은 새 의도도 같은 길로 저장되는지를 본다.

**Files:**
- Modify: `packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py`(맥락)
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py`
- Modify: `packages/core-engine/src/videobox_core_engine/editing_session.py`(적용기, `_YUJIN_SESSION_LEVEL_KEYS`)
- Modify: `services/api/src/videobox_api/routers/director_proposals.py`(맥락)
- Modify: `apps/web/src/features/editor/workbench/yujinEditingSummary.ts`, `.test.ts`
- Modify: `tests/test_yujin_editing_screen_elements.py`

**Interfaces:**
- Consumes: `update_caption_style(*, session, style: dict, scope: str, segment_ids: list[str])`; `CaptionStyle` 범위(색 `#RRGGBBAA`, 외곽선 0~12, 위치 0~100, 정렬 left/center/right)
- Produces: `SetCaptionStyleOperation(intent: Literal["set_caption_style"], text_color/outline_color/background_color: str|None(#RRGGBBAA), outline_width_px: int|None 0..12, position_y_percent: int|None 0..100, horizontal_align: Literal|None, bold: bool|None, italic: bool|None)` — 하나 이상 필수; `YujinEditingContext.caption_style_now: tuple[tuple[str, str], ...] = ()`(`_YUJIN_SESSION_LEVEL_KEYS`는 Task 6이 이미 `caption_style`까지 담았다 — 바꾸지 않는다)

- [ ] **Step 1: 실패하는 시험** — `tests/test_yujin_editing_screen_elements.py` 끝에:

```python
# --- 자막 모양 ----------------------------------------------------------------

def test_caption_style_needs_a_change_and_real_colors() -> None:
    nothing = interpret_yujin_editing_request(_response({"intent": "set_caption_style"}), _context())
    bad_color = interpret_yujin_editing_request(_response({"intent": "set_caption_style", "text_color": "yellow"}), _context())
    fine = interpret_yujin_editing_request(_response({"intent": "set_caption_style", "text_color": "#FFE600FF", "position_y_percent": 12}), _context())

    assert nothing.reason == "invalid_editing_response"
    assert bad_color.reason == "invalid_editing_response"
    assert fine.status == "candidate_only"


def test_yujin_changes_only_the_caption_parts_it_was_told_and_the_whole_project_keeps_it(tmp_path: Path) -> None:
    provider = ScriptedEditingProvider(operations=[{"intent": "set_caption_style", "text_color": "#FFE600FF"}])
    app, client, project_id, session = plain_session_project(
        tmp_path, provider, extra_session={"caption_style": {"font_size_px": 70, "outline_width_px": 5}},
    )

    response = create_and_apply(client, project_id, session, "자막 노란색으로 바꿔줘")

    assert response.status_code == 200, response.text
    after = current_session(client, project_id, session["session_id"])
    # 맨 위 값이 저장된다(예전에는 `mutate`가 장면 목록만 옮겨 이 값이 버려졌다).
    assert after["caption_style"]["text_color"] == "#FFE600FF"
    # 말 안 한 칸은 그대로다.
    assert after["caption_style"]["font_size_px"] == 70
    assert after["caption_style"]["outline_width_px"] == 5

    provider.operations = [{"intent": "undo_last_edit"}]
    assert create_and_apply(client, project_id, session, "방금 거 되돌려줘").status_code == 200
    assert current_session(client, project_id, session["session_id"])["caption_style"].get("text_color") != "#FFE600FF"


def test_the_prompt_maps_color_and_position_words() -> None:
    prompt = _editing_prompt(instruction="자막 노랗게", context=_context(caption_style_now=(("text_color", "#FFFFFFFF"),)))
    assert "set_caption_style" in prompt
    assert "노란색 #FFE600FF" in prompt
    assert "위 12" in prompt
    assert "text_color=#FFFFFFFF" in prompt
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_screen_elements.py::test_caption_style_needs_a_change_and_real_colors`
Expected: FAIL — `fine.status` 가 `rejected`(모르는 intent)

- [ ] **Step 2: 의도 모델** — `RemoveShapeOverlayOperation` 다음에:

```python
_RGBA_PATTERN = r"^#[0-9A-Fa-f]{8}$"


class SetCaptionStyleOperation(_StrictFrozenModel):
    """자막 모양(색·외곽선·배경·위치·정렬·굵게·기울임) -- 화면 자막 모양 칸과 같은 함수, **편집본 전체**.

    글꼴·크기는 `set_caption_font`가 맡는다(이미 있다). 말한 칸만 싣는다 -- 빈칸을 채우면 맞춰 둔
    나머지가 조용히 바뀐다(`set_caption_font`에서 겪은 일). 범위는 `CaptionStyle`과 같다.
    """

    intent: Literal["set_caption_style"]
    text_color: str | None = Field(default=None, pattern=_RGBA_PATTERN)
    outline_color: str | None = Field(default=None, pattern=_RGBA_PATTERN)
    background_color: str | None = Field(default=None, pattern=_RGBA_PATTERN)
    outline_width_px: int | None = Field(default=None, ge=0, le=12)
    position_y_percent: int | None = Field(default=None, ge=0, le=100)
    horizontal_align: Literal["left", "center", "right"] | None = None
    bold: bool | None = None
    italic: bool | None = None

    @model_validator(mode="after")
    def asks_for_at_least_one(self) -> "SetCaptionStyleOperation":
        if all(value is None for value in self.model_dump(exclude={"intent"}).values()):
            raise ValueError("caption_style_needs_a_change")
        return self
```

유니언·`__all__`(`"SetCaptionStyleOperation",`를 `"SetCaptionTextOperation",` 앞)에 넣는다.

- [ ] **Step 3: 맥락** — adapter 맥락 필드(`text_overlays_by_segment` 다음):

```python
    #: 지금 자막 모양 중 유진이 바꿀 수 있는 칸의 값 -- `(칸 이름, 값)`. 목록과 지금 값은 한 쌍.
    caption_style_now: tuple[tuple[str, str], ...] = ()
```

(`set_caption_style`은 장면 무관이라 Task 2의 `not hasattr(operation, "segment_id")` 갈래가 열쇠를 만든다. 따로 검사할 것은 없다 — 범위는 모델이 막는다.)

`director_proposals.py` 맥락(`text_overlays_by_segment=` 블록 다음):

```python
            caption_style_now=tuple(
                (key, str(value))
                for style in [session.get("caption_style") if isinstance(session.get("caption_style"), dict) else {}]
                for key, value in sorted(style.items())
                if key in {"text_color", "outline_color", "background_color", "outline_width_px", "position_y_percent", "horizontal_align", "bold", "italic"}
            ),
```

- [ ] **Step 4: 적용기** — `editing_session.py`: import에 `SetCaptionStyleOperation,`, Task 13의 `RemoveShapeOverlayOperation` 갈래 다음에:

```python
        elif isinstance(operation, SetCaptionStyleOperation):
            # `set_caption_font`와 같은 방식 -- 지금 모양 위에 말한 칸만 얹고 편집본 전체에 건다.
            current = working.get("caption_style")
            style = dict(current) if isinstance(current, dict) else {}
            style.update({key: value for key, value in operation.model_dump(exclude={"intent"}).items() if value is not None})
            working = update_caption_style(session=working, style=style, scope="whole_project", segment_ids=[])
```

`_YUJIN_SESSION_LEVEL_KEYS`는 **Task 6에서 이미** `(SESSION_TRACK_STATES_KEY, "caption_style")`이다 — 고치지 않는다. 확인만 한다: `git grep -n "_YUJIN_SESSION_LEVEL_KEYS: tuple" -- packages/core-engine/src/videobox_core_engine/editing_session.py`에 `"caption_style"`이 있어야 한다. 없으면 Task 6 Step 0~5가 덜 된 것이니 멈추고 보고한다(`editing_transactions._snapshot`이 `caption_style`을 담으므로 되돌리기도 된다).

- [ ] **Step 5: 스키마·안내문**

스키마(Task 13 줄 다음):

```python
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "set_caption_style"}, "text_color": {"type": "string", "pattern": "^#[0-9A-Fa-f]{8}$"}, "outline_color": {"type": "string", "pattern": "^#[0-9A-Fa-f]{8}$"}, "background_color": {"type": "string", "pattern": "^#[0-9A-Fa-f]{8}$"}, "outline_width_px": {"type": "integer", "minimum": 0, "maximum": 12}, "position_y_percent": {"type": "integer", "minimum": 0, "maximum": 100}, "horizontal_align": {"enum": ["left", "center", "right"]}, "bold": {"type": "boolean"}, "italic": {"type": "boolean"}}, "required": ["intent"]},
```

허용 intent 문장 — 기존 `"set_caption_font(자막 글꼴·크기), "`를 `"set_caption_font(자막 글꼴·크기), set_caption_style(자막 색·외곽선·배경·위치·정렬·굵게·기울임 -- \"자막 노랗게 해줘\"가 이것이다), "`로 바꾼다.

새 함수(`_screen_element_catalogue` 다음):

```python
def _caption_style_catalogue(context: YujinEditingContext) -> str:
    """자막 모양(묶음 D2). 창작자는 색 코드를 말하지 않는다 -- 낱말 -> 값 표와 **지금 값**을 같이 준다."""
    current = ", ".join(f"{key}={value}" for key, value in context.caption_style_now) or "기본값"
    return (
        "자막 색·외곽선·배경·위치·정렬·굵게·기울임은 set_caption_style이다(편집본 전체, 말한 칸만). "
        "색은 #RRGGBBAA로 싣는다: 흰색 #FFFFFFFF, 검은색 #000000FF, 노란색 #FFE600FF, 빨간색 #FF3B30FF, "
        "주황색 #FF9500FF, 초록색 #34C759FF, 파란색 #0A84FFFF, 하늘색 #5AC8FAFF, 분홍색 #FF6FB5FF, 회색 #8E8E93FF. "
        "글자 색은 text_color, 테두리 색은 outline_color, 테두리 두께는 outline_width_px(0~12, '테두리 없애줘'는 0), "
        "글자 뒤 배경은 background_color('배경 없애줘'는 #00000000, '반투명 검은 배경'은 #00000099). "
        "위치 position_y_percent: 위 12, 가운데 50, 아래 88. 정렬 horizontal_align: left·center·right. "
        "굵게 bold, 기울임 italic(true/false). 글꼴·크기는 set_caption_font다. "
        f"지금 값: {current}."
    )
```

`_editing_prompt` 안 `        f"{_screen_element_catalogue(context)} "` 다음 줄에 `        f"{_caption_style_catalogue(context)} "`.

- [ ] **Step 6: 화면 한 줄** — `yujinEditingSummary.ts`의 D1 줄들 다음:

```ts
  if (operation.intent === "set_caption_style") return "자막 모양을 바꿔요.";
```

시험:

```ts
  it("자막 모양 바꾸기를 말한다", () => {
    expect(summary({ intent: "set_caption_style", text_color: "#FFE600FF" })).toBe("자막 모양을 바꿔요.");
  });
```

- [ ] **Step 7: 통과·넓은 검증·커밋**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_screen_elements.py tests/test_yujin_caption_font.py tests/test_yujin_editing_basics.py tests/test_editor_timeline_mutations.py tests/test_api_format_templates.py` → 통과(`set_caption_font`가 이제 맨 위 값도 남긴다 — 기존 시험이 "맨 위 값은 그대로"를 단정하고 있으면 그 시험이 옛 결함을 고정한 것이다. 고치기 전에 보고서에 적는다)
Run: `cd apps/web && npx vitest run src/features/editor/workbench/yujinEditingSummary.test.ts` → passed

```bash
git add packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py packages/core-engine/src/videobox_core_engine/editing_session.py services/api/src/videobox_api/routers/director_proposals.py apps/web/src/features/editor/workbench/yujinEditingSummary.ts apps/web/src/features/editor/workbench/yujinEditingSummary.test.ts tests/test_yujin_editing_screen_elements.py
git commit -m "feat(yujin): 말로 자막 색·외곽선·배경·위치 -- 편집본 전체 모양이 실제로 저장되게

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 15: D3 — 저장한 포맷 입히기(`apply_format_template`)

화면 포맷 카드의 `적용`(`api.ts` `saveFormatTemplate` 옆, `POST /api/projects/{p}/format-templates/{template_id}/apply` — `services/api/src/videobox_api/routers/format_templates.py:68-104`)의 본문을 **함수로 뽑아** 화면과 유진이 같이 부른다. 적용은 자막 모양만 바꾼다(그 라우트 머리말).

**Files:**
- Modify: `services/api/src/videobox_api/routers/format_templates.py:68-104`(본문 → `apply_saved_format_template_to_session`)
- Modify: `packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py`
- Modify: `services/api/src/videobox_api/routers/director_proposals.py`
- Modify: `apps/web/src/features/editor/workbench/yujinEditingSummary.ts`, `.test.ts`
- Modify: `tests/test_yujin_editing_screen_elements.py`

**Interfaces:**
- Consumes: `request.app.state.format_template_store`(`main.py:1619`, `FormatTemplateStore.list_templates() -> list[dict]`(`template_id`, `name`), `get_template(*, template_id)`), `apply_format_template`, `FormatTemplateError`, `orchestrator.update_caption_style(...)`
- Produces: `apply_saved_format_template_to_session(*, orchestrator, template_store, project_id: str, session_id: str, template_id: str, expected_revision: int) -> dict`(저장된 세션); `ApplyFormatTemplateOperation(intent: Literal["apply_format_template"], template_id: str)`; `YujinEditingContext.format_templates: tuple[tuple[str, str], ...] = ()`; 거절 이유 `format_template_not_available`

- [ ] **Step 1: 실패하는 시험** — `tests/test_yujin_editing_screen_elements.py` 끝에:

```python
# --- 저장한 포맷 ----------------------------------------------------------------

def test_a_format_that_is_not_saved_is_refused() -> None:
    made_up = interpret_yujin_editing_request(_response({"intent": "apply_format_template", "template_id": "nope"}), _context())
    saved = interpret_yujin_editing_request(
        _response({"intent": "apply_format_template", "template_id": "format_template_1"}),
        _context(format_templates=(("format_template_1", "셀러 교육"),)),
    )
    assert made_up.reason == "format_template_not_available"
    assert saved.status == "candidate_only"


def test_yujin_puts_a_saved_format_on_another_edit_from_the_real_chat(tmp_path: Path) -> None:
    from videobox_core_engine.format_template import format_template_from_session

    provider = ScriptedEditingProvider(operations=None)
    app, client, project_id, session = plain_session_project(tmp_path, provider)
    styled = {"segments": [{"segment_id": "s1", "caption_text": "a", "start_sec": 0.0, "end_sec": 2.0}],
              "caption_style": {"text_color": "#FFE600FF", "font_size_px": 70}}
    # 시험 세션의 타임라인(`timeline-source`)은 실제로 없어서 저장 라우트 대신 저장소에 바로 넣는다.
    template = app.state.format_template_store.save_template(
        template=format_template_from_session(name="노란 자막", session=styled, timeline=None),
    )
    provider.operations = [{"intent": "apply_format_template", "template_id": template["template_id"]}]

    response = create_and_apply(client, project_id, session, "노란 자막 포맷 입혀줘")

    assert response.status_code == 200, response.text
    assert current_session(client, project_id, session["session_id"])["caption_style"]["text_color"] == "#FFE600FF"
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_screen_elements.py::test_a_format_that_is_not_saved_is_refused`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'format_templates'`

- [ ] **Step 2: 라우트 본문을 함수로** — `format_templates.py`

`def build_format_templates_router(` **앞**에:

```python
def apply_saved_format_template_to_session(
    *, orchestrator: Any, template_store: FormatTemplateStore, project_id: str, session_id: str,
    template_id: str, expected_revision: int,
) -> dict[str, Any]:
    """저장한 포맷의 자막 모양을 편집본에 입힌다 -- 화면 `적용`과 유진이 같이 쓴다."""
    template = template_store.get_template(template_id=template_id)
    session = orchestrator.pipeline.store.get_editing_session(project_id=project_id, session_id=session_id)
    applied = apply_format_template(session=session, template=template)
    # 자막 모양이 빈 포맷을 그대로 흘리면 `CaptionStyle.from_dict({})`가 기본값으로 장면마다 손본
    # 모양까지 전부 덮어쓴다. 입힐 모양이 없으면 입히지 않고 그렇게 말한다.
    if not applied.get("caption_style"):
        raise FormatTemplateError(
            "이 포맷에는 저장된 자막 모양이 없어요. 자막 모양을 정한 편집본에서 다시 저장해 주세요."
        )
    # 장면이 없는 편집본에는 기본값만 바꾼다(`whole_project`는 바꿀 장면이 없으면 에러다).
    has_segments = any(isinstance(item, dict) for item in session.get("segments", []))
    return orchestrator.update_caption_style(
        project_id=project_id,
        session_id=session_id,
        style=applied.get("caption_style") or {},
        scope="whole_project" if has_segments else "project_default",
        segment_ids=[],
        expected_revision=expected_revision,
    )
```

라우트 `apply_saved_format_template`의 `try:` 본문을 다음으로 바꾼다(주석은 새 함수로 옮겼다):

```python
        try:
            updated = apply_saved_format_template_to_session(
                orchestrator=orchestrator, template_store=template_store, project_id=project_id,
                session_id=payload.session_id, template_id=template_id, expected_revision=payload.expected_revision,
            )
            return {"template_id": template_id, "session": updated}
        except Exception as exc:
            raise _http_error(exc) from exc
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_api_format_templates.py` → 통과(동작 같음).

- [ ] **Step 3: 의도 모델** — `SetCaptionStyleOperation` 다음:

```python
class ApplyFormatTemplateOperation(_StrictFrozenModel):
    """저장한 포맷(자막 모양)을 이 편집본에 입힌다 -- 화면 포맷 카드 `적용`과 같은 함수.

    `template_id`는 맥락이 보여 준 저장 목록 안의 값만 된다(지어내면 검증기가 막는다).
    """

    intent: Literal["apply_format_template"]
    template_id: str = Field(min_length=1, max_length=128)
```

유니언·`__all__`(`"ApplyFormatTemplateOperation",`를 `"ApplyMediaOperation",` 앞).

- [ ] **Step 4: 검증기·맥락** — adapter: 도메인 import, `STANDALONE_INTENTS`에 `"apply_format_template"`, 맥락 필드(`caption_style_now` 다음):

```python
    #: 저장해 둔 포맷 `(template_id, 이름)`. 최근 것부터 20개.
    format_templates: tuple[tuple[str, str], ...] = ()
```

검사:

```python
        if isinstance(operation, ApplyFormatTemplateOperation) and operation.template_id not in {
            template_id for template_id, _name in context.format_templates
        }:
            return "format_template_not_available"
```

`director_proposals.py` — import `from videobox_api.routers.format_templates import apply_saved_format_template_to_session`(Task 11의 outputs import 다음). 맥락(`caption_style_now=` 블록 다음):

```python
            format_templates=tuple(
                (str(item["template_id"]), str(item.get("name") or ""))
                for item in (
                    request.app.state.format_template_store.list_templates()[:20]
                    if getattr(request.app.state, "format_template_store", None) is not None
                    else []
                )
            ),
```

`_apply_standalone_intent`의 `request_upload_approval` 갈래 다음:

```python
        if intent == "apply_format_template":
            # 화면 포맷 카드 `적용`과 같은 함수(routers/format_templates.py).
            return apply_saved_format_template_to_session(
                orchestrator=orchestrator, template_store=request.app.state.format_template_store,
                project_id=project_id, session_id=session_id,
                template_id=str(getattr(operation, "template_id", "")), expected_revision=expected_session_revision,
            )
```

(`FormatTemplateError`는 `ValueError`의 자식이다(`packages/core-engine/src/videobox_core_engine/format_template.py:17`) — 적용 라우트의 `except (KeyError, ValueError)`가 422로 바꾼다. 없는 `template_id`는 `KeyError`로 같은 자리에서 422가 된다.)

- [ ] **Step 5: 스키마·안내문**

스키마:

```python
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "apply_format_template"}, "template_id": {"type": "string"}}, "required": ["intent", "template_id"]},
```

허용 intent 문장: `"apply_format_template(저장한 포맷의 자막 모양을 입힌다 -- \"저번 포맷 입혀줘\"가 이것이다), "`.

`_caption_style_catalogue`의 반환 문자열 끝 `f"지금 값: {current}."`를 다음으로 바꾼다:

```python
        f"지금 값: {current}. "
        + (
            "저장한 포맷(자막 모양 묶음): "
            + ", ".join(f"{template_id}({name})" for template_id, name in context.format_templates)
            + " -- '그 포맷 입혀줘'는 apply_format_template이고 template_id는 이 목록 값만 쓴다(혼자 싣는다)."
            if context.format_templates
            else "저장한 포맷이 없다 -- 포맷을 입혀 달라고 하면 먼저 화면에서 포맷을 저장해 달라고 답한다."
        )
```

- [ ] **Step 6: 화면 한 줄·통과·커밋**

`yujinEditingSummary.ts`: `if (operation.intent === "apply_format_template") return "저장한 포맷을 입혀요.";` + 시험

```ts
  it("포맷 입히기를 말한다", () => {
    expect(summary({ intent: "apply_format_template", template_id: "t" })).toBe("저장한 포맷을 입혀요.");
  });
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_screen_elements.py tests/test_api_format_templates.py` → 통과
Run: `cd apps/web && npx vitest run src/features/editor/workbench/yujinEditingSummary.test.ts` → passed

```bash
git add services/api/src/videobox_api/routers/format_templates.py packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py services/api/src/videobox_api/routers/director_proposals.py apps/web/src/features/editor/workbench/yujinEditingSummary.ts apps/web/src/features/editor/workbench/yujinEditingSummary.test.ts tests/test_yujin_editing_screen_elements.py
git commit -m "feat(yujin): 말로 저장한 포맷 입히기 -- 화면 적용과 같은 함수로 뽑음

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 16: 묶음 D 닫기

- [ ] **Step 1: 넓은 검증**

```powershell
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_screen_elements.py tests/test_yujin_editing_outputs.py tests/test_yujin_editing_basics.py tests/test_yujin_caption_font.py tests/test_api_format_templates.py tests/test_yujin_editing_proposal_adapter.py tests/test_yujin_editing_command_evaluation.py tests/test_editor_timeline_mutations.py
cd apps/web; npx vitest run src/features/editor/workbench src/user-copy-policy.test.ts; npx tsc --noEmit; cd ../..
```

- [ ] **Step 2: 역방향 — 재빌드·새 편집본 실기·지연**

```powershell
.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild
lms ps
.venv/Scripts/python.exe scripts/measure_yujin_prompt_size.py
.venv/Scripts/python.exe scripts/owner-path/ask_yujin_capabilities.py <project_id> D
.venv/Scripts/python.exe scripts/owner-path/ask_yujin_capabilities.py <project_id> baseline
```
Expected: `7/7 통과`, `3/3 통과`. 수치 기록(1.5배 넘으면 멈추고 보고 — Task 7 Step 5와 같은 규칙, Task 23 제시).

- [ ] **Step 3: 역방향·동작 — 브라우저 + 픽셀**

새 편집본에서: "2번 장면에 '핵심: 재고 회전율' 설명 카드 띄워줘" → 미리보기에 카드. "자막 노란색으로, 화면 위쪽으로" → 자막이 노랗게 위로. "1번 장면 오른쪽 위에 화살표 작게" → 표시. "방금 거 되돌려줘" → 표시가 사라짐.
동작(픽셀): 출력 화면에서 완성본을 만들고, 자막이 보이는 시각의 프레임을 뽑아 위쪽 띠에 노란 픽셀이 있는지 잰다:
```powershell
docker exec videobox-api ffmpeg -hide_banner -ss 1 -i <완성본 파일> -frames:v 1 -vf "crop=iw:ih*0.25:0:0,format=rgb24" -f rawvideo -y /tmp/top.rgb
docker exec videobox-api python3 -c "d=open('/tmp/top.rgb','rb').read(); n=len(d)//3; y=sum(1 for i in range(0,len(d),3) if d[i]>200 and d[i+1]>180 and d[i+2]<80); print('yellow_ratio', round(y/n,4))"
```
`yellow_ratio`가 0보다 커야 한다(자막 노란 글자). 수치를 적는다.

- [ ] **Step 4: 갭·배선·푸시**

갭: D1~D3 대조. 안 한 것: 장면마다 다른 자막 모양(유진은 편집본 전체만 — `set_caption_font`와 같은 결정), 표 칸 상한(6x8)은 화면보다 좁다(읽힘 때문, 보고서에 적는다), 포맷 **저장**(화면 전용으로 둠 — 이름 짓기가 사람 일).
배선: `git grep -n "set_caption_style\|apply_format_template\|set_explanation_card" -- apps/web/src`.
확인 뒤 `git push origin main` (정확히 이 명령. 도구 권한이 막으면 **우회하지 말고 멈춘다** — owner에게 `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`에서 `git push origin main`을 직접 실행하거나 허용 규칙 `Bash(git push origin main)`을 추가해 달라고 알리고 기다린다. Global Constraint 18).

---

### Task 17: E1 — 자막 번역(`translate_captions`)·자막 언어 바꾸기(`set_caption_language`)

번역: 화면 `번역` → `POST .../caption-translations`(`routers/editing_session.py:249-285`) = `orchestrator.start_caption_translation` + 백그라운드 `run_caption_translation_job`(runtime 필요). 실측 최악 630초라 반드시 job이다(330초 벽). 언어 바꾸기: `PATCH .../caption-language`(`:343-360`) = `orchestrator.set_caption_language`(세션 동기 저장). 둘 다 단독 실행형.

**Files:**
- Modify: `packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py`
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py`(import `SUPPORTED_CAPTION_LANGUAGES`, 맥락 `translated_languages`, 검사)
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py`
- Modify: `services/api/src/videobox_api/routers/director_proposals.py`
- Modify: `apps/web/src/features/editor/workbench/captionTranslationProgress.ts`(따라가기 함수 뽑기), `yujinBackgroundWork.ts`, `yujinBackgroundWork.test.ts`, `yujinEditingSummary.ts`, `.test.ts`
- Modify: `tests/yujin_chat_fakes.py`(`ImmediateThread`)
- Create: `tests/test_yujin_editing_language_voice.py`

**Interfaces:**
- Consumes: `orchestrator.start_caption_translation(*, project_id, session_id, language, expected_revision) -> {"job_id","status"}`, `orchestrator.run_caption_translation_job(*, project_id, session_id, job_id, language, expected_revision, runtime)`, `orchestrator.set_caption_language(*, project_id, session_id, language: str|None, expected_revision) -> dict`, `SUPPORTED_CAPTION_LANGUAGES = {"en":"영어","ja":"일본어","zh":"중국어"}`(`caption_translation.py:31-35`)
- Produces: `TranslateCaptionsOperation(intent, language: str)`, `SetCaptionLanguageOperation(intent, language: str | None = None)`; `YujinEditingContext.translated_languages: tuple[str, ...] = ()`; 거절 이유 `caption_language_not_supported`, `caption_language_not_translated`; 적용 응답 `{"status": "caption_translation_started", "job_id", "language", "notice"}`; TS `followCaptionTranslationJob(input: { projectId; sessionId; jobId; language; isStillRelevant? }): Promise<CaptionTranslationOutcome>`; 시험 도구 `ImmediateThread`

- [ ] **Step 1: 시험 도구에 즉시 도는 스레드를 더한다** — `tests/yujin_chat_fakes.py` 끝에:

```python
class ImmediateThread:
    """`threading.Thread` 대신 꽂는다 -- 백그라운드 일을 시험 안에서 바로 돌려 무엇이 불렸는지 본다."""

    def __init__(self, *, target, kwargs=None, daemon=None) -> None:  # noqa: ANN001
        self.target = target
        self.kwargs = dict(kwargs or {})

    def start(self) -> None:
        self.target(**self.kwargs)
```

- [ ] **Step 2: 실패하는 시험** — `tests/test_yujin_editing_language_voice.py`:

```python
"""묶음 E -- 번역·더빙·목소리를 말로. 긴 일은 job으로만(프록시 330초 벽)."""
from __future__ import annotations

from pathlib import Path

import pytest

import videobox_api.routers.director_proposals as director_proposals_module
from videobox_core_engine.yujin_editing_proposal_adapter import YujinEditingContext, interpret_yujin_editing_request
from videobox_core_engine.yujin_editing_proposal_service import _editing_prompt
from yujin_chat_fakes import ImmediateThread, ScriptedEditingProvider, create_and_apply, current_session, plain_session_project

_IDS = ("seg-hook", "seg-middle", "seg-close")
_TRANSLATED = (
    {"segment_id": "seg-hook", "caption_text": "이것만 보세요", "caption_translations": {"en": "Just watch this"}, "start_sec": 0.0, "end_sec": 3.0},
    {"segment_id": "seg-middle", "caption_text": "중간 설명", "caption_translations": {"en": "Middle"}, "start_sec": 3.0, "end_sec": 20.0},
    {"segment_id": "seg-close", "caption_text": "결론입니다", "start_sec": 20.0, "end_sec": 24.0},
)


def _response(*operations: dict, revision: int = 3) -> dict:
    return {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "맡겨 주세요.",
        "proposal": {"proposal_id": "p", "base_session_revision": revision, "operations": list(operations)},
    }


def _context(**extra: object) -> YujinEditingContext:
    return YujinEditingContext(session_id="s", session_revision=3, segment_ids=_IDS, **extra)  # type: ignore[arg-type]


# --- 번역·자막 언어 -------------------------------------------------------------

def test_only_supported_languages_and_only_translated_ones_can_be_shown() -> None:
    unsupported = interpret_yujin_editing_request(_response({"intent": "translate_captions", "language": "fr"}), _context())
    translate = interpret_yujin_editing_request(_response({"intent": "translate_captions", "language": "en"}), _context())
    show_untranslated = interpret_yujin_editing_request(_response({"intent": "set_caption_language", "language": "ja"}), _context(translated_languages=("en",)))
    show_translated = interpret_yujin_editing_request(_response({"intent": "set_caption_language", "language": "en"}), _context(translated_languages=("en",)))
    back_to_original = interpret_yujin_editing_request(_response({"intent": "set_caption_language"}), _context())

    assert unsupported.reason == "caption_language_not_supported"
    assert translate.status == "candidate_only"
    assert show_untranslated.reason == "caption_language_not_translated"
    assert show_translated.status == "candidate_only"
    assert back_to_original.status == "candidate_only"


def test_yujin_starts_caption_translation_as_a_background_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = ScriptedEditingProvider(operations=[{"intent": "translate_captions", "language": "en"}])
    app, client, project_id, session = plain_session_project(tmp_path, provider)
    ran: list[dict] = []
    orchestrator = app.state.orchestrator
    monkeypatch.setattr(orchestrator, "start_caption_translation", lambda *, project_id, session_id, language, expected_revision: {"job_id": "tr-1", "status": "processing"})
    monkeypatch.setattr(orchestrator, "run_caption_translation_job", lambda **kwargs: ran.append(kwargs))
    monkeypatch.setattr(director_proposals_module, "Thread", ImmediateThread)

    response = create_and_apply(client, project_id, session, "자막 영어로 번역해줘")

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "caption_translation_started", "job_id": "tr-1", "language": "en", "notice": "자막을 영어로 옮기고 있어요."}
    assert ran and ran[0]["job_id"] == "tr-1" and ran[0]["language"] == "en" and "runtime" in ran[0]


def test_yujin_switches_the_caption_language_from_the_real_chat(tmp_path: Path) -> None:
    provider = ScriptedEditingProvider(operations=[{"intent": "set_caption_language", "language": "en"}])
    app, client, project_id, session = plain_session_project(tmp_path, provider, segments=_TRANSLATED)

    response = create_and_apply(client, project_id, session, "자막 영어로 보여줘")

    assert response.status_code == 200, response.text
    assert current_session(client, project_id, session["session_id"])["caption_language"] == "en"


def test_the_prompt_lists_languages_and_which_are_ready() -> None:
    prompt = _editing_prompt(instruction="영어 자막", context=_context(translated_languages=("en",), caption_language=None))
    assert "translate_captions" in prompt
    assert "set_caption_language" in prompt
    assert "번역해 둔 언어: en(영어)" in prompt
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_language_voice.py::test_only_supported_languages_and_only_translated_ones_can_be_shown`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'translated_languages'`

- [ ] **Step 3: 의도 모델** — `ApplyFormatTemplateOperation` 다음:

```python
class TranslateCaptionsOperation(_StrictFrozenModel):
    """자막을 다른 언어로 옮긴다 -- 화면 `번역`(`POST .../caption-translations`)과 같은 자리.

    오래 걸려(실측 최악 630초) job만 걸고 돌아온다. 끝나면 그 언어로 보여 준다(서버가 고른다).
    `language`는 `SUPPORTED_CAPTION_LANGUAGES` 열쇠만 -- 대조는 검증기가 한다.
    """

    intent: Literal["translate_captions"]
    language: str = Field(min_length=2, max_length=8)


class SetCaptionLanguageOperation(_StrictFrozenModel):
    """보여 줄 자막 언어를 고른다 -- 화면 언어 고르기(`PATCH .../caption-language`)와 같은 함수.

    `None`이면 원본(한국어)으로 돌린다 -- 번역은 지우지 않는다.
    """

    intent: Literal["set_caption_language"]
    language: str | None = Field(default=None, min_length=2, max_length=8)
```

유니언·`__all__`.

- [ ] **Step 4: 검증기·맥락** — adapter

import `from videobox_core_engine.caption_translation import SUPPORTED_CAPTION_LANGUAGES`(다른 core import 옆), 도메인 import 둘, `STANDALONE_INTENTS`에 `"translate_captions", "set_caption_language"`. 맥락 필드(`format_templates` 다음):

```python
    #: 장면 하나라도 번역이 들어 있는 언어. 언어 바꾸기·더빙은 번역해 둔 언어로만 된다(화면도 그렇다).
    translated_languages: tuple[str, ...] = ()
```

검사:

```python
        if isinstance(operation, TranslateCaptionsOperation) and operation.language not in SUPPORTED_CAPTION_LANGUAGES:
            return "caption_language_not_supported"
        if isinstance(operation, SetCaptionLanguageOperation) and operation.language is not None:
            if operation.language not in SUPPORTED_CAPTION_LANGUAGES:
                return "caption_language_not_supported"
            if operation.language not in set(context.translated_languages):
                return "caption_language_not_translated"
```

`director_proposals.py` — 맥락(`format_templates=` 블록 다음):

```python
            translated_languages=tuple(sorted({
                str(language)
                for item in session.get("segments", [])
                if isinstance(item, dict) and isinstance(item.get("caption_translations"), dict)
                for language, text in item["caption_translations"].items()
                if str(text or "").strip()
            })),
```

import `from videobox_core_engine.caption_translation import SUPPORTED_CAPTION_LANGUAGES` — 15행 `from videobox_core_engine.caption_translation import caption_text_for_language`를 `from videobox_core_engine.caption_translation import SUPPORTED_CAPTION_LANGUAGES, caption_text_for_language`로 바꾼다.

`_apply_standalone_intent`의 `apply_format_template` 갈래 다음:

```python
        if intent == "translate_captions":
            # 화면 `번역`과 같은 두 걸음(routers/editing_session.py `translate_editing_session_captions`).
            language = str(getattr(operation, "language", ""))
            started = orchestrator.start_caption_translation(
                project_id=project_id, session_id=session_id, language=language,
                expected_revision=expected_session_revision,
            )
            Thread(
                target=orchestrator.run_caption_translation_job,
                kwargs={
                    "project_id": project_id, "session_id": session_id, "job_id": started["job_id"],
                    "language": language, "expected_revision": expected_session_revision,
                    "runtime": request.app.state.local_only_runtime_service_factory(store),
                },
                daemon=True,
            ).start()
            return {
                "status": "caption_translation_started",
                "job_id": str(started["job_id"]),
                "language": language,
                "notice": f"자막을 {SUPPORTED_CAPTION_LANGUAGES.get(language, language)}로 옮기고 있어요.",
            }
        if intent == "set_caption_language":
            # 화면 언어 고르기와 같은 함수.
            return orchestrator.set_caption_language(
                project_id=project_id, session_id=session_id,
                language=getattr(operation, "language", None), expected_revision=expected_session_revision,
            )
```

(`Thread`는 이 파일 10행에서 이미 import돼 있다 — 시험이 그 이름을 `ImmediateThread`로 바꿔치기한다.)

- [ ] **Step 5: 스키마·안내문**

스키마:

```python
        # 묶음 E(2026-10-02). 언어 목록은 `SUPPORTED_CAPTION_LANGUAGES` 하나가 원본이다.
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "translate_captions"}, "language": {"enum": sorted(SUPPORTED_CAPTION_LANGUAGES)}}, "required": ["intent", "language"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "set_caption_language"}, "language": {"type": ["string", "null"], "enum": [*sorted(SUPPORTED_CAPTION_LANGUAGES), None]}}, "required": ["intent"]},
```

허용 intent 문장: `"translate_captions(자막을 다른 언어로 번역한다), set_caption_language(보여 줄 자막 언어를 고른다 -- 원래 한국어로 돌리려면 language를 비운다), "`.

새 함수(`_caption_style_catalogue` 다음):

```python
def _language_voice_catalogue(context: YujinEditingContext) -> str:
    """번역·자막 언어(묶음 E1). 고를 수 있는 언어와 **번역해 둔 언어·지금 보는 언어**를 한 쌍으로 준다."""
    languages = ", ".join(f"{code}({label})" for code, label in sorted(SUPPORTED_CAPTION_LANGUAGES.items()))
    ready = ", ".join(
        f"{code}({SUPPORTED_CAPTION_LANGUAGES.get(code, code)})" for code in context.translated_languages
    ) or "없음"
    showing = SUPPORTED_CAPTION_LANGUAGES.get(context.caption_language or "", "원본(한국어)")
    return (
        f"번역할 수 있는 언어: {languages}. 번역해 둔 언어: {ready}. 지금 보는 자막: {showing}. "
        "'자막 영어로 번역해줘'는 translate_captions(language=en) -- 몇 분 걸리고, 끝나면 그 언어로 보인다. "
        "'영어 자막으로 보여줘'는 번역해 둔 언어일 때만 set_caption_language, 아니면 먼저 번역한다. "
        "'원래 자막으로 돌려줘'는 set_caption_language에 language를 싣지 않는다. 둘 다 혼자 싣는다."
    )
```

`_editing_prompt` 안 `        f"{_caption_style_catalogue(context)} "` 다음 줄에 `        f"{_language_voice_catalogue(context)} "`.

- [ ] **Step 6: 화면 — 번역 따라가기를 뽑아 유진도 쓴다**

`captionTranslationProgress.ts`의 `runCaptionTranslationWithProgress`를 두 함수로 나눈다(동작 같음):

```ts
export async function followCaptionTranslationJob(input: {
  projectId: string;
  sessionId: string;
  jobId: string;
  language: string;
  isStillRelevant?: () => boolean;
}): Promise<CaptionTranslationOutcome> {
  const outcome = await pollJobUntilTerminal(
    () => api.getEditingSessionCaptionTranslationStatus(input.projectId, input.sessionId, input.jobId),
    {
      intervalMs: CAPTION_TRANSLATION_POLL_INTERVAL_MS,
      maxAttempts: CAPTION_TRANSLATION_MAX_POLL_ATTEMPTS,
      delayFirst: true,
      isStillRelevant: input.isStillRelevant,
    },
  );

  if (outcome.kind === "succeeded") {
    // **못 옮긴 장면이 있으면 말해 준다.** 안 말하면 그 장면은 원래 자막
    // 그대로 완성본에 나가는데, 창작자는 다 옮겨진 줄 안다.
    const missingCount = outcome.result.segments.filter(
      (segment) =>
        String(segment.caption_text ?? "").trim() &&
        !String(segment.caption_translations?.[input.language] ?? "").trim(),
    ).length;
    return { kind: "succeeded", missingCount };
  }
  if (outcome.kind === "cancelled") return { kind: "cancelled" };
  if (outcome.kind === "timed_out") return { kind: "timed_out" };
  return { kind: "failed", detail: outcome.error_detail ?? null };
}

export async function runCaptionTranslationWithProgress(input: {
  projectId: string;
  sessionId: string;
  expectedRevision: number;
  language: string;
  isStillRelevant?: () => boolean;
}): Promise<CaptionTranslationOutcome> {
  const started = await api.startEditingSessionCaptionTranslation(input.projectId, input.sessionId, {
    expected_revision: input.expectedRevision,
    language: input.language,
  });
  return followCaptionTranslationJob({
    projectId: input.projectId, sessionId: input.sessionId, jobId: started.job_id,
    language: input.language, isStillRelevant: input.isStillRelevant,
  });
}
```

`yujinBackgroundWork.ts` — import에 `import { captionTranslationOutcomeMessage, followCaptionTranslationJob } from "./captionTranslationProgress";`, 마지막 `return YUJIN_WORK_LOST_TRACK;` **앞**에:

```ts
  if (work.kind === "caption_translation") {
    const outcome = await followCaptionTranslationJob({
      projectId, sessionId: input.sessionId, jobId: work.jobId, language: work.language ?? "",
      isStillRelevant: input.isStillRelevant,
    });
    return captionTranslationOutcomeMessage(outcome);
  }
```

`yujinBackgroundWork.test.ts`에:

```ts
  it("번역은 화면 번역과 같은 말로 끝을 알린다", { timeout: 20000 }, async () => {
    vi.spyOn(api, "getEditingSessionCaptionTranslationStatus").mockResolvedValueOnce({
      job_id: "tr-1", status: "succeeded", error_detail: null,
      result: { segments: [{ segment_id: "a", caption_text: "가", caption_translations: { en: "A" } }] },
    } as never);

    const message = await followYujinWork({
      projectId: "p", sessionId: "s",
      work: { kind: "caption_translation", jobId: "tr-1", notice: "", totalSceneCount: 0, language: "en" },
      isStillRelevant: () => true,
    });

    expect(message).toBe("자막을 번역했어요.");
  });
```

`yujinEditingSummary.ts`:

```ts
  // 묶음 E(2026-10-02): 번역·목소리.
  if (operation.intent === "translate_captions") return "자막을 번역해요.";
  if (operation.intent === "set_caption_language") return typeof operation.language === "string" ? "자막 언어를 바꿔요." : "원래 자막으로 돌려요.";
```

시험:

```ts
  it("번역과 자막 언어를 말한다", () => {
    expect(summary({ intent: "translate_captions", language: "en" })).toBe("자막을 번역해요.");
    expect(summary({ intent: "set_caption_language" })).toBe("원래 자막으로 돌려요.");
  });
```

- [ ] **Step 7: 통과·넓은 검증·커밋**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_language_voice.py tests/test_yujin_chat_fakes.py` → 통과
Run: `cd apps/web && npx vitest run src/features/editor/workbench/captionTranslationProgress.test.ts src/features/editor/workbench/yujinBackgroundWork.test.ts src/features/editor/workbench/yujinEditingSummary.test.ts` → passed

```bash
git add tests/yujin_chat_fakes.py tests/test_yujin_editing_language_voice.py packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py services/api/src/videobox_api/routers/director_proposals.py apps/web/src/features/editor/workbench/captionTranslationProgress.ts apps/web/src/features/editor/workbench/yujinBackgroundWork.ts apps/web/src/features/editor/workbench/yujinBackgroundWork.test.ts apps/web/src/features/editor/workbench/yujinEditingSummary.ts apps/web/src/features/editor/workbench/yujinEditingSummary.test.ts
git commit -m "feat(yujin): 말로 자막 번역(job)·자막 언어 바꾸기 -- 화면과 같은 함수, 번역 따라가기 공용화

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 18: E2 — 더빙(`dub_narration`)

화면 더빙(`InspectorControls.tsx:1165-1200`의 `{언어} 목소리로 더빙` → `EditorWorkbenchRoute.dubNarration` → `POST .../dubbing`, `routers/editing_session.py:296-330`) = `orchestrator.start_dubbing` + 백그라운드 `run_dubbing_job`. 장면당 13초(2026-09-03 실측)라 스물세 장면이면 330초 벽 — 반드시 job. 화면처럼 **번역해 둔 언어만** 된다. 목소리는 화면이 목소리 하나일 때와 같이 `voice_sample_asset_id=None`(서버 기본)으로 보낸다 — 여러 목소리 중 고르기는 이 Task에서 열지 않는다(갭에 적는다). 목소리 엔진이 꺼져 있으면(`scripts/start-voice.ps1`) 실패하고, 화면과 같은 실패 문구가 나온다.

**Files:**
- Modify: 도메인 모델, adapter(검사), service(스키마·안내문), `director_proposals.py`
- Modify: `apps/web/src/features/editor/workbench/dubbingProgress.ts`(따라가기 뽑기), `yujinBackgroundWork.ts`, `.test.ts`, `yujinEditingSummary.ts`, `.test.ts`
- Modify: `tests/test_yujin_editing_language_voice.py`

**Interfaces:**
- Consumes: `orchestrator.start_dubbing(*, project_id, session_id, language, expected_revision, voice_sample_asset_id=None) -> {"job_id","status","total_scene_count"}`, `orchestrator.run_dubbing_job(*, project_id, session_id, job_id, language, expected_revision, voice_sample_asset_id=None)`
- Produces: `DubNarrationOperation(intent: Literal["dub_narration"], language: str)`; 거절 이유 `dubbing_needs_translation`; 적용 응답 `{"status": "dubbing_started", "job_id", "total_scene_count", "language", "notice"}`; TS `followDubbingJob(input: { projectId; sessionId; jobId; totalSceneCount; onProgress?; isStillRelevant? }): Promise<DubbingOutcome>`

- [ ] **Step 1: 실패하는 시험** — `tests/test_yujin_editing_language_voice.py` 끝에:

```python
# --- 더빙 ---------------------------------------------------------------------

def test_dubbing_only_in_a_language_that_was_translated() -> None:
    not_ready = interpret_yujin_editing_request(_response({"intent": "dub_narration", "language": "ja"}), _context(translated_languages=("en",)))
    ready = interpret_yujin_editing_request(_response({"intent": "dub_narration", "language": "en"}), _context(translated_languages=("en",)))
    assert not_ready.reason == "dubbing_needs_translation"
    assert ready.status == "candidate_only"


def test_yujin_starts_dubbing_as_a_background_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = ScriptedEditingProvider(operations=[{"intent": "dub_narration", "language": "en"}])
    app, client, project_id, session = plain_session_project(tmp_path, provider, segments=_TRANSLATED)
    ran: list[dict] = []
    orchestrator = app.state.orchestrator
    monkeypatch.setattr(orchestrator, "start_dubbing", lambda **kwargs: {"job_id": "dub-1", "status": "processing", "total_scene_count": 2})
    monkeypatch.setattr(orchestrator, "run_dubbing_job", lambda **kwargs: ran.append(kwargs))
    monkeypatch.setattr(director_proposals_module, "Thread", ImmediateThread)

    response = create_and_apply(client, project_id, session, "영어 목소리로 더빙해줘")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["job_id"], body["total_scene_count"], body["language"]) == ("dubbing_started", "dub-1", 2, "en")
    assert ran and ran[0]["voice_sample_asset_id"] is None
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_language_voice.py::test_dubbing_only_in_a_language_that_was_translated`
Expected: FAIL — `assert 'invalid_editing_response' == 'dubbing_needs_translation'`

- [ ] **Step 2: 모델·검증·적용**

모델(`SetCaptionLanguageOperation` 다음):

```python
class DubNarrationOperation(_StrictFrozenModel):
    """번역해 둔 자막을 그 언어 목소리로 읽힌다 -- 화면 `{언어} 목소리로 더빙`과 같은 자리.

    장면당 13초라 job만 걸고 돌아온다(330초 벽). 번역해 둔 언어만 된다(화면도 그렇다).
    """

    intent: Literal["dub_narration"]
    language: str = Field(min_length=2, max_length=8)
```

유니언·`__all__`. adapter: 도메인 import, `STANDALONE_INTENTS`에 `"dub_narration"`, 검사:

```python
        if isinstance(operation, DubNarrationOperation) and operation.language not in set(context.translated_languages):
            return "dubbing_needs_translation"
```

`_apply_standalone_intent`(`set_caption_language` 갈래 다음):

```python
        if intent == "dub_narration":
            # 화면 더빙과 같은 두 걸음(routers/editing_session.py `start_dubbing`). 목소리는 화면이
            # 목소리 하나일 때처럼 서버 기본을 쓴다.
            language = str(getattr(operation, "language", ""))
            started = orchestrator.start_dubbing(
                project_id=project_id, session_id=session_id, language=language,
                voice_sample_asset_id=None, expected_revision=expected_session_revision,
            )
            Thread(
                target=orchestrator.run_dubbing_job,
                kwargs={
                    "project_id": project_id, "session_id": session_id, "job_id": started["job_id"],
                    "language": language, "expected_revision": expected_session_revision,
                    "voice_sample_asset_id": None,
                },
                daemon=True,
            ).start()
            return {
                "status": "dubbing_started",
                "job_id": str(started["job_id"]),
                "total_scene_count": int(started.get("total_scene_count") or 0),
                "language": language,
                "notice": "목소리를 만들고 있어요. 장면이 많으면 오래 걸려요.",
            }
```

스키마:

```python
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "dub_narration"}, "language": {"enum": sorted(SUPPORTED_CAPTION_LANGUAGES)}}, "required": ["intent", "language"]},
```

허용 intent 문장: `"dub_narration(번역해 둔 자막을 그 언어 목소리로 더빙한다 -- \"영어 목소리로 더빙해줘\"가 이것이다), "`. `_language_voice_catalogue` 반환 문자열 끝 `"둘 다 혼자 싣는다."`를 `"'영어로 더빙해줘'는 번역해 둔 언어일 때만 dub_narration -- 아니면 먼저 번역하자고 답한다(장면이 많으면 오래 걸린다). 모두 혼자 싣는다."`로 바꾼다.

- [ ] **Step 3: 화면 — 더빙 따라가기를 뽑아 유진도 쓴다**

`dubbingProgress.ts`의 `runDubbingWithProgress`를 둘로 나눈다(동작 같음):

```ts
export async function followDubbingJob(input: {
  projectId: string;
  sessionId: string;
  jobId: string;
  totalSceneCount: number;
  onProgress?: (done: number, total: number) => void;
  isStillRelevant?: () => boolean;
}): Promise<DubbingOutcome> {
  const outcome = await pollJobUntilTerminal(
    async () => {
      const status = await api.getEditingSessionDubbingStatus(input.projectId, input.sessionId, input.jobId);
      input.onProgress?.(status.done_scene_count, status.total_scene_count);
      return status;
    },
    {
      intervalMs: DUBBING_POLL_INTERVAL_MS,
      maxAttempts: pollAttemptsFor(input.totalSceneCount),
      delayFirst: true,
      isStillRelevant: input.isStillRelevant,
    },
  );

  if (outcome.kind === "succeeded") {
    return {
      kind: "succeeded",
      dubbedSceneCount: outcome.result?.dubbed_scene_count ?? 0,
      notice: outcome.result?.dubbing_notice ?? null,
    };
  }
  if (outcome.kind === "cancelled") return { kind: "cancelled" };
  if (outcome.kind === "timed_out") return { kind: "timed_out" };
  return { kind: "failed", detail: outcome.error_detail ?? null };
}

export async function runDubbingWithProgress(input: {
  projectId: string;
  sessionId: string;
  expectedRevision: number;
  language: string;
  voiceSampleAssetId?: string | null;
  /** 몇 장면 중 몇 장면째인지. 스무 장면이면 사 분이 넘으므로 말해 줘야 한다. */
  onProgress?: (done: number, total: number) => void;
  isStillRelevant?: () => boolean;
}): Promise<DubbingOutcome> {
  const started = await api.startEditingSessionDubbing(input.projectId, input.sessionId, {
    expected_revision: input.expectedRevision,
    language: input.language,
    voice_sample_asset_id: input.voiceSampleAssetId ?? null,
  });
  input.onProgress?.(0, started.total_scene_count);
  return followDubbingJob({
    projectId: input.projectId, sessionId: input.sessionId, jobId: started.job_id,
    totalSceneCount: started.total_scene_count, onProgress: input.onProgress, isStillRelevant: input.isStillRelevant,
  });
}
```

`yujinBackgroundWork.ts` — import에 `import { dubbingOutcomeMessage, followDubbingJob } from "./dubbingProgress";`, `return YUJIN_WORK_LOST_TRACK;` 앞에:

```ts
  if (work.kind === "dubbing") {
    const outcome = await followDubbingJob({
      projectId, sessionId: input.sessionId, jobId: work.jobId, totalSceneCount: work.totalSceneCount,
      isStillRelevant: input.isStillRelevant,
      onProgress: (done, total) => input.onProgress?.(
        total > 0 ? `목소리를 만들고 있어요. ${total}개 장면 중 ${done}개 했어요.` : "목소리를 만들고 있어요.",
      ),
    });
    return dubbingOutcomeMessage(outcome);
  }
```

시험(`yujinBackgroundWork.test.ts`):

```ts
  it("더빙은 몇 장면째인지 말하며 끝까지 지켜본다", { timeout: 20000 }, async () => {
    vi.spyOn(api, "getEditingSessionDubbingStatus")
      .mockResolvedValueOnce({ job_id: "d1", status: "processing", result: null, error_detail: null, done_scene_count: 1, total_scene_count: 2 } as never)
      .mockResolvedValueOnce({ job_id: "d1", status: "succeeded", result: { dubbed_scene_count: 2, dubbing_notice: null, session_revision: 5 }, error_detail: null, done_scene_count: 2, total_scene_count: 2 } as never);
    const labels: string[] = [];

    const message = await followYujinWork({
      projectId: "p", sessionId: "s",
      work: { kind: "dubbing", jobId: "d1", notice: "", totalSceneCount: 2, language: "en" },
      isStillRelevant: () => true,
      onProgress: (label) => labels.push(label),
    });

    expect(labels[0]).toBe("목소리를 만들고 있어요. 2개 장면 중 1개 했어요.");
    expect(message).toBe("2개 장면의 목소리를 바꿨어요.");
  });
```

`yujinEditingSummary.ts`: `if (operation.intent === "dub_narration") return "목소리를 더빙해요.";` + 시험 한 줄(`expect(summary({ intent: "dub_narration", language: "en" })).toBe("목소리를 더빙해요.");`).

- [ ] **Step 4: 통과·커밋**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_language_voice.py` → 통과
Run: `cd apps/web && npx vitest run src/features/editor/workbench/dubbingProgress.test.ts src/features/editor/workbench/yujinBackgroundWork.test.ts src/features/editor/workbench/yujinEditingSummary.test.ts` → passed

```bash
git add packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py services/api/src/videobox_api/routers/director_proposals.py apps/web/src/features/editor/workbench/dubbingProgress.ts apps/web/src/features/editor/workbench/yujinBackgroundWork.ts apps/web/src/features/editor/workbench/yujinBackgroundWork.test.ts apps/web/src/features/editor/workbench/yujinEditingSummary.ts apps/web/src/features/editor/workbench/yujinEditingSummary.test.ts tests/test_yujin_editing_language_voice.py
git commit -m "feat(yujin): 말로 더빙(job) -- 번역해 둔 언어만, 화면과 같은 따라가기

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 19: E3 — TTS 교체, 받아쓰기 캡션, 부분 다시 만들기

셋 다 단독 실행형.
- **TTS 교체**: 화면 `PATCH/DELETE .../segments/{id}/tts-replacement`(`routers/editing_session.py:1077-1120`) = `orchestrator.select_segment_tts_replacement`/`clear_segment_tts_replacement`(`orchestration.py:1674-1710`). 서버가 **듣기 승인된 후보만** 받는다(`editing_session_and_regeneration.py:1409-1457`) — 유진은 그 목록 안에서만 고른다(듣기 승인은 열지 않는다).
- **받아쓰기 캡션**: 화면 `자동 캡션`(`apps/web/src/features/editor/transcript/AutoCaptionCard.tsx:51-82`) = 받아쓰기 job(`POST .../jobs/transcription`, `routers/jobs.py:43-63`) → 끝나면 `POST .../captions-from-transcript`. 서버는 받아쓰기만 걸고, 캡션 옮기기는 화면이 job을 지켜본 뒤 같은 API로 한다(화면 `자동 캡션`과 같은 두 걸음). **MCP 경로에서는 받아쓰기까지만 된다** — 갭에 적는다.
- **부분 다시 만들기**: 화면 `부분 다시 만들기`(`routers/editing_session.py:706-752`) = `orchestrator.start_editing_session_partial_regeneration` + 백그라운드 `run_partial_regeneration_job`(`orchestration.py:1400-1440`). 항목은 `ALLOWED_PARTIAL_REGEN_FIELDS`(`editing_session.py:41-53`).

**Files:**
- Modify: 도메인 모델, adapter, service, `director_proposals.py`
- Modify: `apps/web/src/features/editor/workbench/yujinBackgroundWork.ts`, `.test.ts`, `yujinEditingSummary.ts`, `.test.ts`
- Modify: `tests/test_yujin_editing_language_voice.py`

**Interfaces:**
- Consumes: `orchestrator.list_tts_replacement_candidates(*, project_id, segment_id) -> list[dict]`(`candidate_id, asset_id, segment_id, technical_status, operator_review_status`), `select_segment_tts_replacement(*, project_id, session_id, segment_id, recommendation_id, asset_id, expected_revision)`, `clear_segment_tts_replacement(*, project_id, session_id, segment_id, expected_revision)`, `store.list_assets(*, project_id)`, `orchestrator.start_transcription(*, project_id, narration_asset_id) -> {"job_id",...}`, `run_transcription_job(*, project_id, job_id, narration_asset_id)`, `orchestrator.start_editing_session_partial_regeneration(*, project_id, session_id, segment_ids, fields, expected_revision) -> {"job_id","_session","_request","_captured_revision",...}`, `run_partial_regeneration_job(*, project_id, session_id, job_id, session, request, captured_revision)`; 웹 `api.getTranscriptionJob(projectId, jobId)`, `api.applyCaptionsFromTranscript(projectId, sessionId, {transcription_job_id, expected_revision})`, `api.getPartialRegenerationResult(projectId, jobId)`; `_mentioned_scene_numbers(instruction) -> list[int]`(`yujin_editing_proposal_service.py:382-389`)
- Produces: `SetTtsReplacementOperation(segment_id, intent, candidate_id: str)`, `ClearTtsReplacementOperation(segment_id, intent)`, `CaptionsFromTranscriptOperation(intent)`, `RegeneratePartOperation(intent, segment_ids: tuple[str,...] 1..16, fields: tuple[str,...] 1..len(ALLOWED))`; 맥락 `approved_tts_candidates: tuple[tuple[str, str], ...]`(segment_id, candidate_id), `segment_ids_with_tts_replacement: tuple[str, ...]`, `has_narration_for_transcript: bool`; 거절 이유 `tts_candidate_not_approved`, `tts_replacement_not_present`, `transcript_needs_narration`, `partial_regeneration_field_not_available`, `segment_not_current`

- [ ] **Step 1: 실패하는 시험** — `tests/test_yujin_editing_language_voice.py` 끝에:

```python
# --- TTS 교체·받아쓰기·부분 다시 만들기 -----------------------------------------

def test_tts_replacement_picks_only_approved_candidates_and_clearing_needs_one_on() -> None:
    unapproved = interpret_yujin_editing_request(_response({"intent": "set_tts_replacement", "segment_id": "seg-middle", "candidate_id": "tts_candidate_9"}), _context())
    approved = interpret_yujin_editing_request(
        _response({"intent": "set_tts_replacement", "segment_id": "seg-middle", "candidate_id": "tts_candidate_1"}),
        _context(approved_tts_candidates=(("seg-middle", "tts_candidate_1"),)),
    )
    nothing_on = interpret_yujin_editing_request(_response({"intent": "clear_tts_replacement", "segment_id": "seg-middle"}), _context())
    assert unapproved.reason == "tts_candidate_not_approved"
    assert approved.status == "candidate_only"
    assert nothing_on.reason == "tts_replacement_not_present"


def test_transcript_captions_need_a_narration_and_regeneration_needs_known_fields() -> None:
    no_narration = interpret_yujin_editing_request(_response({"intent": "captions_from_transcript"}), _context())
    bad_field = interpret_yujin_editing_request(_response({"intent": "regenerate_part", "segment_ids": ["seg-middle"], "fields": ["everything"]}), _context())
    fine = interpret_yujin_editing_request(_response({"intent": "regenerate_part", "segment_ids": ["seg-middle"], "fields": ["broll"]}), _context())
    assert no_narration.reason == "transcript_needs_narration"
    assert bad_field.reason == "partial_regeneration_field_not_available"
    assert fine.status == "candidate_only"


def test_yujin_swaps_in_an_approved_voice_take_through_the_screen_function(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = ScriptedEditingProvider(operations=[{"intent": "set_tts_replacement", "segment_id": "seg-middle", "candidate_id": "tts_candidate_1"}])
    app, client, project_id, session = plain_session_project(tmp_path, provider)
    orchestrator = app.state.orchestrator
    monkeypatch.setattr(orchestrator, "list_tts_replacement_candidates", lambda *, project_id, segment_id: [
        {"candidate_id": "tts_candidate_1", "asset_id": "asset-tts-1", "segment_id": segment_id, "technical_status": "accepted", "operator_review_status": "approved"},
    ] if segment_id == "seg-middle" else [])
    picked: list[dict] = []

    def _select(**kwargs: object) -> dict:
        picked.append(kwargs)
        return app.state.store.get_editing_session(project_id=project_id, session_id=session["session_id"])

    monkeypatch.setattr(orchestrator, "select_segment_tts_replacement", _select)

    response = create_and_apply(client, project_id, session, "2번 장면 목소리 승인한 걸로 바꿔줘")

    assert response.status_code == 200, response.text
    assert picked and picked[0]["recommendation_id"] == "tts_candidate_1" and picked[0]["asset_id"] == "asset-tts-1"


def test_yujin_starts_transcription_and_partial_regeneration_as_jobs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = ScriptedEditingProvider(operations=[{"intent": "captions_from_transcript"}])
    app, client, project_id, session = plain_session_project(tmp_path, provider)
    store = app.state.store
    real_list_assets = store.list_assets
    monkeypatch.setattr(store, "list_assets", lambda **kwargs: [{"asset_id": "nar-1", "asset_type": "narration_audio", "metadata": {}}, *real_list_assets(**kwargs)])
    orchestrator = app.state.orchestrator
    ran: list[str] = []
    monkeypatch.setattr(orchestrator, "start_transcription", lambda *, project_id, narration_asset_id: {"job_id": "tx-1", "status": "running"})
    monkeypatch.setattr(orchestrator, "run_transcription_job", lambda **kwargs: ran.append(f"tx:{kwargs['narration_asset_id']}"))
    monkeypatch.setattr(orchestrator, "start_editing_session_partial_regeneration", lambda **kwargs: {"job_id": "pr-1", "status": "running", "_session": {}, "_request": {}, "_captured_revision": 1})
    monkeypatch.setattr(orchestrator, "run_partial_regeneration_job", lambda **kwargs: ran.append(f"pr:{kwargs['job_id']}"))
    monkeypatch.setattr(director_proposals_module, "Thread", ImmediateThread)

    transcription = create_and_apply(client, project_id, session, "말 받아써서 캡션 만들어줘")
    provider.operations = [{"intent": "regenerate_part", "segment_ids": ["seg-middle"], "fields": ["broll"]}]
    regeneration = create_and_apply(client, project_id, session, "2번 장면 영상만 다시 골라줘")

    assert transcription.status_code == 200, transcription.text
    assert transcription.json()["status"] == "transcription_started"
    assert regeneration.status_code == 200, regeneration.text
    assert regeneration.json()["status"] == "partial_regeneration_started"
    assert ran == ["tx:nar-1", "pr:pr-1"]
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_language_voice.py::test_tts_replacement_picks_only_approved_candidates_and_clearing_needs_one_on`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'approved_tts_candidates'`

- [ ] **Step 2: 모델** — `DubNarrationOperation` 다음:

```python
class SetTtsReplacementOperation(_SegmentOperation):
    """이 장면 목소리를 **듣기 승인된** 다른 녹음으로 바꾼다 -- 화면 목소리 바꾸기와 같은 함수.

    듣기 승인은 사람이 한다 -- 유진은 승인된 후보 안에서만 고른다(서버도 다시 막는다).
    """

    intent: Literal["set_tts_replacement"]
    candidate_id: str = Field(min_length=1, max_length=256)


class ClearTtsReplacementOperation(_SegmentOperation):
    """바꾼 목소리를 원래 목소리로 돌린다."""

    intent: Literal["clear_tts_replacement"]


class CaptionsFromTranscriptOperation(_StrictFrozenModel):
    """말을 받아써서 캡션으로 옮긴다 -- 화면 `자동 캡션`과 같은 두 걸음(받아쓰기 job → 캡션 옮기기)."""

    intent: Literal["captions_from_transcript"]


class RegeneratePartOperation(_StrictFrozenModel):
    """고른 장면의 고른 항목만 다시 만든다 -- 화면 `부분 다시 만들기`와 같은 자리(job).

    `fields`는 `editing_session.ALLOWED_PARTIAL_REGEN_FIELDS` 안의 값만 -- 대조는 검증기가 한다.
    """

    intent: Literal["regenerate_part"]
    segment_ids: Annotated[tuple[str, ...], BeforeValidator(_list_to_tuple)] = Field(min_length=1, max_length=16)
    fields: Annotated[tuple[str, ...], BeforeValidator(_list_to_tuple)] = Field(min_length=1, max_length=11)
```

유니언·`__all__`.

- [ ] **Step 3: 검증기·맥락** — adapter

import `from videobox_core_engine.editing_session import ALLOWED_PARTIAL_REGEN_FIELDS, MIN_SEGMENT_DURATION_SEC`(Task 2의 import 줄을 이렇게 넓힌다), 도메인 import 넷. `STANDALONE_INTENTS`에 `"set_tts_replacement", "clear_tts_replacement", "captions_from_transcript", "regenerate_part"`. 맥락 필드(`translated_languages` 다음):

```python
    #: 듣기 승인된 목소리 후보 `(segment_id, candidate_id)`. 창작자가 말한 장면 것만 싣는다(장면마다
    #: 조회가 하나씩 들어서). 이 밖의 후보는 고를 수 없다.
    approved_tts_candidates: tuple[tuple[str, str], ...] = ()
    #: 목소리를 바꿔 둔 장면. "원래 목소리로 돌려줘"가 무엇을 돌리는지의 근거.
    segment_ids_with_tts_replacement: tuple[str, ...] = ()
    #: 받아쓸 내레이션(또는 원본 영상)이 있는가 -- 화면 `자동 캡션`도 이게 없으면 안 된다.
    has_narration_for_transcript: bool = False
```

검사:

```python
        if isinstance(operation, SetTtsReplacementOperation) and (
            operation.segment_id, operation.candidate_id
        ) not in set(context.approved_tts_candidates):
            return "tts_candidate_not_approved"
        if isinstance(operation, ClearTtsReplacementOperation) and operation.segment_id not in set(context.segment_ids_with_tts_replacement):
            return "tts_replacement_not_present"
        if isinstance(operation, CaptionsFromTranscriptOperation) and not context.has_narration_for_transcript:
            return "transcript_needs_narration"
        if isinstance(operation, RegeneratePartOperation):
            if not set(operation.fields) <= ALLOWED_PARTIAL_REGEN_FIELDS:
                return "partial_regeneration_field_not_available"
            if not set(operation.segment_ids) <= current_segment_ids:
                return "segment_not_current"
```

`director_proposals.py` — import `from videobox_core_engine.yujin_editing_proposal_service import YujinEditingProposalService, _mentioned_scene_numbers`(29행을 이렇게 넓힌다). 맥락(`translated_languages=` 블록 다음):

```python
            approved_tts_candidates=_approved_tts_candidates(project_id=project_id, session=session, instruction=body.instruction),
            segment_ids_with_tts_replacement=tuple(
                str(item["segment_id"]) for item in session.get("segments", [])
                if isinstance(item, dict) and item.get("segment_id") and isinstance(item.get("tts_replacement"), dict)
            ),
            has_narration_for_transcript=_narration_asset_id(project_id) is not None,
```

라우터 빌더 안 `    def _has_current_final_render(` 다음에:

```python
    def _approved_tts_candidates(*, project_id: str, session: dict, instruction: str) -> tuple[tuple[str, str], ...]:
        """말한 장면의 **듣기 승인된** 목소리 후보. 화면 `loadApprovedTtsCandidates`와 같은 거름."""
        ordered = [str(item["segment_id"]) for item in session.get("segments", []) if isinstance(item, dict) and item.get("segment_id")]
        mentioned = [ordered[number - 1] for number in _mentioned_scene_numbers(instruction) if 1 <= number <= len(ordered)]
        found: list[tuple[str, str]] = []
        for segment_id in dict.fromkeys(mentioned):
            for candidate in orchestrator.list_tts_replacement_candidates(project_id=project_id, segment_id=segment_id):
                if candidate.get("technical_status") == "accepted" and candidate.get("operator_review_status") == "approved":
                    found.append((segment_id, str(candidate["candidate_id"])))
        return tuple(found)

    def _narration_asset_id(project_id: str) -> str | None:
        """받아쓸 소리. 화면 `자동 캡션`이 쓰는 목록(`draft-readiness/narration-options`)과 같은 거름의 첫째."""
        for item in store.list_assets(project_id=project_id):
            if item.get("asset_type") in {"raw_video", "narration_audio"}:
                return str(item["asset_id"])
        return None
```

`_apply_standalone_intent`(`dub_narration` 갈래 다음):

```python
        if intent == "set_tts_replacement":
            # 화면 목소리 바꾸기와 같은 함수 -- 서버가 듣기 승인을 다시 확인한다.
            segment_id = str(getattr(operation, "segment_id", ""))
            candidate_id = str(getattr(operation, "candidate_id", ""))
            candidate = next(
                (item for item in orchestrator.list_tts_replacement_candidates(project_id=project_id, segment_id=segment_id)
                 if str(item.get("candidate_id")) == candidate_id),
                None,
            )
            if candidate is None:
                raise HTTPException(status_code=409, detail="tts_candidate_not_approved")
            return orchestrator.select_segment_tts_replacement(
                project_id=project_id, session_id=session_id, segment_id=segment_id,
                recommendation_id=candidate_id, asset_id=str(candidate["asset_id"]),
                expected_revision=expected_session_revision,
            )
        if intent == "clear_tts_replacement":
            return orchestrator.clear_segment_tts_replacement(
                project_id=project_id, session_id=session_id,
                segment_id=str(getattr(operation, "segment_id", "")), expected_revision=expected_session_revision,
            )
        if intent == "captions_from_transcript":
            # 화면 `자동 캡션`의 첫 걸음(받아쓰기 job). 둘째 걸음(캡션 옮기기)은 화면이 job을
            # 지켜본 뒤 같은 API(`captions-from-transcript`)로 한다.
            narration_asset_id = _narration_asset_id(project_id)
            if narration_asset_id is None:
                raise HTTPException(status_code=409, detail="transcript_needs_narration")
            started = orchestrator.start_transcription(project_id=project_id, narration_asset_id=narration_asset_id)
            Thread(
                target=orchestrator.run_transcription_job,
                kwargs={"project_id": project_id, "job_id": started["job_id"], "narration_asset_id": narration_asset_id},
                daemon=True,
            ).start()
            return {
                "status": "transcription_started",
                "job_id": str(started["job_id"]),
                "notice": "말을 받아쓰고 있어요. 끝나면 캡션으로 옮길게요.",
            }
        if intent == "regenerate_part":
            # 화면 `부분 다시 만들기`와 같은 두 걸음(routers/editing_session.py).
            started = orchestrator.start_editing_session_partial_regeneration(
                project_id=project_id, session_id=session_id,
                segment_ids=list(getattr(operation, "segment_ids", ())), fields=list(getattr(operation, "fields", ())),
                expected_revision=expected_session_revision,
            )
            Thread(
                target=orchestrator.run_partial_regeneration_job,
                kwargs={
                    "project_id": project_id, "session_id": session_id, "job_id": started["job_id"],
                    "session": started["_session"], "request": started["_request"],
                    "captured_revision": started["_captured_revision"],
                },
                daemon=True,
            ).start()
            return {
                "status": "partial_regeneration_started",
                "job_id": str(started["job_id"]),
                "notice": "고른 장면을 다시 만들고 있어요.",
            }
```

- [ ] **Step 4: 스키마·안내문**

스키마:

```python
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "set_tts_replacement"}, "segment_id": {"type": "string"}, "candidate_id": {"type": "string"}}, "required": ["intent", "segment_id", "candidate_id"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "clear_tts_replacement"}, "segment_id": {"type": "string"}}, "required": ["intent", "segment_id"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "captions_from_transcript"}}, "required": ["intent"]},
        {"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "regenerate_part"}, "segment_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 16}, "fields": {"type": "array", "items": {"enum": sorted(ALLOWED_PARTIAL_REGEN_FIELDS)}, "minItems": 1}}, "required": ["intent", "segment_ids", "fields"]},
```

(service import에 `from videobox_core_engine.editing_session import ALLOWED_PARTIAL_REGEN_FIELDS`를 더한다.)

허용 intent 문장: `"set_tts_replacement/clear_tts_replacement(장면 목소리를 듣기 승인된 녹음으로 바꾸기·원래대로), captions_from_transcript(말을 받아써 캡션으로 -- \"말 받아써서 캡션 만들어줘\"), regenerate_part(고른 장면의 고른 항목만 다시 만들기), "`.

`_language_voice_catalogue` 반환 끝에 덧붙인다(마지막 `"... 모두 혼자 싣는다."` 앞):

```python
        + (
            "듣기 승인된 목소리 후보: "
            + ", ".join(f"{segment_id}={candidate_id}" for segment_id, candidate_id in context.approved_tts_candidates)
            + " -- '그 녹음으로 바꿔줘'는 set_tts_replacement(이 목록만). "
            if context.approved_tts_candidates
            else "목소리를 바꾸려면 장면 번호를 말해 달라고 하거나, 승인된 녹음이 없으면 화면에서 먼저 들어 보고 승인해 달라고 답한다. "
        )
        + f"목소리를 바꿔 둔 장면: {', '.join(context.segment_ids_with_tts_replacement) or '없음'} -- '원래 목소리로'는 clear_tts_replacement. "
        + (
            "'말 받아써서 캡션 만들어줘'는 captions_from_transcript(몇 분 걸린다, 말이 있는 장면만 바뀐다). "
            if context.has_narration_for_transcript
            else "받아쓸 내레이션이 없다 -- 받아쓰기는 먼저 내레이션을 넣어 달라고 답한다. "
        )
        + "부분 다시 만들기는 regenerate_part -- fields: " + ", ".join(sorted(ALLOWED_PARTIAL_REGEN_FIELDS))
        + ". '2번 장면 영상 다시 골라줘'처럼 **다시 추천받아** 만들라는 말일 때만 쓴다(특정 자산을 깔라는 말은 apply_media). "
```

(Task 18 뒤로 마지막 문자열 하나에 "'원래 자막으로 돌려줘'는 … 싣지 않는다. "와 "'영어로 더빙해줘'는 … 모두 혼자 싣는다."가 붙어 있다 — **이 문자열을 둘로 나눈다.** 위 덩이는 `+`로 시작하므로, 앞쪽의 붙여 쓴 문자열들(`f"번역할 수 있는 언어: ..." ... "'원래 자막으로 돌려줘'는 ..."`) **바로 뒤**에 넣고, 원래 맨 끝에 있던 Task 18의 글귀는 앞에 `+`를 붙여 `+ "'영어로 더빙해줘'는 번역해 둔 언어일 때만 dub_narration -- 아니면 먼저 번역하자고 답한다(장면이 많으면 오래 걸린다). 모두 혼자 싣는다."`로 맨 끝에 둔다. 반환식 전체는 한 쌍의 괄호 안에 있어야 한다. 고친 뒤 `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_language_voice.py -k prompt`로 문법·내용을 함께 확인한다.)

부분 다시 만들기가 **되돌리기로 돌아오는지** 먼저 확인한다: `git grep -n "partial_regeneration" packages/core-engine/src/videobox_core_engine/editing_session_and_regeneration.py | grep -n "undo\|history"`. 되돌리기 칸에 안 쌓이면 위 문장 끝에 `"이건 되돌리기로 못 돌린다 -- 창작자가 분명히 다시 만들어 달라고 했을 때만 쓴다. "`를 더한다.

- [ ] **Step 5: 화면 — 받아쓰기·부분 재생성 지켜보기**

`yujinBackgroundWork.ts` — `return YUJIN_WORK_LOST_TRACK;` 앞에:

```ts
  if (work.kind === "transcription") {
    const outcome = await pollJobUntilTerminal(async () => {
      const job = await api.getTranscriptionJob(projectId, work.jobId);
      return asPollStatus(job.status, job, job.status === "failed" ? "transcription_failed" : null);
    }, options);
    if (outcome.kind !== "succeeded") {
      return outcomeLine(outcome, {
        succeeded: "",
        failed: "말을 받아쓰지 못했어요. 잠시 뒤 다시 말해 주세요.",
        timedOut: "받아쓰기가 너무 오래 걸려서 기다리기를 멈췄어요. 잠시 뒤 다시 확인해 주세요.",
      });
    }
    // 화면 `자동 캡션`의 둘째 걸음과 같은 API.
    const revision = input.expectedRevision?.() ?? null;
    if (revision === null) return YUJIN_WORK_LOST_TRACK;
    await api.applyCaptionsFromTranscript(projectId, input.sessionId, { transcription_job_id: work.jobId, expected_revision: revision });
    return "말을 받아써서 캡션으로 옮겼어요.";
  }
  if (work.kind === "partial_regeneration") {
    const outcome = await pollJobUntilTerminal(async () => {
      const job = await api.getPartialRegenerationResult(projectId, work.jobId);
      return asPollStatus(job.status, job, job.status === "failed" ? "partial_regeneration_failed" : null);
    }, options);
    return outcomeLine(outcome, {
      succeeded: "고른 장면을 다시 만들었어요.",
      failed: "고른 장면을 다시 만들지 못했어요. 잠시 뒤 다시 말해 주세요.",
      timedOut: "다시 만들기가 오래 걸려서 기다리기를 멈췄어요. 편집본에서 확인해 주세요.",
    });
  }
```

시험(`yujinBackgroundWork.test.ts`):

```ts
  it("받아쓰기가 끝나면 화면 자동 캡션과 같은 API로 캡션을 옮긴다", { timeout: 20000 }, async () => {
    vi.spyOn(api, "getTranscriptionJob").mockResolvedValueOnce({ job_id: "tx-1", status: "succeeded", transcript_uri: "file://t" } as never);
    const apply = vi.spyOn(api, "applyCaptionsFromTranscript").mockResolvedValueOnce({} as never);

    const message = await followYujinWork({
      projectId: "p", sessionId: "s",
      work: { kind: "transcription", jobId: "tx-1", notice: "", totalSceneCount: 0, language: null },
      isStillRelevant: () => true,
      expectedRevision: () => 7,
    });

    expect(apply).toHaveBeenCalledWith("p", "s", { transcription_job_id: "tx-1", expected_revision: 7 });
    expect(message).toBe("말을 받아써서 캡션으로 옮겼어요.");
  });
```

`yujinEditingSummary.ts`:

```ts
  if (operation.intent === "set_tts_replacement") return "승인한 녹음으로 목소리를 바꿔요.";
  if (operation.intent === "clear_tts_replacement") return "원래 목소리로 돌려요.";
  if (operation.intent === "captions_from_transcript") return "말을 받아써서 캡션으로 옮겨요.";
  if (operation.intent === "regenerate_part") return "고른 장면을 다시 만들어요.";
```

시험:

```ts
  it("목소리 바꾸기·받아쓰기·부분 다시 만들기를 말한다", () => {
    expect(summary({ intent: "set_tts_replacement", segment_id: "s", candidate_id: "c" })).toBe("승인한 녹음으로 목소리를 바꿔요.");
    expect(summary({ intent: "captions_from_transcript" })).toBe("말을 받아써서 캡션으로 옮겨요.");
    expect(summary({ intent: "regenerate_part", segment_ids: ["s"], fields: ["broll"] })).toBe("고른 장면을 다시 만들어요.");
  });
```

- [ ] **Step 6: 통과·커밋**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_language_voice.py` → 통과
Run: `cd apps/web && npx vitest run src/features/editor/workbench/yujinBackgroundWork.test.ts src/features/editor/workbench/yujinEditingSummary.test.ts && npx tsc --noEmit` → passed

```bash
git add packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_adapter.py packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py services/api/src/videobox_api/routers/director_proposals.py apps/web/src/features/editor/workbench/yujinBackgroundWork.ts apps/web/src/features/editor/workbench/yujinBackgroundWork.test.ts apps/web/src/features/editor/workbench/yujinEditingSummary.ts apps/web/src/features/editor/workbench/yujinEditingSummary.test.ts tests/test_yujin_editing_language_voice.py
git commit -m "feat(yujin): 말로 목소리 교체(승인된 것만)·받아쓰기 캡션·부분 다시 만들기

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 20: 묶음 E 닫기 — 330초 벽 실측 포함

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_local_conversation.py`, `tests/test_yujin_local_conversation.py`

- [ ] **Step 1: 답장 문장** — 시험(`tests/test_yujin_local_conversation.py` 끝):

```python
def test_reply_prompt_knows_language_and_voice_work_runs_for_real() -> None:
    runtime = _RecordingRuntime()
    YujinLocalConversationService(runtime=runtime).reply(project_id="proj-1", user_text="영어로 더빙해줘")
    prompt = runtime.calls[0]["prompt"]
    assert "자막 번역·더빙·받아쓰기" in prompt
    assert "정확히 무엇을 적용할지 되물어라" in prompt
```

RED 확인 뒤, Task 12에서 바꾼 기준 글귀 `"만들기·다시 만들기·펼치기·내보내기, 완성본 만들기·캡컷 초안 만들기·미리보기 링크 만들기를 말로 시키면, 그 편집·렌더는 화면이 "`를 `"만들기·다시 만들기·펼치기·내보내기, 완성본 만들기·캡컷 초안 만들기·미리보기 링크 만들기, 자막 번역·더빙·받아쓰기·목소리 바꾸기를 말로 시키면, 그 편집·렌더는 화면이 "`로 바꾼다. GREEN → 커밋:

```bash
git add packages/core-engine/src/videobox_core_engine/yujin_local_conversation.py tests/test_yujin_local_conversation.py
git commit -m "fix(yujin): 답장이 번역·더빙·받아쓰기도 실제로 실행된다고 알게

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: 넓은 검증**

```powershell
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_language_voice.py tests/test_yujin_editing_screen_elements.py tests/test_yujin_editing_outputs.py tests/test_yujin_editing_basics.py tests/test_yujin_local_conversation.py tests/test_yujin_editing_proposal_adapter.py
cd apps/web; npx vitest run src/features/editor src/user-copy-policy.test.ts; npx tsc --noEmit; npm run build; cd ../..
```

- [ ] **Step 3: 역방향 — 재빌드·목소리 엔진·실기·지연**

```powershell
.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild
.\scripts\start-voice.ps1
lms ps
.venv/Scripts/python.exe scripts/measure_yujin_prompt_size.py
.venv/Scripts/python.exe scripts/owner-path/ask_yujin_capabilities.py <project_id> E
.venv/Scripts/python.exe scripts/owner-path/ask_yujin_capabilities.py <project_id> baseline
```
Expected: `6/6 통과`, `3/3 통과`("응 그걸로 해줘"가 편집안을 만들지 않는 줄 포함). 수치를 기준선 옆에 적는다(1.5배 넘으면 멈추고 보고 — Task 7 Step 5와 같은 규칙, Task 23 제시).

- [ ] **Step 4: 동작 — 330초 벽을 실제로 넘기는지 잰다**

브라우저 새 편집본(장면 20개 이상인 실제 영상 프로젝트): "자막 영어로 번역해줘" → **적용 요청 자체가 몇 초 안에 돌아오는지**(브라우저 개발자 도구 Network 탭의 `.../apply` 응답 시간, 또는 `docker logs videobox-api --since 5m 2>&1 | Select-String "/apply"`) 먼저 적는다 — 수십 초 이상이면 적용 라우트가 일을 기다리고 있다는 뜻이라 Global Constraint 21 위반이다, 멈추고 보고한다. 그 다음 유진 패널 `유진이 맡은 일`·저장 상태 줄이 진행을 말하는 동안 시계를 잰다(시작~완료 초). 기다리는 동안 `유진이 맡은 일` 줄이 **한 번도 사라지지 않는지** 본다(침묵 구간이 있으면 그 조각은 안 끝났다). 이어서 "영어 목소리로 더빙해줘" → `목소리를 만들고 있어요. N개 장면 중 M개 했어요.`가 늘어나는지, 완료까지 초를 잰다. **둘 중 하나라도 330초를 넘겨도 끝까지 완료되어야 한다**(job이라서). 장면당 초 = 전체 초 ÷ 장면 수를 기록한다. 끝난 뒤 완성본을 만들어 더빙 구간 음량을 잰다:

```powershell
docker exec videobox-api ffmpeg -hide_banner -i <완성본 파일> -af volumedetect -f null - 2>&1 | Select-String "mean_volume|max_volume"
```
`mean_volume`가 -50dB보다 커야 한다(무음이 아님). "말 받아써서 캡션 만들어줘" → 끝나면 장면 캡션이 바뀌어 있는지 화면에서 본다.

- [ ] **Step 5: 갭·배선·푸시**

갭: E1~E3 대조. 안 한 것: 여러 목소리 중 고르기(서버 기본 목소리만), MCP 경로의 받아쓰기는 job만 걸리고 캡션 옮기기는 화면이 한다, 듣기 승인(사람 몫).
배선: `git grep -n "translate_captions\|dub_narration\|captions_from_transcript\|regenerate_part\|set_tts_replacement" -- apps/web/src`, `git grep -n "followCaptionTranslationJob\|followDubbingJob" -- apps/web/src ':!*.test.*'` → 정의 + 화면 run 함수 + `yujinBackgroundWork.ts`.
확인 뒤 `git push origin main` (정확히 이 명령. 도구 권한이 막으면 **우회하지 말고 멈춘다** — owner에게 `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`에서 `git push origin main`을 직접 실행하거나 허용 규칙 `Bash(git push origin main)`을 추가해 달라고 알리고 기다린다. Global Constraint 18).

---

### Task 21: F — 남은 빈칸을 다시 세고, 후보를 하나씩 연다

결정 문서: "그 밖에 필요한 것 전부". 계획서 묶음 F: "시작 전에 화면 기능 전체를 다시 세어 빈칸 목록을 확정한다". 이 Task는 **세는 절차(Step 1~3)**와 **후보별 하위 단계(F1~F12)**다. 후보마다 §0의 여덟 겹을 그대로 따르고, 시험은 `tests/test_yujin_editing_more.py` 한 파일에 쌓는다. **재계수 결과 이미 열려 있거나 화면 전용이 맞는 후보는 건너뛰고 그 이유를 갭에 적는다.**

**Files:**
- Create: `scripts/count_yujin_capability_gaps.py`, `tests/test_yujin_editing_more.py`
- Modify(후보별): 도메인 모델, adapter, service, `director_proposals.py`, `yujinEditingSummary.ts`/`.test.ts`, 필요하면 `routers/library_assets.py`(F4 함수 뽑기)

**Interfaces:**
- Consumes: `store.archive_project(*, project_id)`, `store.rename_project(*, project_id, name)`(`local_project_store.py:675-690`), 라우터 인자 `library_store`(= `MediaLibraryStore`, `.user_asset_store: LibraryUserAssetStore` — `set_favorite(id, *, favorite)`, `update_media_type(id, media_type)`, `get_asset(id)`), `request.app.state.scene_image_service.generate_scene_image(*, project_id, prompt, segment_id, vertical, duration_sec, gap_slot_id)`(`routers/scene_images.py:39-64`), `orchestrator.start_exact_preview(*, project_id, session_id, expected_revision, start_sec=None, end_sec=None)` + `run_exact_preview(*, project_id, generation_id)`(`orchestration.py:819-831`, 라우트 `routers/outputs.py:173-185`), `orchestrator.list_preview_shares_for_render(*, project_id, export_id)`·`revoke_preview_share(*, project_id, share_id)`(`orchestration.py:1824-1830`), `orchestrator.start_variant_renders`·`launch_pending_variant_render_workers`(`orchestration.py:1771-1802`)
- Produces: 후보별 의도(아래), `YujinEditingContext.library_asset_ids: tuple[str, ...] = ()`, `.library_asset_types: tuple[tuple[str, str], ...] = ()`

- [ ] **Step 1: 세는 스크립트를 만든다** — `scripts/count_yujin_capability_gaps.py`:

```python
"""화면이 부르는 '바꾸는' API와 유진 의도를 나란히 놓는다 -- 묶음 F 착수 전 재계수(계획서 Task 21).

자동 판정이 아니다. 사람이 표를 보고 셋으로 가른다: (a) 이미 유진 의도가 있다, (b) 유진에게 연다,
(c) 화면 전용이 맞다(영구 삭제·사람 게이트 승인·듣기 승인·대화/기억 관리 등 -- 결정 문서 경계).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_FILE = ROOT / "apps" / "web" / "src" / "api.ts"
INTENTS_FILE = ROOT / "packages" / "domain-models" / "src" / "videobox_domain_models" / "yujin_editing_proposals.py"


def mutating_api_methods() -> list[tuple[str, str, str]]:
    text = API_FILE.read_text(encoding="utf-8")
    found: list[tuple[str, str, str]] = []
    for match in re.finditer(r"^  (\w+): (?:async )?\(", text, re.M):
        body = text[match.end(): match.end() + 1200]
        next_member = re.search(r"^  \w+: (?:async )?\(", body, re.M)
        body = body[: next_member.start()] if next_member else body
        method = re.search(r'method: "(POST|PUT|PATCH|DELETE)"', body)
        path = re.search(r"`(/api/[^`]+)`", body)
        if method and path:
            found.append((match.group(1), method.group(1), path.group(1)))
    return found


def screen_callers(name: str) -> int:
    result = subprocess.run(
        ["git", "grep", "-l", f"api.{name}(", "--", "apps/web/src", ":!*.test.ts", ":!*.test.tsx"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    return len([line for line in result.stdout.splitlines() if line.strip()])


def main() -> int:
    intents = sorted(set(re.findall(r'intent: Literal\["(\w+)"\]', INTENTS_FILE.read_text(encoding="utf-8"))))
    print(f"유진 의도 {len(intents)}개: {', '.join(intents)}\n")
    print("| api.ts 메서드 | HTTP | 경로 | 화면에서 부르는 파일 수 | 분류(a/b/c) |")
    print("|---|---|---|---|---|")
    for name, method, path in mutating_api_methods():
        callers = screen_callers(name)
        if callers:
            print(f"| {name} | {method} | {path} | {callers} | |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run: `.venv/Scripts/python.exe scripts/count_yujin_capability_gaps.py > C:/Users/atgro/AppData/Local/Temp/yujin-gaps.md`
Expected: 의도 목록 한 줄과 표. (api.ts 안에서 보조 함수로 요청을 만드는 메서드 — 예: `createYujinEditingProposal` — 는 표에 안 나올 수 있다. 그런 것은 `git grep -n "Request(\`/api" apps/web/src/api.ts`로 따로 훑는다.)

- [ ] **Step 2: 분류해서 표를 남긴다**

표의 마지막 칸을 채운다. **(c) 화면 전용**의 기준(결정 문서 경계): 영구 삭제(`DELETE` 프로젝트·자료실 `trash`·대화·기억 삭제), 사람 게이트 승인(제목 선택·대본 확정·결재 결정 기록), TTS 듣기 승인(`listening-review`), 유진 기억 승인·저장(owner 승인 구조), 설정(목소리 엔진·모델 등 §10.13 4항), 업로드 자체. 분류 표를 `docs/handoffs/`의 이번 인계 문서(Task 22) 부록으로 옮긴다 — 그래서 여기서는 임시 파일로 둔다.

- [ ] **Step 3: 후보를 확정한다**

아래 F1~F12 중 표에서 (b)로 남은 것만 연다. 표에 새로 나온 (b)가 있으면 F13으로 같은 모양의 하위 단계를 더한다(§0 여덟 겹 + 시험 넷). 표에 (b)가 하나도 없으면 F는 Step 1~3과 "영구 삭제·승인 의도가 없다" 시험(F0)만 하고 닫는다.

- [ ] **F0: 경계 시험(항상 한다)** — `tests/test_yujin_editing_more.py`:

```python
"""묶음 F -- 그 밖에 화면에서 되는 것. 경계: 영구 삭제·사람 게이트 승인은 열지 않는다(2026-10-02)."""
from __future__ import annotations

from pathlib import Path
from typing import get_args

import pytest

import videobox_api.routers.director_proposals as director_proposals_module
from videobox_core_engine.yujin_editing_proposal_adapter import YujinEditingContext, interpret_yujin_editing_request
from videobox_core_engine.yujin_editing_proposal_service import _editing_prompt
from videobox_domain_models.yujin_editing_proposals import YujinEditingOperation
from yujin_chat_fakes import ImmediateThread, ScriptedEditingProvider, create_and_apply, plain_session_project

_IDS = ("seg-hook", "seg-middle", "seg-close")


def _response(*operations: dict, revision: int = 3) -> dict:
    return {
        "schema_version": "videobox.yujin-editing-response.v1",
        "reply_text": "해 볼게요.",
        "proposal": {"proposal_id": "p", "base_session_revision": revision, "operations": list(operations)},
    }


def _context(**extra: object) -> YujinEditingContext:
    return YujinEditingContext(session_id="s", session_revision=3, segment_ids=_IDS, **extra)  # type: ignore[arg-type]


def _all_intents() -> set[str]:
    union = get_args(get_args(YujinEditingOperation)[0])
    return {get_args(model.model_fields["intent"].annotation)[0] for model in union}


def test_no_intent_deletes_forever_or_approves_a_human_gate() -> None:
    forbidden_words = ("delete", "trash", "purge", "approve_", "confirm_script", "select_title", "listening_review")
    assert not [intent for intent in _all_intents() if any(word in intent for word in forbidden_words)]
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_more.py::test_no_intent_deletes_forever_or_approves_a_human_gate` → PASS(지키는 시험이라 처음부터 초록이 맞다 — 이 시험의 RED는 "누가 `delete_project`를 더했을 때"다. 확인: 임시로 `_all_intents()` 반환에 `"delete_project"`를 더해 FAIL을 한 번 본 뒤 되돌린다).

- [ ] **F1: 프로젝트 보관(`archive_project`)** — 되돌릴 수 있는 일(목록 화면 `보관`·`되돌리기`, `routers/projects.py:141-152`). 단독 실행형.

모델:
```python
class ArchiveProjectOperation(_StrictFrozenModel):
    """이 프로젝트를 보관한다 -- 프로젝트 목록 `보관`과 같은 함수. 되돌릴 수 있다(목록의 보관함).
    **영구 삭제는 의도로 만들지 않는다**(2026-10-02 결정)."""

    intent: Literal["archive_project"]
```
`STANDALONE_INTENTS`에 `"archive_project"`. 적용(`_apply_standalone_intent`):
```python
        if intent == "archive_project":
            store.archive_project(project_id=project_id)
            return {"status": "project_archived", "notice": "프로젝트를 보관했어요. 프로젝트 목록의 보관함에서 되돌릴 수 있어요."}
```
스키마 `{"type": "object", "additionalProperties": False, "properties": {"intent": {"const": "archive_project"}}, "required": ["intent"]}`, 허용 intent 문장 `"archive_project(이 프로젝트를 보관한다 -- 되돌릴 수 있다. '지워줘·삭제해줘'라고 해도 영구 삭제는 못 하고 보관만 한다고 답한다), "`, 화면 한 줄 `if (operation.intent === "archive_project") return "프로젝트를 보관해요.";`.
시험:
```python
def test_yujin_archives_the_project_but_never_deletes_it(tmp_path: Path) -> None:
    provider = ScriptedEditingProvider(operations=[{"intent": "archive_project"}])
    app, client, project_id, session = plain_session_project(tmp_path, provider)

    response = create_and_apply(client, project_id, session, "이 프로젝트 보관해줘")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "project_archived"
    assert app.state.store.get_project(project_id=project_id)["status"] == "archived"
```
(`get_project`의 보관 상태 값이 `"archived"`가 아니면 `git grep -n "def archive_project" -A6 packages/storage-abstractions/src/videobox_storage/local_project_store.py`로 실제 값을 보고 시험을 맞춘다.)

- [ ] **F2: 프로젝트 이름 바꾸기(`rename_project`)** — `PATCH /api/projects/{id}`(`routers/projects.py:116-139`).

```python
class RenameProjectOperation(_StrictFrozenModel):
    """프로젝트 이름을 바꾼다 -- 프로젝트 화면 이름 바꾸기와 같은 함수(`RenameProjectRequest`와 같은 1..200자)."""

    intent: Literal["rename_project"]
    name: str = Field(min_length=1, max_length=200)
```
적용:
```python
        if intent == "rename_project":
            store.rename_project(project_id=project_id, name=str(getattr(operation, "name", "")).strip())
            return {"status": "project_renamed", "notice": "프로젝트 이름을 바꿨어요."}
```
스키마 `{"intent": {"const": "rename_project"}, "name": {"type": "string"}}`(required intent·name), 허용 문장 `"rename_project(프로젝트 이름 바꾸기 -- 창작자가 말한 이름 그대로), "`, 화면 한 줄 `"프로젝트 이름을 바꿔요."`. 시험: 적용 뒤 `app.state.store.get_project(project_id=project_id)["name"] == "셀러 교육 3편"`.

- [ ] **F3: 자료실 즐겨찾기(`set_library_favorite`)** — `PATCH /api/library/assets/{id}/favorite`(`routers/library_assets.py:680-689`). 대상은 이 대화에서 유진에게 보여 준 자료실 후보뿐이다.

맥락 필드(adapter, `has_narration_for_transcript` 다음):
```python
    #: 이번 요청에서 유진에게 보여 준 자료실 자산 id와 종류(`_library_candidates`). 자료실을 바꾸는
    #: 의도(즐겨찾기·종류 고치기·이름 바꾸기)는 이 목록 안에서만 된다.
    library_asset_ids: tuple[str, ...] = ()
    library_asset_types: tuple[tuple[str, str], ...] = ()
```
`director_proposals.py` 맥락: `library_asset_ids=tuple(str(item["asset_id"]) for item in library_candidates),` 와 `library_asset_types=tuple((str(item["asset_id"]), {"bgm": "music", "broll_video": "broll"}.get(str(item["asset_type"]), str(item["asset_type"]))) for item in library_candidates),`.
모델:
```python
class SetLibraryFavoriteOperation(_StrictFrozenModel):
    intent: Literal["set_library_favorite"]
    library_asset_id: str = Field(min_length=1, max_length=256)
    favorite: bool
```
검사: `if isinstance(operation, SetLibraryFavoriteOperation) and operation.library_asset_id not in set(context.library_asset_ids): return "library_asset_not_shown"`. 적용:
```python
        if intent == "set_library_favorite":
            asset_id = str(getattr(operation, "library_asset_id", ""))
            user_store = getattr(library_store, "user_asset_store", None)
            if user_store is None or user_store.get_asset(asset_id) is None:
                raise HTTPException(status_code=409, detail="builtin_asset_immutable")
            user_store.set_favorite(asset_id, favorite=bool(getattr(operation, "favorite", False)))
            return {"status": "library_favorite_set", "notice": "자료실 즐겨찾기를 바꿨어요."}
```
화면 한 줄 `favorite === true ? "자료실 즐겨찾기에 넣어요." : "자료실 즐겨찾기에서 빼요."`(`yujinEditingSummary.ts`에 `if (operation.intent === "set_library_favorite") return operation.favorite === true ? ... : ...;`). 시험 — 자료실 후보는 의미검색이 없으면 이름 대비책(`director_proposals.py:357-377` `_library_assets_by_name` → `library_store.inspect_active_assets()`)으로 오므로 그 자리를 바꿔 넣는다:

```python
def test_library_ops_only_touch_assets_yujin_was_shown() -> None:
    hidden = interpret_yujin_editing_request(_response({"intent": "set_library_favorite", "library_asset_id": "lib-x", "favorite": True}), _context())
    shown = interpret_yujin_editing_request(
        _response({"intent": "set_library_favorite", "library_asset_id": "lib-x", "favorite": True}), _context(library_asset_ids=("lib-x",)),
    )
    assert hidden.reason == "library_asset_not_shown"
    assert shown.status == "candidate_only"


def test_yujin_toggles_a_library_favorite_from_the_real_chat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = ScriptedEditingProvider(operations=[{"intent": "set_library_favorite", "library_asset_id": "lib-music-1", "favorite": True}])
    app, client, project_id, session = plain_session_project(tmp_path, provider)
    library = app.state.media_library_store
    monkeypatch.setattr(library, "inspect_active_assets", lambda: [{"library_asset_id": "lib-music-1", "media_type": "music", "asset_id": "music-calm-1"}])
    favorites: list[tuple[str, bool]] = []
    monkeypatch.setattr(library.user_asset_store, "get_asset", lambda asset_id: object() if asset_id == "lib-music-1" else None)
    monkeypatch.setattr(library.user_asset_store, "set_favorite", lambda asset_id, *, favorite: favorites.append((asset_id, favorite)))

    response = create_and_apply(client, project_id, session, "그 잔잔한 음악 즐겨찾기 해줘")

    assert response.status_code == 200, response.text
    assert favorites == [("lib-music-1", True)]
```

- [ ] **F4: 자료실 종류 고치기(`correct_library_media_type`)** — `PATCH /api/library/assets/{id}/media-type`(`routers/library_assets.py:634-660`). **같은 갈래 안에서만**(음악↔효과음, 영상↔그림)이라는 규칙이 라우트 안에 있다 — 함수로 뽑아 두 곳이 같이 쓴다.

`routers/library_assets.py`의 `_MEDIA_TYPE_GROUPS` 정의(52-57행) 다음에:
```python
def media_type_correction_problem(current: LibraryMediaType, target: LibraryMediaType) -> str | None:
    """종류 고치기는 같은 갈래 안에서만(owner 결정 2026-09-07). 화면 라우트와 유진이 같이 쓴다."""
    if _MEDIA_TYPE_GROUPS[target] != _MEDIA_TYPE_GROUPS[current]:
        return "media_type_group_mismatch"
    return None
```
라우트의 `if _MEDIA_TYPE_GROUPS[target] != _MEDIA_TYPE_GROUPS[asset.media_type]:` 두 줄을 `problem = media_type_correction_problem(asset.media_type, target)` / `if problem: raise HTTPException(status_code=422, detail=problem)`로 바꾼다. 모델 `CorrectLibraryMediaTypeOperation(intent, library_asset_id, media_type: Literal["broll","music","sfx","image"])`, 검사(목록 안 + `library_asset_types`로 같은 갈래인지 — `{"music": "audio", "sfx": "audio", "broll": "visual", "image": "visual"}`), 적용은 `user_store.get_asset(id)`로 지금 종류를 읽고 `media_type_correction_problem`을 다시 본 뒤 `user_store.update_media_type(id, LibraryMediaType(target))`. 화면 한 줄 `"자료실 종류를 고쳐요."`. 시험: 음악→그림은 생성 단계 거절(`media_type_group_mismatch`), 음악→효과음 통과. Run `tests/` 안 자료실 종류 시험(`git grep -ln "media-type" tests`)으로 라우트 동작이 같은지.

- [ ] **F5: 자료실 이름 바꾸기(`rename_library_asset`) — 묶음 A 의존**

이 단계는 **묶음 A 계획서**(`docs/superpowers/plans/2026-10-02-audit-a-security-tools-rename.ko.md` Task 6, "A4(API)")가 만드는 라우트 `PATCH /api/library/assets/{asset_id}/filename`과 저장소 메서드 `LibraryUserAssetStore.rename_asset(self, library_asset_id: str, *, filename: str) -> LibraryUserAsset`(없으면 `KeyError`, 기본 소재팩이면 `ValueError("builtin_asset_immutable")`, 빈 이름이면 `ValueError("filename_empty")`, 이름 1~255자)에 기댄다.

먼저 둘 다 있는지 센다:
```powershell
git grep -n "/api/library/assets/{asset_id}/filename" -- services/api/src/videobox_api/routers/library_assets.py
git grep -n "def rename_asset" -- packages
```
**둘 중 하나라도 0건이면 이 단계를 통째로 건너뛰고**(코드·시험을 쓰지 않는다) 갭에 "F5 건너뜀 — 묶음 A4(`PATCH /api/library/assets/{asset_id}/filename`) 미착수"라고 적는다. 둘 다 있으면: 그 라우트 본문(이름 다듬기·검사·`rename_asset` 호출)을 F4처럼 모듈 수준 함수 `rename_user_library_asset(*, user_asset_store, asset_id: str, filename: str) -> LibraryUserAsset`로 뽑아 라우트와 유진이 같이 부르게 한다(**라우트 본문을 복사하지 않는다**, 묶음 A의 `RenameLibraryAssetRequest` 검사 규칙 — `/`·`\`·제어 문자·`.`·`..` 거절 — 도 함수 안에서 같이 쓴다). 모델 `RenameLibraryAssetOperation(intent: Literal["rename_library_asset"], library_asset_id: str 1..256, filename: str 1..255)`, 검사(`library_asset_id`가 `context.library_asset_ids` 안 — 아니면 `library_asset_not_shown`), 적용(`rename_user_library_asset`; `ValueError("builtin_asset_immutable")`은 409로), 화면 한 줄 `"자료실 이름을 바꿔요."`, 시험 둘(목록 밖 거절 + F3 시험처럼 `inspect_active_assets`·`user_asset_store`를 바꿔 끼운 앱에서 적용 뒤 `rename_asset`이 받은 이름 확인). 끝나면 묶음 A의 이름 바꾸기 시험(`git grep -ln "/filename" tests`)을 같이 돌려 라우트 동작이 같은지 본다.

- [ ] **F6: 자료실 권리 적기(`set_library_rights`) — SKIPPED(owner 승인 전까지 건너뜀)**

**이 계획에서는 구현하지 않는다.** 코드·시험·안내문 어느 것도 쓰지 않는다. 재계수 표(Step 2)에 이 줄이 (b)로 보여도 (c)가 아니라 **"보류 — owner 결정 대기"**로 적는다. owner가 채팅으로 명시적으로 승인한 뒤에만 별도 계획으로 연다(이 Task 안에서 승인을 받아 바로 여는 것도 하지 않는다 — 승인 뒤 F7까지 끝낸 다음 같은 모양의 하위 단계로 더한다).

이유(반대 논리): 권리(`unknown`)는 업로드 승인 요청을 막는 **사람 확인 장치**다(`routers/outputs.py:441-449`, AK W1215-4, "owner만 안다 -- 추측해 채우지 않는다" `library_user_asset_store.py:351`). 유진이 이 값을 쓰면 말 한마디로 업로드 게이트(사람 게이트)의 전제 하나를 바꾸게 된다. 반대쪽 논리(열자는 쪽): 대표님이 "이건 내가 찍은 거야"라고 말로 하는 것은 화면에서 직접 적는 것과 같은 정보이고, 24개 넘는 자산을 하나씩 클릭하는 것보다 빠르다. 판단은 owner 몫이다.

**owner에게 물을 질문(그대로 Task 22 인계 문서 "owner 결정 필요"에 옮기고, 묶음 F를 닫을 때 채팅 보고에도 그대로 쓴다):**

> 루이스 대표님, 자료실 자산의 "누가 만들었는지(권리)" 칸을 유진에게 말로 적게 할까요? 예를 들어 대표님이 "이 영상들은 내가 찍은 거야"라고 하면 유진이 그 자산들의 권리를 `직접 촬영`으로 적습니다. 이 칸은 업로드 승인 요청을 막는 안전장치라서, 열면 말 한마디로 그 장치가 풀립니다. (1) 열지 않음(지금처럼 화면에서만) (2) 대표님이 그 대화에서 **권리를 직접 말한 자산만**, 유진이 적기 전에 자산 이름과 적을 값을 되묻고 "응"을 받은 뒤 적기 (3) 그대로 열기 — 어느 쪽으로 할까요? (기본: 1)

- [ ] **F7: 장면 그림 만들기(`generate_scene_image`)** — `POST /api/projects/{p}/scene-images`(`routers/scene_images.py:39-64`), 실측 1920x1080 약 24초(동기 응답, 330초 벽 안). **그림 묘사는 영어여야 한다**(메모리: 한국어를 넣으면 거절이 아니라 엉뚱한 그림이 나온다).

모델:
```python
class GenerateSceneImageOperation(_SegmentOperation):
    """이 장면에 쓸 그림을 만든다 -- 화면 장면 그림 만들기와 같은 함수. 만든 그림은 자산으로 들어가고,
    장면에 까는 것은 따로 `apply_media`다. `prompt_en`은 **영어** 묘사다(한국어는 엉뚱한 그림이 나온다)."""

    intent: Literal["generate_scene_image"]
    prompt_en: str = Field(min_length=3, max_length=600)
```
검사: `if isinstance(operation, GenerateSceneImageOperation) and not operation.prompt_en.isascii(): return "image_prompt_must_be_english"`. 적용:
```python
        if intent == "generate_scene_image":
            service = getattr(request.app.state, "scene_image_service", None)
            if service is None:
                raise HTTPException(status_code=503, detail="scene_image_generation_unavailable")
            session = store.get_editing_session(project_id=project_id, session_id=session_id)
            segment_id = str(getattr(operation, "segment_id", ""))
            segment = next(item for item in session.get("segments", []) if isinstance(item, dict) and str(item.get("segment_id")) == segment_id)
            made = service.generate_scene_image(
                project_id=project_id, prompt=str(getattr(operation, "prompt_en", "")), segment_id=segment_id,
                vertical=False, duration_sec=max(0.5, float(segment["end_sec"]) - float(segment["start_sec"])), gap_slot_id=None,
            )
            return {"status": "scene_image_created", "asset_id": str(made.get("scene_asset_id") or ""), "notice": "장면 그림을 만들었어요. 장면에 깔려면 '이 그림 깔아줘'라고 말해 주세요."}
```
(`vertical=False`인 이유: 세로 기본이 롱폼까지 세로로 렌더된 사고 F-9 — `models.py:547`.) `SceneImageGenerationError`는 `routers/scene_images.py`처럼 코드별 상태로 바꾼다: `except SceneImageGenerationError as exc: raise HTTPException(status_code=502 if exc.code == "failed" else 503, detail=exc.code) from exc`. 안내문: "그림 묘사는 영어로 옮겨 적는다(창작자 말이 한국어여도)". 화면 한 줄 `"장면 그림을 만들어요."`. 시험: 한국어 묘사 거절 + `monkeypatch.setattr(app.state, "scene_image_service", 가짜)`로 적용 경로(가짜의 `generate_scene_image`가 받은 `vertical`이 `False`인지).

- [ ] **F8: 장면 짧은 영상 만들기(`generate_scene_video`) — 조건부**

실측 full 18~23분·GPU 독점(`models.py:581-583`). job 저장소가 라우터 안 전역(`routers/scene_videos.py:50-90`의 `_jobs`, `_run_job`)이라, 열려면 **그 시작 절반을 모듈 함수로 뽑아야 한다**(`start_scene_video_job(*, store, service, project_id, payload, schedule)`). 재계수(Step 2)에서 owner가 실제로 쓰는 기능으로 분류됐을 때만 연다 — 아니면 갭에 "GPU를 20분 쓰는 일이라 말로 열지 않음(owner 확인 필요)"으로 올린다. 열 경우 job 지켜보기는 Task 8 모양에 `"scene_video"` 종류를 더하고(`api.getSceneVideoJob` 등 화면이 쓰는 조회 함수를 그대로 부른다), `quality`는 기본 `"preview"`(약 12초)로 둔다.

- [ ] **F9: 인포그래픽(`make_infographic`) — 숫자는 창작자 말만**

`POST /api/library/infographics`(`routers/infographics.py:76-120`) = `request.app.state.infographic_service.generate(project_id="library", topic, facts=[InfographicFact(label, value, unit, note)], style, title)`. 그림에 들어가는 숫자는 `facts`에 있는 것만 통과한다(`InfographicFactRequest` 머리말). 모델 `MakeInfographicOperation(intent, topic: str 1..200, facts: tuple[_InfographicFact, ...] 1..8, title: str|None)` — `_InfographicFact(_StrictFrozenModel)`: `label: str 1..80`, `value: float`, `unit: str = ""`. 안내문: "**facts의 숫자는 창작자가 이번 대화에서 말한 숫자만** -- 없으면 되묻는다". 적용은 라우트와 같은 호출을 하되 `InfographicUnavailable`을 라우트처럼 상태 코드로 바꾼다(`routers/infographics.py:96-115` 표 그대로 — 그 본문을 `make_library_infographic(*, service, payload) -> InfographicResponse`로 뽑아 같이 쓴다). 화면 한 줄 `"인포그래픽을 만들어요."`. 시험: 숫자 0개 거절(모델 `min_length=1`), 가짜 서비스로 적용 경로.

- [ ] **F10: 정확한 미리보기 다시 만들기(`refresh_exact_preview`)** — `POST .../exact-preview`(`routers/outputs.py:173-185`).

```python
class RefreshExactPreviewOperation(_StrictFrozenModel):
    """편집본 전체의 정확한 미리보기를 다시 만든다 -- 재생기의 미리보기 다시 만들기와 같은 함수."""

    intent: Literal["refresh_exact_preview"]
```
적용:
```python
        if intent == "refresh_exact_preview":
            started = orchestrator.start_exact_preview(
                project_id=project_id, session_id=session_id, expected_revision=expected_session_revision,
            )
            Thread(
                target=orchestrator.run_exact_preview,
                kwargs={"project_id": project_id, "generation_id": started["generation_id"]},
                daemon=True,
            ).start()
            return {"status": "exact_preview_started", "notice": "미리보기를 다시 만들고 있어요. 다 되면 재생기에 나와요."}
```
(재생기가 미리보기 상태를 스스로 읽으므로 Task 8의 지켜보기 종류를 더하지 않는다 — `notice`만.) 화면 한 줄 `"미리보기를 다시 만들어요."`. 시험: `start_exact_preview`·`run_exact_preview`를 가짜로, `Thread`를 `ImmediateThread`로.

- [ ] **F11: 미리보기 링크 끄기(`revoke_preview_links`)** — 출력 화면 `링크 끄기`(`routers/preview_shares.py:69`). 지금 편집본의 마스터 완성본에 걸린 링크를 전부 끈다(되살리기는 새 링크).

```python
class RevokePreviewLinksOperation(_StrictFrozenModel):
    intent: Literal["revoke_preview_links"]
```
적용:
```python
        if intent == "revoke_preview_links":
            session = store.get_editing_session(project_id=project_id, session_id=session_id)
            state = master_final_render_state(store=store, orchestrator=orchestrator, project_id=project_id, session=session)
            shares = orchestrator.list_preview_shares_for_render(project_id=project_id, export_id=state.export_id) if state and state.export_id else []
            for share in shares:
                if not share.get("revoked_at"):
                    orchestrator.revoke_preview_share(project_id=project_id, share_id=str(share["share_id"]))
            return {"status": "preview_links_revoked", "notice": "미리보기 링크를 껐어요."}
```
(`list_preview_shares`가 돌려주는 끈 표시 열쇠 이름은 `git grep -n "def list_preview_shares" -A20 packages/storage-abstractions/src/videobox_storage/local_project_store.py`로 확인하고 `revoked_at`을 맞춘다.) 화면 한 줄 `"미리보기 링크를 꺼요."`.

- [ ] **F12: 가로·세로 전체 변형본 출력(`render_output_variants`)** — 출력 화면 `가로·세로 출력 만들기`(`OutputsPage.tsx:754-783`, `routers/outputs.py` `variant-renders`). 숏폼은 이미 `render_short_form`. 모델 `RenderOutputVariantsOperation(intent, kinds: tuple[Literal["horizontal","vertical_full"], ...] 1..2)`. 적용: `store.list_output_variants(project_id=..., session_id=...)`에서 `kind`가 고른 것인 `variant_id`를 모아 `orchestrator.start_variant_renders(...)` + `launch_pending_variant_render_workers(...)`(숏폼 렌더 갈래 `director_proposals.py:776-798`과 같은 두 줄). 응답 `{"status": "variant_renders_started", "notice": "가로·세로 출력을 만들고 있어요. 출력 화면에서 확인해 주세요."}`(진행은 출력 화면 폴링이 보여 준다 — `render_short_form`과 같은 결정). 화면 한 줄 `"가로·세로 출력을 만들어요."`.

- [ ] **Step 4: 후보마다 커밋**

후보 하나 = 커밋 하나. 메시지 예: `feat(yujin): 말로 프로젝트 보관(되돌릴 수 있음, 영구 삭제는 안 엶)`, 마지막 줄 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. 각 커밋 전에 `tests/test_yujin_editing_more.py`와 `yujinEditingSummary.test.ts`를 돌린다.

- [ ] **Step 5: 묶음 F 닫기**

`yujin_local_conversation.py` 답장 문장에 연 것(보관·이름 바꾸기·즐겨찾기 등)을 더하고, "지워 달라는 말은 보관까지만"을 한 줄 넣는다(시험: `assert "보관까지만" in prompt`). 넓은 검증(Task 20 Step 2와 같은 명령 + `tests/test_yujin_editing_more.py`), 재빌드, `ask_yujin_capabilities.py <project_id> F`(`4/4 통과` — "영구 삭제해줘"가 편집안을 안 만드는지 포함), 브라우저에서 "이 프로젝트 보관해줘" → 프로젝트 목록 보관함에 있고 `되돌리기`로 돌아오는지. 갭: 분류표의 (c)와 건너뛴 후보·이유(F5 의존, F6 owner 결정, F8 조건). 확인 뒤 `git push origin main` (정확히 이 명령. 도구 권한이 막으면 **우회하지 말고 멈춘다** — owner에게 `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`에서 `git push origin main`을 직접 실행하거나 허용 규칙 `Bash(git push origin main)`을 추가해 달라고 알리고 기다린다. Global Constraint 18).

---

### Task 22: 프롬프트 크기·지연 최종 측정, 전체 검증, 인계

**Files:**
- Create: `docs/handoffs/2026-10-0X-yujin-capabilities-bf.ko.md`(X는 실제 날짜)
- Modify: `CLAUDE.md`(§2 표 `최신 세션 인계` 줄)

- [ ] **Step 1: 프롬프트 크기·지연 표를 만든다**

```powershell
lms ps
.venv/Scripts/python.exe scripts/measure_yujin_prompt_size.py
.venv/Scripts/python.exe scripts/owner-path/ask_yujin_capabilities.py <project_id> baseline
```
Task 0(기준선 A·B)과 Task 7·12·16·20·21에서 적은 수치를 한 표로 모은다:

| 시점 | 프롬프트 글자 수 | baseline 중앙값(초) | 그 묶음 중앙값(초) | 올라간 모델 수(`lms ps`) |
|---|---|---|---|---|

판단: baseline 중앙값이 기준선 B의 1.5배를 넘거나 한 건이라도 120초를 넘으면 **결함 후보**로 인계에 올리고, 안내문을 임의로 줄이지 않는다(owner 결정 필요 — 줄이면 "목록과 지금 값은 한 쌍" 교훈을 다시 어긴다). 그 경우 인계의 "owner 결정 필요"에 **Task 23(두 단계 판단) 실행 여부**를 측정 표와 함께 올린다. 모델이 둘 이상 올라가 있었다면 그 측정은 "GPU 경합"으로 표시한다(메모리: 경합만으로 605초까지 늘었다).

- [ ] **Step 2: 전체 검증(혼자 돌린다)**

```powershell
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --ignore=tests/test_mcp_server.py
```
(약 40~50분. 다른 명령과 동시에 돌리지 않는다.) 실패가 있으면 Global Constraint 6의 알려진 실패인지, 이 계획의 변경 때문인지 가른다 — 의심되면 `git worktree add ..\vb-before ca39f2a7f`에서 같은 시험을 돌려 비교하고, 끝나면 `git worktree remove ..\vb-before`.

```powershell
cd apps/web; npx vitest run; npx tsc --noEmit; npm run build; cd ../..
```

- [ ] **Step 3: 끝에서 끝까지 — owner 경로 한 바퀴(브라우저, 새 편집본)**

장면이 있는 실제 영상 프로젝트에서 유진에게 차례로: "2번 장면 2초에서 나눠줘" → "방금 거 되돌려줘" → "2번 장면 느리게" → "배경 음악 트랙 소리 꺼줘" → "자막 노란색으로 위쪽에" → "2번 장면에 핵심 한 줄 카드" → "자막 영어로 번역해줘"(끝까지 기다림 표시 확인) → "영어 자막으로 보여줘" → "완성본 만들어줘"(끝까지) → "미리보기 링크 만들어줘"(새 탭 재생) → "업로드 승인 요청해줘, 내일 오전"(답장이 승인됐다고 말하지 않음) → "응 그걸로 해줘"(되묻기). 각 단계 완료 목록 문구를 캡처해 인계에 붙인다. 완성본은 Task 7·12·16·20의 동작 측정(음량·픽셀·길이)을 한 번 더 한다.

- [ ] **Step 4: 배선 최종 세기**

```powershell
git grep -c "intent: Literal\[" -- packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py
git grep -n "operation.intent === \"" -- apps/web/src/features/editor/workbench/yujinEditingSummary.ts | Measure-Object -Line
```
두 수가 같아야 한다(모든 의도가 화면 한 줄을 가진다 — 다르면 빠진 의도를 찾아 Task를 연다). `_EDITING_OPERATION_SCHEMA`의 `"const": "` 개수도 같은지 센다: `git grep -c "\"const\": \"" -- packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py`(스키마 밖 `const` 두 곳 — `schema_version`, `base_session_revision` — 을 빼고 비교).

- [ ] **Step 5: 인계 문서와 CLAUDE.md 줄**

`docs/handoffs/2026-10-0X-yujin-capabilities-bf.ko.md`에 (§7 턴 종료 보고 요건): 한 일(묶음별 연 의도 목록), 검증(전체 pytest 수·시간, vitest, 실기 표, 프롬프트·지연 표, 동작 측정 수치), **검증 못 한 것**, 재사용 게이트(§8.1: 재사용 — 화면 라우트가 부르는 core·orchestrator 함수 전부, 공용 폴링 / 부분 이식 — 라우트 본문을 함수로 뽑은 넷: 완성본·캡컷 워커, 업로드 승인 요청, 포맷 적용 / 새로 쓴 것 — `session_master_outputs.py`(화면 규칙의 서버판), `yujinApplyOutcome.ts`, `yujinBackgroundWork.ts` / 제외 — 영구 삭제·사람 게이트 승인·듣기 승인·캡컷 앱 넘기기·권리 적기(owner 결정 대기)), 경계 보존 여부, owner 결정 필요 항목(F6 권리 — Task 21 F6의 질문 문단을 **글자 그대로** 옮긴다, F8 장면 영상, Task 23 실행 여부(지연이 기준을 넘었을 때), 지연 표가 기준을 넘었으면 그 판단), Task 21 분류표 부록, 알려진 갭(받아쓰기 캡션은 MCP에서 job까지만; 단독 실행형은 실행 전에 편집안을 소진하므로 실행이 중간에 실패하면 그 편집안은 다시 못 쓴다 — 창작자가 다시 말하면 새 편집안이 생긴다. 두 번 적용 방지는 Task 4·Task 12 실측 결과를 그대로 옮긴다).

`CLAUDE.md` §2 표의 `| **최신 세션 인계** | ... |` 줄을 새 문서 경로로 바꾼다. Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_handoff_entry_point.py` → 통과.

```bash
git add docs/handoffs/2026-10-0X-yujin-capabilities-bf.ko.md CLAUDE.md
git commit -m "docs: 유진 화면 기능 전부 열기(묶음 B~F) 인계 + 최신 인계 줄 옮김

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
확인 뒤 `git push origin main` (정확히 이 명령. 도구 권한이 막으면 **우회하지 말고 멈춘다** — owner에게 `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`에서 `git push origin main`을 직접 실행하거나 허용 규칙 `Bash(git push origin main)`을 추가해 달라고 알리고 기다린다. Global Constraint 18).

---

### Task 23 (조건부): 두 단계 판단 — 묶음을 먼저 고르고, 그 묶음의 안내문·스키마만 싣는다

**언제 하나:** Task 7·12·16·20·21·22의 지연 측정에서 baseline 중앙값이 기준선 B의 **1.5배를 넘었고**(GPU 경합 없는 측정끼리 비교), owner가 채팅으로 "Task 23 해 보자"를 승인했을 때만. 그 밖에는 **건너뛰고** 인계에 "Task 23 미실행(조건 불충족)"이라고 적는다. 안내문을 임의로 깎는 것은 여전히 금지다 — 이 Task는 안내문을 지우지 않고 **이번 요청에 필요 없는 묶음만 이번 호출에서 빼는** 설계다.

**설계:** 첫 단계는 짧은 구조화 호출 하나로 창작자 말이 어느 **기능 묶음**(1~3개)에 속하는지 고른다. 둘째 단계는 지금의 편집 판단 호출 그대로이되, (a) 목록 문단(`_..._catalogue`)은 고른 묶음 것만 싣고, (b) 응답 스키마의 `oneOf`도 고른 묶음의 의도만 남긴다. 기본 규칙(JSON만, revision, 모호하면 null, 장면 번호 표, 출력 예시)은 **언제나** 싣는다. 첫 단계가 실패하거나 이상한 답을 내면 **전부 싣는다**(지금과 같은 동작 — fail-open). 묶음에 안 들어간 의도는 늘 싣는다(조용히 기능이 사라지지 않게). 스위치 `TWO_STAGE_ROUTING`(기본 `False`)로만 켠다.

**대가(반대 논리):** 호출이 하나 늘어난다(첫 단계 몇 초). 첫 단계가 묶음을 잘못 고르면 둘째 단계에 맞는 의도가 없어 편집안이 안 나온다(잘못된 편집 대신 되묻기가 된다 — 스키마가 그 밖의 의도를 막는다). 그래서 **채택 기준은 지연과 정확도 둘 다**다(Step 6).

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py`(`_EDITING_OPERATION_SCHEMA` 다음에 묶음 표·첫 단계 함수, `_editing_response_schema`·`_editing_prompt`·`YujinEditingProposalService.create`)
- Modify: `scripts/measure_yujin_prompt_size.py`(묶음 인자)
- Create: `tests/test_yujin_editing_routing.py`

**Interfaces:**
- Consumes: `runtime.generate_structured(*, project_id: str, task_type: LLMTaskType, prompt: str, response_schema: dict) -> 응답(.output_data: dict)`(같은 파일 `YujinEditingProposalService.create`가 쓰는 그 모양), `_EDITING_OPERATION_SCHEMA["oneOf"]`(항목마다 `["properties"]["intent"]["const"]`)
- Produces: `TWO_STAGE_ROUTING: bool = False`; `_INTENT_GROUPS: dict[str, frozenset[str]]`; `_ROUTING_GROUP_LABELS: dict[str, str]`; `_ALL_SCHEMA_INTENTS: frozenset[str]`; `_UNGROUPED_INTENTS: frozenset[str]`; `_intents_for_groups(groups: frozenset[str]) -> frozenset[str]`; `route_editing_groups(*, runtime, project_id: str, instruction: str) -> frozenset[str] | None`; `_editing_response_schema(session_revision: int, intents: frozenset[str] | None = None)`; `_editing_prompt(*, instruction: str, context: YujinEditingContext, groups: frozenset[str] | None = None) -> str`

- [ ] **Step 1: 실패하는 시험** — `tests/test_yujin_editing_routing.py`:

```python
"""두 단계 판단(계획 Task 23, 조건부). 첫 단계가 묶음을 고르고 둘째 단계는 그 묶음만 싣는다.

지키는 것: (1) 모든 의도가 묶음을 가진다, (2) 첫 단계가 실패하면 전부 싣는다(지금과 같다),
(3) 고른 묶음만 실어도 기본 규칙("모호하면 null")은 남는다, (4) 스위치가 꺼져 있으면 호출은 하나다.
"""
from __future__ import annotations

import pytest

import videobox_core_engine.yujin_editing_proposal_service as service_module
from videobox_core_engine.yujin_editing_proposal_adapter import YujinEditingContext
from videobox_core_engine.yujin_editing_proposal_service import (
    _ALL_SCHEMA_INTENTS,
    _UNGROUPED_INTENTS,
    YujinEditingProposalService,
    _editing_prompt,
    _editing_response_schema,
    _intents_for_groups,
    route_editing_groups,
)
from videobox_provider_interfaces.llm import StructuredLLMResponse

_CONTEXT = YujinEditingContext(session_id="s", session_revision=3, segment_ids=("seg-1", "seg-2"))


class _Runtime:
    def __init__(self, answers: list[object]) -> None:
        self.answers = list(answers)
        self.calls: list[dict] = []

    def generate_structured(self, *, project_id, task_type, prompt, response_schema):  # noqa: ANN001
        self.calls.append({"prompt": prompt, "response_schema": response_schema})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return StructuredLLMResponse(provider_name="local_qwen", model_name="q", output_data=answer, raw_text="{}", metadata={})


def _no_proposal() -> dict:
    return {"schema_version": "videobox.yujin-editing-response.v1", "reply_text": "어느 장면일까요?", "proposal": None}


def test_every_editing_intent_belongs_to_a_routing_group() -> None:
    assert _UNGROUPED_INTENTS == frozenset(), sorted(_UNGROUPED_INTENTS)


def test_routing_falls_back_to_everything_when_the_answer_is_unusable() -> None:
    assert route_editing_groups(runtime=_Runtime([RuntimeError("engine off")]), project_id="p", instruction="자막 노랗게") is None
    assert route_editing_groups(runtime=_Runtime([{"groups": ["nope"]}]), project_id="p", instruction="자막 노랗게") is None
    assert route_editing_groups(runtime=_Runtime([{"groups": "captions"}]), project_id="p", instruction="자막 노랗게") is None


def test_routing_returns_the_groups_it_was_given() -> None:
    chosen = route_editing_groups(runtime=_Runtime([{"groups": ["captions", "nope"]}]), project_id="p", instruction="자막 노랗게")
    assert chosen == frozenset({"captions"})


def test_a_routed_prompt_keeps_the_base_rules_and_is_shorter() -> None:
    full = _editing_prompt(instruction="자막 노랗게 해줘", context=_CONTEXT)
    routed = _editing_prompt(instruction="자막 노랗게 해줘", context=_CONTEXT, groups=frozenset({"captions"}))

    assert "요청이 모호하거나 안전한 후보를 만들 수 없으면 proposal은 null" in routed
    assert "현재 revision: 3." in routed
    assert "이번 요청에 쓸 수 있는 intent는" in routed
    assert "set_caption_style" in routed
    assert "되돌릴 수 있는 편집" not in routed  # 기본기 묶음의 목록 문단은 빠졌다
    assert "되돌릴 수 있는 편집" in full
    assert len(routed) < len(full)


def test_a_routed_schema_only_offers_the_chosen_intents() -> None:
    schema = _editing_response_schema(3, frozenset({"set_caption_style"}))
    entries = schema["properties"]["proposal"]["properties"]["operations"]["items"]["oneOf"]
    assert [entry["properties"]["intent"]["const"] for entry in entries] == ["set_caption_style"]
    everything = _editing_response_schema(3)["properties"]["proposal"]["properties"]["operations"]["items"]["oneOf"]
    assert len(everything) == len(_ALL_SCHEMA_INTENTS)


def test_intents_for_groups_never_offers_an_intent_the_schema_does_not_have() -> None:
    assert _intents_for_groups(frozenset({"basics"})) <= _ALL_SCHEMA_INTENTS
    assert "set_scene_speed" in _intents_for_groups(frozenset({"basics"}))


def test_routing_off_means_one_call_and_on_means_two(monkeypatch: pytest.MonkeyPatch) -> None:
    off = _Runtime([_no_proposal()])
    YujinEditingProposalService(runtime=off).create(project_id="p", instruction="자막 노랗게", context=_CONTEXT)
    assert len(off.calls) == 1

    monkeypatch.setattr(service_module, "TWO_STAGE_ROUTING", True)
    on = _Runtime([{"groups": ["captions"]}, _no_proposal()])
    YujinEditingProposalService(runtime=on).create(project_id="p", instruction="자막 노랗게", context=_CONTEXT)
    assert len(on.calls) == 2
    second_entries = on.calls[1]["response_schema"]["properties"]["proposal"]["properties"]["operations"]["items"]["oneOf"]
    assert {entry["properties"]["intent"]["const"] for entry in second_entries} == _intents_for_groups(frozenset({"captions"}))
```

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_routing.py::test_every_editing_intent_belongs_to_a_routing_group`
Expected: FAIL — `ImportError: cannot import name '_ALL_SCHEMA_INTENTS'`

- [ ] **Step 2: 묶음 표와 첫 단계** — `yujin_editing_proposal_service.py`, `_EDITING_OPERATION_SCHEMA = {` 블록이 닫힌 **다음**(그 블록을 닫는 `}` 줄 다음, `def _editing_response_schema(` 앞)에:

```python
#: 두 단계 판단(계획 Task 23)을 켜는 스위치. 꺼져 있으면 지금과 똑같이 한 번만 부른다.
#: 켜는 것은 owner 승인과 실측(정확도·지연)을 거친 뒤에만 -- 계획서 Task 23 Step 6.
TWO_STAGE_ROUTING = False

#: 기능 묶음 -> 의도. 아직 안 연 의도(묶음 F의 건너뛴 후보)가 들어 있어도 된다 --
#: `_intents_for_groups`가 스키마에 있는 것만 남긴다. **새 의도를 열면 여기에도 넣는다**
#: (`test_every_editing_intent_belongs_to_a_routing_group`이 지킨다).
_INTENT_GROUPS: dict[str, frozenset[str]] = {
    "basics": frozenset({
        "set_scene_speed", "set_segment_bounds", "set_cut_action", "reorder_segments",
        "split_segment", "merge_with_previous", "undo_last_edit", "redo_last_edit", "set_track_state",
    }),
    "media": frozenset({
        "apply_media", "remove_media", "set_scene_look", "set_photo_motion", "set_picture_cleanup",
        "set_sound_cleanup", "set_scene_transform", "set_scene_transition", "set_image_overlay",
        "remove_image_overlay", "regenerate_part", "generate_scene_image", "generate_scene_video",
    }),
    "captions": frozenset({
        "set_caption_text", "set_caption_font", "set_caption_style", "apply_format_template",
        "translate_captions", "set_caption_language", "captions_from_transcript",
    }),
    "screen_elements": frozenset({
        "set_explanation_card", "remove_explanation_card", "set_table_overlay", "remove_table_overlay",
        "set_shape_overlay", "remove_shape_overlay",
    }),
    "voice": frozenset({"dub_narration", "set_tts_replacement", "clear_tts_replacement"}),
    "outputs": frozenset({
        "render_final_video", "export_capcut_draft", "create_preview_link", "request_upload_approval",
        "create_short_form", "remake_short_form", "unfold_short_form", "render_short_form",
        "resolve_variant_conflict", "refresh_exact_preview", "revoke_preview_links", "render_output_variants",
    }),
    "project": frozenset({
        "archive_project", "rename_project", "set_library_favorite", "correct_library_media_type",
        "rename_library_asset", "make_infographic",
    }),
}

#: 첫 단계가 읽는 묶음 설명. 창작자가 할 말로 적는다.
_ROUTING_GROUP_LABELS: dict[str, str] = {
    "basics": "장면 자르기·나누기·붙이기·순서 바꾸기·빼기·배속·되돌리기·다시 하기·트랙 숨기기와 소리 끄기",
    "media": "영상·사진·음악·효과음 깔기와 빼기, 색감·전환·화면 맞춤·손떨림·소리 정리, 화면 위에 사진·영상 얹기, 장면 다시 만들기, 장면 그림 만들기",
    "captions": "자막 글·글꼴·크기·색·위치, 저장한 포맷, 자막 번역·자막 언어, 말 받아써서 캡션",
    "screen_elements": "설명 카드·표·도형 얹기와 빼기",
    "voice": "더빙, 장면 목소리 바꾸기",
    "outputs": "완성본·숏폼·캡컷 초안·미리보기 링크·업로드 승인 요청·가로세로 출력·변형본 충돌",
    "project": "프로젝트 보관·이름, 자료실 즐겨찾기·종류·이름, 인포그래픽",
}

_ALL_SCHEMA_INTENTS: frozenset[str] = frozenset(
    str(entry["properties"]["intent"]["const"]) for entry in _EDITING_OPERATION_SCHEMA["oneOf"]
)
_UNGROUPED_INTENTS: frozenset[str] = _ALL_SCHEMA_INTENTS - frozenset().union(*_INTENT_GROUPS.values())

_ROUTING_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "groups": {"type": "array", "items": {"enum": sorted(_ROUTING_GROUP_LABELS)}, "minItems": 1, "maxItems": 3},
    },
    "required": ["groups"],
}


def _intents_for_groups(groups: frozenset[str]) -> frozenset[str]:
    """고른 묶음의 의도 + 묶음 없는 의도. 스키마에 없는 이름은 뺀다."""
    chosen = frozenset().union(*(_INTENT_GROUPS[group] for group in groups if group in _INTENT_GROUPS))
    return (chosen & _ALL_SCHEMA_INTENTS) | _UNGROUPED_INTENTS


def route_editing_groups(*, runtime: object, project_id: str, instruction: str) -> frozenset[str] | None:
    """첫 단계: 창작자 말이 어느 묶음(1~3개)인지. **실패하면 None**(= 전부 싣는다, 지금과 같다)."""
    labels = " / ".join(f"{name}: {label}" for name, label in _ROUTING_GROUP_LABELS.items())
    prompt = (
        "너는 VideoBox 편집 요청 분류기다. 창작자 말이 아래 기능 묶음 중 어디에 속하는지 1~3개 고른다. "
        "JSON 객체 하나만 출력한다. 애매하면 가능성 있는 묶음을 모두(최대 3개) 고른다. "
        f"묶음: {labels}. "
        f"창작자 요청: {instruction}"
    )
    try:
        response = runtime.generate_structured(  # type: ignore[attr-defined]
            project_id=project_id,
            task_type=LLMTaskType.YUJIN_CONVERSATION,
            prompt=prompt,
            response_schema=_ROUTING_SCHEMA,
        )
        groups = response.output_data.get("groups") if isinstance(response.output_data, dict) else None
    except Exception:  # noqa: BLE001 -- 첫 단계는 거들 뿐이다. 실패하면 지금처럼 전부 싣는다.
        return None
    if not isinstance(groups, list):
        return None
    chosen = frozenset(str(group) for group in groups if str(group) in _INTENT_GROUPS)
    return chosen or None
```

- [ ] **Step 3: 스키마·안내문·서비스가 묶음을 받게**

(a) `_editing_response_schema` — 기준 글귀

```python
def _editing_response_schema(session_revision: int) -> dict[str, object]:
    return {
```

를 다음으로 바꾼다:

```python
def _editing_response_schema(session_revision: int, intents: frozenset[str] | None = None) -> dict[str, object]:
    items: dict[str, object] = (
        _EDITING_OPERATION_SCHEMA
        if intents is None
        else {"oneOf": [entry for entry in _EDITING_OPERATION_SCHEMA["oneOf"] if entry["properties"]["intent"]["const"] in intents]}
    )
    return {
```

같은 함수 안 기준 글귀 `"operations": {"type": "array", "minItems": 1, "maxItems": 16, "items": _EDITING_OPERATION_SCHEMA},`를 `"operations": {"type": "array", "minItems": 1, "maxItems": 16, "items": items},`로 바꾼다.

(b) `_editing_prompt` — 머리 `def _editing_prompt(*, instruction: str, context: YujinEditingContext) -> str:`를 `def _editing_prompt(*, instruction: str, context: YujinEditingContext, groups: frozenset[str] | None = None) -> str:`로 바꾸고, 본문 첫 줄(`    durations = dict(context.segment_durations)` — Task 2가 넣은 줄) **앞**에:

```python
    def part(group: str, text: str) -> str:
        # 두 단계 판단(Task 23): 고른 묶음의 목록 문단만 싣는다. groups가 None이면 전부(지금과 같다).
        return text if groups is None or group in groups else ""

    language_voice_text = (
        _language_voice_catalogue(context) if groups is None or groups & {"captions", "voice"} else ""
    )
    routing_note = "" if groups is None else (
        f"이번 요청에 쓸 수 있는 intent는 {', '.join(sorted(_intents_for_groups(groups)))}뿐이다 -- "
        "맞는 것이 없으면 proposal은 null로 두고 무엇을 하려는지 되묻는다. "
    )
```

그리고 반환식 안 목록 문단 줄을 아래 표대로 감싼다 — 각 줄의 `f"{X} "`를 `f"{part('묶음', X)} "`로 바꾼다. 예: `        f"{_approved_asset_catalogue(context)} "` → `        f"{part('media', _approved_asset_catalogue(context))} "`. f-string 안의 문자열은 **작은따옴표**로 쓴다(바깥이 큰따옴표다).

| 줄 | 묶음 |
|---|---|
| `_caption_catalogue(context, instruction)` | `captions` |
| `_approved_asset_catalogue(context)`, `_scene_look_catalogue(context)`, `_photo_motion_catalogue(context)`, `_frame_fit_catalogue(context)`, `_scene_transition_catalogue()`, `_image_overlay_catalogue(context)` | `media` |
| `_caption_font_catalogue(context)`, `_caption_style_catalogue(context)` | `captions` |
| `_short_form_catalogue(context)`, `_variant_conflict_catalogue(context)`, `_output_catalogue(context)` | `outputs` |
| `_split_merge_catalogue(context)`, `_undo_redo_catalogue(context)`, `_speed_words_catalogue()`, `_track_state_catalogue(context)` | `basics` |
| `_screen_element_catalogue(context)` | `screen_elements` |
| `_language_voice_catalogue(context)` | `captions`·`voice` 둘 중 하나라도 고르면 싣는다 — 이 줄은 `        f"{language_voice_text} "`로 바꾸고, 변수는 아래 (b) 머리에서 만든다 |

표에 없는 목록 문단 줄(Task 21에서 더한 것)은 **감싸지 않는다**(늘 싣는다). 목록 문단이 아닌 줄(허용 intent 문장, 장면 번호 표, 소리 정리 규칙 문단, 출력 예시)은 건드리지 않는다. 마지막으로 기준 글귀 `        f"proposal이 있을 때 출력 예시: {json.dumps(success_example, ensure_ascii=False)}. "` **앞 줄**에 `        f"{routing_note}"`를 넣는다.

(c) `YujinEditingProposalService.create` — 기준 글귀

```python
        response = self.runtime.generate_structured(  # type: ignore[attr-defined]
            project_id=project_id,
            task_type=LLMTaskType.YUJIN_CONVERSATION,
            prompt=_editing_prompt(instruction=instruction, context=context),
            response_schema=_editing_response_schema(context.session_revision),
        )
```

를 다음으로 바꾼다:

```python
        groups = (
            route_editing_groups(runtime=self.runtime, project_id=project_id, instruction=instruction)
            if TWO_STAGE_ROUTING
            else None
        )
        response = self.runtime.generate_structured(  # type: ignore[attr-defined]
            project_id=project_id,
            task_type=LLMTaskType.YUJIN_CONVERSATION,
            prompt=_editing_prompt(instruction=instruction, context=context, groups=groups),
            response_schema=_editing_response_schema(
                context.session_revision, None if groups is None else _intents_for_groups(groups),
            ),
        )
```

(`TWO_STAGE_ROUTING`은 함수 안에서 모듈 전역 이름으로 그때그때 읽힌다 — 그래야 시험의 `monkeypatch.setattr(service_module, "TWO_STAGE_ROUTING", True)`가 먹는다. 지역 변수나 기본 인자로 복사하지 않는다.)

(d) `scripts/measure_yujin_prompt_size.py` — `    prompt = _editing_prompt(instruction="2번 장면 두 배 빠르게 해줘", context=context)`를

```python
    groups = frozenset(sys.argv[1:]) or None
    prompt = _editing_prompt(instruction="2번 장면 두 배 빠르게 해줘", context=context, groups=groups)
```

로 바꾼다(인자 없이 돌리면 지금과 같은 숫자).

- [ ] **Step 4: 통과·넓은 검증**

Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_routing.py` → 전부 통과. `test_every_editing_intent_belongs_to_a_routing_group`이 실패하면 실패 메시지의 의도를 `_INTENT_GROUPS`의 맞는 묶음에 넣는다(묶음을 새로 만들지 않는다).
Run: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_yujin_editing_basics.py tests/test_yujin_editing_outputs.py tests/test_yujin_editing_screen_elements.py tests/test_yujin_editing_language_voice.py tests/test_yujin_editing_more.py tests/test_yujin_editing_proposal_adapter.py tests/test_yujin_editing_command_evaluation.py tests/test_yujin_caption_font.py tests/test_yujin_editing_short_form.py` → 전부 통과(스위치가 꺼져 있으니 기존 동작이 같아야 한다)
Run: `.venv/Scripts/python.exe scripts/measure_yujin_prompt_size.py` → Task 22 Step 1의 마지막 숫자와 **같아야 한다**(다르면 감싸기가 묶음 없는 경우에도 글자를 바꾼 것이다 — 고친다). `... measure_yujin_prompt_size.py basics`·`captions`·`outputs` → 각각 더 작은 숫자. 넷을 적는다.

- [ ] **Step 5: 커밋(스위치 꺼진 채)**

```bash
git add packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py scripts/measure_yujin_prompt_size.py tests/test_yujin_editing_routing.py
git commit -m "feat(yujin): 두 단계 판단(묶음 고르기 -> 그 묶음만) 스위치 -- 기본 꺼짐, 실측 뒤 owner 판단

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: 실측 — 켜고 재고, 채택 여부를 owner에게 묻는다**

`yujin_editing_proposal_service.py`의 `TWO_STAGE_ROUTING = False`를 **커밋하지 않은 채** `True`로 바꾸고 재빌드한다(이미지는 작업 트리로 빌드된다):
```powershell
.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild
lms ps
foreach ($bundle in "baseline","B","C","D","E","F") { .venv/Scripts/python.exe scripts/owner-path/ask_yujin_capabilities.py <project_id> $bundle }
```
각 묶음의 `N/M 통과`와 중앙값을 **스위치 꺼진 마지막 측정**(Task 22 Step 1 표) 옆에 적는다(스크립트가 지시마다 새 편집본을 연다 — 새 세션 규칙). 채택 기준(셋 다): (1) 모든 묶음의 통과 수가 꺼졌을 때 이상, (2) "응 그걸로 해줘"·"영구 삭제해줘"가 여전히 편집안을 만들지 않음, (3) baseline 중앙값이 기준선 B의 1.5배 이하(경합 없는 측정). 결과 표를 owner에게 보이고 채택 여부를 묻는다.

- [ ] **Step 7: 결정대로 마무리**

- **채택(owner가 채팅으로 승인):** `TWO_STAGE_ROUTING = True`로 두고, 그 줄 위 주석에 "owner 승인 날짜, 실측 표 요약"을 한 줄 적어 커밋한다(메시지 `feat(yujin): 두 단계 판단 켬 -- 실측 …`, 마지막 줄 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`). 재빌드 후 브라우저 새 편집본에서 "자막 노란색으로"·"2번 장면 2초에서 나눠줘"·"완성본 만들어줘"·"응 그걸로 해줘"를 한 번 더 밟는다.
- **불채택:** `git checkout -- packages/core-engine/src/videobox_core_engine/yujin_editing_proposal_service.py`로 스위치를 되돌리고, Step 5 커밋을 `git revert --no-edit <Step 5 커밋 sha>`로 되돌린다(꺼진 채 남는 죽은 코드를 두지 않는다). 재빌드한다. 실측 표와 불채택 이유를 인계에 남긴다.
- 어느 쪽이든 그 뒤 `git push origin main` (정확히 이 명령. 도구 권한이 막으면 **우회하지 말고 멈춘다** — owner에게 `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`에서 `git push origin main`을 직접 실행하거나 허용 규칙 `Bash(git push origin main)`을 추가해 달라고 알리고 기다린다. Global Constraint 18).
