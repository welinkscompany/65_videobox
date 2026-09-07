# 인계 — 전체 중간 점검: 문서·계획서·시험·경계·죽은 코드 (2026-09-07, 두 번째)

## 한 줄

**코드는 한 줄도 안 고쳤다.** 다섯 항목을 코드와 실행 결과로만 재서 결함을 뽑았고,
낡은 문서 열아홉 개에 표시를 달았으며, 운영 SSOT 셋(`CLAUDE.md`·fast-path·계획서)의
거짓 문장을 직접 고쳤다. **다음 세션은 이 문서의 §2 순서대로 고친다.** 보고서를 한 번
걸러서 넘겼다 — 하위 조사의 틀린 지적 둘을 뺐다(§6).

같은 날 앞선 인계: `2026-09-07-infographics-mcp-scope-and-the-main-merge.ko.md`
(그 문서 맨 위에 대체됨 표시를 넣었다).

## 0. 어떻게 쟀나 — 다음 사람이 결과를 믿어도 되는 이유

- 판단 근거는 **코드 file:line과 실행 결과**뿐이다. 문서는 대조 대상이지 근거가 아니다.
- 병렬 조사 에이전트 다섯 + 하위 여덟이 돌았고, 그중 셋이 사용량 한도로 죽었다(하위
  결과는 전부 받았고 빠진 문서 열둘은 다시 돌렸다). **핵심 결함은 전부 내가 직접
  재현했다** — 아래 "확인함"은 내가 밟았다는 뜻이다.
- 시험은 worktree venv(`.venv/Scripts/python.exe`)로만 돌렸다. 루트 `.venv`는
  `cryptography`가 없어 훅 가드가 환경 오류로 뜬다(§2-9).
- 변형 탐침은 격리 worktree에서 했고 그 worktree는 깨끗이 정리됐다(`git status` 비어 있음).

## 1. 결함 — 심각한 순

### 1-1. 프로젝트 자산 등록 여섯 문이 **아무 호스트 경로나 읽어 준다** (어제 결함의 프로젝트판)

- **무엇이** — `POST /api/projects/{id}/assets/{script-document,broll-video,broll-video/batch,raw-video,sfx,narration-audio,voice-sample}`가
  `source_path`로 받은 절대 경로를 봉쇄 검사 없이 프로젝트로 복사하고, `/content`로 도로 내려준다.
- **어디** — 라우터 `services/api/src/videobox_api/routers/assets.py:95,166,181,206,257,272,280` →
  `orchestration.py:168~356` → `packages/core-engine/.../local_pipeline.py:729~1000` → **실제 위험 지점**
  `packages/storage-abstractions/src/videobox_storage/local_project_store.py:2405-2413`
  (`Path(source_path)` 존재만 보고 `shutil.copy2`). 읽는 문 `assets.py:465` `get_asset_content`.
- **왜 결함인가** — `POST .../assets/script-document {"source_path": "<프로젝트 밖 파일>"}` → 201,
  `GET .../assets/{aid}/content` → 원문 200. 컨테이너가 볼 수 있는 파일(다른 프로젝트 DB, 자료실
  `media_library.sqlite`, 마운트된 설정)을 전부 꺼낼 수 있다. 어제 `library_assets.py`에 넣은
  `allowed_ingest_roots` 봉쇄가 이 여섯에는 없다.
- **확인함** — TestClient로 프로젝트 밖 `secret.txt`를 등록(201)하고 `/content`가 `TOP SECRET HOST FILE`을
  200으로 돌려주는 것을 직접 밟았다.
- **고치는 법**
  1. RED: `tests/test_api_asset_registration_rejects_out_of_root_paths.py::test_register_asset_by_path_outside_allowed_roots_is_refused`.
     `create_app(projects_root=tmp/"projects")`, `tmp/outside/secret.txt` 생성, 여섯 문 각각에
     `{"source_path": str(secret)}` → `assert 403`, 이어 자산이 생기지 않았음을 단언. 지금은 201이라 RED.
  2. 봉쇄는 **새로 짜지 말고** `library_assets.py`의 `_inside_any` + `allowed_ingest_roots`를 재사용한다.
     `create_app`이 이미 계산한 허용 폴더(드롭 폴더)와 **프로젝트 자신의 root**를 허용 집합으로 두고,
     `local_project_store.register_asset` 앞(또는 `orchestration`의 각 `register_*`)에서 `resolve()` + `is_relative_to`.
  3. 화면이 아직 쓰는 문 하나(`voice-sample`, `VoiceTtsSettings.tsx:577`의 `localPath` 입력칸)는 드롭 폴더
     안 경로만 받게 되므로 그 화면 문구도 같이 바꾼다.
  4. **컨테이너에서 밟아라.** 윈도우 pytest는 `C:\...` 절대 경로 판정이 달라 못 잡는다(§1-5).
  - 이 여섯을 **살릴지 지울지**는 owner 결정이다(§3-2). 지우더라도 봉쇄는 먼저 넣어라 — 지우는 데 시간이 걸린다.

### 1-2. 스타터 미디어팩 효과음 셋의 **저작자가 엉뚱한 사람으로 찍혀 나갔다**

- **무엇이** — `sfx-rpg-door`·`sfx-rpg-grass`·`sfx-rpg-steps`가 `Delta12 Studio / RPG Sound Effect Pack`이어야 하는데
  `cogitollc / pop-sounds`로 기록된다.
- **어디** — 원장 `docs/starter-media-pack-license-research.ko.md`의 RPG 표 세 행(`same page/hash`); 파서
  `scripts/build_starter_media_pack.py:88-125`(앞 표 줄의 저작자·페이지·해시를 상속); 고정 지문
  `_APPROVED_CANDIDATE_FINGERPRINT`(`:170-182`); **실물** `/videobox-data/starter-media-pack-130/LICENSES.md:74-76`.
- **왜 결함인가** — 2026-09-06에 RPG 표의 앞 줄 17개를 지우면서 `same page/hash` 세 행이 그 위 표(`sfx-pop10`)를
  상속하게 됐다. 지문이 그 잘못된 값으로 고정돼 검증(104/30/74)이 통과한다. 1.0.0·1.1.0 팩은 맞게 적혀 있고
  1.3.0만 틀렸다. CC0라 법적 위험은 없지만 저작자 표기가 거짓이다.
- **확인함** — 로더를 읽기 전용으로 돌려 셋이 `cogitollc`로 나오는 것, 컨테이너의 1.3.0 `LICENSES.md`에 그렇게
  찍힌 것, 1.2.0 증거 파일이 `Delta12 Studio`인 것을 직접 봤다.
- **고치는 법**
  1. RED: `tests/test_starter_media_pack_ledger.py::test_rpg_sfx_inherit_delta12_not_pop_sounds` — 로더 결과에서
     `sfx-rpg-door`의 creator가 `Delta12 Studio`, official page가 `rpg-sound-effect-pack`임을 단언.
  2. 원장 `sfx-rpg-door` 행의 둘째 칸을 되살린다:
     `Delta12 Studio · [RPG Sound Effect Pack](https://opengameart.org/content/rpg-sound-effect-pack) · \`e6b3928faa6f503a64336f7655e07855378511abfe5427b14fa01138fa2c8efb\``
     (커밋 `f5ca1b6f1`의 지워진 줄, 1.2.0 증거와 동일).
  3. 지문을 다시 고정하고 팩 버전을 1.3.1로 올려 다시 빌드·설치한다(`POST /api/media-library/install`은
     화면이 안 부르니 손으로).
  4. 원장 제목 "(47 individual WAV)"→18, "(20)"→3도 같이 고친다.

### 1-3. **날 예외 문구가 컨테이너 절대 경로·ffmpeg stderr를 응답에 싣는다**

- **무엇이** — `_http_error`가 모든 분기에서 `detail=str(exc)`. `FileNotFoundError`면 404 본문에 `/videobox-data/...`가 그대로 나간다.
  잡 실패 저장부 여섯 곳도 `error_message=str(exc)`라 200 응답의 상태 칸으로 샌다.
- **어디** — `services/api/src/videobox_api/errors.py:9-34`; 대표 `assets.py:472`; 잡 저장 `local_pipeline.py:554/693/2425`,
  조회 `outputs.py:57,245`, `director_proposals.py:601`, `editing_session.py:307`, `footage_organizer.py:458`, `scene_videos.py`;
  Whisper 인라인 `draft_readiness.py:103,152`·`jobs.py:33` → `faster_whisper_stt.py:41`; `outputs.py:303` → `audio_export.py:71`.
- **왜 결함인가** — 밑 파일이 지워진 자산의 `/content` → `404 {"detail": "Asset file not found: '/videobox-data/projects/…'"}`.
  라우터 18개 약 130곳이 이 함수를 탄다.
- **확인함** — 자산 등록 후 파일을 지우고 `/content`를 불러 절대 경로가 실리는 것을 재현했다(보안 조사 에이전트).
- **고치는 법** — RED: `tests/test_error_detail_has_no_filesystem_path.py` — 위 재현 뒤 `detail`에 `/`·`\`가 없음을 단언.
  `_http_error`의 `FileNotFoundError`·일반 분기를 고정 코드(`asset_file_missing`/`internal_error`)로, 원문은
  `_LOGGER.warning(exc_info=True)`로만(`library_assets.py:342`가 이미 쓰는 관례). 잡 저장 여섯 곳도 `type(exc).__name__`으로.

### 1-4. `project_id`에 `%2e%2e`가 라우터까지 통과한다 — 프로젝트 삭제와 겹치면 부모 폴더 `rmtree` 위험

- **어디** — `local_project_store.py:730` `project_root`(봉쇄 없음); `projects.py:167` `DELETE`→`:696-706` `shutil.rmtree`.
- **왜 결함인가** — `DELETE /api/projects/%2e%2e?confirm=true`가 `project_id=".."`로 도달하는 것은 재현됐다.
  `project_root("..")`는 `projects/`(부모)다. `get_project("..")`가 먼저 `KeyError`를 낼 가능성이 높아 실제 삭제까지
  가는지는 **그럴듯함**.
- **고치는 법** — RED: `tests/test_project_id_shape.py::test_traversal_project_ids_are_rejected`(`%2e%2e`, `a/../b` → 404/422).
  라우터 진입 또는 `project_root`에서 `^[A-Za-z0-9_-]+$` 화이트리스트. 1-1의 방어 심층으로도 쓰인다.

### 1-5. 초록 시험이 안 지키는 울타리 둘 (변형 탐침 12개 중 초록 2)

**(a) 호스트 경로(`C:\...`) 분기 — 어제 역방향 검증이 잡은 결함의 재발 방지 장치인데 회귀 방어가 0**
- **어디** — `routers/library_assets.py:276-291`(`_looks_like_another_os_path` → 403 `source_path_not_visible`);
  시험 `tests/test_api_uniform_job_and_path_ingest.py`.
- **왜 결함인가** — 그 분기 17줄을 통째로 지웠는데 `15 passed`. 유일한 관련 시험은 정규식만 재고 라우트를 안 부른다.
  라우트 시험은 윈도우에서 `C:\...`가 절대 경로라 분기가 켜지지 않는다.
- **확인함.**
- **고치는 법** — RED: 라우터에 `_NATIVE_PATH = Path` 모듈 상수를 두고 시험에서 `PurePosixPath`로 바꾼 뒤
  `POST /api/library/ingest-path {"source_path": "C:\\Users\\x.png"}` → `403` + `reason == "source_path_not_visible"`
  (422 `must_be_absolute`가 아님)을 단언. **정규식만 mock하지 말 것.**

**(b) 더빙 엔진 `host_bridge`를 espeak로 바꿔치기해도 초록**
- **어디** — `services/api/src/videobox_api/provider_factories.py:50-58`; 시험 `tests/test_tts_provider_selection.py`(host_bridge 없음),
  `test_host_tts_bridge.py`(팩토리 안 거침), `test_api_dubbing.py`(가짜 provider 주입).
- **왜 결함인가** — `46 passed`. 기억 문서의 "안 켜면 조용히 기계 목소리로 대신 읽지 않는다"를 지키는 시험이 없다.
  코드에 명시적 폴백 금지 가드는 없다 — 폴백이 *없다는 사실*이 가드다.
- **확인함.**
- **고치는 법** — RED: `test_tts_provider_selection.py::test_host_bridge_builds_the_bridge_provider_and_nothing_else`
  (`_build_tts_provider(engine="host_bridge")`가 `HostTTSBridgeProvider`, base_url 그대로). `test_api_dubbing.py`에
  URLError를 던지는 가짜 http_client를 꽂은 실제 `HostTTSBridgeProvider`로 더빙 → `dubbing_notice`에 엔진 실패,
  **어떤 장면도 교체되지 않음**을 단언.

**(d) skip이 숨긴 빨간 시험 — Postgres 전용 시험 하나가 2026-08-20부터 빨갛다**
- **어디** — `tests/test_postgres_project_store.py:822` `test_postgres_yujin_memory_retrieval_rows_match_sqlite_exactly`;
  구현 `packages/storage-abstractions/src/videobox_storage/_store_yujin_memory.py:530`(두 저장소가 같은 mixin, Postgres 오버라이드 없음).
- **왜 결함인가** — `scripts/run-postgres-store-tests.ps1`로 돌리면 `1 failed, 51 passed`. 커밋 `dac11c7dd`(08-20, "기억이 만들어진 대화를
  넘어 살아남게")가 `conversation_id` 스코프를 일부러 걷어냈는데, 이 시험만 옛 기대값(다른 대화의 기억이 안 나와야 함)으로 남았다.
  기본 회귀에서 `VIDEOBOX_TEST_POSTGRES_URL`이 없어 skip이라 **18일 동안 아무도 몰랐다.** 제품 동작은 두 저장소가 같으니 결함 아님 —
  결함은 "초록이 Postgres 경로를 한 번도 안 본다"는 것이다.
- **확인함** — 일회용 DB로 두 번 재현, 두 저장소 결과가 서로 같고 기대값만 다른 것을 traceback으로 확인.
- **고치는 법** — 시험의 기대값을 SQLite 쪽 현행 동작(다른 대화의 승인 기억도 포함, `category, text` 순)에 맞춘다. 그리고
  **§2의 매 항목 뒤에 `run-postgres-store-tests.ps1`도 돌려라** — 1-1 봉쇄가 Postgres 스토어 경로에도 걸리는지 이것으로만 잰다.

**(c) 구조적 한계(구멍 아님)** — LM Studio·ComfyUI base_url 허용 목록(`settings.py:394,566,636`)에 특정 문자열을 하나 더
넣어도 초록. 시험이 예시 URL 거절만 본다. 허용 목록을 모듈 상수로 빼고 "길이 2, hostname ∈ {127.0.0.1, host.docker.internal}"을 단언하면 닫힌다.

빨개진 열: `_inside_any`(2건), 로컬 기억 대조 `:207`, `orientation` 422(pydantic `models.py:1555`), 프로젝트 삭제 confirm,
`resolve_managed_path` 봉쇄, `verify_output_freshness`(12건), 인계 진입점 시험.

### 1-6. 프록시 330초 벽에 잘릴 수 있는 **인라인 동기 문이 인계의 "다섯"보다 많다**

- **어디** — 자막 번역 `editing_session.py:250`(최악 630s), 받아쓰기 `draft_readiness.py:103,152`·`jobs.py:33`(Whisper 타임아웃 없음),
  부분 재생성 `editing_session.py:623`(202인데 인라인, 브리지 600s), TTS 후보 `assets.py:423`(600s), 촬영본 파생 렌더
  `footage_organizer.py:416,458`(202인데 인라인), 장면 이미지 `scene_images.py:39`(compose 300s / **env 없으면 코드 기본 600s** `settings.py:46`).
- **왜 결함인가** — `docker/workspace-nginx.conf:41` `proxy_read_timeout 330s`. `jobs.py:33,52,76,100`·`outputs.py:85,130,154`·`timeline.py:14`는
  202를 돌려주지만 `local_pipeline`에서 RUNNING→SUCCEEDED를 한 호출로 끝내는 인라인이라 라벨과 실제가 어긋난다.
- **확인함(코드)**, 실측은 앞 인계(더빙은 걸렸고 번역은 안 걸렸다).
- **고치는 법** — 정확성 결함이지 보안 아님. 앞 인계 §5 "잡 없이 도는 넷을 잡으로"와 같은 결정이다. 먼저 `settings.py:46` 기본값을 300으로.

### 1-7. **사람이 눌렀다는 증명이 없다** — principal 검사가 사실상 없음 (설계상, 그러나 MCP 전에 짚어야)

- **어디** — `services/api/src/videobox_api/principal.py:19-21`, `packages/domain-models/.../principal.py:58`(요청을 안 보고 env만 읽어
  항상 owner), `entitlements.can`은 항상 True. 승인 문: `review.py:112`, `footage_organizer.py:212,384`, `yujin_memory.py:145→167`,
  `director_proposals.py:912`.
- **왜 결함인가** — `127.0.0.1:5173`에 닿는 로컬 프로세스면 무엇이든 검토 승인·촬영본 승인·기억 승인 저장·제안 적용을 사람 대신 누른다.
  **Hermes(유진 컨테이너)는 못 한다**(toolset `context_engine` 하나, `hermes_rpc_client.py:342`가 tool 이벤트를 끊음, internal 네트워크).
  MCP 클라이언트나 다른 로컬 에이전트는 할 수 있다. CORS/미들웨어도 전무해 owner가 악성 페이지를 열면 파괴적 POST/DELETE가 CSRF로 나간다.
- **확인함(코드)**. 1인 로컬 제품의 설계 결과라 결함 등급은 owner 판단. **MCP 착수 전에** 승인 문 넷에 최소 Origin 검사나 승인 토큰을 둘지 결정할 것.

### 1-8. 출처 기록 셋이 OpenCut 재작성판을 **AGPL이라 적었는데 실제는 MIT**

- **어디** — `docs/oss/editor-ui-source-map.json:31`, `THIRD_PARTY_NOTICES.md:80`, `scripts/verify-editor-ui-source-provenance.ps1:23`.
- **왜 결함인가** — 고정 커밋 `bab8af8`의 LICENSE는 MIT 본문이고 AGPL 문구가 없다(2026-09-07 `gh api`로 확인). 코드를 한 줄도 안 가져와
  법적 위험은 없지만 "AGPL이라 거절"이라는 근거가 거짓이다. `oss-adoption-map.ko.md:123`의 "MIT"가 맞다.
- **확인함.**
- **고치는 법** — 셋을 `MIT; rejected runtime (reference only)`로 맞추고 `verify-editor-ui-source-provenance.ps1`을 돌려 초록 확인.
  거절 사유는 "AGPL"이 아니라 "런타임 미채택"으로 적는다.

### 1-9. 훅 가드가 환경 문제로 매번 실패한다

- **어디** — `.claude/settings.json` 훅이 `$CLAUDE_PROJECT_DIR/.venv/Scripts/python.exe`를 먼저 집는데 루트 `.venv`에 `cryptography`가 없다
  (`hermes_capabilities.py`·`context_capabilities.py`가 import). worktree `.venv`에는 45.0.6이 있다.
- **고치는 법** — 루트에서 `.venv/Scripts/python.exe -m pip install -r requirements-dev.txt`(가장 단순) 또는 훅에 `VIDEOBOX_GUARD_PYTHON`을
  worktree venv로 고정. 고친 뒤 아무 문서나 한 글자 고쳐 훅이 초록으로 끝나는지 본다.

### 1-10. 문서가 거짓이던 것 — 전부 **이번 턴에 고쳤거나 표시했다** (§4)

## 2. 다음 사람이 집을 순서 (수정 세션용)

1. **1-1 봉쇄** — RED 먼저, `_inside_any` 재사용, 컨테이너에서 역방향. 가장 위험하고 가장 명확하다.
2. **1-2 원장 복구 + 1.3.1 재빌드** — 대표님 데이터에 이미 들어간 거짓 표기.
3. **1-5(a)·(b)·(d) 시험 셋** — 어제 결함의 재발 방지 장치가 비어 있고, Postgres 전용 시험 하나가 18일째 빨갛다. 1-1을 고칠 때 같이.
4. **1-3 예외 문구** — `_http_error` 한 곳 + 잡 저장 여섯 곳. 1-4 화이트리스트도 여기 묶어 처리.
5. **1-9 훅 venv** — 5분짜리. 다음 세션들의 가드가 살아난다.
6. **1-8 출처 기록 셋** — 10분짜리.
7. **§3 죽은 코드 넷 삭제**(A-1~A-4) + 프론트 고아(A-6·A-7). 삭제 순서는 §3-1에 있다. **§3-2 여섯 문의 운명은 owner 결정 뒤.**
8. **1-6·1-7** — owner 결정 필요. 결정 전엔 `settings.py:46` 기본값 300만.

각 항목: RED → GREEN → 겨눈 울타리 한 줄 깨서 빨간 것 확인 → 컨테이너 역방향 → 커밋. 한도를 넘기지 말고 **항목마다 커밋**.

## 3. "안 쓰는 것 같다" — 세 겹(화면·게이팅·시험)을 다 본 결과

측정: 라우터 32개 경로 275개, `api.ts` 메서드 213개(직접 호출 없는 것 10개 = 4.7%, 고아 컴포넌트 경유 4개).

### 3-1. 세 겹이 다 죽은 것 — 넷 + 프론트 셋 (지워도 된다, 이 순서로)

| # | 무엇 | 어디 | 남길 것 |
|---|---|---|---|
| A-1 | `GET .../editing-sessions/{sid}/fixed-timeline` | `editing_session.py:167-172` → `orchestration.py:726-727` → `editing_session_and_regeneration.py:325-327` | 밑의 `build_fixed_track_timeline`(`editing_session.py:1082`)은 `build_selected_range_preview`가 쓰고 시험 있음 — **남긴다** |
| A-2 | `DELETE /api/format-templates/{id}` | `format_templates.py:103-113` | 스토어 `delete_template`은 시험 있음 — 남긴다 |
| A-3 | `GET /api/media-library/recent`(전역판) | `media_library.py:175-180` | 옆 `favorites`(`:168`)는 시험 있음 — **같이 지우지 마라** |
| A-4 | `POST .../creation-briefs/{b}/questions/{q}` 데코레이터만 | `creation_briefs.py:79` | 함수 `answer`는 `answer_from_body`가 부름 — 데코레이터 한 줄만 |
| A-5 | `packages/domain-models/.../director_conversation.py`(16줄) | 비테스트 import 0, 시험 0 | 파일 삭제 |
| A-6 | `apps/web/src/features/media/MediaLibraryBrowser.tsx` + 자기 시험 + `api.ts` 넷(`getMediaLibraryInstallState`, `listProjectMediaLibraryFavorites`, `listProjectRecentMediaLibraryAssetIds`, `setProjectMediaLibraryFavorite`) | 2026-09-01 `367538211`이 마지막 import를 지움 | **백엔드 경로는 시험이 있어 남긴다.** `task22-parity-owners.test.ts`가 이름을 잡는지 vitest 한 번 |
| A-7 | `hasPersistedEditorUiState` | `features/editor/workbench/editorUiState.ts:89-95` | 함수만 |

### 3-2. 살아 있음, 다만 화면에서만 거둠 (지우지 마라)

- `api.ts` 미배선 10개: `listDirectorMessages`·`prepareDirectorMessage`·`applyDirectorProposal`·`getDirectorProposal`(web+백엔드 시험),
  Hermes 넷(`main.py:1391`이 gateway env 둘 있을 때만 mount — **잠자는 배선**), `getPreview`·`getExport`(task22 시험이 정규식으로 고정).
- 잡 문들(`jobs.py`, `timeline.py:14`, `outputs.py:130,154` 등): 백엔드 시험 + `scripts/verify-production-readiness-smoke.py:687-727`.
- 테스트만 가져가는 계약 모듈 5개(`hermes_capability_authority`, `provider_evidence_intake`, `yujin_agent_package_contract`(여기 `McpPolicy`),
  `yujin_provider_adapter`, `lm_studio_smoke_evidence`) — 전부 "승인 대기 계약", 시험 붙음.
- 백엔드 시험만으로 사는 문 13개(`media-library/install·search·favorites`, `media-analysis/provenance`, review 추천 approve/reject,
  `provider-traces`, `final-renders/{j}/shares`, footage `sources/preview`·`derivatives/render`, `format-templates/{id}/apply`, visual-overlay 등).
- **경로 받는 프로젝트 자산 등록 여섯 문(§1-1)** — 화면 호출은 `voice-sample` 하나(`VoiceTtsSettings.tsx:206-214`), 스모크 스크립트가 다섯을 부름,
  시험 21건(단 `sfx`는 **0건**). 서비스 층 `orchestrator.register_*`는 업로드 문이 같이 쓰므로 지울 수 없다. 결정 대상은 HTTP 문 여섯과 스키마뿐.
  - 살리면: MCP `register_project_asset`의 문으로 다시 자리매김 + 1-1 봉쇄.
  - 지우면: `voice-sample` 경로 입력칸을 업로드로 바꾸고 스모크 `:644-671`·시험 21건 재작성. 자료실 쪽 경로 문을 방금 연 것과 앞뒤가 안 맞는다.
  - **어느 쪽이든 `sfx` 시험 0건부터.**

### 3-3. 2026-08-24 문서와의 차이 — 표시해 뒀다

`docs/2026-08-24-unowned-web-api-methods.ko.md` 머리에 거짓 셋을 달았다. 그 문서 뒤 `4ea1bcbd1`(08-31)이 15개를 지우고 9개를 남겼다.

## 4. 문서 — 무엇을 고쳤고 무엇을 표시했나

**직접 고친 SSOT (거짓 문장 → 참):**
- `CLAUDE.md` §6 — Mem0 기본은 자체 호스팅(밖으로 안 나감), "조회 폴백이 없다"→있다(`:194`), `:181`→`:207`. 7992자(한도 8000).
- `docs/development-fast-path.ko.md` §10.14 2-A(Mem0 "항상 외부로 나간다"→키 채울 때만), `:181`→`:207`, 2-C(장면 그림 "아직 없다"→08-21에 만듦,
  FLUX.1-schnell 확보→owner가 flux1-dev로 결정, "재지 않은 것"→24초 실측), §10.15 색인 묶음 8→32, 비전 프롬프트 둘.
- `docs/implementation-plan.ko.md` — 머리 안내 한 줄, §4 전환 "없다"→있다(2곳), §4 멀티트랙 제외 문장에 실물 주석, §8.5 "비어 있는 넷"→전부 만들어짐,
  §23.1 gemini 시험 삭제 완료, §23.1A "host bridge 안 받는다"→받는다, §23.2 gateway 존재·signer 배포됨(`[ ]`→`[~]`), §23.3B 편집 승인 게이트·대본 해제·
  로컬 경로·호스트 네트워크 해소, §23.5 `[ ]`→`[~]`.
- `docs/development-status-2026-06-29.ko.md` — 배너가 죽은 곳을 가리키고 있어 갱신.

**"낡았다 + 지금 맞는 문서 + 거짓 셋" 표시를 단 것(19):** `local-storage-strategy`(통째), `architecture-plan`, `oss-research-and-scope-cut`(통째),
`oss-adoption-map`, `research/2026-07-17-…adoption`, `capcut-parity-audit-2026-09-04`, `capcut-parity-plan-2026-09-04`, `capcut-full-adoption-plan-2026-09-04`,
`capcut-gap-2026-09-05`(정정 넷), `reference/capcut-observed-2026-08-22`(정정 둘), `brollbox-reuse-audit`(역사), `saas-expansion-design-notes` 한/영(역사),
`2026-08-24-unowned-web-api-methods`, `development-context.ko`(통째), `llm-provider-strategy`(정정 둘), `videobox-data-path-audit`, `oss/videobox-e2e-harness`,
`phase-6-…closeout`·`provider-trace-…closeout`(배너가 삭제된 파일을 가리킴), `starter-media-pack-license-research`(**주의 문만**, 행은 §1-2대로 다음 세션이).

**참으로 확인해 보고 안 한 것:** `2026-08-24-test-fixture-shape-audit`, `2026-08-24-web-user-copy-inventory`, `development-context.md`,
`exact-preview-performance`, `reference/capcut-screens/README`, `initial-architecture-and-folder-plan` 한/영(배너 있음). `docs/references/` 폴더는 없다.

**아직 못 넣은 것 — `CLAUDE.md` 자리 부족(8자 남음):** 2026-09-07 승인 기록 셋(`capcut-handoff-bridge`, `infographics-made-by-yujin`,
`one-drop-folder-sorted-for-me`)이 §2 목록에 없다. §2 목록을 fast-path로 내리는 것이 답이다.

## 5. 계획서 대조 — 남은 일이 실제로 남았나

**계획서엔 남았는데 이미 만들어진 것:** §8.5 넷 전부, §4 전환, §23.1 gemini 시험 삭제, §23.2 gateway·signer, §23.3B 로컬 경로·호스트 네트워크·
편집 승인·대본 해제, §23.5 Mem0 — 전부 계획서에 표시했다(§4).

**계획서엔 없는데 만들어진 것(전부 화면 도달 가능, 승인 기록 있음):** 인포그래픽(`infographics.py`, 결정 09-07), 동영상 번역기(자막 번역+더빙,
결정 09-02/03), 장면 그림·영상 생성(`scene_images.py`·`scene_videos.py`, 결정 08-29 — 단 편집기가 아니라 만들기 단계에서만 보임),
촬영본 정리(`footage_organizer.py` 17경로, `/footage`), 자료실 경로 등록·잡 조회(09-07), 미디어 inbox·드롭 폴더(결정 09-07),
공유 링크·출력 변형·포맷 저장·글꼴, Tauri 셸(결정 08-30, **어떤 스크립트도 안 부름**, 런처는 브라우저 `--app`), 6줄 타임라인(§1-10 아래 참조).
**계획서에 이름조차 없는 것:** 인포그래픽·더빙·촬영본 정리·경로 등록·잡 조회·공유 링크·포맷 저장·Tauri·드롭 폴더·자동 컷·MCP(1건).

**§4 제외 목록 대조:** 마스크·키프레임·멀티캠·전문 색보정·AI 스타일·결제·다중사용자·클라우드 렌더는 **정말 없다**(각각 grep 0건 또는 부정 시험).
**단 하나가 어긋난다** — "실시간 멀티트랙 편집 UI"(§4, `CLAUDE.md` §2.1, 결정 08-29 §103 "이 문서로도 열리지 않는다")인데 실물은
역할 고정 6줄 타임라인(`TimelineDock.tsx:772`)에 잠금·숨김·음소거·끌기·트림이 있다. 자유 트랙 추가는 없다. **owner가 문장을 고치든 실물을 확인하든 결정할 것.**

**계획서에 남았고 실제로도 남은 것:** §23.1 egress 게이트웨이·OAuth(코드 0건, `yujin_provider_adapter.py:13`이 스스로 "아직 안 지음"),
§23.4 read-only workflow(§1-7과 같은 문제), §23.5 TTL·retention, §23.6 release gate, MCP transport 0건(`McpPolicy`는 거부 전용 선언),
앞 인계 §5의 결정 둘(`list_project_assets` 문, 경로 등록 래퍼). 전부 owner 결정 대기다.

**반쪽(백엔드만, 화면 없음)으로 남은 것:** `ingest-path`, 자동 컷 둘, `media-analysis` POST·단건·provenance, `format-templates/{id}/apply`·DELETE,
공유 목록·메타, `jobs.py` 6개, `scene-images`·`scene-videos` 목록, `media-library/install`·`search`, footage `sources/preview`·`derivatives/render`,
review 추천 approve/reject, `preview-render`·`capcut-export`·`provider-traces`. 색감 **추천**은 양쪽 다 없다(정적 9종 카탈로그만 — `filters.py` docstring "여섯"도 낡음).

## 6. 걸러낸 것 — 하위 조사가 틀렸고 내가 뒤집은 지적 둘

1. "`EditorAssetBrowser.test.tsx:698`이 `대본` 탭 부재를 단언해 낡았다" — **아니다.** `대본` 탭은 `script` 속성이 있을 때만 그려지고
   (`EditorAssetBrowser.tsx:282`) 시험은 그 속성 없이 렌더한다. 단언이 맞다.
2. "OpenCut 재작성판은 AGPL이고 `oss-adoption-map`의 MIT가 틀렸다" — **반대다.** 업스트림 고정 커밋의 LICENSE가 MIT다(§1-8).

그리고 "`preview-render` 문이 아직 있다"는 앞 인계와 모순이 아니다 — 앞 인계도 "화면에서만 거둔 것"이라 적었다.

## 7. 확인한 것 / 못 한 것

- 변형 탐침 12개 실행(격리 worktree, 복구 확인). 재현 3건(1-1·1-2·1-3) 직접 실행. 업스트림 라이선스 `gh api`로 확인.
- 전체 백엔드 pytest(`-rs`)를 분리 프로세스로 돌렸다 — 결과는 이 문서 끝 "부록"에.
- **못 한 것:** 화면 시험(vitest)은 안 돌렸다(문서만 바꿨다). 1-4의 실제 삭제 도달 여부. 1-6 실측(앞 인계 값 사용).
  Tauri 셸 빌드. 실행 중 컨테이너의 env 값(compose 파일 기준으로만 판단).

## 부록 — 전체 pytest 결과 (2026-09-07 저녁, worktree venv)

`.venv/Scripts/python.exe -m pytest -q -rs -p no:cacheprovider` (분리 프로세스, 32분 20초)

**4714 통과 / 0 실패 / 56 skip / 경고 4.** skip은 초록이 아니라 안 돈 것이다. 사유별:

| 건수 | 사유 | 뜻 |
|---|---|---|
| 43 | `VIDEOBOX_TEST_POSTGRES_URL` 미설정 (`test_postgres_project_store.py` 39, `test_postgres_snapshot_import.py` 4) | **제품이 실제로 쓰는 저장소 경로가 기본 회귀에서 한 번도 안 돈다.** `scripts/run-postgres-store-tests.ps1`이 일회용 DB를 띄워 따로 돌린다(스크립트 머리가 이 함정을 그대로 적어 뒀다). §1-1을 고칠 때 Postgres 스토어에도 같은 등록 경로가 있는지 보고 **이 스크립트로도** 초록을 받아라. |
| 3 | 아이콘 글리프 폰트 없음 (`test_ffmpeg_final_renderer.py` 2, `test_exact_preview_artifact.py` 1) | 윈도우에는 그 폰트가 없어 아이콘 오버레이 렌더 시험이 안 돈다. 컨테이너(리눅스)에서만 실물이 나온다 — §1-5와 같은 종류의 눈먼 자리. |
| 4 | 라이브 게이트(`VIDEOBOX_RUN_*=1`): 유진 대화·LM Studio·미디어 디렉터 e2e·스타터 팩 e2e | 의도된 opt-in. 릴리스 게이트로만 돈다. |
| 1 | 이 윈도우 계정이 심볼릭 링크를 못 만든다 (`test_hermes_yujin_profile_distribution.py`) | 환경. 컨테이너에서는 돈다. |

`scripts/run-postgres-store-tests.ps1`(일회용 DB, 30초): **1 failed / 51 passed** — §1-5(d).

정적 집계: `tests/` 안 skip 구문 147곳(`pytest.skip`/`importorskip`/`mark.skip*`), 대부분 위 조건들의 중복이다.
