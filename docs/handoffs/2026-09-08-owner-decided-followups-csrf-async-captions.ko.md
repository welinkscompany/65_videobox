# 인계 — owner 결정 뒤 후속 조치: CSRF 방어·자막 번역 비동기화·정리 (2026-09-08, 두 번째)

## 한 줄

`2026-09-08-fixing-the-2026-09-07-full-audit.ko.md`가 owner 결정 대기로 남겨 둔
§1-6·§3-2·미디어팩 정리에 대해 owner가 실제로 결정했고(2026-09-08 대화), 그
결정대로 처리했다. 처리한 뒤 owner가 컨테이너 재시작·나머지 미디어팩 정리·
독립 코드리뷰·재현 검증을 다시 지시했고(같은 대화, §7), 그 코드리뷰가
`local_pipeline.py`의 `start_variant_renders`(§1-3 확장 grep이 놓친 세 번째
leak 자리)를 찾아 같이 고쳤다. 커밋 다섯 + 미디어팩 정리(git 밖, 총
2.9GB) + 컨테이너 재빌드 두 번 + 그 안에서 직접 재현한 확인 셋(§7.3) +
전체 pytest 두 번(4745→4747, 둘 다 0 failed).

## 0. owner 결정 (2026-09-08 대화)

| 항목 | 결정 |
|---|---|
| §1-6 (인라인 동기 문 다섯) | 자막번역부터, 나머지는 이어서 |
| §1-7 (principal 없음) | 지금 Origin 헤더 검사 추가 |
| §3-2 (경로 등록 여섯 문) | 유지 |
| 옛 미디어팩 1.3.0 (477MB×2) | 지금 지운다 |

## 1. §1-7. 승인 문 다섯 개에 최소 CSRF 방어

**무엇을** — `services/api/src/videobox_api/csrf_guard.py`의
`require_trusted_origin` FastAPI dependency를 다섯 라우트에 `Depends()`로
걸었다: `review.py`의 `approve_review`, `footage_organizer.py`의
`approve_proposal`·`approve_sequence`, `yujin_memory.py`의 `approve_candidate`,
`director_proposals.py`의 `apply`.

**규칙** — `Origin` 헤더가 있는데 `http://127.0.0.1:5173`·`http://localhost:5173`
목록 밖이면 403 `{"reason": "untrusted_origin"}`. **헤더가 아예 없으면
통과시킨다** — curl·스모크 스크립트·MCP 도구·`owner_sample_edit_package.py`
같은 브라우저 밖 호출자가 전부 이 모양이고, 크로스오리진 POST는 브라우저가
Origin을 반드시 붙이므로 이 길로는 못 들어온다.

**정식 인증이 아니다.** SaaS·다중사용자 인증(CLAUDE.md §6)과는 다른 저비용
CSRF 완화책이다. §1-7의 나머지(principal 자체 증명, 승인 토큰)는 여전히
owner 결정 대기다 — 이번엔 딱 owner가 승인한 것만 넣었다.

**RED→GREEN** — `tests/test_approval_routes_reject_untrusted_origin.py`: 신뢰
목록 밖 Origin 다섯 문 전부 403, Origin 없는 요청은 통과(진짜 핸들러까지
도달), 신뢰 목록 안 Origin도 통과.

**Tauri 셸로 전환하면** — 웹뷰가 다른 origin(예: `tauri://`)으로 뜰 수 있다.
그러면 `TRUSTED_ORIGINS`에 추가해야 한다. 이번엔 안 건드렸다 — Tauri 실제
빌드가 아직 없다(§10.19 참고).

## 2. §1-3 확장. 잡 실패 저장부가 21곳 더 있었다

지난 세션(2026-09-08 첫 번째 인계)은 "잡 저장 여섯 곳"을 26곳 이상으로 재고
**의도적으로 건너뛰었다.** 이번엔 그 결정을 다시 열지 않고, 대신 그 26곳 중
**실제로 파일 경로/명령 출력을 담을 수 있는 예외 종류만** 좁혀 잡는
`packages/core-engine/src/videobox_core_engine/job_error_message.py`의
`safe_job_error_message(exc)`를 만들어 지난번 조사가 찾은 사이트 21곳
(`local_pipeline.py` 21 · `media_analysis.py` 2 · `scene_videos.py` 1 ·
`footage_organizer.py`의 `_footage_error` catch-all 1)에 적용했다. 이번
세션 작업(orchestration.py의 캡션 번역 잡)을 짜다가 같은 패턴
(`error_detail=str(exc)`)이 orchestration.py에도 둘(유튜브 학습 잡, 더빙 잡)
더 있는 것을 찾아 같이 고쳤다.

**규칙** — `FileNotFoundError`·`PermissionError`·`subprocess.CalledProcessError`만
고정 문구(`asset_file_missing`/`asset_file_permission_denied`/
`external_command_failed`)로 바꾸고 원문은 로그로만. 그 밖(코드성 `ValueError`,
이 저장소 시험 다수가 쓰는 `raise OSError("설명 문구")`류 주입 실패)은
그대로 둔다.

**처음엔 `OSError`를 통째로 잡았다가 전체 pytest가 실제 결함을 잡았다** —
`test_api.py::test_provider_trace_audit_endpoint_includes_review_guidance_attempt_entry`가
`raise OSError("review guidance persistence offline")`(경로 없는 안전한
설명 문구)를 그대로 기대하고 있었다. `grep "raise OSError("`로 세어 보니 이
저장소에 이 패턴이 40건 넘게 있다 — 전부 저장소 장애를 흉내 내는 시험
더블이다. `OSError`를 통째로 잡는 것은 위험하다는 것을 이걸로 확인했다.

**RED** — `tests/test_job_error_message_has_no_filesystem_path.py`: 헬퍼
단위 시험 넷(경로 없는 코드성 문구·`RuntimeError`는 그대로 둔다는 것 포함) +
실제 재현 하나(`run_segment_analysis`가 지워진 대본 파일을 읽으려다
`FileNotFoundError`를 내는 것 → 잡 기록의 `error_message`가 절대 경로
없이 `asset_file_missing`으로 남는 것을 확인).

## 3. §1-6 (부분). 자막 번역을 비동기로

**무엇을** — `POST .../editing-sessions/{sid}/caption-translations`가
이제 202 + `job_id`만 돌려주고 실제 번역은 `BackgroundTasks`에서 돈다.
새 문 `GET .../caption-translations/{job_id}`로 진행을 묻는다. 더빙
(2026-09-03에 같은 이유로 이미 비동기로 바뀜)과 완전히 같은 패턴 —
`orchestration.py`에 `_caption_translation_jobs`(메모리 딕셔너리 + lock),
`start_caption_translation`/`run_caption_translation_job`/
`get_caption_translation_job` 셋을 더빙의 `_dubbing_jobs`/`start_dubbing`/
`run_dubbing_job`/`get_dubbing_job`을 그대로 본떠 추가했다.

**왜** — 2026-09-07 전체 점검 §1-6: 실측(2026-09-03)으로 자막 번역이 장면당
처리 시간이 길어 최악 630초가 걸릴 수 있다. `docker/workspace-nginx.conf`의
`proxy_read_timeout 330s`보다 길다 — 자막이 많은 편집본은 인라인으로 절대
끝을 못 본다.

**프런트** — `api.ts`의 `translateEditingSessionCaptions`(즉시 응답 기대)를
`startEditingSessionCaptionTranslation` + `getEditingSessionCaptionTranslationStatus`
둘로 나눴다. 더빙의 `dubbingProgress.ts`(`pollJobUntilTerminal` 공용 루프)를
그대로 본떠 `captionTranslationProgress.ts`를 새로 만들었다.
`EditorCommandPort`에서 `translateCaptions`를 뺐다 — 더빙과 마찬가지로
편집본 전체에 걸리는 오래 걸리는 작업은 이 포트(장면 하나짜리 즉시 편집)의
계약과 안 맞는다. `EditorWorkbenchRoute.tsx`의 `handleInspectorAction`이
`dub-narration`과 나란히 `translate-captions`를 전용 통로(`translateCaptions`
함수)로 분기한다.

**더빙과 다른 점** — 서버가 장면별 진행 수를 아직 안 센다. 그 계측을
추가하는 것은 이번 변경 목적(330초 벽을 넘기지 않는 것)과 다른 일이라
안 했다 — 폴링 간격·최대 시도는 더빙처럼 장면 수로 계산하지 않고 실측
최악 630초에 넉넉한 여유(약 3배, 32분)를 곱한 고정값을 쓴다.

**RED→GREEN** — 기존 `tests/test_api_caption_translation.py`(시험 일곱)를
더빙 시험의 `_dub` 헬퍼와 같은 패턴(`_translate` 헬퍼: POST로 걸고 GET으로
받는다, `TestClient`가 `BackgroundTasks`를 응답 뒤 바로 돌리므로 시험에서
실제로 기다릴 필요는 없다)으로 고쳐 그대로 재사용했다. 새 프런트 시험
`captionTranslationProgress.test.ts`(다섯) 추가.

**§1-6의 나머지 넷 — 조사만 하고 손 안 댔다.** 다음 세션이 순서를 정할 때
참고할 것:

- **받아쓰기**(`draft_readiness.py:103,152`·`jobs.py:33`, Whisper 타임아웃
  없음) — 아직 실제 코드를 안 읽었다.
- **부분재생성**(`editing_session.py:644` `start_editing_session_partial_regeneration`) —
  **단순 background task 감싸기가 아니다.** 라우트가 `status_code=202`를
  달고 있지만 핸들러 자체가 전부 동기다: `orchestrator.start_...`로 실제
  재생성을 그 자리에서 끝내고, `_build_targeted_segments`·
  `_build_affected_output_areas`·`_build_preflight_review_prediction`으로
  풍부한 `PartialRegenerationResponse`를 그 자리에서 조립해 돌려준다. 진짜
  비동기로 바꾸려면 이 조립 단계를 백그라운드로 옮기고, 폴링 응답
  (`GET /api/projects/{id}/partial-regenerations/{job_id}`, 지금은 얇은
  `PartialRegenerationJobResponse`)이 그 풍부한 모양을 실어 나르도록
  응답 계약을 다시 설계해야 한다. **이건 새 설계 작업이지 리팩터가 아니다.**
- **TTS 후보**(`assets.py:496` `generate_tts_candidate`) — `status_code=201`
  (202도 아니다)이고 세그먼트 하나짜리 짧은 작업이다. 보통은 몇 초 안에
  끝나는 단일 값 응답을 owner가 목소리 후보를 고르는 동안 상호작용으로
  쓴다 — 통째로 비동기 폴링으로 바꾸면 흔한 경우(빠른 경우)의 체감
  지연이 늘어난다. 그대로 바꾸는 게 맞는지부터 owner 판단이 필요해 보인다.
- **촬영본 파생 렌더**(`footage_organizer.py` `render_derivative` 계열) —
  부분재생성과 같은 문제(202 라벨 + 동기 본문)일 가능성이 높다. 확인 안 함.

**권장** — 다음 세션은 부분재생성·촬영본 파생 렌더의 정확한 응답 계약부터
설계하고(둘 다 "202 라벨 뒤에 동기 코드" 패턴이라 같은 리팩터 모양일 수
있다), TTS 후보는 비동기 전환 여부 자체를 owner에게 다시 확인한 뒤
진행하는 것을 권한다. 받아쓰기는 코드를 먼저 읽어 실제로 무엇이 문제인지
(타임아웃 없음 자체가 문제인지, 걸리는 시간이 문제인지)부터 가른다.

## 4. §3-2. 경로 등록 여섯 문 — 유지, 코드 변경 없음

owner가 "유지"로 결정했다(§1-1 봉쇄가 이미 들어가 더 위험하지 않다는 것이
근거). 이번 세션에서 추가로 건드린 것은 없다 — 결정을 기록만 한다. 살리는
쪽 다음 단계(MCP `register_project_asset` 문으로 재사용)는 여전히 미래
작업이다.

## 5. 옛 스타터 미디어팩 1.3.0 정리

**지웠다** —
`D:\...\20_project\65_videobox-project\runtime\starter-media-pack-130\`(478MB)와
`D:\...\runtime\videobox-user-library\packs\starter-v1\1.3.0\`(478MB)
둘 다. 지우기 전 `diff -rq`로 둘이 바이트까지 완전히 같은 내용임을 확인했다
(둘 다 저작자 오표기가 있던 1.3.0 그대로).

지운 뒤 실행 중인 컨테이너(`127.0.0.1:5173`)에서 `/api/media-library/assets`를
직접 불러 1.3.1 자산이 여전히 정상 서빙되는 것을 확인했다 — DB의
`media_packs` 테이블에서 `active=1`인 것이 이미 1.3.1이라(2026-09-07에
활성화), 1.3.0 디렉터리는 정말 안 쓰는 사본이었다.

**후속(같은 대화, owner 지시로 마저 지움)** — 1.0.0(472MB)·1.1.0(495MB)·
1.2.0(501MB)도 `media_packs` 테이블에서 전부 `active=0`인 것을 확인하고
지웠다. `runtime/starter-media-pack-131`도 `diff -rq`로 `packs/starter-v1/1.3.1`과
바이트까지 완전히 같은 사본임을 확인하고 지웠다. **총 확보한 디스크:
약 2.9GB**(1.3.0 중복 955MB + 이번 넷 1.945GB).

지우기 전에 `media_assets` 테이블을 확인해 안전을 검증했다 -- 이 테이블은
버전마다 행이 남아 있고(`path` 컬럼이 그 버전 디렉터리를 절대경로로 직접
가리킨다) **지워도 새는 곳 없이 안전한 이유**: (1) 화면·API는 `active=1`인
버전의 자산만 나열한다(§1-1 이전부터 있던 동작, 이번에 안 건드림) -- 지운
버전을 owner가 새로 고를 방법 자체가 없다. (2) 자산을 실제 장면에 쓰면
`library_materialization.py`가 프로젝트 폴더로 파일을 복사해 두므로, 이미
쓴 프로젝트는 소스 팩 디렉터리가 없어져도 영향받지 않는다. (3)
`library_project_references`(40건)·`library_favorites`(0건)를 직접 조회해
지운 버전을 가리키는 참조가 없음을 확인했다. `recent_library_usage`의
오래된 항목 셋(2026-08-19/20)은 버전 없는 `library_asset_id`만 들고 있어
그대로 두어도 위험하지 않다(활성 버전에 같은 이름이 없으면 화면에서
조용히 안 나올 뿐).

**지우지 않은 것** — 지운 버전들의 `media_assets` DB 행 자체(옛 버전 행이
이제 없는 파일을 가리키는 죽은 참조로 남는다)는 정리하지 않았다. 위 확인대로
아무것도 그 행을 읽지 않아 당장 위험하지는 않지만, DB 정리는 이번에 owner가
승인한 범위(폴더 삭제)를 넘는 별도 작업이라 손대지 않았다.

## 6. 유진 관련 질문 (owner, 2026-09-08 대화)

> "우리 내 목소리를 자동 자막 전사 하는기능도 되고 유진이한테 명령하면
> 유진이가 작동하도록 할수 있는거지?"

확인한 사실: **자동 전사는 이미 있다.** 내레이션 오디오를 등록하면
`transcription` 잡(Whisper 기반)이 돌아 자막의 바탕이 되는 대본 정렬을
만든다 — 프로젝트를 만드는 표준 파이프라인의 한 단계다(내레이션 → 전사 →
장면 분석 → 타임라인).

**유진에게 말해서 켜는 것은 지금 안 된다.** 유진의 편집 명령
(`packages/domain-models/src/videobox_domain_models/yujin_editing_proposals.py`의
`intent` 목록: 속도·구간·컷·순서·자막 글꼴/문구·장면 룩·사진 움직임·전환·
정리·변형·오버레이·미디어 교체)은 전부 **이미 만들어진 편집본을 고치는
것**이지, 전사처럼 편집본을 만드는 앞 단계를 거는 것이 아니다. 유진에게
"이 목소리 전사해 줘"라고 말해서 새로 걸게 하려면 새 intent를 설계해야
한다 — 지금은 없다.

## 7. owner 지시로 재확인 (같은 대화, 이어서): 재시작·나머지 미디어팩 정리·코드리뷰·실제 확인

owner: "지금 다시 재시작하고, 미디어팩 폴더에 안 쓰는 옛 버전도 삭제하자.
그리고 재시작후에 지금까지 작업 리뷰 하고 역방향 검증도 다시 진행해줘."

### 7.1. 독립 코드리뷰가 §1-3 확장이 놓친 세 번째 자리를 찾았다

일반 목적 에이전트에게 이 문서 §1~§3의 세 커밋 diff만 따로 검토시켰다(이
세션 자체의 판단과 별개로 다시 보라는 취지). 결과: **`local_pipeline.py`의
`start_variant_renders`가 항목별 실패를 `error_message`가 아니라
`error_code` 열쇠로 정상적인 200 응답(`POST /api/projects/{id}/output-variants/render`,
`VariantRenderBatchResponse`) 본문에 그대로 실어 나르고 있었다** — §1-3
확장의 grep이 `error_message=str(exc)`라는 정확한 문구만 찾아서 다른 열쇠
이름을 쓰는 이 자리를 놓쳤다. `FileNotFoundError`/`CalledProcessError`가
같은 파일 다른 곳에서 실제로 호스트 경로를 담아 던지는 것을 이미 확인했으니
같은 위험이 있었다.

**고쳤다** — `safe_job_error_message(exc)`로 바꿨다(같은 헬퍼 재사용, 새
분류 안 추가). RED: `tests/test_job_error_message_has_no_filesystem_path.py::test_variant_render_batch_item_error_code_has_no_host_path`
(`_materialize_variant_for_output`를 monkeypatch로 `FileNotFoundError(호스트경로)`를
던지게 하고, 응답 항목의 `error_code`가 `asset_file_missing`이고 경로가
없음을 확인) → 드릴(고치기 전으로 되돌려 실제로 경로가 그대로 나오는 것
확인) → 고정.

리뷰 에이전트가 함께 지적한 사소한 것도 고쳤다: 이 시험 파일의 머리말이
"그 밖의 `OSError`"도 안전하게 바뀐다고 적어 실제 동작(그 세 종류 **이외의**
`OSError`는 그대로 둔다 — 이 저장소 시험 다수가 안전한 설명 문구로 `raise
OSError(...)`를 쓰기 때문)과 어긋났다. 문구만 바로잡았다.

### 7.2. 나머지 옛 미디어팩 버전 정리 (§5에 반영함)

1.0.0·1.1.0·1.2.0·`runtime/starter-media-pack-131`까지 지웠다. 근거와
안전성 확인은 §5로 옮겨 적었다.

### 7.3. 컨테이너 재시작(재빌드) + 실제 확인 (역방향 검증)

`scripts/owner-ready.ps1 -Mode Start -Rebuild`로 오늘 바뀐 코드 전부를
반영해 이미지를 다시 만들고 컨테이너를 새로 켰다. 그 뒤 **API를 통해서가
아니라 실제로 돌아가는 컨테이너 안에서** 세 가지를 직접 재현했다(주소는
매번 `127.0.0.1:5173`):

- **§1-7 CSRF** — `POST .../review-approvals/.../approve`에 `Origin:
  https://evil.example`를 실어 보내 **403 `{"reason":"untrusted_origin"}`**
  확인. Origin 헤더가 없는 요청과 `http://127.0.0.1:5173` Origin의 요청은
  둘 다 403이 아니라 평소 로직(404, 존재하지 않는 프로젝트라서)까지
  도달함을 확인. `footage/proposals/.../approve`도 같은 방식으로 403 확인.
- **§1-3 확장** — 실제 프로젝트를 만들고, 대본 파일을 등록한 뒤 지우고,
  segment-analysis를 걸어 잡 기록의 `error_message`가 정확히
  `"asset_file_missing"`이고 컨테이너 절대 경로(`/videobox-data/...`)가
  전혀 안 실리는 것을 직접 확인.
- **§1-6 자막 번역** — 실제 프로젝트에 자막을 쓰고 번역을 걸어 **202 +
  job_id**를 받은 뒤 `GET .../caption-translations/{job_id}`를 두 번
  물어 `processing`→`succeeded`로 넘어가는 것과, 결과의 번역문("안녕하세요"
  → "Hello", 실제 로컬 모델이 옮김)이 그대로 담기는 것을 확인.

확인에 쓴 임시 프로젝트 셋(`reverse-check-*`)은 전부 `DELETE
.../projects/{id}?confirm=true`로 지워 owner의 실제 데이터에 남기지
않았다.

## 8. 확인함 / 확인 못 함

**확인함:**
- §1-7: RED→GREEN, 신뢰 Origin·비신뢰 Origin·Origin 없음 세 갈래 전부.
- §1-3 확장: RED→GREEN + 드릴(OSError 전체 포획으로 바꿔 실제 시험이 깨지는 것 확인 → 좁힘).
- §1-6: 백엔드 `tests/test_api_caption_translation.py`(7) 전부 그린. 프런트
  `captionTranslationProgress.test.ts`(5) + 기존 `editor-workbench-route.test.tsx`(151,
  이번 변경으로 깨지지 않음) 전부 그린. `npx tsc -b` 클린 컴파일.
- 프런트 전체(vitest): **128 files / 1588 tests 전부 초록** (재실행 확인,
  최초 1회 전체 스위트 동시 실행에서 내 새 시험 하나가 5초 기본 타임아웃에
  걸려 flaky했던 것을 20초로 고정해 재확인).
- 미디어팩 정리 뒤 컨테이너 실서빙 확인(`curl 127.0.0.1:5173/api/media-library/assets`).
- 백엔드 전체 pytest: **4745 passed, 56 skipped, 0 failed(38분 19초).** 부록 참고.
- `scripts/run-postgres-store-tests.ps1`: 이 문서의 모든 변경을 마친 뒤
  **다시 돌려 52 passed 재확인.**

**§7에서 추가로 확인함:**
- 컨테이너 재빌드·재시작(`owner-ready.ps1 -Mode Start -Rebuild`) **두 번**
  (§7.1 결함 고치기 전후 각 한 번) — 이번엔 안 미룬다.
- §1-7·§1-3 확장·§1-6·§7.1을 전부 **실제로 돌아가는 컨테이너 안에서** 직접
  재현해 확인함(§7.3). API 단건이 아니라 여러 단계(자산 등록→삭제→잡 실행,
  또는 잡 걸기→폴링→완료)를 실제로 밟았다.
- 독립 코드리뷰 에이전트에게 세 커밋을 다시 검토시켰다 — 하나 더 찾았고
  고쳤다(§7.1). 나머지는 문제없음으로 확인됨.
- 전체 pytest **재실행: 4747 passed, 0 failed, 56 skipped(35분 8초)** —
  §7.1의 새 시험(`test_variant_render_batch_item_error_code_has_no_host_path`)
  포함, 회귀 없음.
- `scripts/run-postgres-store-tests.ps1` **재실행: 52 passed.**

**확인 못 함:**
- §1-6의 나머지 넷(받아쓰기·부분재생성·TTS 후보·촬영본 파생 렌더) — §3에
  적은 대로 조사만 하고 코드는 안 건드렸다.
- 프런트(vitest)는 이번 §7 라운드에서 다시 돌리지 않았다 — §7.1의 수정이
  백엔드 전용(`local_pipeline.py`)이고 프런트 파일은 이번 라운드에서 하나도
  안 바뀌어, 앞서(§8 재사용 게이트 전) 이미 확인한 128 files/1588 tests
  결과가 여전히 유효하다고 판단했다.
- Tauri 셸 빌드는 이번에도 안 함 — owner 지시 범위 밖.

## 9. 재사용 게이트 (CLAUDE.md §8.3)

- **확인한 재사용 후보**: 더빙의 비동기 잡 패턴(`_dubbing_jobs`/
  `start_dubbing`/`run_dubbing_job`/`get_dubbing_job`, `dubbingProgress.ts`,
  `pollJobUntilTerminal`), `errors.py::_http_error`의 로그+고정코드 관례,
  `library_media_facts.py`/`local_pipeline.py`의 "ffprobe 예외 문구에 경로가
  섞여 나간 전례" 주석.
- **실제 반영한 항목**: 위 전부 그대로 가져다 썼다. 자막 번역용 새 잡 인프라를
  안 짜고 더빙 것을 그대로 본떴다. CSRF 방어는 이 저장소에 전례가 없어
  새로 짰지만(`csrf_guard.py`), `_http_error`의 로그 관례는 그대로 따랐다.
- **이번 범위에서 제외한 항목**: §1-6 나머지 넷(§3에 이유), §1-7의 정식
  principal 증명(Origin 검사만, owner가 그만큼만 승인).
- **경계 보존**: CSRF 방어는 라우터 다섯 곳에 `Depends()`로만 걸었다 — 전역
  미들웨어로 만들지 않았다(다른 GET/조회 문까지 걸릴 위험을 피하려고).

## 부록 — 전체 pytest 결과 (2026-09-08, worktree venv, 두 차례)

### 1차 (§1~§6 완료 뒤)

`.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` (분리 프로세스, 38분 19초)

**첫 실행에서 1건 실패, 재확인 후 통과.** `test_handoff_entry_point.py::test_entry_map_points_at_the_newest_handoff`가
같은 날짜(2026-09-08)에 인계 문서가 둘 있는데 옛 문서(`...fixing-the-2026-09-07-full-audit.ko.md`)에
대체 표시가 없다고 잡았다 — 이 문서를 새로 쓰면서 그 표시를 까먹었다. 옛
문서 맨 위에 대체 배너를 추가해 고쳤다(이 세션이 직접 낸 결함, 남의 실수가
아니다). **덤으로 그 정확한 표시 문구를 이 문단에 그대로 인용했더니 이
문서 자신도 "대체됨"으로 오인되는 것까지 확인했다** — 짧게 풀어 썼다.

**4745 통과 / 0 실패 / 56 skip.** skip 사유는 이전 인계와 동일
(`VIDEOBOX_TEST_POSTGRES_URL` 미설정 43건, 아이콘 글리프 폰트 없음 3건, 라이브
게이트 opt-in 4건, 심볼릭 링크 권한 1건, 이번 세션 새 시험 파일의 정적 skip
구문 5건). 4733(2026-09-08 첫 번째 인계)에서 4745로 는 것은 이번 세션이
추가한 시험(`test_approval_routes_reject_untrusted_origin.py` 7건,
`test_job_error_message_has_no_filesystem_path.py` 6건, 기존
`test_api_caption_translation.py`는 건수 그대로 재작성) 때문이다.

`scripts/run-postgres-store-tests.ps1`(일회용 DB): **52 passed** (변화 없음).

프런트(vitest): **128 files / 1588 tests 전부 초록.**

### 2차 (§7.1이 세 번째 leak 자리를 고친 뒤, owner 지시로 재실행)

`.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` (분리 프로세스, 35분 8초)

**4747 통과 / 0 실패 / 56 skip.** 4745→4747은 §7.1이 추가한 시험
(`test_variant_render_batch_item_error_code_has_no_host_path`)과 4745 계산
당시 기준선 오차 하나 때문이다 — 실패는 전혀 없었다.

`scripts/run-postgres-store-tests.ps1`(일회용 DB): **52 passed** (변화 없음).

프런트(vitest)는 이번 2차에서 다시 돌리지 않았다 — §7.1의 수정이 백엔드
전용이라 1차 결과(128/1588 초록)가 여전히 유효하다고 판단했다.

**컨테이너 재빌드·실제 확인은 §7.3 참고.** 두 라운드 다 owner-ready.ps1로
재빌드·재시작한 뒤 실제 돌아가는 컨테이너에서 직접 재현해 확인했다 —
API 단건이 아니라 여러 단계를 실제로 밟았다(§7.3).
