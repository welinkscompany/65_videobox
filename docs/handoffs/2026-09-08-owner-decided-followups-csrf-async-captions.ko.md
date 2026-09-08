# 인계 — owner 결정 뒤 후속 조치: CSRF 방어·자막 번역 비동기화·정리 (2026-09-08, 두 번째)

## 한 줄

`2026-09-08-fixing-the-2026-09-07-full-audit.ko.md`가 owner 결정 대기로 남겨 둔
§1-6·§3-2·미디어팩 정리에 대해 owner가 실제로 결정했고(2026-09-08 대화), 그
결정대로 처리했다. 처리한 뒤 owner가 컨테이너 재시작·나머지 미디어팩 정리·
독립 코드리뷰·재현 검증을 다시 지시했고(같은 대화, §7), 그 코드리뷰가
`local_pipeline.py`의 `start_variant_renders`(§1-3 확장 grep이 놓친 세 번째
leak 자리)를 찾아 같이 고쳤다. 이어서 owner가 "추천작업 바로 진행하자"고
지시해(같은 대화, §10) §1-6 나머지 넷(받아쓰기·부분재생성·촬영본 파생 렌더·
TTS 후보)의 범위를 owner가 결정한 대로 처리했고, **이걸로 §1-6이 완전히
닫혔다**(TTS 후보만 owner 판단으로 동기 유지). 커밋 다섯 + §10 커밋 셋
(받아쓰기·촬영본 파생 렌더·부분 재생성) + 미디어팩 정리(git 밖, 총
2.9GB) + 컨테이너 재빌드 두 번 + 그 안에서 직접 재현한 확인 셋(§7.3) +
전체 pytest 두 번(4745→4747, 둘 다 0 failed) + §10 관련 백엔드 재확인
(468 passed) + 프런트 재확인(130 files/1597 tests).

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

## 10. owner 지시로 §1-6 나머지 넷을 마저 진행 (같은 대화, 이어서) — §1-6 완전히 닫힘

owner: "추천작업 바로 진행하자." (§3에서 "다음 세션이 처리" 로 남겨 뒀던
받아쓰기·부분재생성·촬영본 파생 렌더·TTS 후보 넷을 가리킴). 이어서 각 항목의
정확한 범위를 다시 물어 owner가 결정했다(§10.0). **이걸로 §1-6(인라인 동기
문 다섯 개가 nginx 330초 벽을 넘길 수 있던 문제) 전부가 닫혔다** — 자막
번역(§3, 지난 라운드)·받아쓰기·촬영본 파생 렌더·부분 재생성 넷이 진짜
비동기로 바뀌었고, TTS 후보는 owner 판단으로 그대로 뒀다.

### 10.0 owner 결정

| 항목 | 결정 | 근거로 제시한 것 |
|---|---|---|
| 받아쓰기(전사) | 전체 비동기 전환 | 12개 백엔드 시험 파일 + 프런트 컴포넌트 하나가 영향받는 큰 작업이라고 미리 알림 |
| 부분재생성·촬영본 파생 렌더 | 둘 다 새로 설계해서 진행 | 라벨만 202고 실제로는 그 자리에서 다 처리 + 응답까지 조립하던 것 |
| TTS 후보 생성 | 비동기로 바꾸지 않는다 | 몇 초짜리 짧은 작업이라 폴링으로 바꾸면 흔한(빠른) 경우 체감 속도만 나빠짐 |

### 10.1 받아쓰기(전사) — 예상보다 컸지만 예상대로 끝남

**무엇을** — `jobs.py`의 `POST/GET .../jobs/transcription`는 이미 202 라벨과
GET 폴링 문을 갖고 있었지만(다른 잡 종류들과 같은 모양), 실제로는
`orchestrator.start_transcription`이 Whisper 호출까지 그 자리에서 다 하고
"succeeded"로 끝난 잡만 돌려주고 있었다. `local_pipeline.py`의
`start_transcription`(잡 생성만, 빠름)과 `run_transcription_job`(실제
Whisper 호출, 배경)으로 나눴다.

**되짚어 보니 결함 하나를 더 찾았다** — 동기 코드에는 STT 실패를 잡아 잡을
FAILED로 적는 처리 자체가 없었다. 엔진이 죽으면 잡이 영원히 RUNNING으로
멈춰 있었다(관찰만 됐지, 화면에 실패로도 안 뜬다). 비동기로 바꾸면서
`safe_job_error_message`로 안전하게 같이 고쳤다.

**재시도 라우트도 손봤다** — `jobs.py`의 `_RETRY_BACKGROUND_RUNNERS`가
이제 `final_render`/`capcut_draft_export`와 다른 kwargs 모양(`narration_asset_id`)이
필요한 `transcription`도 다뤄야 해서, 잡 종류별 kwargs를 만드는
`_retry_background_kwargs` 헬퍼를 추가했다. 안 했으면 재시도한 잡이 새
job_id만 받고 영원히 처리 중으로 남았을 것이다 — RED 시험으로 직접 확인.

**"예상했던 blast radius는 문제가 안 됐다"는 처음 판단은 틀렸다 — 전체
저장소 pytest를 돌려서야 드러났다.** HTTP 레벨(`TestClient`) 시험들은
정말 문제가 없었지만, `orchestration.py` 안에 **파이프라인의
`start_transcription`을 직접 불러 결과가 그 자리에서 바로 있다고 가정하던
내부 합성 흐름 셋**을 grep으로 못 찾았다(§1-6 작업 당시엔 `jobs.py`
라우터와 프런트만 봤지, `orchestration.py` 자체의 다른 메서드는 안 봤다):

1. `transcribe_source_video`(영상 업로드 → 대본 초안) — `start_transcription`
   뒤 바로 `get_transcription_result`를 읽고 있었다.
2. `sync_script_draft_to_narration_recording`(대본 초안을 실제 녹음
   타이밍에 맞추는 길, 2026-08-29 추가) — `start_transcription` 뒤 바로
   `store.get_transcript(transcript_id=job["output_ref"])`를 읽고 있었다.
3. **더빙의 내부 부분 재생성 호출**(`generate_dubbed_take`가 딴 뒤
   `pipeline.start_editing_session_partial_regeneration`을 부르는 자리) —
   부분 재생성도 같은 라운드에 비동기로 바뀌면서 똑같은 함정에 빠졌다.
   **이건 2026-09-02에 이미 한 번 고쳤던 바로 그 결함
   ("세션에 걸어도 완성본은 안 바뀐다")이 그대로 되살아난 것**이었다 —
   `run_partial_regeneration_job`을 안 부르면 더빙 선택만 세션에 걸리고
   타임라인은 안 바뀐다.

전체 pytest에서 **16개**가 이 패턴으로 실패했고(`test_api_source_video_start.py`·
`test_api_source_voice_start.py`·`test_api_media_director.py`·
`test_api_dubbing.py`·`test_auto_apply_policy.py`·`test_vertical_composition.py`),
`scripts/verify_owner_path.py`(실제 STT provider로 owner path를 검증하는
운영 스크립트, 시험이 아니라 진짜 코드)도 같은 이유로 죽어 있었다
(`test_owner_path_verifier.py` 경유로 발견). 세 내부 호출부 모두
"빠른 시작 뒤 바로 배경 함수를 직접 불러 예전 동작(동기)을 그대로 지킨다"로
고쳤다 — 이 세 경로는 owner가 결정한 §1-6 대상(직통
`POST/GET .../jobs/transcription` 문, `POST .../partial-regenerations`
문)이 아니라 **그 위에 얹힌 기존 합성 흐름**이라, 이들까지 비동기로
다시 설계하는 건 범위 밖으로 판단해 동기 동작을 보존하는 쪽을 택했다
(다시 열면: 이 셋도 nginx 330초 벽 앞에 그대로 노출돼 있다는 뜻이므로,
다음에 이 경로들이 실제로 벽에 부딪히면 별도 owner 결정이 필요하다).

**딱 하나 프런트에서 실제로 바꿔야 했던 자리**는
`apps/web/src/features/editor/transcript/AutoCaptionCard.tsx` — 받아쓰기
시작 직후 곧바로 `applyCaptionsFromTranscript`를 부르던 것을, 새
`transcriptionProgress.ts`(같은 폴링 패턴)로 먼저 완료를 기다리게 고쳤다.
컨테이너 환경에서는 응답 직후 배경 작업이 곧바로 끝난다는 보장이 없어서
실제로 필요한 수정이었다.

RED: `tests/test_transcription_is_async.py`(정상 흐름·실패 처리·재시도 셋).

### 10.2 촬영본 파생 렌더 — 프런트가 아직 안 부르는 문이라 백엔드만

`POST /api/footage/derivatives/render`는 202 라벨을 달고 있었지만 그 자리에서
ffmpeg 렌더까지 전부 끝내고 있었다. `_render_derivative`를
`_start_derivative_render`(멱등성 확인·잡 생성·빠른 검증 -- 승인 여부·다중
소스 거부 등)와 `_run_derivative_render_job`(실제 ffmpeg 렌더, 배경)으로
나눴다. **이 잡 종류는 지금까지 조회(GET) 문이 아예 없었다** — 새로
`GET /api/footage/derivatives/{job_id}`를 만들었다.

`apps/web/src`에서 이 POST 문을 부르는 자리가 **하나도 없었다**(확인함,
2026-08-31 이후 미배선 상태 그대로) — 백엔드·시험만 고치고 프런트는
손대지 않았다.

기존 시험 셋이 시작 응답에서 바로 완성된 결과(`status`·`derived_asset_id`)를
읽고 있어서 새 GET 문으로 폴링하도록 고쳤다(공용 `_await_derivative`
헬퍼). 시작 응답이 정말 아직 처리 중인지(`status == "running"`,
`derived_asset_id`가 없음)를 직접 재는 시험도 새로 추가하고 드릴로
확인했다 — 백그라운드 예약 대신 그 자리에서 동기로 돌리게 임시로 되돌려서
실제로 빨간불이 뜨는 것을 봤다.

### 10.3 부분 재생성 — 넷 중 가장 컸다, 응답 계약을 다시 설계해야 했다

**무엇을** — `start_editing_session_partial_regeneration`(빠른 부분: 편집본
조회·판 확인·`build_partial_regeneration_request`·잡 생성만)과
`run_partial_regeneration_job`(실제 재생성·CAS 충돌 처리·롤백·발행,
배경)으로 나눴다. CAS 충돌·발행 실패 시의 기존 보정 로직(옛 세션 복원,
고아 타임라인 폐기, 정리 필요 표시)은 **그대로 두고 위치만 옮겼다** —
로직 자체는 안 건드렸다.

**핵심 설계 결정: 배경 작업은 더는 예외를 다시 던지지 않는다.** 옛 코드는
`except Exception: ...; raise`로 정리 후 재던졌고, 그게 라우터의
`except EditingSessionConflict: return _editing_session_conflict_response(exc)`로
이어져 "편집본이 바뀌었어요"라는 특별한 응답이 됐다. 배경 작업에는 그
`raise`를 받을 사람이 없어서(HTTP 요청은 이미 202로 끝났다) 뺐다 — 정리
로직이 끝난 뒤 잡을 그냥 `FAILED`로 남긴다. 폴링하는 쪽은 "실패"라는
일반적인 사유만 보게 되고, 예전처럼 "다른 사람이 먼저 바꿨어요"라는 구체적
안내는 못 받는다 — 이 정도 UX 손실은 이번 변경의 목적(330초 벽 회피)과
직접 관련 없어 감수했다. 다음에 이걸 다시 열면: 잡 레코드에 "conflict"
같은 별도 상태 값을 추가해 폴링 쪽이 구분할 수 있게 하는 것을 권한다.

**영향 범위·검토 예측(`targeted_segments`·`affected_output_areas`·
`predicted_review_status_after_rerun`·`prediction_reasons`)은 이제 시작
응답이 아니라 GET 폴링이 조립한다** — 성공한 잡을 조회할 때마다 **그
시점의 최신 편집본**으로 다시 계산한다. 재생성 직후 fresh 세션을 다시
읽던 옛 동작과 실질적으로 같은 값이 나온다(재생성과 조회 사이 시간차가
찰나였으니까) — 다만 이제는 정말로 "지금 조회하는 시점"의 값이라는 점이
다르다. `PartialRegenerationJobResponse` 모델에 그 넷을 추가하고, 기존
필수 필드(`session_id`·`timeline` 등)는 아직 안 끝난 잡을 표현할 수 있게
전부 optional로 바꿨다.

**프런트** — `runPartialRegeneration`을 `startPartialRegeneration`(즉시
완료 기대 안 함)으로 바꾸고 새 `partialRegenerationProgress.ts`(같은
`pollJobUntilTerminal` 패턴)를 만들었다. 폴링 대상 GET 문
(`getPartialRegenerationResult`)은 **이미 있었다** — "이전 결과 열기"
기능이 쓰고 있었다 — 그대로 재사용했다. `activePartial.run`이 들고 있던
옛 응답 모양(`PartialRegenerationRun`, `delta` 필드 포함)은 어디서도
화면에 그려지지 않는 것을 직접 확인하고(`activePartial.run`을 읽는
자리가 코드 전체에 하나도 없었다), `PartialRegenerationJob`(GET이 이미
쓰던 모양)로 통일해 타입을 단순화했다.

**시험 37개(파이프라인 직접 호출 15개, HTTP 레벨 22개)가 영향받았다** —
분량이 커서 서브에이전트에게 정확한 계약(무엇이 빠르게 실패하고 무엇이
배경에서 실패로 바뀌는지)을 자세히 적어 위임했고, 다시 읽고 직접
재실행해 확인했다. CAS 충돌 시험 셋은 `pytest.raises(EditingSessionConflict)`를
걷어내고 `store.update_job`이 `FAILED` 상태로 불렸는지 확인하는 것으로
바꿨다(보정 로직 자체의 검증은 그대로 유지 — 예외가 뜨는지가 아니라 실제
부작용이 맞는지를 잰다는 게 핵심이었으니 검증의 실질은 안 약해졌다).

RED: `test_derivative_render_start_response_does_not_carry_the_finished_result`류
(부분재생성·촬영본렌더 각각) + 드릴.

### 10.4 확인함 / 확인 못 함 (§10 한정)

**확인함:**
- 넷 다 RED→GREEN, 적어도 하나씩은 드릴(백그라운드 예약을 빼고 동기로
  되돌려 실제로 빨간불이 뜨는 것 확인)까지 직접 돌렸다.
- `tests/test_api.py`(407) + `tests/test_editing_session.py`(61) 전부
  초록 — 부분재생성 관련 37개를 고친 서브에이전트의 결과를 내가 직접
  다시 돌려 재확인했다(위임 결과를 그대로 안 믿음).
- 프런트 전체(vitest): **130 files / 1597 tests 전부 초록** (파셜리제너레이션
  진행 헬퍼·시험 추가 포함, 재실행 확인).
- 촬영본 파생 렌더는 프런트가 안 부르는 문임을 직접 grep으로 확인했다
  (`apps/web/src`에 `derivatives/render` 호출 0건) — 백엔드만 고친 판단의 근거.
- **전체 저장소 pytest(4753개)를 실제로 돌려서 §10.1에 적은 회귀 16건을
  찾았다** — 부분 파일만 골라 돌렸으면 못 봤을 것들이다. 원인 셋
  (`transcribe_source_video`·`sync_script_draft_to_narration_recording`·
  더빙의 내부 부분 재생성 호출)을 `orchestration.py`에서 고치고,
  `scripts/verify_owner_path.py`도 같은 이유로 같이 고쳤다(§10.1 상세).
  고친 뒤 해당 시험 파일 전부(123개) 재확인, 전체 pytest 재실행 중.
- postgres 저장소 시험: 첫 실행에서 `Address already in use`로 1건
  실패했으나 **포트 경합에 의한 일시적 결함으로 확인**(재실행 시
  52/52 전부 통과) — 내 코드 변경(connection pooling과 무관)이 원인이
  아님을 확인 후 결함으로 안 올렸다.

**추가로 확인함 (컨테이너 재빌드 뒤 실제 재현):**
- `owner-ready.ps1 -Mode Start -Rebuild`로 재빌드·재시작, healthy 확인.
- **받아쓰기**: 실제 컨테이너 안에서 프로젝트를 만들고 진짜 wav를 올려
  `POST .../jobs/transcription`을 불렀다 — 시작 응답이 `202`+`status:
  running`+`transcript_uri: null`(완성된 결과를 안 실었음을 직접 확인),
  8초 뒤 폴링이 `succeeded`+실제 대본 주소로 바뀌는 것까지 실제로
  지켜봤다. 시험 프로젝트는 확인 뒤 지웠다(재확인함, 남은 폴더 없음).
- **촬영본 파생 렌더**: 새로 만든 `GET /api/footage/derivatives/{job_id}`가
  실제로 마운트돼 있는지 직접 쳐서 확인 — 없는 job_id에 내가 설계한
  `footage_derivative_job_missing` 404가 돌아왔다(라우트 자체가 안 걸려
  있었다면 FastAPI 기본 404나 405가 왔을 것).
- **부분 재생성**: 별도 라이브 워크스루는 안 했다 — 더빙이 내부에서 이
  경로를 그대로 타고, §10.1에서 찾은 회귀(더빙이 부분 재생성 배경 함수를
  안 부르던 것)를 고친 뒤 전체 pytest(더빙 관련 시험 포함)가 실제
  `TestClient`로 이 코드를 재현해 초록을 확인했다 — 받아쓰기 라이브
  확인이 같은 BackgroundTasks+폴링 배선이 실제 컨테이너에서도 동작함을
  이미 증명했으므로, 부분 재생성 전용 라이브 재현은 한계 대비 이득이
  낮다고 판단해 생략했다.

**확인 못 함:**
- 부분 재생성의 "conflict를 폴링에서 구분 못 한다"는 의도적 축소는
  §10.3에 적었다 — 필요하면 다음 세션이 잡 레코드에 상태 구분 값을
  추가하는 설계를 검토할 것.
- 부분 재생성·촬영본 파생 렌더는 화면(vitest/브라우저)에서 직접 밟아
  보지는 않았다 — 부분 재생성은 프런트 시험(151개 포함)으로, 촬영본
  파생 렌더는 프런트가 안 부르는 문임을 grep으로 대신 확인했다.

### 10.5 재사용 게이트 (§10 한정)

- **확인한 재사용 후보**: 더빙의 비동기 잡 패턴을 이번에도 그대로 썼다
  (자막 번역 라운드에서 이미 확인한 것과 같음). 부분 재생성의 GET 폴링
  문(`getPartialRegenerationResult`)은 **새로 안 만들고 이미 있던 것**을
  재사용했다(이전 결과 열기 기능이 쓰던 것).
- **실제 반영한 항목**: 잡 분할 패턴(시작=빠른 부분, 실행=배경) 넷 다
  동일하게 적용. 오류 문구 안전화(`safe_job_error_message`)도 새 배경
  실행기 안에서 재사용.
- **이번 범위에서 제외한 항목**: TTS 후보 비동기 전환(owner 결정, §10.0).
  부분 재생성의 conflict 상태 구분(§10.3에 다음 세션 권고로 남김).
- **경계 보존**: 촬영본 파생 렌더는 프런트가 안 쓰는 문이라 백엔드
  경계만 지켰다 -- 안 쓰는 프런트 코드를 새로 만들지 않았다.

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

### 3차 (§10 완료 뒤, 회귀 수정 포함)

전체 저장소 pytest를 처음 돌렸을 때 **16개가 실패**했다 — §10.1에 적은
대로 받아쓰기 비동기 전환이 `orchestration.py`의 내부 합성 흐름 셋을
못 보고 지나간 진짜 회귀였다. 원인을 셋 다 고치고(`orchestration.py`
2곳 + `scripts/verify_owner_path.py` 1곳), 영향받은 시험 파일 둘도 같이
맞췄다(`test_auto_apply_policy.py`·`test_vertical_composition.py`).

고친 뒤 재실행: **4752 통과 / 1 실패(`test_owner_ready_script.py::test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure`) / 56 skip**
(3004초). 이 1건은 격리 재실행에서도 그대로 재현되지만, 코드가 아니라
`-TimeoutSec 1`로 자식 프로세스를 죽이는 타이밍이 기계 상태에 따라
30초 밖으로 밀리는 **2026-09-02에 이미 bisect로 내 탓이 아님을 증명해
둔 flaky 시험**이다([[videobox-smoke-timeout-test-fails-by-machine-state]]) —
이번 §10 변경 파일(`orchestration.py`·`verify_owner_path.py`·시험 둘)과
전혀 겹치지 않는다.

postgres 저장소 시험은 §10.4에 적은 대로 첫 실행에서 포트 경합으로 1건
실패했다가 재실행에서 **52/52** 전부 통과했다 — 결함으로 안 올렸다.
