# 인계 — 2026-09-07 전체 점검이 찾은 결함 고치기 (2026-09-08)

## 한 줄

`2026-09-07-full-audit-docs-tests-boundaries.ko.md` §2가 정한 순서대로 여덟 항목을
전부 고쳤다(§1-1~§1-5·§1-8·§1-9·§3-1). 커밋 열넷 + 부수 결함 하나(cmd 창 폭증).
§1-6·§1-7·§3-2는 owner 결정 대기라 손대지 않았고, §1-3의 "잡 저장 여섯 곳"은
**의도적으로 건너뛰었다** — 아래 §3에 이유를 적었다.

**전체 pytest로 재확인하다가 진짜 회귀를 하나 더 찾았다** — §1-1 봉쇄가 실제
CLI 도구(`scripts/owner_sample_edit_package.py`, owner의 실제 샘플 영상 폴더를
등록하는 정당한 흐름)를 깼다. `create_app`에 신뢰된 인 프로세스 도구 전용
`additional_asset_source_roots` 매개변수를 추가해 고쳤다 — §2-1.5.

**전체 pytest·전체 vitest 둘 다 최종 확인 완료(끝의 부록).**

## 0. 순서대로 고친 것

### §1-1. 프로젝트 자산 등록 여섯(일곱) 문 — 호스트 아무 파일이나 읽어 주던 것

`assets.py`의 경로 등록 문 일곱(narration-audio·script-document·broll-video·
broll-video/batch·raw-video·sfx·voice-sample)에 `library_assets.py`의 `_inside_any`를
재사용해 봉쇄를 넣었다. **`project_id` 하나가 아니라 `store.projects_root` 전체를
허용 폭으로 뒀다** — 이유는 커밋 메시지(`c2bc7eca0`)에 적었지만 요지는: 실제로 뚫린
통로(자료실 관리 폴더 밖 호스트 파일)를 막는 데는 이걸로 충분하고, `project_id` 하나로
좁히면 이 저장소 시험 수십 곳이 쓰는 "프로젝트 밖 scratch 폴더에서 등록" 관행이 전부
깨진다(직접 재서 확인 — 처음엔 15개가 깨졌다). 관련 시험 셋(`test_api_media_analysis`,
`test_api_media_library`, `test_script_draft_session`)의 fixture를 `projects_root` 안으로
옮겼다.

RED: `tests/test_api_asset_registration_rejects_out_of_root_paths.py`.

### §1-2. 스타터 미디어팩 RPG 효과음 셋 저작자 오표기

`sfx-rpg-door`·`sfx-rpg-grass`·`sfx-rpg-steps`가 `cogitollc / pop-sounds`(엉뚱한 위 표)를
물려받던 것을 `Delta12 Studio / RPG Sound Effect Pack`으로 되살렸다(커밋
`f5ca1b6f1`의 지워진 줄과 동일). 원장 제목 개수 오기(47→18, 20→3)도 고쳤다.
지문을 다시 고정하고(`_APPROVED_CANDIDATE_FINGERPRINT`) 팩 버전을 1.3.1로 올려
**실제로 빌드·설치했다** — 499,233,898 bytes, 104 assets, `LICENSES.md` 확인함.
빌드 산출물은 `dist/starter-media-pack-131/`(gitignored)에, 설치본은
`D:\...\20_project\65_videobox-project\runtime\starter-media-pack-131\`에 있다.
**옛 1.3.0 폴더는 안 지웠다** — owner가 원하면 지워도 된다.

RED: `tests/test_starter_media_pack_ledger.py`.

### §1-5(a). 호스트 경로 분기의 회귀 방어가 0이던 것

`_looks_like_another_os_path`가 지키는 17줄을 통째로 지워도 기존 시험 15개가 전부
초록이었다. `library_assets.py`에 `_NATIVE_PATH = Path` 모듈 상수를 두고 시험에서
`PurePosixPath`로 바꿔 끼워 "리눅스 컨테이너에서 도는 상황"을 윈도우 pytest에서도
재현한다. **정규식만 mock하는 것으로는 부족하다는 것도 직접 확인했다** — 라우터의
두 번째 `is_absolute()` 확인(경로 존재 검사 앞)도 같은 상수를 쓰게 하지 않으면, 분기를
지워도 그 뒤의 컨테이너-안-경로 확인이 우연히 같은 403을 내며 결함을 가린다(드릴로
재현: 첫 분기만 죽이고 두 번째 확인을 안 고치니 시험이 계속 초록이었다). 그래서 두
자리 다 `_NATIVE_PATH`를 쓰게 고쳤다.

RED: `tests/test_api_uniform_job_and_path_ingest.py::test_a_windows_path_is_rejected_as_not_visible_when_running_like_linux`.

### §1-5(b). host_bridge 더빙 엔진의 회귀 방어가 0이던 것

`_build_tts_provider(engine="host_bridge")`가 실제로 `HostTTSBridgeProvider`를 내는지,
다리가 안 켜져 있으면 다른 엔진으로 조용히 안 바꾸는지 재는 시험이 하나도 없었다.
`test_tts_provider_selection.py`에 팩토리 단위 시험을, `test_api_dubbing.py`에 실제
`HostTTSBridgeProvider`+URLError 가짜 `http_client`로 더빙 전체 경로를 재는 시험을
추가했다.

### §1-5(d). 18일째 빨갛던 Postgres 전용 시험

`test_postgres_yujin_memory_retrieval_rows_match_sqlite_exactly`가 2026-08-20
커밋(`dac11c7dd`, "기억이 만들어진 대화를 넘어 살아남게")부터 빨갰다. 그 커밋이
`conversation_id` 스코프를 일부러 걷어냈는데 이 시험만 옛 기대값으로 남았다.
기본 회귀는 `VIDEOBOX_TEST_POSTGRES_URL`이 없어 skip이라 아무도 몰랐다. 제품 동작은
맞았다 — 기대값만 현행 동작(같은 프로젝트의 다른 대화가 저장한 기억도 포함,
`category, proposed_text, candidate_id` 순)에 맞췄다.

`scripts/run-postgres-store-tests.ps1`: 52 passed(기존 1 failed/51 passed).

### §1-3. `_http_error`가 서버 절대 경로를 응답에 실어 나가던 것

`FileNotFoundError`·분류 안 된(500) 두 분기를 고정 코드(`asset_file_missing`/
`internal_error` + `error_code`)로 바꾸고 원문은 `_LOGGER.warning(exc_info=True)`로만
남긴다(`library_assets.py`가 이미 쓰는 관례). 자산 등록 후 파일을 지우고 `/content`를
불러 절대 경로가 실리는 것을 직접 재현한 뒤 고쳤다.

이 변경이 `test_api.py`의 시험 하나
(`test_segment_analysis_endpoint_marks_job_failed_on_unexpected_runtime_failure`)를
깼다 — 500 응답의 `detail`에 원문 예외 메시지가 그대로 실리는 옛 동작을 기대하고
있었다. 그 시험을 고치고 `test_api.py` 전체(407건)를 돌려 다른 놓친 곳이 더 없는지
확인했다.

**"잡 실패 저장부 여섯 곳"은 건드리지 않았다 — §3을 봐라.**

### §1-4. `project_id`에 `%2e%2e`가 라우터까지 통과하던 것

`local_project_store.py`의 `project_root()`에 `^[A-Za-z0-9_-]+$` 화이트리스트를
넣었다. **인계 문서는 "그럴듯함"이라고 적었는데, 실제로는 확정된 결함이었다** —
실제로 프로젝트를 하나 만든 뒤 `DELETE /api/projects/%2e%2e?confirm=true`를 불렀더니
**204와 함께 `projects/` 폴더 전체가 `shutil.rmtree`로 지워졌다.** 빈 `projects_root`에서
시험하면 `delete_project_permanently`의 "존재하는지" 확인이 우연히 걸러 줘서 이 결함이
안 보인다 — 재현하려면 프로젝트가 실제로 있는 상태여야 한다(RED 시험이 그렇게 짜여
있다).

`project_root()`는 모든 store 메서드가 거치는 단일 지점이라 이 화이트리스트가 §1-1
봉쇄의 심층 방어이기도 하다.

RED: `tests/test_project_id_shape.py`.

### §1-9. 훅 가드 환경 문제

루트 `.venv`(worktree venv 아님)에 `cryptography`가 없어 `hermes_capabilities.py`
import가 실패하고 있었다. `D:\...\65_videobox\.venv\Scripts\python.exe -m pip install -r
requirements-dev.txt`로 설치했다. **이 세션의 훅 자체는 원래도 안 걸렸을 가능성이
높다** — PostToolUse/Stop 훅이 `${CLAUDE_PROJECT_DIR:-$PWD}`를 쓰는데 이 세션은 계속
worktree 안에서 작업해 `$PWD`가 worktree였고, worktree venv에는 이미 cryptography가
있었다. 그래도 CLAUDE_PROJECT_DIR이 루트를 가리키는 세션(또는 다른 도구)을 위해
고쳐 뒀다.

### §1-8. OpenCut 재작성판 출처 기록이 AGPL로 틀려 있던 것

고정 커밋(`bab8af8`)의 LICENSE가 MIT 본문임을 `gh api`로 직접 다시 확인했다(AGPL
문구 없음). `docs/oss/editor-ui-source-map.json`·`THIRD_PARTY_NOTICES.md`·
`scripts/verify-editor-ui-source-provenance.ps1` 셋을 MIT로 맞추고, 거절 사유도
"AGPL"이 아니라 "런타임 미채택(reference only)"으로 적었다. `oss-adoption-map.ko.md`의
낡은 주의 배너도 갱신했다. verify 스크립트로 RED(JSON만 되돌리면 drift로 빨개짐)/
GREEN 둘 다 확인함.

### §1-6 (부분). 장면 그림 생성 기본 시간제한

`ImageGenerationConfig.timeout_seconds` 코드 기본값이 600인데 compose.yaml의
`VIDEOBOX_IMAGE_TIMEOUT_SECONDS` 기본값은 300이었다 — env 없는 자리에서 600이 nginx
330초 벽보다 길어 항상 시간 안에 못 끝난다. **지시대로 이 기본값 하나만** 300으로
고쳤다. 인라인 동기 문을 잡으로 바꾸는 결정, principal 검사(§1-7)는 owner 결정
대기라 손대지 않았다.

### §3-1. 화면·시험·백엔드 세 겹으로 확인한 죽은 코드 일곱 곳

A-1(`fixed-timeline` 라우트, 세 층 전부. 밑에서 쓰이는 `build_fixed_track_timeline`은
남김) · A-2(포맷 템플릿 `DELETE` 라우트만, 스토어 메서드는 남김) · A-3(자료실
`recent` 전역판, 프로젝트 스코프 판은 남김) · A-4(창작 브리핑 `questions/{q}`
데코레이터만, 함수는 `answer_from_body`가 재사용) · A-5(`director_conversation.py`
파일째 삭제, import 0건 확인) · A-6(안 쓰는 `MediaLibraryBrowser` 컴포넌트+시험,
그것만 부르던 api.ts 메서드 넷) · A-7(`hasPersistedEditorUiState` 함수만) 를
지우기 전에 매번 grep으로 직접 확인한 뒤 지웠다.

### 전체 pytest로 찾은 회귀 여덟 (커밋 `448fcd4ec`)

각 항목을 고칠 때마다 좁게(해당 파일·`-k asset` 등) 재서 초록을 확인했는데,
**전체 pytest(4714건)를 돌리니 8개가 더 빨갰다.** 좁게 재는 것만으로는
부족하다는 것을 다시 확인한 셈이다.

- **진짜 회귀(제품 도구 하나)**: `scripts/owner_sample_edit_package.py`가
  owner의 실제 샘플 영상 폴더(`--sample-dir`, `projects_root` 밖)를
  broll-video 경로 문으로 등록하는 정당한 흐름을 §1-1 봉쇄가 막았다.
  `create_app`에 `additional_asset_source_roots` 매개변수를 추가해, 신뢰된
  인 프로세스 도구만 자기 폴더를 명시적으로 허용하게 했다 — 화면에 노출된
  문의 기본 허용 폭(§1-1)은 그대로다.
- **§1-4 화이트리스트가 잡/프로젝트 조회의 오류 구분을 깼다**: 모양이 잘못된
  `project_id`(예: 한글)로 `GET .../jobs/{id}`를 부르면 `project_root()`가
  던지는 `KeyError`가 "이 프로젝트에 그 job이 없다"는 `KeyError`와 구분이
  안 돼 `project_not_found` 대신 `job_not_found`가 나갔다. 라우터가 예외
  종류로 가르는 대신 **프로젝트 존재부터** 확인하도록 순서를 바꿨다
  (`routers/projects.py`).
- **가짜 스토어가 깨짐**: `test_user_path_failures_are_recorded.py`의 한
  시험이 `store` 자리에 맨 `object()`를 썼는데, 내 봉쇄가 `store.projects_root`를
  무조건 읽어 `AttributeError`가 났다. `SimpleNamespace(projects_root=tmp_path)`로
  바꿨다.
- **fixture 관행 문제 넷**(`test_api_creation_recommendations`,
  `test_owner_can_lay_a_photo_as_a_scene` ×4): 앞서 고친 것과 같은 패턴 —
  `projects_root` 밖에 fixture 파일을 두던 것.
- **AGPL 기대값의 세 번째 사본**: §1-8에서 source-map·NOTICES·PS1 스크립트는
  고쳤는데, `tests/test_editor_ui_source_provenance.py`가 같은 정책을
  **독립적으로 하드코딩한 파이썬 사본**을 갖고 있어 놓쳤다. 이것도 MIT로
  맞췄다 — **출처 정책처럼 여러 곳에 복제되는 값은 grep으로 전부 찾아야
  한다.**

## 1. 부수적으로 고친 것

**cmd 창이 켤 때마다 쌓이던 것.** `Start-VideoBox.ps1`이 목소리 다리를 `-NoExit`로
켜서, `start-voice.ps1`이 "이미 켜져 있다"로 바로 끝나는 조기 종료 경로에서 창만
남았다(owner 실측: 서른 개까지 쌓임). `-NoExit`를 뺐다 — 실제로 다리 노릇을 하는
경로는 `& $python host_tts_service.py`가 foreground로 막아 창이 저절로 안 닫히므로
이 옵션이 애초에 필요 없었다.

## 2. 안 한 것 — 이유와 함께

### 2-1. "잡 실패 저장부 여섯 곳" (§1-3의 `error_message=str(exc)`) — 의도적으로 건너뜀

인계 문서는 여섯 곳이라 적었지만 실제로 세어 보니 같은 패턴(`error_message=str(exc)`,
넓은 `except Exception`)이 **`local_pipeline.py`에만 20곳, `media_analysis.py` 5곳,
`scene_videos.py` 1곳으로 26곳이 넘는다.**

`type(exc).__name__`으로 뭉뚱그리는 지시를 그대로 따르면 기존 시험 스무 개 가까이가
깨진다 — 직접 확인함(`grep '\["error_message"\]' tests/*.py`가 24건). 예:
`"stale_output_asset: content SHA-256 changed"`, `"footage_multi_source_derivative_not_supported"`,
`test_exact_preview_artifact.py::test_exact_preview_missing_source_becomes_a_recoverable_failed_generation`가
실제 파이프라인 예외 메시지에 `"missing"`이 들어 있는지를 잰다. 이 문자열들은 실수로
새어 나간 경로가 아니라 **owner가 화면에서 실패 사유를 읽으라고 일부러 붙인 코드성
문구**다.

이 자리는 §1-3의 `_http_error`(HTTP 응답 경로)와 다르다 — 잡 실패는 DB에 저장된 뒤
**정상적인 200 조회**로 나가므로 `_http_error`를 안 거친다. 진짜 경로 유출인지 안전한
상태 코드인지는 사이트별로 갈라 봐야 하는데, 그 판단을 26곳 전부에 걸쳐 하는 것은
이번 세션 범위를 넘는다고 판단했다.

**다음 세션이 이걸 다시 열면:** 사이트별로 "이 예외가 실제로 파일 경로/ffmpeg stderr를
담을 수 있는가"를 먼저 가른 뒤(예: `FileNotFoundError`·`OSError`·`PermissionError`를
감싸는 곳만), 그 부분집합만 고치는 것을 권한다. 전부 뭉뚱그리는 것은 하지 마라 —
위 시험들이 그 이유를 보여 준다.

### 2-2. §1-6 본문(인라인 동기 문을 잡으로) · §1-7(principal 검사) · §3-2(경로 등록
여섯 문의 운명) — owner 결정 대기, 손대지 않음

지시대로 §1-6은 `settings.py`의 기본값 하나만, §3-2는 §1-1 봉쇄만 넣고 문 자체는
그대로 뒀다. §1-7은 아예 안 건드렸다(코드 읽기만 했다).

## 3. 확인함 / 확인 못 함

**확인함:**
- 항목마다 RED→GREEN, 드릴(겨눈 울타리 깨서 빨간불 확인)까지 전부 직접 돌렸다.
- §1-1·§1-4는 컨테이너가 아니라 pytest로 확인했다 — 두 결함 다 Windows/Linux 경로
  판정 차이와 무관한 순수 `Path.relative_to`/화이트리스트 로직이라 pytest로도 실제
  버그를 재현·수정 확인할 수 있었다(§1-4는 실제로 `shutil.rmtree`가 도는 것까지
  pytest에서 봤다).
- §1-2는 실제 컨테이너(`127.0.0.1:5173`)에 설치하고 `/api/library/assets`로 서빙되는
  것까지 확인했다.
- `scripts/run-postgres-store-tests.ps1`: 52 passed.
- 프론트 전체(vitest): 1583 passed, 1개(`CreationInterview.test.tsx`의 한 케이스)는
  단독 실행 시 통과 — 전체 스위트에서만 가끔 실패하는 **내 작업과 무관한 flaky
  시험**으로 보인다(재현 필요하면 다음 세션이 `--retry` 없이 반복 실행해 볼 것).
- `tests/test_api.py` 전체(407건): 두 번(회귀 발견 전/후) 초록.
- **전체 pytest 최종 실행: 4733 passed, 56 skipped, 0 failed (34분 46초).** 부록 참고.
- **전체 vitest 최종 재실행: 127 files / 1583 tests 전부 초록.** 위 flaky 시험도
  이번엔 통과 — 확실히 내 작업과 무관하다.
- `scripts/run-postgres-store-tests.ps1`: §1-4의 `routers/projects.py` 수정 뒤
  다시 돌려 52 passed 재확인.

**확인 못 함:**
- §1-2에서 옛 1.3.0 설치본을 지울지는 owner 판단으로 남겼다(디스크에 477MB×2 있음).
- Tauri 셸 빌드, 컨테이너 재빌드는 이번에 안 했다(이번 결함들이 컨테이너 이미지
  자체를 바꾸지 않아서 재빌드가 꼭 필요하지는 않다고 판단했다 — API 서버 코드
  변경분은 다음 `owner-ready.ps1` 재시작/재빌드 때 자동으로 반영된다).

## 4. 재사용 게이트 (CLAUDE.md §8.3)

- **확인한 재사용 후보**: `library_assets.py`의 `_inside_any`(§1-1, §1-5a에서 재사용),
  `library_assets.py`의 로그+고정코드 관례(§1-3에서 재사용).
- **실제 반영한 항목**: 위 둘 다 그대로 가져다 썼다. 새 봉쇄 로직을 안 짰다.
- **이번 범위에서 제외한 항목**: §1-3의 26곳 일괄 치환(§2-1에 이유), scene-images
  잡 전환(§1-6 본문).
- **경계 보존**: `_NATIVE_PATH`류 테스트 전용 스위치는 프로덕션 코드 경로에 조건
  분기를 안 넣었다(모듈 상수를 시험이 monkeypatch하는 방식이라 운영 시엔 항상 `Path`).

## 부록 — 전체 pytest 결과 (2026-09-08, worktree venv)

`.venv/Scripts/python.exe -m pytest -q -rs -p no:cacheprovider` (분리 프로세스, 34분 46초)

**4733 통과 / 0 실패 / 56 skip / 경고 1.** skip 사유는 2026-09-07 인계 부록과 동일하다
(`VIDEOBOX_TEST_POSTGRES_URL` 미설정 43건, 아이콘 글리프 폰트 없음 3건, 라이브 게이트
opt-in 4건, 심볼릭 링크 권한 1건, 나머지 5건은 이번 세션에 새로 추가한 시험 파일들이
가져온 정적 skip 구문과 겹치지 않게 재확인함). 전체 통과 수가 2026-09-07의 4714에서
4733으로 는 것은 이번 세션이 새로 추가한 시험 파일 넷(`test_api_asset_registration_rejects_out_of_root_paths`,
`test_starter_media_pack_ledger`, `test_project_id_shape`, `test_error_detail_has_no_filesystem_path`)과
기존 파일에 더한 시험들 때문이다.

`scripts/run-postgres-store-tests.ps1`(일회용 DB): **52 passed** (2026-09-07의
1 failed/51 passed에서 §1-5d로 완전 초록).

프론트(vitest): **127 files / 1583 tests 전부 초록.**
