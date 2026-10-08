# 설명 모션 2단계 — 템플릿 셋·모션 다리(8202)·자료실 등록·편집기 `모션 만들기` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> 실행 모델은 **Claude Sonnet**. 이 문서의 Global Constraints가 모든 Task에 걸린다.

**Goal:** 대표님이 편집기에서 `모션`을 눌러 막대 비교·금액 카운터·단계 목록 중 하나를 고르고 숫자·글만 적으면, 이 컴퓨터의 하이퍼프레임이 1920×1080 mp4를 만들어 자료실 영상에 넣고 지금 프로젝트로 가져와, 장면에 `적용`(전체 화면 B-roll)으로 바로 쓸 수 있게 한다.

**Architecture:** 인포그래픽 길을 끝에서 끝까지 그대로 베낀다. 호스트 다리 `scripts/host_motion_service.py`(8202, 문지기 `host_bridge_guard`·공유 토큰·127.0.0.1만)가 **저장소에 들어 있는 템플릿**을 빈 임시 폴더에 복사하고, 검증된 JSON만 `data.js`로 적고, 길이·모양 자리표시자 둘만 숫자·정해진 낱말로 바꾼 뒤 `node …/hyperframes.mjs render`를 시간 상한·한 번에 하나(잠금)로 돌려 영상 바이트를 base64로 돌려준다. 컨테이너는 `MotionHostBridge` → `MotionService`(템플릿 고르기·엄격한 pydantic 변수 검사·자료실 등록) → `POST /api/library/motions`·`GET /api/library/motion-templates`로 연다. 화면은 편집기 `미디어 더하기` 줄의 `모션` 팝업(`MotionPanel`)이고, 만든 뒤 `materializeLibraryAsset`로 이 프로젝트에 가져온다. 투명 오버레이(webm 알파)는 다리까지는 만들지만 **완성본 렌더러가 VP9 알파를 못 읽어서** 화면에는 열지 않고, 별도 마지막 Task 9로 둔다.

**Tech Stack:** Python 3.12(FastAPI, pydantic v2, `http.server`, urllib, subprocess), Node 24 + npm `hyperframes` **0.8.140**(Apache-2.0, 호스트 전용), 손으로 쓴 의존성 없는 타임라인(JS, GSAP 없음), React 19 + TypeScript + vitest 2.1 + Testing Library, PowerShell 5.1, ffmpeg/ffprobe 8.1.1, Docker compose(`owner-ready.ps1` 경유로만).

**Spec:** `docs/decisions/2026-10-08-motion-graphics-with-hyperframes.ko.md`(승인 결정·설계 방침·실측) + `artifacts/motion-spike/motion-spike-report.md`(스파이크 보고서·명령·필터, gitignore 대상이라 이 계획이 필요한 것을 옮겨 적었다).

## Global Constraints

- 작업 위치: 메인 체크아웃 `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`, 브랜치 `main`. Task를 시작할 때마다 `git status --short`(`.anchor/`만 보여야 한다), `git log --oneline -1`(앞 Task 커밋)을 본다. 다르면 멈추고 보고한다.
- 이 계획은 **공식 계획서 밖의 범위 확장**이다(2026-10-08 승인 결정 2단계). 3단계(유진 연결)·4단계(오버레이 다듬기, 리모션 재검토)는 이 계획 밖이다. 인계·갭 보고에 그렇게 적는다.
- 백엔드 시험: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider <파일>::<시험>`. bare `pytest`·시스템 파이썬 결과는 근거가 아니다. 전체 시험은 마지막 Task에서 **혼자** `--ignore=tests/test_mcp_server.py`를 붙여 돌린다(약 45분).
- 명령은 저장소 루트의 Git Bash 한 셸에서 친다고 가정한다. 웹 명령은 늘 괄호 subshell로 감싼다: `(cd apps/web && npx vitest run <file>)`. 타입 검사 `(cd apps/web && npx tsc --noEmit)`, 빌드 `npm --prefix apps/web run build`.
- **RED/GREEN 단계에서는 시험을 정확히 하나만 돌린다.** RED가 처음부터 초록이면 멈추고 보고한다. 파일 단위 실행은 그 뒤 "좁은 확인"에서만 한다.
- 컨테이너는 `.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild`(PowerShell)로만 다시 짓는다. `docker compose`를 직접 치지 않는다(`docker exec`로 읽기만 하는 확인은 된다).
- **모델이 코드를 쓰지 않는다.** 템플릿은 저장소에 들어 있는 파일이고, 바깥에서 들어오는 것은 템플릿 이름 하나·숫자·글(검증됨)·길이·모양(`full`|`overlay`)뿐이다. HTML·JS·CSS를 요청으로 받는 자리를 만들지 않는다.
- **네트워크 0건.** 템플릿 파일에 `http://`·`https://`·`cdn`·`gsap`가 없어야 한다(Task 1 시험이 지킨다). **GSAP를 저장소에 넣지 않는다**(owner 승인 필요 항목). 스파이크가 오프라인으로 증명한 손으로 쓴 `window.__timelines` 방식만 쓴다. 글꼴은 `assets/fonts/korean/NotoSansKR-Variable.ttf`를 렌더마다 임시 폴더로 복사한다(저장소에 두 벌 두지 않는다).
- 하이퍼프레임은 **항상** `HYPERFRAMES_NO_TELEMETRY=1`, `DO_NOT_TRACK=1`, `HYPERFRAMES_SKIP_SKILLS=1`, `HYPERFRAMES_NO_UPDATE_CHECK=1`, `HYPERFRAMES_NO_AUTO_INSTALL=1`로 부른다. 버전은 `scripts/motion-bridge/package.json`에 `"hyperframes": "0.8.140"`(정확히, `^` 없음)으로 못박고 `package-lock.json`도 커밋한다. `node_modules`는 커밋하지 않는다(루트 `.gitignore`의 `node_modules/`가 이미 막는다).
- 다리: `127.0.0.1`에만 묶고, 모든 요청(읽기 포함)이 `check_request`(Host·토큰·JSON)를 먼저 지난다. 결과 파일은 설정된 작업 뿌리(`--work-root`) 아래에서만 만든다. 렌더 상한 180초, 한 번에 하나(바쁘면 409 `motion_render_busy`). 렌더 요청 안에서 브라우저를 받지 않는다(준비 전이면 503 `motion_engine_not_prepared`).
- 시간 값 셋은 어긋나면 안 된다: 다리 렌더 상한 `RENDER_TIMEOUT_SECONDS=180` < 컨테이너 대기 `BRIDGE_TIMEOUT_SECONDS=240` < nginx `proxy_read_timeout 600s`. `tests/test_compose_contract.py`가 잡는다(Task 4).
- 화면 문구: 쉬운 해요체, 이름꼴 이름표(`모션`, `모션 만들기`). 금지어(provider, runtime, model, job, revision, pipeline, 시스템, 모델, 파이프라인 등)를 쓰지 않는다 — `apps/web/src/user-copy-policy.test.ts`가 새 `.tsx`를 자동으로 찾아 검사한다. 존댓말 호칭이 필요한 보고는 "루이스 대표님".
- **팔레트·CSS를 바꾸지 않는다.** `MotionPanel`은 인포그래픽 패널이 쓰는 기존 클래스(`vb-infographic*`)를 재사용한다. `apps/web/src/styles/`에 diff가 생기면 그 Task는 실패다.
- 화면 조작은 `components/ui`의 `Button`·`Input`만 쓴다(native `<button>`/`<input>` 금지). 그러면 `task22-parity-owners.test.ts`의 허용 목록을 고칠 일이 없다 — 마지막에 그 시험을 돌려 확인만 한다.
- 새 `.ps1` 두 개(`start-motion.ps1`, `prepare-motion.ps1`)는 **UTF-8 BOM + CRLF**로 저장한다(윈도우 PowerShell 5.1이 한글을 읽는다). `owner-ready.ps1`은 이미 BOM이 있다 — 고친 뒤 첫 3바이트가 `ef bb bf`인지 확인한다.
- 비밀값(`.env.container` 값, 다리 토큰)은 화면·로그·커밋·인계에 찍지 않는다. `cat .env.container` 금지. 토큰은 셸 변수로만 다루고 `unset`한다.
- 이미 알려진 실패(이번 변경 탓이 아니다): `editor-workbench.test.tsx` "gives the material dock back the same way, without needing a second click", `tests/test_owner_ready_script.py::test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure`. 부하로 흔들리는 e2e·vitest 건은 **혼자 다시 돌려 본 뒤** 탓을 정한다.
- 커밋은 Task마다 하나. 메시지는 한국어, 끝 줄 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. 푸시는 Task 8(그리고 Task 9) 검증이 끝난 뒤 `git push origin main`만(`--force` 금지). 확인과 푸시를 한 명령에 묶지 않는다. 도구 권한이 푸시를 막으면 우회하지 말고 멈춰 owner에게 `git push origin main` 직접 실행 또는 허용 규칙 `Bash(git push origin main)` 추가를 요청한다.
- **모든 Task는 검증 넷으로 닫는다.** 갭(이 Task의 Step과 대조, 안 한 것을 적는다) · 역방향(실제 런타임) · 동작(재서 숫자로) · 배선(grep으로 부르는 자리를 센다). 컨테이너가 필요한 역방향·동작은 Task 8에서 몰아 하고, 다리(호스트)만으로 되는 것은 그 Task에서 한다. 각 Task 마지막 Step에 해당 명령이 있다.
- **화면에 연 기능은 유진에게도 연다(상시 지시)** — 이번 계획은 결정 문서의 단계 구분에 따라 **유진 연결을 3단계로 미룬다.** 3단계가 할 세 겹은 아래 "3단계(유진)로 넘기는 것"에 적었다. 갭 보고에 "유진 미연결(3단계)"을 반드시 적는다.

## 앵커 규칙과 다른 계획서와 겹치는 파일

이 계획은 `docs/superpowers/plans/2026-10-02-audit-00-master.ko.md`의 규칙을 그대로 따른다: **줄 번호가 아니라 인용된 문자열로 앵커를 찾는다. 문자열이 그대로 있으면 진행, 없으면 멈추고 보고한다(짐작해서 고치지 않는다).** 아래 줄 번호는 2026-10-08 작성 시점 참고값일 뿐이다.

이 계획은 **B–F 계획서(`2026-10-02-audit-bf-yujin-capabilities.ko.md`)보다 먼저** 실행한다. 함께 고치는 파일:

| 파일 | 이 계획 | 뒤에 오는 계획 |
|---|---|---|
| `apps/web/src/api.ts` | 타입 셋·메서드 둘 추가(Task 6) | B–F, G |
| `scripts/owner-ready.ps1` | 모션 다리 블록 추가(Task 5) | B–F, G |
| `services/api/src/videobox_api/models.py` | 모션 모델 넷 추가(Task 4) | B–F |
| `services/api/src/videobox_api/main.py` | import 셋·state 하나·라우터 하나(Task 4) | B–F |
| `packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py` | (Task 9만) VP9 알파 입력 | — |
| `tests/test_host_bridge_guard.py`, `tests/test_compose_contract.py`, `compose.yaml`, `.dockerignore` | 다리 넷째·계약 시험 | — |

B–F가 고치는 `YujinPanel.tsx`·`OutputsPage.tsx`·`library_assets.py`·`editing_session.py`는 **이 계획에서 건드리지 않는다**(B–F Task 13 "설명 카드·표·도형 얹기"와 부딪히지 않게). Task 8에서 총괄 문서 §1 표 아래에 이 계획이 먼저 들어왔다는 한 줄을 남긴다.

## Task 0에서 미리 확인해 적어 둔 것 (2026-10-08 계획 작성 때 실측·코드 확인)

**자료실 → 편집 세션(전체 화면):**
1. 인포그래픽은 `InfographicService._ingest` → `LibraryIngestService.ingest(media_type=LibraryMediaType.IMAGE, …)`로 **자료실에만** 들어간다(`infographic_service.py`). 편집기는 자료실 그림을 `api.listLibraryAssets({ mediaType: "image" })`로 직접 보여 준다(`EditorWorkbenchRoute.tsx` "라이브러리 그림. 프로젝트마다 다시 넣지 않고").
2. **자료실 영상(broll)은 편집기 목록에 바로 안 뜬다.** 편집기 카드는 `api.listBrollAssets(projectId)`(이 프로젝트 자산)뿐이다. 자료실 영상을 쓰려면 `POST /api/library/assets/{id}/materialize`(`api.materializeLibraryAsset(libraryAssetId, projectId)`)로 프로젝트 자산(`AssetType.BROLL_VIDEO`)으로 복사해야 한다. `LibraryPickerDialog`(`자료실에서 가져오기`)와 `AddMediaFiles`가 이 길을 쓴다. → **`MotionPanel`은 만든 뒤 바로 materialize한다.**
3. 프로젝트 영상 카드의 `적용` → `applyAssetCard` → `port.applyMedia({ kind: "broll", segmentId, assetId })` → `update_segment_broll_override`(`editing_session.py`). 이것이 **전체 화면 B-roll**이다. 기본 media_controls는 `loop: true`, `pad: false`(`media_controls.py`) — 장면보다 짧은 클립은 **처음부터 다시 돈다**. 그래서 `MotionPanel`은 고른 장면 길이를 기본 길이로 쓴다(Review Focus 1).
4. `LibraryIngestService.ingest`는 확장자를 거르지 않는다(mp4·webm 둘 다 들어간다). `materialize_user_library_asset`는 `broll → AssetType.BROLL_VIDEO`.

**오버레이(작은 창):**
5. 세션 모델에 **영상 오버레이가 이미 있다**: 카드의 `화면에 얹기`(영상·사진 카드) → `applyImageOverlay` → `update_segment_image_overlay(…, vertical, horizontal, size, motion, preserve_source_audio)`, `overlay_type="image_overlay"`. 자리(`top|middle|bottom`·`left|center|right`)·크기(`small 0.35|medium 0.55|large 0.80`)·움직임(`fade_in_out` 등)이 `export_image_overlay_geometry`(`ffmpeg_final_renderer.py`)에 있다. → **불투명 mp4는 지금도 `화면에 얹기`로 작은 창+페이드가 된다**(어두운 배경이 그대로 카드처럼 보인다).
6. **투명(알파)은 안 된다.** 제품이 지나는 렌더 길(`track_overlay_indices`, 주석 "제품이 실제로 지나는 길이 여기다")이 입력을 `command += ["-i", str(path)]`로만 연다. 스파이크 실측대로 VP9 알파 webm은 `-c:v libvpx-vp9`를 `-i` **앞에** 줘야 알파가 산다(안 주면 투명 자리가 저장된 색으로 칠해진다). 저장소 어디에도 `libvpx`가 없다(`grep -rn libvpx packages` → 0). → 투명 오버레이는 **렌더러 변경이 필요해서** 2단계 화면에 열지 않고 Task 9로 뗀다. 다리·템플릿은 `overlay`(투명 바탕+반투명 카드)를 처음부터 만든다(Task 1·2·7에서 재 둔다).
7. 같은 렌더러의 옛 길(`broll_with_overlays.mp4`를 만드는 export overlay 경로)은 모든 오버레이를 `-loop 1 -i`로 연다. 영상 오버레이는 이 길로 안 온다(위 주석). Task 9 범위 밖이고 갭에 적는다.

**스파이크에서 옮겨 온 사실(보고서는 gitignore 대상):** 6초 1080p30 = 12~16초(고정 시작 약 4초 + 출력 1초당 1~1.3초), 0.3~1MB H.264. `--format webm` = VP9+알파(6초 549KB), `mov` = ProRes 53.5MB. 알파는 `html, body { background: transparent }`일 때만. 첫 렌더에 `~/.cache/hyperframes/chrome/chrome-headless-shell/win64-152.0.7977.30/chrome-headless-shell-win64/chrome-headless-shell.exe`(약 270MB)를 받는다 — 이 컴퓨터에는 이미 있다. GSAP 없는 컴포지션(`window.__timelines["main"]`에 seek/time/duration을 손으로 단 객체)은 죽은 프록시(`NODE_USE_ENV_PROXY=1 HTTPS_PROXY=http://127.0.0.1:9`)에서도 네트워크 로그 0줄로 렌더됐다. CLI: `hyperframes render <dir> -o <out> --format mp4|webm --fps 30 --frames-cache-dir <dir>`, `hyperframes browser ensure`(브라우저 받기), 환경 변수 `HYPERFRAMES_BROWSER_PATH`가 있다. `--variables`는 스파이크에서 시험하지 않았다 — **이 계획은 쓰지 않고** 다리가 `data.js`를 직접 쓴다(결정 문서의 "`--variables` JSON만 채운다"와 같은 뜻: 들어가는 것은 JSON뿐이고, 넣는 통로만 우리가 잰 것으로 바꿨다).

## 3단계(유진)로 넘기는 것 — 이 계획 밖

화면에 연 `모션 만들기`를 유진도 쓰게 하려면 세 겹이 필요하다(상시 지시 "화면에 열면 유진도 같이 연다"). 이번에는 **만들지 않고** 인계에 적는다.

1. **의도**: `yujin_editing_proposals.py`에 `MakeMotionOperation(segment_id, template: Literal[...], variables: dict, duration_sec)` — 변수 검사는 이 계획의 `parse_motion_variables`를 그대로 부른다.
2. **적용기**: `MotionService.make(...)` → `materialize` → `update_segment_broll_override`(전체 화면). 되돌리기는 기존 B-roll 되돌리기. 2~3분 걸릴 수 있어 기다림 표시(작업+폴링)를 재사용한다.
3. **프로필 안내문**: 유진 프롬프트에 "설명이 필요한 숫자 장면에는 막대 비교·금액 카운터·단계 목록 중 하나를 **제안**하고 숫자는 대본에 있는 것만 쓴다"를 넣는다(사람 게이트 유지: 유진은 제안, 대표님이 고른다 — 결정 문서).

## Review Focus

1. **장면보다 짧은 모션**: B-roll 기본이 `loop: true`라 10초 장면에 6초 카운터를 깔면 숫자가 0부터 다시 올라간다. `MotionPanel`이 고른 장면 길이(3~30초로 자름)를 기본 길이로 넣는다 — Task 6 시험 `장면 길이를 기본 길이로 쓴다`.
2. **가장 긴 한글**: 제목 24자·이름 10자·단계 24자·금액 13자리+기호가 판을 넘으면 안 된다. 막대 값 칸은 글 폭을 재서 막대 길이를 줄이고, 금액은 글자 수로 크기를 줄인다(Task 1 템플릿). Task 2 Step의 `--longest` 렌더와 Task 8 프레임 확인이 눈으로 잰다.
3. **두 번 누름·두 창**: 렌더 중 두 번째 요청은 기다리지 않고 409 `motion_render_busy` → 화면 "다른 모션을 만드는 중이에요". Task 2 잠금 시험, Task 6 문구 시험, Task 7 동시 요청 실측.
4. **처음 준비 전**: 브라우저(약 270MB)가 아직 없을 때 렌더 요청 안에서 받기 시작하면 요청이 몇 분 매달린다. 다리는 미리 확인해 503 `motion_engine_not_prepared`, 하이퍼프레임에는 `HYPERFRAMES_BROWSER_PATH`를 준다. 준비는 `owner-ready`가 숨은 창에서 따로 돌린다(시간 상한). Task 2·5 시험.
5. **글 속 기호·이상한 숫자**: `<script>`, `<b>`, 줄바꿈·제어 문자, `NaN`·`Infinity`·음수·1조 초과. 화면(잠금+안내)·API(422 `motion_variables_invalid`, 한국어 문제 목록)·다리(400 `text_not_allowed`) 세 겹에서 막고, 템플릿은 `textContent`만 쓴다(`innerHTML` 금지 grep). Task 1·2·3·6 시험.

---

### Task 0: 출발 점검 — 앵커·도구·포트 확인 (읽기만)

**Files:** 없음(읽기만). 결과는 Task 8 인계에 옮긴다.

**Interfaces:**
- Consumes: 없음
- Produces: 없음

- [ ] **Step 1: 저장소 상태**

```bash
git status --short
git log --oneline -3
git worktree list
git diff --check
```

예상: `.anchor/`(그리고 이 계획서)만 보인다. 최근 커밋에 `d97cfb637 docs: CLAUDE.md에 설명 모션(하이퍼프레임) 결정 한 줄`이 있다(그 뒤 커밋이 있으면 무엇인지 적는다). 다른 제품 코드 변경이 있으면 멈추고 보고한다.

- [ ] **Step 2: 호스트 도구와 포트**

```bash
node --version; npm --version; ffmpeg -hide_banner -version | head -1; ffprobe -hide_banner -version | head -1
ls ~/.cache/hyperframes/chrome/chrome-headless-shell/*/chrome-headless-shell-win64/chrome-headless-shell.exe 2>/dev/null || echo "browser-not-prepared"
.venv/Scripts/python.exe -c "import socket;print('8202', 'busy' if socket.socket().connect_ex(('127.0.0.1',8202))==0 else 'free')"
grep -c '^VIDEOBOX_BRIDGE_TOKEN=' .env.container
ls assets/fonts/korean/NotoSansKR-Variable.ttf
```

예상: node v24.x, ffmpeg 8.x, 브라우저 경로 한 줄(2026-10-08 실측: 있음), `8202 free`, `1`, 글꼴 파일 있음. `8202 busy`면 무엇이 쥐고 있는지 보고하고 멈춘다(다른 프로젝트일 수 있다). 토큰 줄이 `0`이면 `.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory`를 한 번 돌린 뒤 다시 본다.

- [ ] **Step 3: 앵커 문자열이 그대로 있는지 센다**

```bash
grep -c 'export type SceneImageRequest' apps/web/src/api.ts
grep -c '  createSceneImage: (projectId: string, payload: SceneImageRequest)' apps/web/src/api.ts
grep -c 'import { InfographicPanel } from "./InfographicPanel";' apps/web/src/features/editor/assets/EditorAssetBrowser.tsx
grep -c 'const \[infographicOpen, setInfographicOpen\] = useState(false);' apps/web/src/features/editor/assets/EditorAssetBrowser.tsx
grep -c 'className="vb-editor-assets__infographic"' apps/web/src/features/editor/assets/EditorAssetBrowser.tsx
grep -c '        <Dialog open={narrationOpen} onOpenChange={setNarrationOpen}>' apps/web/src/features/editor/assets/EditorAssetBrowser.tsx
grep -c 'VIDEOBOX_INFOGRAPHIC_BRIDGE_URL: ${VIDEOBOX_INFOGRAPHIC_BRIDGE_URL:-http://host.docker.internal:8201}' compose.yaml
grep -c '다리 셋(8199·8200·8201)의 공유 토큰' compose.yaml
grep -c -- '-Summary $infographicSummary -Action $infographicAction -Evidence $infographicEvidence' scripts/owner-ready.ps1
grep -c '^class SceneImageCreateRequest(BaseModel):' services/api/src/videobox_api/models.py
grep -c '# `scene_image_service`와 같은 이유 -- 켜지 않았으면 `None`이다.' services/api/src/videobox_api/main.py
grep -c '^from videobox_api.routers.infographics import build_infographics_router$' services/api/src/videobox_api/main.py
grep -c '    app.include_router(build_infographics_router())' services/api/src/videobox_api/main.py
grep -c '^\*\*/\.venv-\*$' .dockerignore
grep -c '다리 셋(목소리 8199·캡컷 8200·그림 8201)은 공유 토큰을 요구한다' docs/development-fast-path.ko.md
grep -c '^## 자막 글꼴 (컨테이너에 함께 배포)' THIRD_PARTY_NOTICES.md
grep -c '        single_thread_source_indices: set\[int\] = set()' packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py
grep -c '                track_overlay_indices\[item.clip_id\] = len(source_paths)' packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py
grep -c 'command += \["-threads", "1" if source_index in single_thread_source_indices else threads\]' packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py
```

예상: 전부 `1`. `0`이 있으면 그 앵커를 쓰는 Task 전에 멈추고 보고한다. 이 Task는 커밋하지 않는다.

---

### Task 1: 호스트 도구 꾸러미와 템플릿 셋 (`scripts/motion-bridge/`)

**Files:**
- Create: `scripts/motion-bridge/package.json`, `scripts/motion-bridge/package-lock.json`(npm이 만든다)
- Create: `scripts/motion-bridge/templates/_shared/motion-runtime.js`
- Create: `scripts/motion-bridge/templates/{bar_compare,money_counter,step_list}/index.html`, `…/template.js`, `…/hyperframes.json`
- Modify: `.dockerignore`(끝에 덧붙임)
- Test: `tests/test_motion_templates_offline.py`(새 파일)

**Interfaces:**
- Consumes: 없음
- Produces: 템플릿 키 셋 `bar_compare`·`money_counter`·`step_list`. 각 `index.html`은 자리표시자 `__VB_DURATION__`(여러 번)·`__VB_MODE__`(한 번)를 갖고, `data.js` → `motion-runtime.js` → `template.js` 차례로 부른다. `data.js`(다리가 쓴다)는 `window.__VB_MOTION__ = {"variables": {...}, "duration": <초>, "mode": "full"|"overlay"};`. 변수 모양(다리·API가 같은 것을 쓴다):
  - `bar_compare`: `{title: str, subtitle: str, unit: str, bars: [{label: str, value: number}, …2~5]}`
  - `money_counter`: `{lead: str, amount: int, prefix: "₩"|"$"|"", suffix: str, caption: str}`
  - `step_list`: `{title: str, steps: [str, …2~5]}`

배경: 스파이크 컴포지션(`artifacts/motion-spike/c-bar|c-money|c-steps|c-nolib`)은 gitignore 대상이고, 셋은 CDN의 GSAP를 부르며 숫자·글이 박혀 있다. 여기서는 `c-nolib`의 GSAP 없는 타임라인 방식으로 **셋을 다시 쓰고** 자리를 그대로 옮겨 온다. 스파이크의 `hyperframes.json`에는 `$schema`·`registry` 주소(https)가 있어 뺀다.

- [ ] **Step 1: 실패하는 시험을 쓴다** — `tests/test_motion_templates_offline.py`

```python
"""설명 모션 템플릿 -- 저장소에 들어 있는 코드만 돌고, 바깥에 나가지 않는다 (2026-10-08 결정 2단계).

템플릿은 headless 크롬 안에서 도는 HTML+JS다. 그래서 **코드로 다룬다**: 모델이 쓴 코드를
받지 않고(결정 방침 1), 바깥 주소를 부르지 않고(스파이크: 기본 컴포지션은 GSAP를 CDN에서
받았다), 글을 마크업으로 만들지 않는다(`textContent`만). 다리가 넣는 것은 `data.js`의 JSON과
자리표시자 둘(길이·모양)뿐이다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE_ROOT = ROOT / "scripts" / "motion-bridge"
TEMPLATES = BRIDGE_ROOT / "templates"
KEYS = ("bar_compare", "money_counter", "step_list")


def _template_files() -> list[Path]:
    return sorted(path for path in TEMPLATES.rglob("*") if path.is_file())


def test_the_motion_engine_is_pinned_exactly() -> None:
    package = json.loads((BRIDGE_ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["private"] is True
    assert package["dependencies"] == {"hyperframes": "0.8.140"}
    lock = json.loads((BRIDGE_ROOT / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["packages"]["node_modules/hyperframes"]["version"] == "0.8.140"


@pytest.mark.parametrize("key", KEYS)
def test_every_template_ships_its_own_files(key: str) -> None:
    for name in ("index.html", "template.js", "hyperframes.json"):
        assert (TEMPLATES / key / name).is_file(), f"{key}/{name}가 없다"
    assert (TEMPLATES / "_shared" / "motion-runtime.js").is_file()


def test_templates_never_reach_the_network() -> None:
    files = _template_files()
    assert files, "템플릿 파일이 하나도 없다"
    for path in files:
        text = path.read_text(encoding="utf-8").lower()
        for banned in ("http://", "https://", "cdn", "gsap", "@import", "googleapis"):
            assert banned not in text, f"{path.relative_to(ROOT)}에 {banned!r}가 있다"


def test_templates_never_turn_text_into_markup() -> None:
    for path in _template_files():
        text = path.read_text(encoding="utf-8")
        for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function", "fetch(", "XMLHttpRequest", "import("):
            assert banned not in text, f"{path.relative_to(ROOT)}에 {banned!r}가 있다"


@pytest.mark.parametrize("key", KEYS)
def test_each_page_loads_only_its_three_local_scripts_in_order(key: str) -> None:
    page = (TEMPLATES / key / "index.html").read_text(encoding="utf-8")
    tags = re.findall(r"<script\b[^>]*>(.*?)</script>", page, re.DOTALL)
    assert all(body.strip() == "" for body in tags), "안에 코드를 쓴 script가 있다"
    sources = re.findall(r'<script\s+src="([^"]+)"\s*>', page)
    assert sources == ["data.js", "motion-runtime.js", "template.js"]


@pytest.mark.parametrize("key", KEYS)
def test_each_page_takes_only_its_length_and_look_from_the_bridge(key: str) -> None:
    page = (TEMPLATES / key / "index.html").read_text(encoding="utf-8")
    assert page.count('data-mode="__VB_MODE__"') == 1
    assert page.count('data-duration="__VB_DURATION__"') >= 2
    assert set(re.findall(r"__VB_[A-Z]+__", page)) == {"__VB_DURATION__", "__VB_MODE__"}
    assert 'data-composition-id="main"' in page
    assert 'data-width="1920" data-height="1080"' in page


@pytest.mark.parametrize("key", KEYS)
def test_the_overlay_look_keeps_a_card_behind_the_text(key: str) -> None:
    """스파이크 프레임에서 바탕 없는 글자는 무늬 위에서 안 읽혔다(결정 방침 3)."""
    page = (TEMPLATES / key / "index.html").read_text(encoding="utf-8")
    assert 'html[data-mode="overlay"],html[data-mode="overlay"] body{background:transparent}' in page
    assert re.search(r'html\[data-mode="overlay"\] #card\{[^}]*background:rgba\(', page)


@pytest.mark.parametrize("key", KEYS)
def test_the_font_is_the_repository_font_loaded_locally(key: str) -> None:
    page = (TEMPLATES / key / "index.html").read_text(encoding="utf-8")
    assert 'src:url("assets/NotoSansKR-Variable.ttf")' in page
    assert (ROOT / "assets" / "fonts" / "korean" / "NotoSansKR-Variable.ttf").is_file()


def test_the_motion_tools_stay_out_of_the_container_image() -> None:
    """템플릿과 node_modules(약 130MB)는 호스트 다리만 쓴다. 컨테이너는 안 읽는다."""
    patterns = [
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert "scripts/motion-bridge" in patterns
```

- [ ] **Step 2: 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_motion_templates_offline.py::test_the_motion_engine_is_pinned_exactly
```

예상: FAIL, `FileNotFoundError: ...scripts\motion-bridge\package.json`.

- [ ] **Step 3: 꾸러미를 만든다**

`scripts/motion-bridge/package.json`:

```json
{
  "name": "videobox-motion-bridge",
  "private": true,
  "description": "VideoBox 설명 모션 다리가 이 컴퓨터에서 부르는 하이퍼프레임. 컨테이너에는 안 들어간다.",
  "license": "UNLICENSED",
  "dependencies": {
    "hyperframes": "0.8.140"
  }
}
```

잠금 파일을 만든다(npm 레지스트리에서 받는다 — 결정 문서가 승인한 패키지다. 설치 스크립트는 돌리지 않는다; 스파이크에서 esbuild postinstall 없이 렌더가 됐다):

```bash
(cd scripts/motion-bridge && npm install --package-lock-only --ignore-scripts --no-audit --no-fund)
(cd scripts/motion-bridge && npm ci --ignore-scripts --no-audit --no-fund)
git check-ignore -q scripts/motion-bridge/node_modules && echo node-modules-ignored
```

예상: `package-lock.json`이 생기고 `node_modules/hyperframes/package.json`의 version이 `0.8.140`, `node-modules-ignored`.

- [ ] **Step 4: 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_motion_templates_offline.py::test_the_motion_engine_is_pinned_exactly
```

예상: PASS.

- [ ] **Step 5: 공통 타임라인을 쓴다** — `scripts/motion-bridge/templates/_shared/motion-runtime.js`

이 파일이 GSAP를 대신한다. 하이퍼프레임은 `window.__timelines["main"]`의 `seek(t)`를 프레임마다 부르고 그 순간의 DOM을 찍는다(스파이크 `c-nolib`과 같은 객체 모양).

```js
/* VideoBox 설명 모션 공통 타임라인. 바깥 애니메이션 꾸러미 없이 돈다(네트워크 0건, 2026-10-08 스파이크).
 * (이 파일에 그 꾸러미 이름이나 주소를 적지 않는다 -- tests/test_motion_templates_offline.py가 글자로 막는다.)
 * 하이퍼프레임은 window.__timelines["main"].seek(t)를 프레임마다 부르고 그 순간을 찍는다.
 * 글은 textContent로만 넣는다 -- 마크업으로 바꾸지 않는다. */
(function () {
  "use strict";
  var data = window.__VB_MOTION__ || { variables: {}, duration: 6, mode: "full" };
  function clamp(x) { return Math.max(0, Math.min(1, x)); }
  function easeOut(t) { return 1 - Math.pow(1 - t, 3); }
  function byId(id) { return document.getElementById(id); }
  function setText(id, value) {
    var element = byId(id);
    if (element) element.textContent = value === null || value === undefined ? "" : String(value);
    return element;
  }
  function show(id, visible) {
    var element = byId(id);
    if (element) element.style.display = visible ? "" : "none";
  }
  function formatNumber(value) {
    return Number(value).toLocaleString("en-US", { maximumFractionDigits: 1 });
  }
  function register(apply) {
    var timeline = {
      _t: 0,
      _d: Number(data.duration) || 6,
      pause: function () { return this; },
      play: function () { return this; },
      paused: function () { return true; },
      seek: function (t) { this._t = t; apply(t); return this; },
      time: function (t) { if (t === undefined) return this._t; return this.seek(t); },
      totalTime: function (t) { return this.time(t); },
      duration: function () { return this._d; },
      totalDuration: function () { return this._d; },
      getChildren: function () { return []; }
    };
    window.__timelines = window.__timelines || {};
    window.__timelines["main"] = timeline;
    timeline.seek(0);
  }
  window.VBMotion = { data: data, clamp: clamp, easeOut: easeOut, byId: byId, setText: setText, show: show, formatNumber: formatNumber, register: register };
})();
```

- [ ] **Step 6: 막대 비교** — `scripts/motion-bridge/templates/bar_compare/index.html`

```html
<!doctype html>
<html lang="ko" data-mode="__VB_MODE__">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1920, height=1080" />
<style>
@font-face{font-family:"NotoKR";src:url("assets/NotoSansKR-Variable.ttf");font-weight:100 900}
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1920px;height:1080px;overflow:hidden;background:#0f1218}
html[data-mode="overlay"],html[data-mode="overlay"] body{background:transparent}
#root{position:relative;width:1920px;height:1080px;font-family:"NotoKR",sans-serif;color:#f3f5f8}
#card{position:absolute;left:0;top:0;width:1920px;height:1080px}
html[data-mode="overlay"] #card{left:80px;top:50px;width:1760px;height:980px;border-radius:40px;background:rgba(15,18,24,0.86)}
#t{position:absolute;left:140px;top:90px;width:1640px;font-size:64px;font-weight:800;white-space:nowrap;overflow:hidden}
#s{position:absolute;left:140px;top:190px;width:1640px;font-size:34px;color:#9aa6b8;white-space:nowrap;overflow:hidden}
.row{position:absolute;left:140px;width:1640px;height:110px}
.lab{position:absolute;left:0;top:30px;width:420px;font-size:40px;font-weight:600;white-space:nowrap;overflow:hidden}
.bar{position:absolute;left:440px;top:10px;height:90px;width:0;border-radius:10px;background:#4f8cff}
.row.win .bar{background:#ffb020}
.val{position:absolute;left:464px;top:22px;font-size:52px;font-weight:800;font-variant-numeric:tabular-nums;white-space:nowrap}
#m{position:absolute;left:0;top:-200px;font-size:52px;font-weight:800;font-variant-numeric:tabular-nums;white-space:nowrap;visibility:hidden}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="__VB_DURATION__" data-width="1920" data-height="1080">
<div id="card" class="clip" data-start="0" data-duration="__VB_DURATION__" data-track-index="0"></div>
<div id="t" class="clip" data-start="0" data-duration="__VB_DURATION__" data-track-index="1"></div>
<div id="s" class="clip" data-start="0" data-duration="__VB_DURATION__" data-track-index="2"></div>
<div id="r0" class="row clip" style="top:300px" data-start="0" data-duration="__VB_DURATION__" data-track-index="3"><div id="l0" class="lab"></div><div id="b0" class="bar"></div><div id="v0" class="val"></div></div>
<div id="r1" class="row clip" style="top:440px" data-start="0" data-duration="__VB_DURATION__" data-track-index="4"><div id="l1" class="lab"></div><div id="b1" class="bar"></div><div id="v1" class="val"></div></div>
<div id="r2" class="row clip" style="top:580px" data-start="0" data-duration="__VB_DURATION__" data-track-index="5"><div id="l2" class="lab"></div><div id="b2" class="bar"></div><div id="v2" class="val"></div></div>
<div id="r3" class="row clip" style="top:720px" data-start="0" data-duration="__VB_DURATION__" data-track-index="6"><div id="l3" class="lab"></div><div id="b3" class="bar"></div><div id="v3" class="val"></div></div>
<div id="r4" class="row clip" style="top:860px" data-start="0" data-duration="__VB_DURATION__" data-track-index="7"><div id="l4" class="lab"></div><div id="b4" class="bar"></div><div id="v4" class="val"></div></div>
<div id="m"></div>
</div>
<script src="data.js"></script>
<script src="motion-runtime.js"></script>
<script src="template.js"></script>
</body>
</html>
```

`scripts/motion-bridge/templates/bar_compare/template.js` — 막대 길이는 **가장 넓은 최종 값 글의 폭을 재서** 남는 자리로 정한다(가장 긴 값 `1,000,000,000,000` + 단위 4자가 판을 넘지 않게, Review Focus 2). 재기는 매 프레임 한다 — 글꼴이 나중에 실려도 맞는 폭을 쓴다.

```js
(function () {
  "use strict";
  var M = window.VBMotion;
  var v = M.data.variables || {};
  var duration = Number(M.data.duration) || 6;
  var bars = (v.bars || []).slice(0, 5);
  var unit = v.unit || "";
  var max = Math.max.apply(null, bars.map(function (bar) { return Number(bar.value) || 0; }).concat([0])) || 1;
  M.setText("t", v.title);
  M.setText("s", v.subtitle || "");
  for (var i = 0; i < 5; i += 1) {
    M.show("r" + i, i < bars.length);
    if (i < bars.length) {
      M.setText("l" + i, bars[i].label);
      if (Number(bars[i].value) === max) M.byId("r" + i).classList.add("win");
    }
  }
  var grow = Math.min(1.6, duration * 0.3);
  function widestFinalValue() {
    var widest = 0;
    bars.forEach(function (bar) {
      var probe = M.setText("m", M.formatNumber(bar.value) + unit);
      widest = Math.max(widest, probe.offsetWidth);
    });
    return widest;
  }
  M.register(function (t) {
    var title = M.byId("t");
    var p = M.clamp(t / 0.7);
    title.style.opacity = p;
    title.style.transform = "translateY(" + (40 * (1 - p)) + "px)";
    var room = Math.max(400, 1640 - 464 - widestFinalValue() - 16);
    bars.forEach(function (bar, index) {
      var q = M.easeOut(M.clamp((t - 0.8 - index * 0.25) / grow));
      var shown = Number(bar.value) * q;
      var width = room * shown / max;
      M.byId("b" + index).style.width = width + "px";
      var label = M.setText("v" + index, M.formatNumber(shown) + unit);
      label.style.left = (440 + width + 24) + "px";
    });
  });
})();
```

`scripts/motion-bridge/templates/bar_compare/hyperframes.json`(셋 다 같다):

```json
{
  "paths": {
    "blocks": "compositions",
    "components": "compositions/components",
    "assets": "assets"
  },
  "media": {
    "autoProxy": true
  }
}
```

- [ ] **Step 7: 금액 카운터** — `scripts/motion-bridge/templates/money_counter/index.html`

**공통 머리**: 막대 비교 `index.html`의 첫 줄부터 `<style>` 안의 `html[data-mode="overlay"] #card{…rgba(15,18,24,0.86)}` 줄까지(`<!doctype html>`, `<html … data-mode="__VB_MODE__">`, `<head>`, meta 둘, `<style>`, `@font-face`, `*`, `html,body`, overlay 투명 줄, `#root`, `#card`, overlay `#card`)를 **글자까지 같게** 쓴다. 단계 목록도 같다. 그 아래에 이 템플릿 것만 쓰고 `</style></head>`로 닫는다:

```html
#card{background:radial-gradient(circle at 50% 40%,#1c2a1f,#0b0f0c)}
#lead{position:absolute;top:300px;left:0;width:1920px;text-align:center;font-size:54px;color:#9fd9a8;font-weight:600;white-space:nowrap;overflow:hidden}
#num{position:absolute;top:400px;left:0;width:1920px;text-align:center;font-size:230px;line-height:1.1;font-weight:900;color:#7dff9a;font-variant-numeric:tabular-nums;letter-spacing:-4px;white-space:nowrap}
#cap{position:absolute;top:720px;left:0;width:1920px;text-align:center;font-size:46px;color:#dfe6e0;white-space:nowrap;overflow:hidden}
```

`<body>`:

```html
<div id="root" data-composition-id="main" data-start="0" data-duration="__VB_DURATION__" data-width="1920" data-height="1080">
<div id="card" class="clip" data-start="0" data-duration="__VB_DURATION__" data-track-index="0"></div>
<div id="lead" class="clip" data-start="0" data-duration="__VB_DURATION__" data-track-index="1"></div>
<div id="num" class="clip" data-start="0" data-duration="__VB_DURATION__" data-track-index="2"></div>
<div id="cap" class="clip" data-start="0" data-duration="__VB_DURATION__" data-track-index="3"></div>
</div>
<script src="data.js"></script>
<script src="motion-runtime.js"></script>
<script src="template.js"></script>
```

(전체 화면 배경 `#card{background:radial…}`은 공통 머리 **뒤**에 와도 겹 모양(`html[data-mode="overlay"] #card`)을 못 이긴다 — 선택자가 더 구체적이라서. 그래서 겹 모양에서는 반투명 카드 색이 그대로 산다.)

`template.js` — 최종 글(`기호+천 단위 쉼표+뒤에 붙일 말`)의 글자 수로 크기를 정한다(13자리+기호도 판 안).

```js
(function () {
  "use strict";
  var M = window.VBMotion;
  var v = M.data.variables || {};
  var duration = Number(M.data.duration) || 5;
  var amount = Math.max(0, Math.round(Number(v.amount) || 0));
  var prefix = v.prefix === undefined ? "₩" : v.prefix;
  var suffix = v.suffix || "";
  var finalText = prefix + amount.toLocaleString("en-US") + suffix;
  var size = Math.min(230, Math.floor(1700 / Math.max(1, finalText.length * 0.62)));
  var number = M.byId("num");
  number.style.fontSize = size + "px";
  number.style.top = (400 + (230 - size) / 2) + "px";
  M.setText("lead", v.lead || "");
  M.setText("cap", v.caption || "");
  var count = Math.min(2.8, duration * 0.5);
  M.register(function (t) {
    M.byId("lead").style.opacity = M.clamp(t / 0.5);
    var q = M.easeOut(M.clamp((t - 0.4) / count));
    M.setText("num", prefix + Math.round(amount * q).toLocaleString("en-US") + suffix);
    M.byId("cap").style.opacity = M.clamp((t - 0.4 - count - 0.2) / 0.6);
  });
})();
```

- [ ] **Step 8: 단계 목록** — `scripts/motion-bridge/templates/step_list/index.html`

공통 머리(Step 7과 같은 것) 아래:

```html
#t{position:absolute;left:140px;top:110px;width:1640px;font-size:76px;font-weight:800;white-space:nowrap;overflow:hidden}
.st{position:absolute;left:140px;width:1640px;height:130px;display:flex;align-items:center;font-size:52px;font-weight:600;border-bottom:2px solid #232b38;opacity:0}
.no{flex:none;width:96px;height:96px;border-radius:50%;background:#4f8cff;display:flex;align-items:center;justify-content:center;font-size:48px;font-weight:800;margin-right:40px}
.tx{white-space:nowrap;overflow:hidden}
```

`<body>`:

```html
<div id="root" data-composition-id="main" data-start="0" data-duration="__VB_DURATION__" data-width="1920" data-height="1080">
<div id="card" class="clip" data-start="0" data-duration="__VB_DURATION__" data-track-index="0"></div>
<div id="t" class="clip" data-start="0" data-duration="__VB_DURATION__" data-track-index="1"></div>
<div id="s0" class="st clip" style="top:280px" data-start="0" data-duration="__VB_DURATION__" data-track-index="2"><div id="n0" class="no"></div><div id="x0" class="tx"></div></div>
<div id="s1" class="st clip" style="top:430px" data-start="0" data-duration="__VB_DURATION__" data-track-index="3"><div id="n1" class="no"></div><div id="x1" class="tx"></div></div>
<div id="s2" class="st clip" style="top:580px" data-start="0" data-duration="__VB_DURATION__" data-track-index="4"><div id="n2" class="no"></div><div id="x2" class="tx"></div></div>
<div id="s3" class="st clip" style="top:730px" data-start="0" data-duration="__VB_DURATION__" data-track-index="5"><div id="n3" class="no"></div><div id="x3" class="tx"></div></div>
<div id="s4" class="st clip" style="top:880px" data-start="0" data-duration="__VB_DURATION__" data-track-index="6"><div id="n4" class="no"></div><div id="x4" class="tx"></div></div>
</div>
<script src="data.js"></script>
<script src="motion-runtime.js"></script>
<script src="template.js"></script>
```

`template.js`:

```js
(function () {
  "use strict";
  var M = window.VBMotion;
  var v = M.data.variables || {};
  var duration = Number(M.data.duration) || 6;
  var steps = (v.steps || []).slice(0, 5);
  M.setText("t", v.title);
  for (var i = 0; i < 5; i += 1) {
    M.show("s" + i, i < steps.length);
    if (i < steps.length) { M.setText("n" + i, i + 1); M.setText("x" + i, steps[i]); }
  }
  var gap = Math.min(1.2, (duration * 0.6) / Math.max(1, steps.length));
  M.register(function (t) {
    var title = M.byId("t");
    var p = M.clamp(t / 0.5);
    title.style.opacity = p;
    title.style.transform = "translateY(" + (30 * (1 - p)) + "px)";
    steps.forEach(function (_step, index) {
      var q = M.easeOut(M.clamp((t - 0.8 - index * gap) / 0.6));
      var row = M.byId("s" + index);
      row.style.opacity = q;
      row.style.transform = "translateX(" + (-80 * (1 - q)) + "px)";
    });
  });
})();
```

`money_counter/hyperframes.json`, `step_list/hyperframes.json`은 Step 6과 같은 내용이다.

- [ ] **Step 9: `.dockerignore`에 덧붙인다** — 마지막 줄 `**/.venv-*` 다음에:

```
# 설명 모션 다리(호스트 전용, 2026-10-08). 템플릿과 하이퍼프레임 node_modules(약 130MB)는
# 이 컴퓨터의 다리만 읽는다. 컨테이너는 템플릿 이름표만 파이썬(`motion_templates.py`)에서 읽는다.
scripts/motion-bridge
```

- [ ] **Step 10: 좁은 확인**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_motion_templates_offline.py tests/test_compose_contract.py
```

예상: 전부 통과(새 파일 18건 안팎 + 기존 계약 시험). 실물 렌더는 Task 2에서 한다(다리가 `data.js`를 써야 돈다).

- [ ] **Step 11: 검증 넷과 커밋**

- 갭: Step 1~10과 대조. 실물 렌더·글자 크기 눈 확인은 아직 안 했다(Task 2 Step 9, Task 8).
- 배선: `grep -c "motion-runtime.js" scripts/motion-bridge/templates/*/index.html` → 셋 다 `1`. 소비자(다리)는 Task 2에서 생긴다.

```bash
git add scripts/motion-bridge/package.json scripts/motion-bridge/package-lock.json scripts/motion-bridge/templates .dockerignore tests/test_motion_templates_offline.py
git status --short
git commit -m "$(cat <<'EOF'
feat(motion): 설명 모션 템플릿 셋(막대 비교·금액 카운터·단계 목록)과 하이퍼프레임 0.8.140 고정

GSAP 없이 손으로 쓴 타임라인으로 돈다(네트워크 0건). 글은 textContent로만 넣고,
다리가 넣는 것은 data.js의 JSON과 길이·모양 자리표시자 둘뿐이다. 이미지에는 안 싣는다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

`git status --short`에 `scripts/motion-bridge/node_modules`가 보이면 커밋하지 말고 멈춘다.

---

### Task 2: 모션 다리(8202) — `host_motion_service.py`·`start-motion.ps1`·`prepare-motion.ps1`

**Files:**
- Create: `scripts/host_motion_service.py`
- Create: `scripts/start-motion.ps1`, `scripts/prepare-motion.ps1`(UTF-8 BOM, CRLF)
- Modify: `tests/test_host_bridge_guard.py`(다리 넷째를 배선 시험에 더한다)
- Test: `tests/test_motion_host_service.py`(새 파일), `tests/test_motion_host_scripts.py`(새 파일)

**Interfaces:**
- Consumes: Task 1의 템플릿 폴더·키·`data.js` 모양. `scripts/host_bridge_guard.py`의 `check_request(*, method, headers, port, expected_token)`, `load_bridge_token(environ, env_file)`, `BridgeTokenMissing`.
- Produces(Task 3·4·7·8이 쓴다):
  - 상수 `DEFAULT_PORT = 8202`, `BIND_HOST = "127.0.0.1"`, `RENDER_TIMEOUT_SECONDS = 180`, `MAXIMUM_VIDEO_BYTES = 64 * 1024 * 1024`, `MAXIMUM_VARIABLES_BYTES = 16384`, `TEMPLATE_KEYS = ("bar_compare", "money_counter", "step_list")`, `MIN_DURATION_SEC = 3.0`, `MAX_DURATION_SEC = 30.0`, `LAYOUT_FORMATS = {"full": "mp4", "overlay": "webm"}`, `PINNED_ENGINE_VERSION = "0.8.140"`, `FPS = 30`.
  - `@dataclass(frozen=True) BridgeSettings(node: Path | None, ffmpeg: Path | None, engine_root: Path, templates_root: Path, font_path: Path, work_root: Path, cache_root: Path)`, 속성 `hyperframes_bin -> Path`(= `engine_root / "bin" / "hyperframes.mjs"`), 클래스메서드 `discover(*, node: str | None = None, work_root: Path | None = None) -> BridgeSettings`.
  - `@dataclass(frozen=True) RenderOrder(template: str, variables: dict, duration_sec: float, layout: str)`, `@dataclass(frozen=True) RenderedMotion(path: Path, network_mentions: int)`.
  - `find_browser_executable(cache_root: Path) -> Path | None`, `readiness(settings: BridgeSettings) -> str`(`"ready"|"node_not_found"|"ffmpeg_not_found"|"engine_not_installed"|"browser_not_prepared"`), `diagnostics_payload(*, settings: BridgeSettings | None) -> tuple[int, dict]`.
  - `check_render_request(body: dict) -> RenderOrder | tuple[int, dict]`, `motion_data_script(order: RenderOrder) -> str`, `prepare_composition(*, settings, order, scratch: Path) -> Path`, `engine_environment(base: Mapping[str, str], *, browser: Path) -> dict[str, str]`, `confine_to_root(path: Path, root: Path) -> Path`, `run_bounded(arguments, *, timeout, env, cwd, popen=subprocess.Popen, killer=None) -> subprocess.CompletedProcess`, `render_motion(*, settings, order, scratch, runner=run_bounded) -> RenderedMotion`, `render_request_payload(body, *, settings, renderer=render_motion, lock=_RENDER_LOCK) -> tuple[int, dict]`.
  - HTTP: `GET /diagnostics` → `{status, node_path, engine_version, browser_path, recovery_message}`; `POST /render` 본문 `{template, variables, duration_sec, layout}` → 200 `{video_base64, format, byte_size, width: 1920, height: 1080, duration_sec, elapsed_sec, network_mentions}`. 오류: 400 `unknown_template`·`unknown_layout`·`duration_must_be_a_number`·`duration_out_of_range`·`variables_must_be_an_object`·`variables_too_large`·`variables_too_deep`·`text_not_allowed`·`number_not_allowed`; 409 `motion_render_busy`; 503 `motion_engine_not_prepared`(+`detail`: readiness 값); 504 `render_timed_out`; 500 `render_failed`(+`detail`)·`render_too_large`.
  - CLI: `--port`, `--node`, `--work-root`, 그리고 측정용 `--render-sample <키> [--layout full|overlay] [--duration 초] [--longest] --out <경로>`(토큰 없이, 서버 없이 한 번 그리고 JSON 한 줄 `{template, layout, duration_sec, elapsed_sec, byte_size, network_mentions, out}`을 찍는다).

판단과 HTTP 껍데기를 뗀다(시험은 소켓을 못 연다, `tests/conftest.py`). 그림 다리(`host_infographic_service.py`)의 `_Handler`·`_reply`·`_payload`·`_refused`·`build_server`·`main` 모양을 그대로 따른다.

- [ ] **Step 1: 실패하는 시험을 쓴다** — `tests/test_motion_host_service.py`

```python
"""이 컴퓨터에서 도는 모션 다리 자체 (2026-10-08 결정 2단계).

부르는 쪽(`test_motion_host_bridge.py`)과 따로 잰다. **소켓도, node도 안 부른다** --
판단 함수(`*_payload`, `check_render_request`, `prepare_composition`)와 갈아 끼울 수 있는
`runner`·`renderer`로 잰다. 실물 렌더는 이 Task의 Step 9(손으로)와 Task 7(측정)이다.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_PATH = ROOT / "scripts" / "host_motion_service.py"
_spec = importlib.util.spec_from_file_location("videobox_host_motion_service", _PATH)
assert _spec is not None and _spec.loader is not None
motion = importlib.util.module_from_spec(_spec)
# dataclass는 정의한 모듈을 sys.modules에서 찾는다(`test_host_bridge_guard._load`와 같은 이유).
sys.modules["videobox_host_motion_service"] = motion
_spec.loader.exec_module(motion)

BAR = {"title": "월 수익 비교", "subtitle": "", "unit": "만", "bars": [{"label": "쿠팡", "value": 1280}, {"label": "스마트스토어", "value": 860}]}


def _body(**overrides):
    body = {"template": "bar_compare", "variables": BAR, "duration_sec": 6, "layout": "full"}
    body.update(overrides)
    return body


@pytest.fixture()
def settings(tmp_path: Path):
    """준비가 끝난 컴퓨터를 흉내 낸다. 파일만 둔다 -- 실제로 띄우지 않는다."""
    node = tmp_path / "node.exe"
    node.write_bytes(b"node")
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"ffmpeg")
    engine = tmp_path / "bridge" / "node_modules" / "hyperframes"
    (engine / "bin").mkdir(parents=True)
    (engine / "bin" / "hyperframes.mjs").write_text("// fake", encoding="utf-8")
    (engine / "package.json").write_text(json.dumps({"name": "hyperframes", "version": "0.8.140"}), encoding="utf-8")
    chrome = tmp_path / "cache" / "chrome" / "chrome-headless-shell" / "win64-152.0.7977.30" / "chrome-headless-shell-win64" / "chrome-headless-shell.exe"
    chrome.parent.mkdir(parents=True)
    chrome.write_bytes(b"chrome")
    return motion.BridgeSettings(
        node=node, ffmpeg=ffmpeg, engine_root=engine,
        templates_root=ROOT / "scripts" / "motion-bridge" / "templates",
        font_path=ROOT / "assets" / "fonts" / "korean" / "NotoSansKR-Variable.ttf",
        work_root=tmp_path / "work", cache_root=tmp_path / "cache",
    )


def _never(**kwargs):  # noqa: ANN003
    raise AssertionError("여기까지 오면 안 된다 -- 그리기 전에 막혀야 한다")


def _writes(content: bytes, *, mentions: int = 0):
    def renderer(*, settings, order, scratch):  # noqa: ANN001
        out = scratch / f"out.{motion.LAYOUT_FORMATS[order.layout]}"
        out.write_bytes(content)
        return motion.RenderedMotion(path=out, network_mentions=mentions)
    return renderer


# 1. 진단 -- 무엇이 모자란지 차례대로 정직하게 말한다

def test_diagnostics_say_ready_when_everything_is_in_place(settings) -> None:
    status, payload = motion.diagnostics_payload(settings=settings)
    assert status == 200
    assert payload["status"] == "ready"
    assert payload["engine_version"] == "0.8.140"
    assert payload["recovery_message"] is None


def test_readiness_names_the_first_missing_piece(settings) -> None:
    from dataclasses import replace

    assert motion.readiness(replace(settings, node=None)) == "node_not_found"
    assert motion.readiness(replace(settings, ffmpeg=None)) == "ffmpeg_not_found"
    (settings.engine_root / "package.json").write_text(json.dumps({"version": "0.8.139"}), encoding="utf-8")
    assert motion.readiness(settings) == "engine_not_installed"


def test_a_computer_without_the_browser_is_not_ready(settings, tmp_path: Path) -> None:
    from dataclasses import replace

    empty = replace(settings, cache_root=tmp_path / "empty-cache")
    assert motion.find_browser_executable(empty.cache_root) is None
    status, payload = motion.diagnostics_payload(settings=empty)
    assert payload["status"] == "browser_not_prepared"
    assert "prepare-motion.ps1" in payload["recovery_message"]


# 2. 요청 검사 -- 그리기 전에 막는다

@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"template": "free_form"}, "unknown_template"),
        ({"layout": "mov"}, "unknown_layout"),
        ({"duration_sec": "열 초"}, "duration_must_be_a_number"),
        ({"duration_sec": 2.9}, "duration_out_of_range"),
        ({"duration_sec": 30.1}, "duration_out_of_range"),
        ({"duration_sec": float("nan")}, "duration_out_of_range"),
        ({"variables": ["x"]}, "variables_must_be_an_object"),
        ({"variables": {"title": "x" * 20000}}, "variables_too_large"),
        ({"variables": {"a": {"b": {"c": {"d": 1}}}}}, "variables_too_deep"),
        ({"variables": {"title": "<script>alert(1)</script>"}}, "text_not_allowed"),
        ({"variables": {"bars": [{"label": "a\u0000b", "value": 1}]}}, "text_not_allowed"),
        ({"variables": {"amount": float("inf")}}, "number_not_allowed"),
    ],
)
def test_a_bad_request_is_refused_before_anything_runs(settings, overrides, error) -> None:
    status, payload = motion.render_request_payload(_body(**overrides), settings=settings, renderer=_never)
    assert (status, payload["error"]) == (400, error)


def test_an_unprepared_engine_is_said_before_rendering(settings, tmp_path: Path) -> None:
    from dataclasses import replace

    status, payload = motion.render_request_payload(
        _body(), settings=replace(settings, cache_root=tmp_path / "none"), renderer=_never
    )
    assert (status, payload) == (503, {"error": "motion_engine_not_prepared", "detail": "browser_not_prepared"})


def test_a_bridge_without_settings_says_not_prepared() -> None:
    status, payload = motion.render_request_payload(_body(), settings=None, renderer=_never)
    assert (status, payload["error"]) == (503, "motion_engine_not_prepared")


# 3. 한 번에 하나

def test_a_second_render_while_one_is_running_is_told_busy(settings) -> None:
    lock = threading.Lock()
    lock.acquire()
    status, payload = motion.render_request_payload(_body(), settings=settings, renderer=_never, lock=lock)
    assert (status, payload) == (409, {"error": "motion_render_busy"})


def test_the_lock_is_given_back_even_when_a_render_fails(settings) -> None:
    lock = threading.Lock()

    def broken(**kwargs):  # noqa: ANN003
        raise RuntimeError("engine_failed: boom")

    status, payload = motion.render_request_payload(_body(), settings=settings, renderer=broken, lock=lock)
    assert (status, payload["error"]) == (500, "render_failed")
    assert lock.acquire(blocking=False)


# 4. 결과

def test_render_returns_the_exact_bytes_and_leaves_nothing_behind(settings) -> None:
    status, payload = motion.render_request_payload(_body(), settings=settings, renderer=_writes(b"MP4BYTES"), lock=threading.Lock())
    assert status == 200
    assert base64.b64decode(payload["video_base64"]) == b"MP4BYTES"
    assert (payload["format"], payload["byte_size"], payload["width"], payload["height"]) == ("mp4", 8, 1920, 1080)
    assert payload["duration_sec"] == 6
    assert payload["elapsed_sec"] >= 0
    assert list(settings.work_root.iterdir()) == []


def test_overlay_comes_back_as_webm(settings) -> None:
    status, payload = motion.render_request_payload(_body(layout="overlay"), settings=settings, renderer=_writes(b"WEBM"), lock=threading.Lock())
    assert (status, payload["format"]) == (200, "webm")


def test_a_render_that_never_ends_is_reported_as_a_timeout(settings) -> None:
    def slow(**kwargs):  # noqa: ANN003
        raise subprocess.TimeoutExpired(cmd="node", timeout=motion.RENDER_TIMEOUT_SECONDS)

    status, payload = motion.render_request_payload(_body(), settings=settings, renderer=slow, lock=threading.Lock())
    assert (status, payload) == (504, {"error": "render_timed_out"})


# 5. 컴포지션 만들기 -- 넣는 것은 JSON과 자리표시자 둘뿐

def test_prepare_composition_fills_only_the_length_the_look_and_the_data(settings, tmp_path: Path) -> None:
    order = motion.RenderOrder(template="bar_compare", variables=BAR, duration_sec=8.4, layout="overlay")
    comp = motion.prepare_composition(settings=settings, order=order, scratch=tmp_path / "scratch")
    page = (comp / "index.html").read_text(encoding="utf-8")
    assert "__VB_" not in page
    assert 'data-duration="8.4"' in page
    assert 'data-mode="overlay"' in page
    assert (comp / "motion-runtime.js").is_file()
    assert (comp / "assets" / "NotoSansKR-Variable.ttf").stat().st_size == settings.font_path.stat().st_size
    data = (comp / "data.js").read_text(encoding="utf-8")
    assert data.startswith("window.__VB_MOTION__ = ")
    assert json.loads(data[len("window.__VB_MOTION__ = "):].rstrip().rstrip(";")) == {"variables": BAR, "duration": 8.4, "mode": "overlay"}


def test_the_data_file_never_carries_raw_markup_characters() -> None:
    order = motion.RenderOrder(template="step_list", variables={"title": "A & B", "steps": ["1", "2"]}, duration_sec=6, layout="full")
    script = motion.motion_data_script(order)
    for raw in ("<", ">", "&"):
        assert raw not in script
    assert "\\u0026" in script


# 6. 엔진을 부르는 방식 -- 고정 버전·오프라인·텔레메트리 끔·토큰 안 넘김

def test_render_calls_the_pinned_engine_offline_and_quietly(settings, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOBOX_BRIDGE_TOKEN", "t" * 43)
    seen: dict = {}

    def runner(arguments, *, timeout, env, cwd):  # noqa: ANN001
        seen.update(arguments=arguments, timeout=timeout, env=env, cwd=cwd)
        output = Path(arguments[arguments.index("-o") + 1])
        output.write_bytes(b"X")
        return subprocess.CompletedProcess(arguments, 0, "Inlined CDN script https://cdn.example/x.js\n", "")

    scratch = settings.work_root / "one"
    scratch.mkdir(parents=True)
    order = motion.RenderOrder(template="bar_compare", variables=BAR, duration_sec=6, layout="overlay")
    rendered = motion.render_motion(settings=settings, order=order, scratch=scratch, runner=runner)

    arguments, env = seen["arguments"], seen["env"]
    assert arguments[:3] == [str(settings.node), str(settings.hyperframes_bin), "render"]
    assert arguments[arguments.index("--format") + 1] == "webm"
    assert arguments[arguments.index("--fps") + 1] == "30"
    assert Path(arguments[arguments.index("-o") + 1]).resolve().is_relative_to(settings.work_root.resolve())
    assert seen["timeout"] == motion.RENDER_TIMEOUT_SECONDS
    for name in ("HYPERFRAMES_NO_TELEMETRY", "DO_NOT_TRACK", "HYPERFRAMES_SKIP_SKILLS", "HYPERFRAMES_NO_UPDATE_CHECK", "HYPERFRAMES_NO_AUTO_INSTALL", "NODE_USE_ENV_PROXY"):
        assert env[name] == "1", name
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:9"
    assert env["HYPERFRAMES_BROWSER_PATH"] == str(motion.find_browser_executable(settings.cache_root))
    assert "VIDEOBOX_BRIDGE_TOKEN" not in env
    assert rendered.network_mentions == 1


def test_an_engine_that_says_ok_but_writes_nothing_is_a_failure(settings) -> None:
    def runner(arguments, *, timeout, env, cwd):  # noqa: ANN001, ARG001
        return subprocess.CompletedProcess(arguments, 0, "", "")

    scratch = settings.work_root / "two"
    scratch.mkdir(parents=True)
    order = motion.RenderOrder(template="step_list", variables={"title": "x", "steps": ["a", "b"]}, duration_sec=6, layout="full")
    with pytest.raises(RuntimeError, match="engine_wrote_nothing"):
        motion.render_motion(settings=settings, order=order, scratch=scratch, runner=runner)


def test_output_paths_must_stay_under_the_work_root(tmp_path: Path) -> None:
    root = tmp_path / "work"
    root.mkdir()
    assert motion.confine_to_root(root / "a" / "out.mp4", root) == (root / "a" / "out.mp4").resolve()
    with pytest.raises(ValueError, match="outside_work_root"):
        motion.confine_to_root(root / ".." / "escape.mp4", root)


def test_run_bounded_kills_the_whole_tree_when_time_runs_out() -> None:
    killed: list[int] = []

    class _Slow:
        pid = 4242
        returncode = None
        calls = 0

        def communicate(self, timeout=None):  # noqa: ANN001
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired(cmd="node", timeout=timeout)
            return ("", "")

    with pytest.raises(subprocess.TimeoutExpired):
        motion.run_bounded(["node"], timeout=1, env={}, cwd=Path("."), popen=lambda *a, **k: _Slow(), killer=killed.append)
    assert killed == [4242]
```

`tests/test_motion_host_scripts.py`:

```python
"""모션 다리를 켜고 준비하는 PowerShell 스크립트 둘 (2026-10-08)."""

from __future__ import annotations

import codecs
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
START = ROOT / "scripts" / "start-motion.ps1"
PREPARE = ROOT / "scripts" / "prepare-motion.ps1"


@pytest.mark.parametrize("script", [START, PREPARE])
def test_motion_scripts_are_saved_so_windows_powershell_reads_korean(script: Path) -> None:
    assert script.read_bytes().startswith(codecs.BOM_UTF8)


def test_the_start_script_runs_the_motion_bridge_with_the_repository_python() -> None:
    text = START.read_text(encoding="utf-8-sig")
    assert "[int]$Port = 8202" in text
    assert "host_motion_service.py" in text
    assert ".venv\\Scripts\\python.exe" in text


def test_the_prepare_script_is_bounded_and_quiet() -> None:
    """처음 준비(약 120MB 설치 + 약 270MB 브라우저)는 몇 분 걸린다. 끝없이 매달리면 안 된다."""
    text = PREPARE.read_text(encoding="utf-8-sig")
    assert ".WaitForExit(" in text
    assert "taskkill.exe" in text
    assert "'ci', '--ignore-scripts'" in text
    assert "'browser', 'ensure'" in text
    for name in ("HYPERFRAMES_NO_TELEMETRY", "DO_NOT_TRACK", "HYPERFRAMES_NO_UPDATE_CHECK"):
        assert name in text
    assert "0.8.140" in text
```

- [ ] **Step 2: 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_motion_host_service.py::test_diagnostics_say_ready_when_everything_is_in_place
```

예상: FAIL(수집 단계) `FileNotFoundError: ...scripts\host_motion_service.py`.

- [ ] **Step 3: `scripts/host_motion_service.py`를 쓴다**

모듈 첫머리 문서 문자열은 `host_infographic_service.py`처럼 **왜**를 적는다(8202, 하는 일 둘 `GET /diagnostics`·`POST /render`, 템플릿만 돈다, 네트워크 0건, 한 번에 하나, 결과는 내용(base64)으로 돌려주고 이 컴퓨터에 남기지 않는다). 표준 라이브러리만 쓴다. `sys.path.insert(0, str(Path(__file__).resolve().parent))` 뒤 `from host_bridge_guard import BridgeTokenMissing, check_request, load_bridge_token`.

정해진 것(구현자가 본문을 쓴다):

- `_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent`, `_BRIDGE_ROOT = _REPOSITORY_ROOT / "scripts" / "motion-bridge"`, `_RENDER_LOCK = threading.Lock()`, `_NETWORK_MENTION = re.compile(r"(?i)\bcdn\b|googleapis|jsdelivr|unpkg|https://")`.
- `BridgeSettings.discover`: `node = Path(node) if node else (Path(shutil.which("node")) if shutil.which("node") else None)`, `ffmpeg = shutil.which("ffmpeg")`, `engine_root = _BRIDGE_ROOT / "node_modules" / "hyperframes"`, `templates_root = _BRIDGE_ROOT / "templates"`, `font_path = _REPOSITORY_ROOT / "assets" / "fonts" / "korean" / "NotoSansKR-Variable.ttf"`, `work_root = work_root or Path(tempfile.gettempdir()) / "videobox-motion"`, `cache_root = Path.home() / ".cache" / "hyperframes"`.
- `find_browser_executable(cache_root)`: `sorted((cache_root / "chrome" / "chrome-headless-shell").glob("*/chrome-headless-shell-win64/chrome-headless-shell.exe"))`의 마지막, 없으면 `None`.
- `readiness`: 차례는 `node`(None이거나 파일이 아니면 `node_not_found`) → `ffmpeg` → 엔진(`engine_root/"package.json"`의 `version`이 `PINNED_ENGINE_VERSION`이고 `hyperframes_bin`이 파일이어야 함, 아니면 `engine_not_installed`; JSON을 못 읽어도 같은 값) → 브라우저(`browser_not_prepared`) → `"ready"`.
- `diagnostics_payload`: `settings`가 `None`이면 `(200, {"status": "engine_not_installed", ...})`. 복구 문구(한국어, 다리 로그·진단용):
  - `node_not_found`: `"node를 찾지 못했습니다. Node.js 24를 설치한 뒤 VideoBox를 다시 켜세요."`
  - `ffmpeg_not_found`: `"ffmpeg를 찾지 못했습니다. ffmpeg를 설치한 뒤 VideoBox를 다시 켜세요."`
  - `engine_not_installed`·`browser_not_prepared`: `"모션 도구를 처음 한 번 준비해야 합니다. PowerShell에서 .\\scripts\\prepare-motion.ps1 을 실행하거나 VideoBox를 다시 켜세요(약 400MB, 몇 분)."`
  - `ready`: `None`. 답에는 `node_path`, `engine_version`(읽은 값 또는 `None`), `browser_path`도 싣는다.
- `check_render_request(body)`: Interfaces의 차례·오류 이름 그대로(템플릿 → 모양(`body.get("layout") or "full"`) → 길이(`float()` 실패 → `duration_must_be_a_number`; `math.isfinite`가 아니거나 범위 밖 → `duration_out_of_range`) → 변수가 dict인지 → `json.dumps(variables, ensure_ascii=False).encode("utf-8")` 길이 > `MAXIMUM_VARIABLES_BYTES` → `variables_too_large` → 깊이·글·숫자 검사(`_inspect(value, depth)`: 맨 위 변수 dict가 깊이 1이고 안의 dict·list마다 +1, 깊이 > 3이면 `variables_too_deep` — 막대는 dict(1)→list(2)→dict(3)이라 통과한다; str에 `<`·`>` 또는 `ord(ch) < 32 or ord(ch) == 127`이면 `text_not_allowed`; float가 유한하지 않으면 `number_not_allowed`; str·int·float·bool·None 밖의 값은 `text_not_allowed`)). 통과면 `RenderOrder(template, variables, round(duration, 3), layout)`.
- `motion_data_script(order)`: 정확히 이것이다(이스케이프가 이 Task의 핵심이라 본문을 박는다):

```python
def motion_data_script(order: RenderOrder) -> str:
    """`data.js` 한 줄. ensure_ascii로 한글·U+2028까지 \\u로 바꾸고, 마크업 글자 셋도 바꾼다 --
    다리가 이미 `<`·`>`를 거절하지만 여기서 한 번 더 닫는다(2차 방어)."""
    payload = {"variables": order.variables, "duration": order.duration_sec, "mode": order.layout}
    encoded = (
        json.dumps(payload, ensure_ascii=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return f"window.__VB_MOTION__ = {encoded};\n"
```

- `prepare_composition`: `scratch.mkdir(parents=True, exist_ok=True)`, `shutil.copytree(templates_root / order.template, scratch / "comp")`, `_shared/motion-runtime.js` 복사, `comp/assets/NotoSansKR-Variable.ttf`로 글꼴 복사, `index.html`에서 `__VB_DURATION__` → `_duration_text(order.duration_sec)`(`f"{seconds:.3f}".rstrip("0").rstrip(".")`), `__VB_MODE__` → `order.layout`; 바꾼 뒤 `"__VB_"`가 남아 있으면 `RuntimeError("template_placeholder_left")`; `data.js` 쓰기(utf-8). `comp`를 돌려준다.
- `engine_environment(base, *, browser)`: `dict(base)`에서 `VIDEOBOX_BRIDGE_TOKEN`을 빼고, Global Constraints의 하이퍼프레임 다섯 + `NODE_USE_ENV_PROXY="1"`, `HTTPS_PROXY="http://127.0.0.1:9"`, `NO_PROXY="127.0.0.1,localhost"`, `HYPERFRAMES_BROWSER_PATH=str(browser)`를 넣는다(죽은 프록시는 스파이크가 쓴 2차 방어 그대로 — node가 밖으로 받으려 하면 실패한다).
- `confine_to_root(path, root)`: `resolved = path.resolve()`; `resolved.is_relative_to(root.resolve())`가 아니면 `ValueError("outside_work_root")`.
- `run_bounded`: `popen(arguments, cwd=str(cwd), env=env, stdout=PIPE, stderr=PIPE, text=True, encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))`; `communicate(timeout=timeout)`에서 `TimeoutExpired`면 `(killer or _kill_tree)(process.pid)`, `process.communicate(timeout=10)`(여기서 또 시간이 넘으면 무시), 처음 예외를 다시 던진다. 정상이면 `subprocess.CompletedProcess(arguments, process.returncode, stdout, stderr)`. `_kill_tree(pid)`: 윈도우는 `subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=15)`, 그 밖은 `os.kill(pid, signal.SIGKILL)`(`OSError`는 삼킨다). 크롬 자식까지 끊으려고 `/T`다.
- `render_motion`: `prepare_composition` → `fmt = LAYOUT_FORMATS[order.layout]` → `out = confine_to_root(scratch / f"out.{fmt}", settings.work_root)` → `browser = find_browser_executable(settings.cache_root)`(없으면 `RuntimeError("browser_not_prepared")`) → `arguments = [str(settings.node), str(settings.hyperframes_bin), "render", str(comp), "-o", str(out), "--format", fmt, "--fps", str(FPS), "--frames-cache-dir", str(scratch / "frames")]` → `runner(arguments, timeout=RENDER_TIMEOUT_SECONDS, env=engine_environment(os.environ, browser=browser), cwd=scratch)` → `returncode != 0`이면 `RuntimeError(f"engine_failed: {tail}")`(stderr 또는 stdout 끝 400자) → 파일이 없거나 0바이트면 `RuntimeError("engine_wrote_nothing")` → `RenderedMotion(out, network_mentions)`. `network_mentions`는 **줄 수**다: `sum(1 for line in (stdout + "\n" + stderr).splitlines() if _NETWORK_MENTION.search(line))`(한 줄에 낱말이 여럿 걸려도 1 — 시험이 1을 기대한다). `network_mentions > 0`이면 stderr에 `[motion-bridge] 경고: 바깥 주소를 언급한 줄 N개`를 남긴다.
- `render_request_payload`: 차례 고정 — `settings is None` → 503 `{"error": "motion_engine_not_prepared"}`; `check_render_request` 거절 → 그대로; `readiness != "ready"` → 503 `{"error": "motion_engine_not_prepared", "detail": <값>}`; `lock.acquire(blocking=False)` 실패 → 409 `{"error": "motion_render_busy"}`; 그다음 `try/finally: lock.release()` 안에서 `settings.work_root.mkdir(parents=True, exist_ok=True)`, `tempfile.TemporaryDirectory(prefix="render-", dir=settings.work_root, ignore_cleanup_errors=True)`, 시계 시작(`time.monotonic`), `renderer(settings=…, order=…, scratch=Path(dir))`; `subprocess.TimeoutExpired` → 504 `{"error": "render_timed_out"}`; `RuntimeError`·`OSError`·`ValueError` → 500 `{"error": "render_failed", "detail": str(exc)}`; 바이트 > `MAXIMUM_VIDEO_BYTES` → 500 `render_too_large`; 성공 200(Interfaces의 열쇠들, `elapsed_sec`는 소수 둘째 자리).
- `SAMPLE_VARIABLES`(보통)와 `LONGEST_VARIABLES`(상한까지 꽉 찬 것, Review Focus 2)를 둔다:

```python
SAMPLE_VARIABLES = {
    "bar_compare": {"title": "월 수익 비교: 쿠팡 vs 스마트스토어", "subtitle": "2026년 9월 · 단위 만 원 · 예시", "unit": "만", "bars": [{"label": "쿠팡 로켓그로스", "value": 1280}, {"label": "스마트스토어", "value": 860}, {"label": "자사몰", "value": 430}]},
    "money_counter": {"lead": "첫 달 순매출", "amount": 12345678, "prefix": "₩", "suffix": "", "caption": "광고비 · 수수료 제외 후"},
    "step_list": {"title": "처음 시작하는 3단계", "steps": ["상품 소싱하고 가격 정하기", "상세페이지 올리기", "첫 주문 처리하고 정산받기"]},
}
LONGEST_VARIABLES = {
    "bar_compare": {"title": "가" * 24, "subtitle": "나" * 40, "unit": "만원까지", "bars": [{"label": "다" * 10, "value": 1_000_000_000_000}] + [{"label": "라" * 10, "value": 999_999_999_999.9}] * 4},
    "money_counter": {"lead": "마" * 20, "amount": 1_000_000_000_000, "prefix": "₩", "suffix": "원까지요", "caption": "바" * 30},
    "step_list": {"title": "사" * 24, "steps": ["아" * 24] * 5},
}
```

  (주의: `SAMPLE_VARIABLES["bar_compare"]["title"]`은 24자를 넘는다 — 다리는 글 길이를 안 보고, 길이 상한은 API(Task 3)가 지킨다. 표본은 다리 혼자 시험용이라 괜찮다. Task 7 측정에서는 이 표본을 쓴다.)
- `_Handler(BaseHTTPRequestHandler)`: `server_version = "VideoBoxMotionBridge/1.0"`, 클래스 속성 `settings: BridgeSettings | None = None`, `bridge_token: str = ""`; `log_message`는 `[motion-bridge] ` 접두로 stderr. `_reply`·`_payload`·`_refused`는 그림 다리와 같은 모양(`_refused`는 `check_request(method=self.command, headers=self.headers, port=self.server.server_address[1], expected_token=self.bridge_token)`). `do_GET`: `/diagnostics`만. `do_POST`: `/render`만, 본문을 못 읽으면 400 `unreadable_request`. `build_server(*, port, settings, bridge_token) -> ThreadingHTTPServer`(`(BIND_HOST, port)`).
- `main(argv)`: 인자는 Interfaces 그대로(`--port` 기본은 `VIDEOBOX_MOTION_BRIDGE_PORT` 환경 변수 또는 `DEFAULT_PORT`). `--render-sample`이 있으면 토큰을 읽지 않는다: `readiness`가 `ready`가 아니면 진단 JSON을 찍고 `3`; 아니면 `RenderOrder(key, LONGEST_VARIABLES[key] if --longest else SAMPLE_VARIABLES[key], --duration(기본 6.0), --layout(기본 full))`를 `check_render_request`로 한 번 통과시킨 뒤(표본도 같은 문을 지난다) 작업 뿌리 아래 임시 폴더에서 `render_motion` → `--out`으로 복사(부모 폴더 생성) → JSON 한 줄 → `0`. 서버 모드는 `load_bridge_token(os.environ, _REPOSITORY_ROOT / ".env.container")`(실패 시 stderr 한 줄, `2`), 시작 줄 셋(`listening on http://127.0.0.1:8202`, `node: …`, `준비 상태: <readiness>`), `serve_forever`.

- [ ] **Step 4: 통과를 확인한다(하나)**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_motion_host_service.py::test_diagnostics_say_ready_when_everything_is_in_place
```

예상: PASS. 이어서 파일 전체:

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_motion_host_service.py
```

예상: 전부 통과(30건 안팎).

- [ ] **Step 5: 스크립트 둘을 쓴다(BOM)**

`scripts/start-motion.ps1` — `scripts/start-infographic.ps1`를 그대로 옮기고 바꾼다: 설명(모션 다리, 8202, 하이퍼프레임과 브라우저는 이 컴퓨터에만 있다, `owner-ready.ps1`이 창 없이 띄운다, 처음 준비는 `prepare-motion.ps1`), `[int]$Port = 8202`, 메시지 `"모션 다리가 이미 켜져 있습니다 (127.0.0.1:$Port)."`·`"모션 다리를 켭니다 (127.0.0.1:$Port)."`, `$service = Join-Path $PSScriptRoot 'host_motion_service.py'`.

`scripts/prepare-motion.ps1`:

```powershell
<#
.SYNOPSIS
    설명 모션 도구를 처음 한 번 준비한다(하이퍼프레임 0.8.140 설치 + 그릴 브라우저 받기).

.DESCRIPTION
    약 120MB(설치)와 약 270MB(브라우저, ~/.cache/hyperframes)를 인터넷에서 받는다.
    owner-ready.ps1이 준비가 안 된 것을 보면 이 스크립트를 숨은 창으로 띄운다 --
    VideoBox 켜기를 몇 분씩 붙잡지 않으려고 따로 돈다. 단계마다 시간 상한이 있고,
    넘으면 자식까지 끊고 실패로 끝난다(조용히 매달리지 않는다).
#>
[CmdletBinding()]
param(
    [int]$InstallTimeoutSeconds = 300,
    [int]$BrowserTimeoutSeconds = 900
)

$ErrorActionPreference = 'Stop'
$bridgeRoot = Join-Path $PSScriptRoot 'motion-bridge'
$lock = Join-Path ([System.IO.Path]::GetTempPath()) 'videobox-motion-prepare.lock'

# 같은 준비를 두 번 돌리지 않는다. 30분 넘은 잠금은 죽은 것으로 본다.
if (Test-Path $lock) {
    if (((Get-Date) - (Get-Item $lock).LastWriteTime).TotalMinutes -lt 30) {
        Write-Host "모션 도구를 이미 준비하고 있습니다." -ForegroundColor Yellow
        exit 0
    }
    Remove-Item $lock -Force
}
New-Item -ItemType File -Path $lock -Force | Out-Null

function Invoke-Bounded([string]$File, [string[]]$Arguments, [int]$Seconds, [string]$Label) {
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -WorkingDirectory $bridgeRoot -NoNewWindow -PassThru
    if (-not $process.WaitForExit($Seconds * 1000)) {
        & taskkill.exe /PID $process.Id /T /F | Out-Null
        throw "$Label 이(가) $Seconds 초 안에 끝나지 않아 멈췄습니다. 인터넷 연결을 확인한 뒤 다시 실행하세요."
    }
    if ($process.ExitCode -ne 0) {
        throw "$Label 에 실패했습니다(종료 코드 $($process.ExitCode))."
    }
}

try {
    $node = (Get-Command node -ErrorAction SilentlyContinue).Source
    $npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
    if (-not $node -or -not $npm) { throw "node를 찾지 못했습니다. Node.js 24를 설치한 뒤 다시 실행하세요." }
    $env:HYPERFRAMES_NO_TELEMETRY = '1'
    $env:DO_NOT_TRACK = '1'
    $env:HYPERFRAMES_SKIP_SKILLS = '1'
    $env:HYPERFRAMES_NO_UPDATE_CHECK = '1'
    $env:HYPERFRAMES_NO_AUTO_INSTALL = '1'

    $installed = Join-Path $bridgeRoot 'node_modules\hyperframes\package.json'
    $version = $null
    if (Test-Path $installed) { $version = (Get-Content -LiteralPath $installed -Raw | ConvertFrom-Json).version }
    if ($version -ne '0.8.140') {
        Write-Host "모션 도구를 처음 한 번 설치합니다(약 120MB)." -ForegroundColor Cyan
        Invoke-Bounded $npm @('ci', '--ignore-scripts', '--no-audit', '--no-fund') $InstallTimeoutSeconds '모션 도구 설치'
    }
    Write-Host "모션을 그릴 브라우저를 처음 한 번 받습니다(약 270MB, 몇 분)." -ForegroundColor Cyan
    $cli = Join-Path $bridgeRoot 'node_modules\hyperframes\bin\hyperframes.mjs'
    Invoke-Bounded $node @($cli, 'browser', 'ensure') $BrowserTimeoutSeconds '브라우저 받기'
    Write-Host "모션 도구 준비가 끝났습니다." -ForegroundColor Green
    exit 0
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
} finally {
    Remove-Item $lock -Force -ErrorAction SilentlyContinue
}
```

두 파일을 BOM·CRLF로 다시 저장한다(Write 도구는 BOM 없이 쓴다):

```powershell
foreach ($name in 'start-motion.ps1', 'prepare-motion.ps1') {
  $path = Join-Path (Resolve-Path .\scripts) $name
  $text = [IO.File]::ReadAllText($path) -replace "`r?`n", "`r`n"
  [IO.File]::WriteAllText($path, $text, [Text.UTF8Encoding]::new($true))
}
```

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_motion_host_scripts.py
```

예상: 4건 통과.

- [ ] **Step 6: 문지기 배선 시험에 넷째 다리를 더한다** — `tests/test_host_bridge_guard.py`

앵커 `infographic = _load("videobox_host_infographic_service_guard_test", "host_infographic_service.py")` 다음 줄에:

```python
motion = _load("videobox_host_motion_service_guard_test", "host_motion_service.py")
```

앵커 `_INFOGRAPHIC_HANDLER = type("InfographicHandler", (infographic._Handler,), {"bridge_token": TOKEN, "browser": None})` 다음 줄에:

```python
_MOTION_HANDLER = type("MotionHandler", (motion._Handler,), {"bridge_token": TOKEN, "settings": None})
```

`_POSTS` 목록의 `    (_INFOGRAPHIC_HANDLER, "/render", 8201),` 다음 줄에 `    (_MOTION_HANDLER, "/render", 8202),`를 넣는다. 파일 끝에 시험 하나:

```python
def test_the_motion_bridge_needs_the_token_even_to_say_how_it_is() -> None:
    status, payload = _call(_MOTION_HANDLER, method="GET", path="/diagnostics", port=8202, headers={"Host": "127.0.0.1:8202"})
    assert (status, payload) == (401, {"error": "bridge_token_required"})
    status, payload = _call(
        _MOTION_HANDLER, method="GET", path="/diagnostics", port=8202,
        headers={"Host": "host.docker.internal:8202", guard.TOKEN_HEADER: TOKEN},
    )
    assert status == 200
    assert payload["status"] == "engine_not_installed"
```

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_host_bridge_guard.py
```

예상: 전부 통과(넷째 다리 매개변수 셋 + 새 시험 하나 포함). 첫머리 문서 문자열의 "목소리(8199)·캡컷(8200)·그림(8201) 다리"를 "…·모션(8202) 다리"로 고친다.

- [ ] **Step 7: 커밋**

```bash
git add scripts/host_motion_service.py scripts/start-motion.ps1 scripts/prepare-motion.ps1 tests/test_motion_host_service.py tests/test_motion_host_scripts.py tests/test_host_bridge_guard.py
git commit -m "$(cat <<'EOF'
feat(motion): 모션 다리(8202) -- 템플릿만 그리고, 한 번에 하나, 시간 상한, 네트워크 0건

문지기(Host·토큰·JSON)를 그림 다리와 같이 쓴다. 준비 전이면 렌더 안에서 브라우저를
받지 않고 503으로 말한다. 처음 준비는 prepare-motion.ps1이 단계마다 시간 상한을 두고 한다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 8: 역방향 — 진짜 하이퍼프레임으로 셋 다 그린다(죽은 프록시 그대로)**

```bash
mkdir -p artifacts/motion-step2
for key in bar_compare money_counter step_list; do
  .venv/Scripts/python.exe scripts/host_motion_service.py --render-sample $key --duration 6 --out artifacts/motion-step2/$key-full.mp4
  .venv/Scripts/python.exe scripts/host_motion_service.py --render-sample $key --duration 6 --layout overlay --out artifacts/motion-step2/$key-overlay.webm
  .venv/Scripts/python.exe scripts/host_motion_service.py --render-sample $key --duration 6 --longest --out artifacts/motion-step2/$key-longest.mp4
done
```

예상: 9줄, 각 줄 `network_mentions: 0`, `elapsed_sec` 10~25, `byte_size` 수십 KB~1.5MB. 하나라도 실패하면 출력의 `engine_failed:` 끝부분을 그대로 적고 멈춘다(짐작해서 템플릿을 고치지 않는다 — 특히 `hyperframes.json`이나 `.clip` 구조를 탓하는 메시지면 보고한다).

- [ ] **Step 9: 동작 — ffprobe와 프레임으로 잰다**

```bash
for f in artifacts/motion-step2/*.mp4; do ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,pix_fmt,width,height,r_frame_rate:format=duration -of csv=p=0 "$f"; done
for f in artifacts/motion-step2/*.webm; do ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height:stream_tags=alpha_mode -of csv=p=0 "$f"; done
for key in bar_compare money_counter step_list; do
  ffmpeg -hide_banner -loglevel error -y -ss 5.5 -i artifacts/motion-step2/$key-full.mp4 -frames:v 1 artifacts/motion-step2/$key-full.png
  ffmpeg -hide_banner -loglevel error -y -ss 5.5 -i artifacts/motion-step2/$key-longest.mp4 -frames:v 1 artifacts/motion-step2/$key-longest.png
  ffmpeg -hide_banner -loglevel error -y -c:v libvpx-vp9 -ss 5.5 -i artifacts/motion-step2/$key-overlay.webm -frames:v 1 artifacts/motion-step2/$key-overlay.png
done
.venv/Scripts/python.exe -c "
from PIL import Image
for key in ('bar_compare','money_counter','step_list'):
    im = Image.open(f'artifacts/motion-step2/{key}-overlay.png').convert('RGBA')
    print(key, 'corner', im.getpixel((5,5)), 'card', im.getpixel((960,40+30)), 'size', im.size)
"
```

예상: mp4는 `h264,yuv420p,1920,1080,30/1,6.0xxxxx`(길이 6.000±0.05). webm은 `vp9,1920,1080,1`(알파 표시). 겹 프레임: 모서리 `(0,0,0,0)`(완전 투명), 카드 자리(가운데 위쪽, y=70) 알파 200 이상(0.86×255≈219). PIL이 없으면 `.venv/Scripts/python.exe -m pip show pillow`로 확인하고, 없으면 `ffmpeg -c:v libvpx-vp9 -i … -vf "crop=1:1:5:5,format=rgba" -f rawvideo -` 로 4바이트를 읽는다.

PNG 아홉 장을 Read 도구로 **눈으로 본다**: 한글이 또렷한가(₩·쉼표 포함), 가장 긴 글이 판 밖으로 나가지 않는가(제목 24자, 이름 10자, 값 `1,000,000,000,000만원까지`, 단계 24자 다섯 줄), 막대가 화면 오른쪽을 넘지 않는가. 넘는 것이 있으면 그 템플릿 CSS 크기만 줄이고(색은 바꾸지 않는다) Step 8~9를 다시 한다 — 그 수정은 같은 커밋에 `git commit --amend` 하지 말고 새 커밋 `fix(motion): …`로 남긴다.

- [ ] **Step 10: 검증 넷 마무리**

- 갭: Step 1~9 대조. 컨테이너 쪽 호출은 Task 3·4, 화면은 Task 6.
- 배선: `grep -n "check_request(" scripts/host_motion_service.py` → `_refused` 안 1줄. `grep -c "_MOTION_HANDLER" tests/test_host_bridge_guard.py` → 3 이상.
- 실측 숫자(9개 렌더 시간·크기, 알파 화소)는 Task 8 인계에 옮긴다. `artifacts/`는 gitignore 대상이라 커밋하지 않는다.

---

### Task 3: 컨테이너 쪽 — 템플릿 목록·엄격한 변수 검사·`MotionHostBridge`·`MotionService`

**Files:**
- Create: `packages/core-engine/src/videobox_core_engine/motion_templates.py`
- Create: `packages/core-engine/src/videobox_core_engine/motion_host_bridge.py`
- Create: `packages/core-engine/src/videobox_core_engine/motion_service.py`
- Test: `tests/test_motion_templates.py`, `tests/test_motion_host_bridge.py`, `tests/test_motion_service.py`(새 파일 셋)

**Interfaces:**
- Consumes: 다리 HTTP 계약(Task 2 Interfaces), `videobox_provider_interfaces.host_bridge_auth.bridge_request_headers()`, `LibraryIngestService.ingest(*, media_type, source, filename, idempotency_key, provenance)`(돌려주는 dict의 `library_asset_id`), `videobox_core_engine.infographic_service._file_stem(title) -> str`(그대로 import해 쓴다 — 같은 파일 이름 규칙).
- Produces:
  - `motion_templates.py`: `MOTION_TEMPLATE_KEYS = ("bar_compare", "money_counter", "step_list")`, `MIN_MOTION_DURATION_SEC = 3.0`, `MAX_MOTION_DURATION_SEC = 30.0`, `MOTION_LAYOUTS = ("full", "overlay")`, `check_safe_text(value: str) -> str`, 모델 `BarItem`·`BarCompareVariables`·`MoneyCounterVariables`·`StepListVariables`, `@dataclass(frozen=True) MotionTemplate(key, korean_name, description, default_duration_sec, variables_model, limits: Mapping[str, int])`, `MOTION_TEMPLATES: tuple[MotionTemplate, ...]`, `class MotionTemplateUnknown(KeyError)`, `class MotionVariablesInvalid(ValueError)`(속성 `problems: tuple[str, ...]`), `resolve_motion_template(key: str) -> MotionTemplate`, `parse_motion_variables(template_key: str, variables: Mapping[str, Any]) -> BaseModel`, `motion_default_title(template_key: str, parsed: BaseModel) -> str`.
  - `motion_host_bridge.py`: `BRIDGE_PORT = 8202`, `ENVIRONMENT_VARIABLE = "VIDEOBOX_MOTION_BRIDGE_URL"`, `BRIDGE_TIMEOUT_SECONDS = 240`, `MotionHostBridgeUnavailable`, `MotionHostBridgeTimedOut`, `MotionHostBridgeRefused(status: int, error: str, detail: str = "")`(속성 `status`·`error`), `@dataclass MotionClip(video_bytes: bytes, format: str, elapsed_sec: float)`, `@dataclass(slots=True) MotionHostBridge(base_url="http://127.0.0.1:8202", timeout_seconds=BRIDGE_TIMEOUT_SECONDS, http_client=None)`(+ `from_environment`, `diagnose() -> dict`, `render(*, template, variables: dict, duration_sec: float, layout: str) -> MotionClip`).
  - `motion_service.py`: `class MotionUnavailable(RuntimeError)`(속성 `reason: str`, `detail: str`, `problems: tuple[str, ...]`), `@dataclass MadeMotion(video_bytes, template_key, title, duration_sec, layout, format, elapsed_sec, library_asset_id: str | None = None, library_error: str | None = None)`, `@dataclass(slots=True) MotionService(bridge: MotionHostBridge | None = None, library_ingest: Any = None, _scratch_factory=tempfile.TemporaryDirectory)`(+ `make(*, template_key: str, variables: Mapping[str, Any], duration_sec: float, layout: str = "full", title: str | None = None) -> MadeMotion`). 이유(reason) 이름: `motion_template_unknown`, `motion_variables_invalid`, `motion_bridge_not_configured`, `motion_bridge_not_running`, `motion_engine_not_prepared`, `motion_busy`, `motion_took_too_long`, `motion_render_failed`.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`tests/test_motion_templates.py`:

```python
"""설명 모션 템플릿 목록과 변수 검사 -- 들어오는 것은 숫자·글뿐이고, 판에 맞는 길이만 받는다."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from videobox_core_engine.motion_templates import (
    MAX_MOTION_DURATION_SEC,
    MIN_MOTION_DURATION_SEC,
    MOTION_TEMPLATE_KEYS,
    MOTION_TEMPLATES,
    MotionTemplateUnknown,
    MotionVariablesInvalid,
    motion_default_title,
    parse_motion_variables,
    resolve_motion_template,
)

ROOT = Path(__file__).resolve().parents[1]
GOOD = {
    "bar_compare": {"title": "월 수익 비교", "unit": "만", "bars": [{"label": "쿠팡", "value": 1280}, {"label": "자사몰", "value": 430}]},
    "money_counter": {"lead": "첫 달 순매출", "amount": 12345678},
    "step_list": {"title": "처음 시작하는 3단계", "steps": ["소싱", "상세페이지", "정산"]},
}


def _problems(key: str, variables: dict) -> str:
    with pytest.raises(MotionVariablesInvalid) as caught:
        parse_motion_variables(key, variables)
    return " / ".join(caught.value.problems)


def test_three_templates_live_in_one_place() -> None:
    assert tuple(t.key for t in MOTION_TEMPLATES) == MOTION_TEMPLATE_KEYS == ("bar_compare", "money_counter", "step_list")
    assert [t.korean_name for t in MOTION_TEMPLATES] == ["막대 비교", "금액 카운터", "단계 목록"]


def test_the_catalog_matches_the_bridge_and_the_template_folders() -> None:
    """파이썬 목록·다리·템플릿 폴더가 따로 놀면 화면에 있는 종류가 다리에서 400이 된다."""
    spec = importlib.util.spec_from_file_location("motion_bridge_catalog_check", ROOT / "scripts" / "host_motion_service.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["motion_bridge_catalog_check"] = module
    spec.loader.exec_module(module)
    assert module.TEMPLATE_KEYS == MOTION_TEMPLATE_KEYS
    assert (module.MIN_DURATION_SEC, module.MAX_DURATION_SEC) == (MIN_MOTION_DURATION_SEC, MAX_MOTION_DURATION_SEC)
    for key in MOTION_TEMPLATE_KEYS:
        assert (ROOT / "scripts" / "motion-bridge" / "templates" / key / "index.html").is_file()


@pytest.mark.parametrize("key", MOTION_TEMPLATE_KEYS)
def test_a_normal_request_is_accepted(key: str) -> None:
    parsed = parse_motion_variables(key, GOOD[key])
    assert parsed.model_dump(mode="json")


@pytest.mark.parametrize(
    ("key", "variables"),
    [
        ("bar_compare", {**GOOD["bar_compare"], "title": "<b>굵게</b>"}),
        ("bar_compare", {**GOOD["bar_compare"], "bars": [{"label": "<script>", "value": 1}, {"label": "b", "value": 2}]}),
        ("money_counter", {**GOOD["money_counter"], "caption": "a>b"}),
        ("step_list", {**GOOD["step_list"], "steps": ["정상", "<img src=x onerror=alert(1)>"]}),
    ],
)
def test_markup_is_refused_in_every_text(key: str, variables: dict) -> None:
    assert "< > 기호" in _problems(key, variables)


def test_control_characters_are_refused() -> None:
    assert "쓸 수 없는 글자" in _problems("step_list", {"title": "줄\n바꿈", "steps": ["a", "b"]})


def test_korean_text_longer_than_the_board_is_refused() -> None:
    assert "제목: 24자까지" in _problems("bar_compare", {**GOOD["bar_compare"], "title": "가" * 25})
    assert "이름: 10자까지" in _problems("bar_compare", {**GOOD["bar_compare"], "bars": [{"label": "나" * 11, "value": 1}, {"label": "b", "value": 2}]})


@pytest.mark.parametrize(("key", "variables", "expected"), [
    ("bar_compare", {**GOOD["bar_compare"], "bars": [{"label": "a", "value": 1}]}, "막대: 2개 이상"),
    ("bar_compare", {**GOOD["bar_compare"], "bars": [{"label": "a", "value": 1}] * 6}, "막대: 5개까지"),
    ("step_list", {"title": "t", "steps": ["a"] * 6}, "단계: 5개까지"),
])
def test_counts_are_bounded(key: str, variables: dict, expected: str) -> None:
    assert expected in _problems(key, variables)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 1e13])
def test_bar_values_must_be_real_numbers_in_range(value: float) -> None:
    assert "값" in _problems("bar_compare", {**GOOD["bar_compare"], "bars": [{"label": "a", "value": value}, {"label": "b", "value": 2}]})


@pytest.mark.parametrize("amount", [-1, 10**12 + 1, 1.5])
def test_money_must_be_a_whole_amount_in_range(amount) -> None:
    assert "금액" in _problems("money_counter", {"amount": amount})


def test_unknown_fields_are_refused() -> None:
    assert "알 수 없는 칸" in _problems("step_list", {**GOOD["step_list"], "script": "alert(1)"})


def test_all_zero_bars_say_so() -> None:
    assert "0보다 커야" in _problems("bar_compare", {"title": "t", "bars": [{"label": "a", "value": 0}, {"label": "b", "value": 0}]})


def test_an_unknown_template_is_refused() -> None:
    with pytest.raises(MotionTemplateUnknown):
        resolve_motion_template("free_form")


def test_the_default_title_comes_from_what_was_written() -> None:
    assert motion_default_title("bar_compare", parse_motion_variables("bar_compare", GOOD["bar_compare"])) == "월 수익 비교"
    assert motion_default_title("money_counter", parse_motion_variables("money_counter", GOOD["money_counter"])) == "첫 달 순매출"
    assert motion_default_title("money_counter", parse_motion_variables("money_counter", {"amount": 5})) == "금액 카운터"
```

`tests/test_motion_host_bridge.py` — `tests/test_infographic_host_bridge.py`의 `_client`·`_raising_client` 도우미를 같은 모양으로 둔다(`_LOCAL = "http://127.0.0.1:8202"`):

```python
"""컨테이너에서 이 컴퓨터의 모션 다리(8202)를 부르는 쪽."""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.error import HTTPError, URLError

import pytest

from videobox_core_engine.motion_host_bridge import (
    BRIDGE_PORT,
    BRIDGE_TIMEOUT_SECONDS,
    MotionHostBridge,
    MotionHostBridgeRefused,
    MotionHostBridgeTimedOut,
    MotionHostBridgeUnavailable,
)

_LOCAL = f"http://127.0.0.1:{BRIDGE_PORT}"
ORDER = {"template": "bar_compare", "variables": {"title": "t"}, "duration_sec": 6.0, "layout": "full"}


def _client(reply: dict[str, Any], *, seen: list | None = None):
    def client(request, timeout):  # noqa: ANN001
        if seen is not None:
            seen.append((request, timeout))
        return json.dumps(reply).encode("utf-8")
    return client


def _raising_client(error: BaseException):
    def client(request, timeout):  # noqa: ANN001, ARG001
        raise error
    return client


def _http_error(code: int, body: dict) -> HTTPError:
    import io
    return HTTPError(_LOCAL, code, "x", {}, io.BytesIO(json.dumps(body).encode("utf-8")))  # type: ignore[arg-type]


@pytest.mark.parametrize("base_url", [
    f"https://127.0.0.1:{BRIDGE_PORT}", "http://example.com:8202", "http://127.0.0.1:8201",
    f"http://127.0.0.1:{BRIDGE_PORT}/x", f"http://user:pw@127.0.0.1:{BRIDGE_PORT}",
])
def test_the_bridge_refuses_to_call_anywhere_but_this_computer(base_url: str) -> None:
    with pytest.raises(MotionHostBridgeRefused):
        MotionHostBridge(base_url=base_url, http_client=_client({})).diagnose()


@pytest.mark.parametrize("base_url", [_LOCAL, f"http://host.docker.internal:{BRIDGE_PORT}"])
def test_the_bridge_allows_this_computer_and_the_container_address(base_url: str) -> None:
    assert MotionHostBridge(base_url=base_url, http_client=_client({"status": "ready"})).diagnose() == {"status": "ready"}


def test_the_bridge_is_off_when_nobody_configured_an_address() -> None:
    assert MotionHostBridge.from_environment({}) is None
    assert MotionHostBridge.from_environment({"VIDEOBOX_MOTION_BRIDGE_URL": _LOCAL}).base_url == _LOCAL


def test_render_returns_the_bytes_the_host_made_and_waits_long_enough() -> None:
    seen: list = []
    reply = {"video_base64": base64.b64encode(b"MP4").decode(), "format": "mp4", "elapsed_sec": 14.2}
    clip = MotionHostBridge(http_client=_client(reply, seen=seen)).render(**ORDER)
    assert (clip.video_bytes, clip.format, clip.elapsed_sec) == (b"MP4", "mp4", 14.2)
    request, timeout = seen[0]
    assert timeout == BRIDGE_TIMEOUT_SECONDS
    assert json.loads(request.data.decode("utf-8")) == ORDER


@pytest.mark.parametrize("reply", [{}, {"video_base64": "!!!", "format": "mp4"}, {"video_base64": "", "format": "mp4"}, {"video_base64": "TVA0", "format": "gif"}])
def test_a_reply_without_a_usable_video_is_a_refusal(reply: dict) -> None:
    with pytest.raises(MotionHostBridgeRefused):
        MotionHostBridge(http_client=_client(reply)).render(**ORDER)


@pytest.mark.parametrize(("code", "error"), [(409, "motion_render_busy"), (503, "motion_engine_not_prepared"), (400, "text_not_allowed")])
def test_a_refusal_carries_the_bridges_own_reason(code: int, error: str) -> None:
    with pytest.raises(MotionHostBridgeRefused) as caught:
        MotionHostBridge(http_client=_raising_client(_http_error(code, {"error": error}))).render(**ORDER)
    assert (caught.value.status, caught.value.error) == (code, error)


def test_a_bridge_nobody_switched_on_is_unavailable() -> None:
    with pytest.raises(MotionHostBridgeUnavailable):
        MotionHostBridge(http_client=_raising_client(URLError("connection refused"))).render(**ORDER)


@pytest.mark.parametrize("error", [TimeoutError("timed out"), URLError(TimeoutError("timed out"))])
def test_waiting_too_long_is_its_own_answer(error: BaseException) -> None:
    with pytest.raises(MotionHostBridgeTimedOut):
        MotionHostBridge(http_client=_raising_client(error)).render(**ORDER)


def test_the_bridge_token_rides_along(monkeypatch) -> None:
    from videobox_provider_interfaces.host_bridge_auth import TOKEN_ENV, TOKEN_HEADER

    monkeypatch.setenv(TOKEN_ENV, "m" * 43)
    seen: list = []
    MotionHostBridge(http_client=_client({"status": "ready"}, seen=seen)).diagnose()
    assert seen[0][0].get_header(TOKEN_HEADER.capitalize()) == "m" * 43
```

`tests/test_motion_service.py`:

```python
"""모션 한 편 -- 고르고·검사하고·다리에 맡기고·자료실에 넣는다."""

from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

from videobox_core_engine.motion_host_bridge import (
    MotionClip,
    MotionHostBridgeRefused,
    MotionHostBridgeTimedOut,
    MotionHostBridgeUnavailable,
)
from videobox_core_engine.motion_service import MotionService, MotionUnavailable
from videobox_domain_models.library_assets import LibraryMediaType

BAR = {"title": "월 수익 비교", "unit": "만", "bars": [{"label": "쿠팡", "value": 1280}, {"label": "자사몰", "value": 430}]}


class _Bridge:
    def __init__(self, clip: MotionClip | None = None, error: BaseException | None = None) -> None:
        self.clip = clip or MotionClip(video_bytes=b"MP4-1", format="mp4", elapsed_sec=12.5)
        self.error = error
        self.calls: list[dict] = []

    def render(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.clip


class _Library:
    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails
        self.calls: list[dict] = []

    def ingest(self, *, media_type, source, filename, idempotency_key, provenance):
        if self.fails:
            raise RuntimeError("자리 없음")
        self.calls.append({"media_type": media_type, "bytes": Path(source).read_bytes(), "filename": filename, "key": idempotency_key, "provenance": provenance})
        return {"library_asset_id": "user_motion1"}


@contextlib.contextmanager
def _scratch(prefix: str, tmp_path: Path):
    del prefix
    yield tmp_path


def _service(bridge, library=None, *, tmp_path: Path) -> MotionService:
    return MotionService(bridge=bridge, library_ingest=library, _scratch_factory=lambda prefix: _scratch(prefix, tmp_path))


def test_a_made_motion_goes_into_the_library_as_a_video(tmp_path: Path) -> None:
    bridge, library = _Bridge(), _Library()
    made = _service(bridge, library, tmp_path=tmp_path).make(template_key="bar_compare", variables=BAR, duration_sec=6.0)
    assert bridge.calls == [{"template": "bar_compare", "variables": {"title": "월 수익 비교", "subtitle": "", "unit": "만", "bars": [{"label": "쿠팡", "value": 1280.0}, {"label": "자사몰", "value": 430.0}]}, "duration_sec": 6.0, "layout": "full"}]
    call = library.calls[0]
    assert call["media_type"] == LibraryMediaType.BROLL
    assert call["bytes"] == b"MP4-1"
    assert call["filename"] == "월-수익-비교.mp4"
    assert call["key"].startswith("motion:")
    assert call["provenance"]["source_kind"] == "generated_motion"
    assert call["provenance"]["template"] == "bar_compare"
    assert (made.library_asset_id, made.title, made.format, made.elapsed_sec) == ("user_motion1", "월 수익 비교", "mp4", 12.5)


def test_a_library_failure_keeps_the_motion_and_says_why(tmp_path: Path) -> None:
    made = _service(_Bridge(), _Library(fails=True), tmp_path=tmp_path).make(template_key="bar_compare", variables=BAR, duration_sec=6.0)
    assert (made.library_asset_id, made.library_error, made.video_bytes) == (None, "RuntimeError", b"MP4-1")


def test_bad_variables_never_reach_the_bridge(tmp_path: Path) -> None:
    bridge = _Bridge()
    with pytest.raises(MotionUnavailable) as caught:
        _service(bridge, tmp_path=tmp_path).make(template_key="bar_compare", variables={"title": "<b>x</b>", "bars": []}, duration_sec=6.0)
    assert caught.value.reason == "motion_variables_invalid"
    assert caught.value.problems
    assert bridge.calls == []


@pytest.mark.parametrize(("duration", "layout"), [(2.0, "full"), (31.0, "full"), (6.0, "mov")])
def test_length_and_look_are_checked_here_too(tmp_path: Path, duration: float, layout: str) -> None:
    with pytest.raises(MotionUnavailable) as caught:
        _service(_Bridge(), tmp_path=tmp_path).make(template_key="step_list", variables={"title": "t", "steps": ["a", "b"]}, duration_sec=duration, layout=layout)
    assert caught.value.reason == "motion_variables_invalid"


def test_an_unknown_template_is_its_own_reason(tmp_path: Path) -> None:
    with pytest.raises(MotionUnavailable) as caught:
        _service(_Bridge(), tmp_path=tmp_path).make(template_key="free_form", variables={}, duration_sec=6.0)
    assert caught.value.reason == "motion_template_unknown"


def test_no_bridge_says_so(tmp_path: Path) -> None:
    with pytest.raises(MotionUnavailable) as caught:
        MotionService(bridge=None).make(template_key="bar_compare", variables=BAR, duration_sec=6.0)
    assert caught.value.reason == "motion_bridge_not_configured"


@pytest.mark.parametrize(("error", "reason"), [
    (MotionHostBridgeUnavailable("off"), "motion_bridge_not_running"),
    (MotionHostBridgeTimedOut("slow"), "motion_took_too_long"),
    (MotionHostBridgeRefused(409, "motion_render_busy"), "motion_busy"),
    (MotionHostBridgeRefused(503, "motion_engine_not_prepared"), "motion_engine_not_prepared"),
    (MotionHostBridgeRefused(504, "render_timed_out"), "motion_took_too_long"),
    (MotionHostBridgeRefused(500, "render_failed", "engine_failed: boom"), "motion_render_failed"),
])
def test_each_bridge_failure_gets_its_own_reason(tmp_path: Path, error: BaseException, reason: str) -> None:
    with pytest.raises(MotionUnavailable) as caught:
        _service(_Bridge(error=error), tmp_path=tmp_path).make(template_key="bar_compare", variables=BAR, duration_sec=6.0)
    assert caught.value.reason == reason
```

- [ ] **Step 2: 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_motion_templates.py::test_three_templates_live_in_one_place
```

예상: FAIL `ModuleNotFoundError: No module named 'videobox_core_engine.motion_templates'`.

- [ ] **Step 3: `motion_templates.py`를 쓴다**

정해진 값(본문은 구현자가 쓴다; 문서 문자열에 "왜"를 적는다 — 판에 맞는 글 길이, 모델이 코드를 안 쓴다, 3단계 유진도 이 함수를 그대로 쓴다):

- `check_safe_text(value)`: `<`·`>`가 있으면 `ValueError("text_has_markup")`, `unicodedata.category(ch)`가 `Cc`·`Cf`·`Cs`인 글자가 있으면 `ValueError("text_has_control")`, 아니면 그대로.
- `_text(max_length, *, min_length=0)` = `Annotated[str, StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length), AfterValidator(check_safe_text)]`.
- 모델은 모두 `model_config = ConfigDict(extra="forbid")`:
  - `BarItem`: `label: _text(10, min_length=1)`, `value: float = Field(ge=0, le=1e12, allow_inf_nan=False)`.
  - `BarCompareVariables`: `title: _text(24, min_length=1)`, `subtitle: _text(40) = ""`, `unit: _text(4) = ""`, `bars: list[BarItem] = Field(min_length=2, max_length=5)`, `model_validator(mode="after")`: 모든 값이 0이면 `ValueError("bars_all_zero")`.
  - `MoneyCounterVariables`: `lead: _text(20) = ""`, `amount: int = Field(ge=0, le=10**12)`, `prefix: Literal["₩", "$", ""] = "₩"`, `suffix: _text(4) = ""`, `caption: _text(30) = ""`.
  - `StepListVariables`: `title: _text(24, min_length=1)`, `steps: list[_text(24, min_length=1)] = Field(min_length=2, max_length=5)`.
- `MOTION_TEMPLATES`:

| key | korean_name | description | default_duration_sec | limits |
|---|---|---|---|---|
| `bar_compare` | `막대 비교` | `숫자 몇 개를 막대로 견줘요` | 6.0 | `{"title": 24, "subtitle": 40, "unit": 4, "label": 10, "min_items": 2, "max_items": 5}` |
| `money_counter` | `금액 카운터` | `금액이 0부터 올라가요` | 5.0 | `{"lead": 20, "suffix": 4, "caption": 30}` |
| `step_list` | `단계 목록` | `순서를 하나씩 보여 줘요` | 6.0 | `{"title": 24, "step": 24, "min_items": 2, "max_items": 5}` |

- `parse_motion_variables`: `resolve_motion_template`(없으면 `MotionTemplateUnknown(key)`) → `model_validate(dict(variables))` → `ValidationError`면 `MotionVariablesInvalid(problems)`. 문제 문장 하나는 `f"{label}: {message}"`. `label`은 오류 `loc`에서 **마지막 문자열 칸**을 표로 바꾼다 — `{"title": "제목", "subtitle": "작은 설명", "unit": "단위", "bars": "막대", "label": "이름", "value": "값", "lead": "위 문구", "amount": "금액", "prefix": "기호", "suffix": "뒤에 붙일 말", "caption": "아래 문구", "steps": "단계"}`(없으면 `"내용"`). `message`는 `type`으로:
  - `string_too_long` → `f"{ctx['max_length']}자까지 써요"`; `string_too_short`·`missing` → `"적어 주세요"`
  - `too_long` → `f"{ctx['max_length']}개까지예요"`; `too_short` → `f"{ctx['min_length']}개 이상 필요해요"`
  - `value_error`이고 msg에 `text_has_markup` → `"< > 기호는 쓸 수 없어요"`; `text_has_control` → `"쓸 수 없는 글자가 있어요"`; `bars_all_zero` → 라벨을 `"막대"`로 두고 `"하나는 0보다 커야 해요"`
  - `extra_forbidden` → 라벨 없이 `"알 수 없는 칸이 있어요"`(문장 전체가 이것)
  - `literal_error` → `"다시 골라 주세요"`; 그 밖(`greater_than_equal`, `less_than_equal`, `finite_number`, `int_from_float`, `int_parsing`, `float_parsing` 등) → `"숫자를 다시 확인해 주세요"`
  - 같은 문장은 한 번만, 들어온 차례대로 `tuple`.
- `motion_default_title`: `bar_compare`·`step_list` → `title`; `money_counter` → `lead` 또는 `caption` 또는 `"금액 카운터"`.

- [ ] **Step 4: 통과를 확인한다(하나 → 파일)**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_motion_templates.py::test_three_templates_live_in_one_place
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_motion_templates.py
```

예상: PASS, 그다음 전부 통과.

- [ ] **Step 5: 부르는 쪽 둘의 RED를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_motion_host_bridge.py::test_the_bridge_is_off_when_nobody_configured_an_address
```

예상: FAIL `ModuleNotFoundError: ...motion_host_bridge`.

- [ ] **Step 6: `motion_host_bridge.py`를 쓴다**

`infographic_host_bridge.py`를 **부분 이식**한다(`_NoRedirect`, `_endpoint` 검사, `_request`의 헤더·리다이렉트 금지·JSON 해석). 바뀌는 곳만:
- `_ALLOWED_HOSTS = frozenset({"127.0.0.1", "host.docker.internal"})`, 포트 `BRIDGE_PORT = 8202`, 오류 문구 속 이름 `Motion bridge`.
- `_request`: `HTTPError` → 본문 JSON의 `error`(없으면 `""`)를 읽어 `MotionHostBridgeRefused(exc.code, error, detail[:300])`. 그보다 먼저 `except TimeoutError` → `MotionHostBridgeTimedOut`. `URLError`는 `isinstance(exc.reason, TimeoutError)`면 `MotionHostBridgeTimedOut`, 아니면 `MotionHostBridgeUnavailable`. `OSError` → `Unavailable`. 답이 JSON dict가 아니면 `MotionHostBridgeRefused(200, "unreadable_reply")`. 클래스 이름 `class _NoRedirect`의 HTTPError 문구만 바꾼다.
- `MotionHostBridgeRefused.__init__(self, status: int, error: str, detail: str = "")`: `super().__init__(f"Motion bridge refused ({status}): {error} {detail}".strip())`.
- `render`: 본문 `{"template", "variables", "duration_sec", "layout"}`로 `POST /render`. `video_base64`가 비거나 `base64.b64decode(..., validate=True)`가 실패·빈 바이트이거나 `format`이 `"mp4"`·`"webm"`가 아니면 `MotionHostBridgeRefused(200, "no_video")`. `elapsed_sec`는 `float(reply.get("elapsed_sec") or 0.0)`.
- `timeout_seconds` 기본값 `BRIDGE_TIMEOUT_SECONDS`(240 — 다리 상한 180 + 여유, nginx 600 안).

- [ ] **Step 7: `motion_service.py`를 쓴다**

`infographic_service.py`의 모양(밖에서 부품을 넣는다, 자료실 실패해도 결과를 잃지 않는다)을 따른다. `make`의 차례는 고정:
1. `resolve_motion_template` 실패 → `MotionUnavailable("motion_template_unknown")`.
2. `parse_motion_variables` 실패 → `MotionUnavailable("motion_variables_invalid", problems=exc.problems)`.
3. 길이 `math.isfinite`이고 `MIN ≤ d ≤ MAX`가 아니면 `MotionUnavailable("motion_variables_invalid", problems=("길이: 3초에서 30초 사이로 골라 주세요",))`; `layout not in MOTION_LAYOUTS`면 `problems=("모양: 다시 골라 주세요",)`.
4. `bridge is None` → `motion_bridge_not_configured`.
5. `bridge.render(template=key, variables=parsed.model_dump(mode="json"), duration_sec=float(duration_sec), layout=layout)`; 오류 대응은 시험 표 그대로(`Refused`: 409 → `motion_busy`, 503이고 `error == "motion_engine_not_prepared"` → `motion_engine_not_prepared`, 504 → `motion_took_too_long`, 나머지 → `motion_render_failed`(detail=str(exc))).
6. 제목: `(title or motion_default_title(...)).strip()[:60]`.
7. 자료실: `library_ingest`가 없으면 `(None, None)`. 있으면 `_scratch_factory(prefix="videobox-motion-")` 안에 `f"{_file_stem(title)}.{clip.format}"`로 쓰고 `ingest(media_type=LibraryMediaType.BROLL, source=path, filename=path.name, idempotency_key=f"motion:{sha256}", provenance={"generated_by": "videobox-motion", "source_kind": "generated_motion", "template": key, "layout": layout, "duration_sec": duration, "title": title, "engine": "hyperframes 0.8.140"})`. 예외는 `type(exc).__name__`으로 `library_error`에 담는다(`# noqa: BLE001` + 이유 주석).
- `MotionUnavailable.__init__(self, reason: str, detail: str = "", problems: tuple[str, ...] = ())`.

- [ ] **Step 8: 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_motion_host_bridge.py::test_the_bridge_is_off_when_nobody_configured_an_address
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_motion_templates.py tests/test_motion_host_bridge.py tests/test_motion_service.py tests/test_infographic_service.py tests/test_infographic_host_bridge.py
```

예상: 전부 통과(인포그래픽 시험은 `_file_stem`을 같이 쓰는지 확인용).

- [ ] **Step 9: 검증 넷과 커밋**

- 갭: Step 1~8. API·화면은 아직이다.
- 역방향(다리 실물, 컨테이너 없이): Task 2의 다리를 띄우고 파이썬으로 `MotionHostBridge(base_url="http://127.0.0.1:8202").render(...)`를 부른다(토큰은 `.env.container`에서 환경 변수로만 싣는다):

```bash
(TOKEN=$(grep -E '^VIDEOBOX_BRIDGE_TOKEN=' .env.container | head -1 | cut -d= -f2- | tr -d '\r"'); \
 VIDEOBOX_BRIDGE_TOKEN="$TOKEN" .venv/Scripts/python.exe scripts/host_motion_service.py > "$TEMP/motion-bridge.out" 2> "$TEMP/motion-bridge.err" &
 sleep 3; \
 VIDEOBOX_BRIDGE_TOKEN="$TOKEN" .venv/Scripts/python.exe -c "
from videobox_core_engine.motion_service import MotionService
from videobox_core_engine.motion_host_bridge import MotionHostBridge
m = MotionService(bridge=MotionHostBridge()).make(template_key='step_list', variables={'title':'처음 시작하는 3단계','steps':['소싱','상세페이지','정산']}, duration_sec=6.0)
print(m.format, len(m.video_bytes), m.elapsed_sec)
"; unset TOKEN)
```

  예상: `mp4 <수십만> <10~20>`. 끝나면 띄운 다리를 끈다(PowerShell: `Get-NetTCPConnection -LocalPort 8202 -State Listen | % { $p = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)"; if ($p.CommandLine -like '*host_motion_service.py*') { Stop-Process -Id $_.OwningProcess -Force } }`).
- 배선: `grep -rn "parse_motion_variables(" packages services --include=*.py | grep -v test` → `motion_service.py` 1(API는 서비스를 부른다).

```bash
git add packages/core-engine/src/videobox_core_engine/motion_templates.py packages/core-engine/src/videobox_core_engine/motion_host_bridge.py packages/core-engine/src/videobox_core_engine/motion_service.py tests/test_motion_templates.py tests/test_motion_host_bridge.py tests/test_motion_service.py
git commit -m "$(cat <<'EOF'
feat(motion): 템플릿 목록·엄격한 변수 검사·모션 다리 부르는 쪽·자료실 등록 서비스

글 길이는 판에 맞게 막고(한국어 문제 문장), < >·제어 문자·이상한 숫자는 다리에 가기 전에
거절한다. 다리가 거절한 이유는 그대로 이름을 달고 올라간다(바쁨·준비 중·시간 초과).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: API — `GET /api/library/motion-templates`·`POST /api/library/motions`·compose·계약 시험

**Files:**
- Create: `services/api/src/videobox_api/routers/motions.py`
- Modify: `services/api/src/videobox_api/models.py`(앵커 `class SceneImageCreateRequest(BaseModel):` **앞**에 모델 넷)
- Modify: `services/api/src/videobox_api/main.py`(import 셋, state 하나, 라우터 하나)
- Modify: `compose.yaml`(앵커 `VIDEOBOX_INFOGRAPHIC_BRIDGE_URL: …8201}` 다음, 토큰 주석)
- Modify: `tests/test_compose_contract.py`(끝에 시험 둘)
- Test: `tests/test_api_motions.py`(새 파일)

**Interfaces:**
- Consumes: Task 3의 `MotionService.make`, `MotionUnavailable`, `MOTION_TEMPLATES`, `check_safe_text`, `MIN/MAX_MOTION_DURATION_SEC`, `MotionHostBridge.from_environment`, `BRIDGE_PORT`, `BRIDGE_TIMEOUT_SECONDS`.
- Produces(Task 6이 쓴다):
  - `GET /api/library/motion-templates` → 200 `{"templates": [{"key", "korean_name", "description", "default_duration_sec", "min_duration_sec", "max_duration_sec", "limits": {..}}]}`
  - `POST /api/library/motions` 본문 `{"template": str, "variables": object, "duration_sec": number(3~30), "layout": "full", "title"?: str|null}` → 201 `{"library_asset_id", "template", "title", "duration_sec", "layout", "format", "byte_size", "elapsed_sec", "library_error"}`.
  - 오류 `detail`: `motion_generation_unavailable`(503, 서비스 없음), `motion_template_unknown`(422), `{"reason": "motion_variables_invalid", "problems": [...]}`(422), `motion_bridge_not_configured`(503), `motion_bridge_not_running`(503), `motion_engine_not_prepared`(503), `motion_busy`(409), `motion_took_too_long`(504), `motion_render_failed`(502). 본문 자체가 틀리면 FastAPI 기본 422(목록 detail).
  - `app.state.motion_service`.

- [ ] **Step 1: 실패하는 시험을 쓴다** — `tests/test_api_motions.py`

```python
"""설명 모션을 만드는 문(HTTP). 꺼진 것·준비 중·바쁨·못 만든 것이 서로 다른 답으로 나간다."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_core_engine.motion_service import MadeMotion, MotionService, MotionUnavailable
from videobox_core_engine.motion_templates import MOTION_TEMPLATES

BODY = {
    "template": "bar_compare",
    "variables": {"title": "월 수익 비교", "unit": "만", "bars": [{"label": "쿠팡", "value": 1280}, {"label": "자사몰", "value": 430}]},
    "duration_sec": 6,
    "layout": "full",
}


class _Service:
    def __init__(self, made=None, raises: MotionUnavailable | None = None) -> None:
        self.made, self.raises, self.calls = made, raises, []

    def make(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return self.made


def _made(**overrides) -> MadeMotion:
    values = {"video_bytes": b"MP4", "template_key": "bar_compare", "title": "월 수익 비교", "duration_sec": 6.0, "layout": "full", "format": "mp4", "elapsed_sec": 13.1, "library_asset_id": "user_m1"}
    values.update(overrides)
    return MadeMotion(**values)


@pytest.fixture()
def client(tmp_path) -> TestClient:
    return TestClient(create_app(projects_root=tmp_path / "data"))


def test_the_templates_come_from_one_place(client: TestClient) -> None:
    reply = client.get("/api/library/motion-templates")
    assert reply.status_code == 200
    templates = reply.json()["templates"]
    assert [t["key"] for t in templates] == [t.key for t in MOTION_TEMPLATES]
    assert templates[0]["korean_name"] == "막대 비교"
    assert (templates[0]["min_duration_sec"], templates[0]["max_duration_sec"]) == (3.0, 30.0)
    assert templates[0]["limits"]["title"] == 24


def test_the_app_builds_a_motion_service_wired_to_the_library(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("VIDEOBOX_MOTION_BRIDGE_URL", "http://host.docker.internal:8202")
    app = create_app(projects_root=tmp_path / "data")
    assert isinstance(app.state.motion_service, MotionService)
    assert app.state.motion_service.library_ingest is app.state.library_ingest_service
    assert app.state.motion_service.bridge.base_url == "http://host.docker.internal:8202"


def test_a_feature_that_is_not_on_says_so(client: TestClient) -> None:
    client.app.state.motion_service = None
    reply = client.post("/api/library/motions", json=BODY)
    assert (reply.status_code, reply.json()["detail"]) == (503, "motion_generation_unavailable")


def test_a_made_motion_comes_back_with_where_it_went(client: TestClient) -> None:
    service = _Service(_made())
    client.app.state.motion_service = service
    reply = client.post("/api/library/motions", json=BODY)
    assert reply.status_code == 201
    assert reply.json() == {"library_asset_id": "user_m1", "template": "bar_compare", "title": "월 수익 비교", "duration_sec": 6.0, "layout": "full", "format": "mp4", "byte_size": 3, "elapsed_sec": 13.1, "library_error": None}
    assert service.calls == [{"template_key": "bar_compare", "variables": BODY["variables"], "duration_sec": 6.0, "layout": "full", "title": None}]


@pytest.mark.parametrize(("reason", "status"), [
    ("motion_template_unknown", 422), ("motion_bridge_not_configured", 503), ("motion_bridge_not_running", 503),
    ("motion_engine_not_prepared", 503), ("motion_busy", 409), ("motion_took_too_long", 504), ("motion_render_failed", 502),
])
def test_each_kind_of_failure_gets_its_own_answer(client: TestClient, reason: str, status: int) -> None:
    client.app.state.motion_service = _Service(raises=MotionUnavailable(reason))
    reply = client.post("/api/library/motions", json=BODY)
    assert (reply.status_code, reply.json()["detail"]) == (status, reason)


def test_what_was_wrong_with_the_text_is_told_not_swallowed(client: TestClient) -> None:
    client.app.state.motion_service = _Service(raises=MotionUnavailable("motion_variables_invalid", problems=("제목: 24자까지 써요",)))
    reply = client.post("/api/library/motions", json=BODY)
    assert reply.status_code == 422
    assert reply.json()["detail"] == {"reason": "motion_variables_invalid", "problems": ["제목: 24자까지 써요"]}


@pytest.mark.parametrize("patch", [
    {"duration_sec": 2}, {"duration_sec": 31}, {"layout": "overlay"}, {"title": "<b>x</b>"}, {"title": "x" * 61}, {"extra": 1},
])
def test_a_request_that_cannot_be_a_motion_is_refused_at_the_door(client: TestClient, patch: dict) -> None:
    service = _Service(_made())
    client.app.state.motion_service = service
    reply = client.post("/api/library/motions", json={**BODY, **patch})
    assert reply.status_code == 422
    assert service.calls == []
```

(`{"layout": "overlay"}`이 422인 것은 **이 계획 2단계의 결정**이다 — 렌더러가 알파를 못 읽어서. Task 9가 이 줄을 뒤집는다.)

- [ ] **Step 2: 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_api_motions.py::test_the_templates_come_from_one_place
```

예상: FAIL `assert 404 == 200`.

- [ ] **Step 3: 모델을 더한다** — `models.py`, 앵커 `class SceneImageCreateRequest(BaseModel):` 바로 앞에. 파일 위쪽 import에 `from videobox_core_engine.motion_templates import MAX_MOTION_DURATION_SEC, MIN_MOTION_DURATION_SEC, check_safe_text`를 더한다(기존 `from videobox_core_engine.overlay_shapes import (` 앞 줄).

```python
class MotionCreateRequest(BaseModel):
    """설명 모션 한 편. 템플릿 이름·숫자·글만 받는다 -- HTML·코드는 받는 칸이 없다(2026-10-08 결정).

    `variables`의 칸별 검사는 템플릿마다 달라서 `MotionService`가 `parse_motion_variables`로 한다.
    `layout`은 2단계에서 `full`만 연다: 완성본 렌더러가 투명 webm의 알파를 아직 못 읽는다.
    """

    model_config = ConfigDict(extra="forbid")

    template: str = Field(min_length=1, max_length=40)
    variables: dict[str, Any]
    duration_sec: float = Field(ge=MIN_MOTION_DURATION_SEC, le=MAX_MOTION_DURATION_SEC, allow_inf_nan=False)
    layout: Literal["full"] = "full"
    title: str | None = Field(default=None, max_length=60)

    @field_validator("title")
    @classmethod
    def _safe_title(cls, value: str | None) -> str | None:
        return None if value is None else check_safe_text(value.strip())


class MotionResponse(BaseModel):
    library_asset_id: str | None = None
    template: str
    title: str
    duration_sec: float
    layout: str
    format: str
    byte_size: int
    elapsed_sec: float
    #: 자료실 등록이 실패했으면 그 이유. 모션 자체는 만들어졌다.
    library_error: str | None = None


class MotionTemplateResponse(BaseModel):
    key: str
    korean_name: str
    description: str
    default_duration_sec: float
    min_duration_sec: float
    max_duration_sec: float
    limits: dict[str, int]


class MotionTemplateListResponse(BaseModel):
    templates: list[MotionTemplateResponse]
```

- [ ] **Step 4: 라우터를 쓴다** — `routers/motions.py`

`routers/infographics.py`의 모양 그대로: 첫머리 문서 문자열(왜 자료실인가 — 내 자산을 다시 쓰기, 한 요청에 끝나지만 다리 240초 < nginx 600초, 자료실 실패해도 201), `_LOGGER`, `_STATUS_BY_REASON`(Interfaces의 표), `build_motions_router() -> APIRouter`:
- GET: `MotionTemplateListResponse(templates=[MotionTemplateResponse(key=t.key, korean_name=t.korean_name, description=t.description, default_duration_sec=t.default_duration_sec, min_duration_sec=MIN_MOTION_DURATION_SEC, max_duration_sec=MAX_MOTION_DURATION_SEC, limits=dict(t.limits)) for t in MOTION_TEMPLATES])`.
- POST(`status_code=201`): 서비스가 `None`이면 503 `motion_generation_unavailable`. `service.make(template_key=payload.template, variables=payload.variables, duration_sec=payload.duration_sec, layout=payload.layout, title=payload.title)`. `MotionUnavailable`이면 `_LOGGER.warning("모션을 만들지 못했습니다 (%s): %s", exc.reason, exc.detail)` 후 `HTTPException(status_code=_STATUS_BY_REASON.get(exc.reason, 502), detail={"reason": exc.reason, "problems": list(exc.problems)} if exc.problems else exc.reason)`. 그 밖의 예외는 `_http_error(exc)`. 성공 → `MotionResponse(library_asset_id=made.library_asset_id, template=made.template_key, title=made.title, duration_sec=made.duration_sec, layout=made.layout, format=made.format, byte_size=len(made.video_bytes), elapsed_sec=made.elapsed_sec, library_error=made.library_error)`.

- [ ] **Step 5: 앱에 꽂는다** — `main.py`

앵커 `from videobox_api.routers.infographics import build_infographics_router` 다음 줄에:

```python
from videobox_core_engine.motion_host_bridge import MotionHostBridge
from videobox_core_engine.motion_service import MotionService
from videobox_api.routers.motions import build_motions_router
```

앵커 `    # \`scene_image_service\`와 같은 이유 -- 켜지 않았으면 \`None\`이다. owner 결정` **앞**에:

```python
    # 설명 모션(2026-10-08 결정 2단계). 인포그래픽과 같은 이유로 다리가 없어도 서비스는 둔다 --
    # 그래야 화면이 "꺼져 있어요"를 정확히 말한다. 두뇌(런타임)는 안 쓴다: 템플릿과 숫자·글뿐이다.
    app.state.motion_service = MotionService(
        bridge=MotionHostBridge.from_environment(),
        library_ingest=app.state.library_ingest_service,
    )
```

앵커 `    app.include_router(build_infographics_router())` 다음 줄에 `    app.include_router(build_motions_router())`.

- [ ] **Step 6: 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_api_motions.py::test_the_templates_come_from_one_place
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_api_motions.py tests/test_api_infographics.py tests/test_local_media_ai_providers.py
```

예상: 전부 통과(`test_local_media_ai_providers.py`는 앱을 지을 때 provider를 두 번 짓지 않는다는 울타리 — 모션은 두뇌를 안 쓰므로 그대로여야 한다).

- [ ] **Step 7: compose와 계약 시험**

`compose.yaml` 앵커 줄 `      VIDEOBOX_INFOGRAPHIC_BRIDGE_URL: ${VIDEOBOX_INFOGRAPHIC_BRIDGE_URL:-http://host.docker.internal:8201}` 다음에:

```yaml
      # **설명 모션을 그리는 다리**(2026-10-08 결정). 하이퍼프레임(Node)과 그 브라우저는
      # 이 컴퓨터에만 있다. 그림 다리(8201) 옆자리인 8202다.
      # 켜는 법: `scripts/start-motion.ps1` (VideoBox를 켜면 함께 켜진다).
      VIDEOBOX_MOTION_BRIDGE_URL: ${VIDEOBOX_MOTION_BRIDGE_URL:-http://host.docker.internal:8202}
```

바로 아래 주석 `# **다리 셋(8199·8200·8201)의 공유 토큰**`을 `# **다리 넷(8199·8200·8201·8202)의 공유 토큰**`으로 고친다.

`tests/test_compose_contract.py` 위쪽 import에 `from videobox_core_engine.motion_host_bridge import BRIDGE_PORT as MOTION_BRIDGE_PORT, BRIDGE_TIMEOUT_SECONDS as MOTION_BRIDGE_TIMEOUT_SECONDS`를 더하고, 파일 끝에:

```python
def test_the_motion_path_may_only_reach_this_machine() -> None:
    """모션 다리도 그림 다리와 같은 규칙이다 -- 이 기계의 8202뿐(2026-10-08 결정)."""
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    environment = compose["services"]["videobox-workspace"]["environment"]
    assert environment["VIDEOBOX_MOTION_BRIDGE_URL"] == (
        f"${{VIDEOBOX_MOTION_BRIDGE_URL:-http://host.docker.internal:{MOTION_BRIDGE_PORT}}}"
    )


def test_the_proxy_waits_longer_than_a_motion_can_take() -> None:
    """다리 렌더 상한 < 컨테이너 대기 < nginx. 하나라도 뒤집히면 화면은 우리 문구 대신 504 HTML을 본다."""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("motion_bridge_timeout_check", ROOT / "scripts" / "host_motion_service.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["motion_bridge_timeout_check"] = module
    spec.loader.exec_module(module)
    config = (ROOT / "docker/workspace-nginx.conf").read_text(encoding="utf-8")
    proxy = int(re.search(r"proxy_read_timeout\s+(\d+)s\s*;", config).group(1))
    assert module.RENDER_TIMEOUT_SECONDS < MOTION_BRIDGE_TIMEOUT_SECONDS < proxy
```

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_compose_contract.py
```

예상: 전부 통과.

- [ ] **Step 8: 검증 넷과 커밋**

- 갭: Step 1~7. 컨테이너 재빌드·실물 호출은 Task 8.
- 배선: `grep -n "build_motions_router\|motion_service" services/api/src/videobox_api/main.py` → import 1, state 1, include 1. `grep -rn "/api/library/motions" services apps --include=*.py --include=*.ts` → 라우터 1(화면은 Task 6).

```bash
git add services/api/src/videobox_api/routers/motions.py services/api/src/videobox_api/models.py services/api/src/videobox_api/main.py compose.yaml tests/test_api_motions.py tests/test_compose_contract.py
git commit -m "$(cat <<'EOF'
feat(motion): 자료실 모션 만들기 API와 compose 다리 주소(8202)

템플릿 목록은 서버 한 곳에서 나간다. 실패는 이유마다 다른 상태로(꺼짐·준비 중·바쁨·시간 초과).
2단계는 전체 화면(mp4)만 연다 -- 투명 오버레이는 렌더러가 알파를 읽은 뒤(Task 9).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `owner-ready`가 모션 다리를 켜고, 첫 준비는 숨은 창에서 따로 돌린다

**Files:**
- Modify: `scripts/owner-ready.ps1`(앵커 `        -Summary $infographicSummary -Action $infographicAction -Evidence $infographicEvidence` 다음)
- Test: `tests/test_owner_ready_script.py`(시험 하나 추가)

**Interfaces:**
- Consumes: `scripts/start-motion.ps1`, `scripts/prepare-motion.ps1`(Task 2).
- Produces: owner-ready 결과 행 `id = "motion_bridge"`, 증거 `{port: 8202, started, already_running?, preparing, log?, prepare_log?}`. 상태는 늘 `pass`(모션이 없어도 VideoBox는 쓴다 — 그림 다리와 같은 판단).

- [ ] **Step 1: 실패하는 시험을 쓴다** — `tests/test_owner_ready_script.py`의 `test_start_brings_up_the_voice_bridge_without_leaving_a_window_open` 다음에:

```python
def test_start_reports_the_motion_bridge_without_waiting_for_its_first_preparation(tmp_path: Path) -> None:
    """2026-10-08 결정: 처음 준비(약 400MB)는 몇 분 걸린다. VideoBox 켜기를 그동안 붙잡으면 안 된다.

    준비는 숨은 창에서 따로 돌고(`prepare-motion.ps1`), 여기서는 결과 한 줄만 남긴다.
    """
    fixture = _fixture_repository(tmp_path)
    with _health_server() as video_uri:
        result = _run(fixture, mode="Start", video_uri=video_uri)

    assert result.returncode == 0, _why_it_failed(result)
    motion = next((row for row in _payload(result)["checks"] if row["id"] == "motion_bridge"), None)
    assert motion is not None, "모션 다리 결과가 없다"
    assert motion["status"] == "pass"
    assert motion["evidence"]["port"] == 8202

    source = fixture["script"].read_text(encoding="utf-8-sig")
    block = source[source.index('-Id "infographic_bridge"'):source.index('-Id "motion_bridge"')]
    assert "prepare-motion.ps1" in block
    assert "-WindowStyle Hidden" in block
    assert "& $motionPrepareScript" not in block, "준비를 앞에서 기다리면 켜기가 몇 분 멈춘다"
```

(`fixture["script"]`가 이 파일에서 쓰는 열쇠인지 먼저 `grep -n 'fixture\["script"\]' tests/test_owner_ready_script.py`로 확인한다 — 2026-10-08에 1173·1669줄에서 쓰인다. 결과 행의 증거 열쇠 이름이 `evidence`인지도 `voice` 시험 근처에서 확인하고, 다르면 그 이름을 쓴다.)

- [ ] **Step 2: 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider "tests/test_owner_ready_script.py::test_start_reports_the_motion_bridge_without_waiting_for_its_first_preparation"
```

예상: FAIL `AssertionError: 모션 다리 결과가 없다`.

- [ ] **Step 3: 블록을 넣는다** — 앵커 줄 다음, 빈 줄 하나 띄우고:

```powershell
    # **모션 다리도 같이 켠다**(2026-10-08 결정, 설명 모션). 하이퍼프레임(Node)과 그
    # 브라우저는 이 컴퓨터에만 있다. 그림 다리(8201)와 같은 이유·같은 방식이고 8202다.
    #
    # **처음 한 번은 준비가 필요하다**(약 120MB 설치 + 약 270MB 브라우저). 여기서 기다리지
    # 않는다 -- 준비는 숨은 창에서 따로 돌고(`prepare-motion.ps1`, 단계마다 시간 상한),
    # 그동안 다리는 "준비 중"(503)이라고 답한다. VideoBox 켜기를 몇 분씩 붙잡지 않는다.
    #
    # 모션이 없어도 VideoBox는 다 쓸 수 있다. 그래서 blocked를 내지 않는다.
    $motionStatus = "pass"
    $motionSummary = "모션 다리를 켜지 못했습니다. 모션 만들기만 쉬어 갑니다."
    $motionAction = "모션을 만들려면 로그를 확인한 뒤 다시 실행하세요."
    $motionEvidence = @{ port = 8202; started = $false; preparing = $false }
    $motionEnginePackage = Join-Path $PSScriptRoot "motion-bridge\node_modules\hyperframes\package.json"
    $motionEngineReady = $false
    try {
        if (Test-Path $motionEnginePackage) {
            $motionEngineReady = ((Get-Content -LiteralPath $motionEnginePackage -Raw | ConvertFrom-Json).version -eq "0.8.140")
        }
    } catch { $motionEngineReady = $false }
    $motionBrowserReady = $false
    try {
        $motionBrowserRoot = Join-Path $env:USERPROFILE ".cache\hyperframes\chrome\chrome-headless-shell"
        $motionBrowserReady = [bool](Get-ChildItem -Path $motionBrowserRoot -Filter "chrome-headless-shell.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1)
    } catch { $motionBrowserReady = $false }
    $motionPreparing = $false
    $motionPrepareScript = Join-Path $PSScriptRoot "prepare-motion.ps1"
    $motionPrepareLog = Join-Path ([System.IO.Path]::GetTempPath()) "videobox-motion-prepare.log"
    if (-not ($motionEngineReady -and $motionBrowserReady) -and (Test-Path $motionPrepareScript)) {
        try {
            Start-Process -FilePath "powershell" `
                -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $motionPrepareScript) `
                -WindowStyle Hidden `
                -RedirectStandardOutput $motionPrepareLog `
                -RedirectStandardError ($motionPrepareLog + ".err") | Out-Null
            $motionPreparing = $true
        } catch { $motionPreparing = $false }
    }
    $motionAlreadyUp = $false
    try {
        $probe = [System.Net.Sockets.TcpClient]::new()
        $probe.Connect("127.0.0.1", 8202)
        $motionAlreadyUp = $probe.Connected
        $probe.Close()
    } catch { $motionAlreadyUp = $false }
    if ($motionAlreadyUp) {
        $motionSummary = "모션 다리가 이미 준비돼 있습니다."
        $motionAction = "추가 조치가 없습니다."
        $motionEvidence = @{ port = 8202; started = $true; already_running = $true; preparing = $motionPreparing }
    } else {
        $motionScript = Join-Path $PSScriptRoot "start-motion.ps1"
        $motionLog = Join-Path ([System.IO.Path]::GetTempPath()) "videobox-motion-bridge.log"
        if (Test-Path $motionScript) {
            try {
                Start-Process -FilePath "powershell" `
                    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $motionScript) `
                    -WindowStyle Hidden `
                    -RedirectStandardOutput $motionLog `
                    -RedirectStandardError ($motionLog + ".err") | Out-Null
                $motionSummary = "모션 다리를 백그라운드로 켰습니다."
                $motionAction = "추가 조치가 없습니다."
                $motionEvidence = @{ port = 8202; started = $true; already_running = $false; log = $motionLog; preparing = $motionPreparing }
            } catch {
                $motionEvidence = @{ port = 8202; started = $false; log = $motionLog; preparing = $motionPreparing }
            }
        }
    }
    if ($motionPreparing) {
        $motionSummary = "모션 도구를 처음 한 번 준비하고 있습니다(약 400MB 받기, 몇 분). 끝나면 모션 만들기를 쓸 수 있습니다."
        $motionAction = "기다리면 됩니다. 오래 걸리면 준비 로그를 확인하세요."
        $motionEvidence.prepare_log = $motionPrepareLog
    }
    $checks += New-OwnerReadyResult -Id "motion_bridge" -Status $motionStatus `
        -Summary $motionSummary -Action $motionAction -Evidence $motionEvidence
```

고친 뒤 BOM을 확인한다: `head -c 3 scripts/owner-ready.ps1 | od -An -tx1` → `ef bb bf`.

- [ ] **Step 4: 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider "tests/test_owner_ready_script.py::test_start_reports_the_motion_bridge_without_waiting_for_its_first_preparation"
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_owner_ready_script.py -k "start"
```

예상: PASS, 그다음 `start` 시험 묶음 통과(알려진 `test_smoke_timeout…`은 `-k start`에 안 걸린다 — 걸리면 그 하나만 알려진 실패로 둔다).

- [ ] **Step 5: 검증 넷과 커밋**

- 역방향(실물, 컨테이너 재빌드 없이): PowerShell `.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Json` → `motion_bridge` 행이 `pass`이고 이 컴퓨터는 이미 준비돼 있어 `preparing: false`, `started: true`. 몇 초 뒤 `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8202/diagnostics` → `401`(토큰 없음 = 문지기가 섰다). `-Json` 스위치가 없으면 출력의 같은 행을 본다.
- 동작: 준비 길만 따로 재 본다 — `powershell -NoProfile -File scripts/prepare-motion.ps1` 실행 시간을 잰다(이미 준비된 컴퓨터라 `npm ci`는 건너뛰고 `browser ensure`만, 수 초). 출력과 시간을 인계에 적는다. **브라우저를 지우고 다시 받는 시험은 하지 않는다**(270MB 재다운로드 — 필요하면 owner 결정).
- 배선: `grep -c 'motion_bridge' scripts/owner-ready.ps1` → 1 이상, `grep -c 'start-motion.ps1' scripts/owner-ready.ps1` → 1.

```bash
git add scripts/owner-ready.ps1 tests/test_owner_ready_script.py
git commit -m "$(cat <<'EOF'
feat(motion): VideoBox를 켜면 모션 다리(8202)도 켜고, 첫 준비는 숨은 창에서 따로

준비(약 400MB)를 앞에서 기다리지 않는다. 그동안 다리는 준비 중이라고 답한다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: 화면 — `api.ts`·`MotionPanel`·편집기 `모션` 팝업

**Files:**
- Modify: `apps/web/src/api.ts`(타입: 앵커 `export type SceneImageRequest` **앞**; 메서드: 앵커 `  createSceneImage: (projectId: string, payload: SceneImageRequest)` **앞**)
- Create: `apps/web/src/features/editor/assets/MotionPanel.tsx`
- Create: `apps/web/src/features/editor/assets/MotionPanel.test.tsx`
- Modify: `apps/web/src/features/editor/assets/EditorAssetBrowser.tsx`(import·상태·단추·팝업)
- Modify: `apps/web/src/features/editor/assets/EditorAssetBrowser.test.tsx`(describe 하나)

**Interfaces:**
- Consumes: Task 4의 두 경로, 기존 `api.materializeLibraryAsset(libraryAssetId, projectId)`, `ApiRequestError`(`reason`·`detail`), `Button`·`Input`.
- Produces:
  - 타입 `MotionTemplate = { key: string; korean_name: string; description: string; default_duration_sec: number; min_duration_sec: number; max_duration_sec: number; limits: Record<string, number> }`, `MotionRequest = { template: string; variables: Record<string, unknown>; duration_sec: number; layout?: "full"; title?: string | null }`, `MotionResult = { library_asset_id: string | null; template: string; title: string; duration_sec: number; layout: "full" | "overlay"; format: "mp4" | "webm"; byte_size: number; elapsed_sec: number; library_error: string | null }`.
  - 메서드 `listMotionTemplates: () => request<{ templates: MotionTemplate[] }>("/api/library/motion-templates")`, `createMotion: (payload: MotionRequest) => request<MotionResult>("/api/library/motions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })`.
  - 컴포넌트 `export function MotionPanel({ projectId, sceneSeconds = null, onMade }: { projectId?: string; sceneSeconds?: number | null; onMade?: () => void })`.

- [ ] **Step 1: 실패하는 시험을 쓴다** — `MotionPanel.test.tsx`

```tsx
/** 편집기에서 설명 모션을 만드는 자리 (2026-10-08 결정 2단계).
 *  지키는 것: 적은 그대로 간다 · 장면 길이를 기본 길이로 쓴다 · 기다리는 동안 잠그고 말한다 ·
 *  만든 것을 이 프로젝트로 가져온다 · 실패 이유마다 다른 말을 한다 · < >는 보내기 전에 막는다. */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MotionPanel } from "./MotionPanel";
import { api, ApiRequestError, type MotionResult } from "../../../api";

const TEMPLATES = { templates: [
  { key: "bar_compare", korean_name: "막대 비교", description: "숫자 몇 개를 막대로 견줘요", default_duration_sec: 6, min_duration_sec: 3, max_duration_sec: 30, limits: { title: 24, subtitle: 40, unit: 4, label: 10, min_items: 2, max_items: 5 } },
  { key: "money_counter", korean_name: "금액 카운터", description: "금액이 0부터 올라가요", default_duration_sec: 5, min_duration_sec: 3, max_duration_sec: 30, limits: { lead: 20, suffix: 4, caption: 30 } },
  { key: "step_list", korean_name: "단계 목록", description: "순서를 하나씩 보여 줘요", default_duration_sec: 6, min_duration_sec: 3, max_duration_sec: 30, limits: { title: 24, step: 24, min_items: 2, max_items: 5 } },
] };

function made(overrides: Partial<MotionResult> = {}): MotionResult {
  return { library_asset_id: "user_m1", template: "bar_compare", title: "월 수익 비교", duration_sec: 6, layout: "full", format: "mp4", byte_size: 316548, elapsed_sec: 14.2, library_error: null, ...overrides };
}

async function fillBars() {
  await waitFor(() => expect(screen.getByRole("button", { name: "막대 비교" })).toHaveAttribute("aria-pressed", "true"));
  fireEvent.change(screen.getByLabelText("제목"), { target: { value: "월 수익 비교" } });
  fireEvent.change(screen.getByLabelText("단위(선택)"), { target: { value: "만" } });
  fireEvent.change(screen.getByLabelText("1번째 이름"), { target: { value: "쿠팡" } });
  fireEvent.change(screen.getByLabelText("1번째 값"), { target: { value: "1280" } });
  fireEvent.change(screen.getByLabelText("2번째 이름"), { target: { value: "스마트스토어" } });
  fireEvent.change(screen.getByLabelText("2번째 값"), { target: { value: "860" } });
}

const make = () => fireEvent.click(screen.getByRole("button", { name: "모션 만들기" }));

describe("MotionPanel", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "listMotionTemplates").mockResolvedValue(TEMPLATES);
  });
  afterEach(cleanup);

  it("고를 수 있는 종류를 서버에서 받아 오고 첫째가 골라져 있다", async () => {
    render(<MotionPanel projectId="project-a" />);
    await waitFor(() => expect(screen.getByRole("button", { name: "막대 비교" })).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByRole("button", { name: "금액 카운터" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "단계 목록" })).toBeTruthy();
  });

  it("막대 비교는 적은 그대로 보낸다", async () => {
    const create = vi.spyOn(api, "createMotion").mockResolvedValue(made());
    vi.spyOn(api, "materializeLibraryAsset").mockResolvedValue({} as never);
    render(<MotionPanel projectId="project-a" />);
    await fillBars();
    make();
    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][0]).toEqual({
      template: "bar_compare",
      variables: { title: "월 수익 비교", subtitle: "", unit: "만", bars: [{ label: "쿠팡", value: 1280 }, { label: "스마트스토어", value: 860 }] },
      duration_sec: 6,
      layout: "full",
    });
  });

  it("장면 길이를 기본 길이로 쓴다 — 짧으면 숫자가 처음부터 다시 돈다", async () => {
    const create = vi.spyOn(api, "createMotion").mockResolvedValue(made());
    vi.spyOn(api, "materializeLibraryAsset").mockResolvedValue({} as never);
    render(<MotionPanel projectId="project-a" sceneSeconds={8.44} />);
    await fillBars();
    expect(screen.getByLabelText("길이(초)")).toHaveValue("8.4");
    make();
    await waitFor(() => expect(create.mock.calls[0][0].duration_sec).toBe(8.4));
  });

  it("장면이 길어도 30초, 짧아도 3초로 맞춘다", async () => {
    const { unmount } = render(<MotionPanel projectId="project-a" sceneSeconds={45} />);
    await waitFor(() => expect(screen.getByLabelText("길이(초)")).toHaveValue("30"));
    unmount();
    render(<MotionPanel projectId="project-a" sceneSeconds={1} />);
    await waitFor(() => expect(screen.getByLabelText("길이(초)")).toHaveValue("3"));
  });

  it("만드는 동안 잠기고 얼마나 걸리는지 말한다", async () => {
    let release: (value: MotionResult) => void = () => {};
    vi.spyOn(api, "createMotion").mockReturnValue(new Promise<MotionResult>((resolve) => { release = resolve; }));
    vi.spyOn(api, "materializeLibraryAsset").mockResolvedValue({} as never);
    render(<MotionPanel projectId="project-a" />);
    await fillBars();
    make();
    const busy = await screen.findByRole("button", { name: /만드는 중/ });
    expect(busy).toHaveProperty("disabled", true);
    expect(busy.textContent).toContain("1분");
    release(made());
    await screen.findByRole("status");
  });

  it("만들면 이 프로젝트로 가져오고 목록을 다시 읽게 한다", async () => {
    vi.spyOn(api, "createMotion").mockResolvedValue(made());
    const materialize = vi.spyOn(api, "materializeLibraryAsset").mockResolvedValue({} as never);
    const onMade = vi.fn();
    render(<MotionPanel projectId="project-a" onMade={onMade} />);
    await fillBars();
    make();
    await waitFor(() => expect(materialize).toHaveBeenCalledWith("user_m1", "project-a"));
    await waitFor(() => expect(onMade).toHaveBeenCalled());
    expect((await screen.findByRole("status")).textContent).toContain("장면을 고르고");
  });

  it("가져오지 못하면 자료실에서 꺼내 쓰라고 말한다", async () => {
    vi.spyOn(api, "createMotion").mockResolvedValue(made());
    vi.spyOn(api, "materializeLibraryAsset").mockRejectedValue(new Error("x"));
    render(<MotionPanel projectId="project-a" />);
    await fillBars();
    make();
    expect((await screen.findByRole("status")).textContent).toContain("자료실에서 가져오기");
  });

  it.each([
    ["motion_engine_not_prepared", "처음 한 번 준비하는 중"],
    ["motion_bridge_not_running", "VideoBox를 다시 켜 주세요"],
    ["motion_busy", "다른 모션을 만드는 중"],
    ["motion_took_too_long", "길이를 줄이고"],
    ["motion_variables_invalid", "적은 내용을 다시 확인"],
  ])("%s 이면 그에 맞는 말을 한다", async (reason, expected) => {
    vi.spyOn(api, "createMotion").mockRejectedValue(new ApiRequestError(reason, 503, "/api/library/motions", reason));
    render(<MotionPanel projectId="project-a" />);
    await fillBars();
    make();
    expect((await screen.findByRole("alert")).textContent).toContain(expected);
  });

  it("< > 기호를 적으면 보내기 전에 막고 이유를 말한다", async () => {
    const create = vi.spyOn(api, "createMotion");
    render(<MotionPanel projectId="project-a" />);
    await fillBars();
    fireEvent.change(screen.getByLabelText("제목"), { target: { value: "<b>굵게</b>" } });
    expect(screen.getByRole("button", { name: "모션 만들기" })).toHaveProperty("disabled", true);
    expect(screen.getByText("< > 기호는 쓸 수 없어요.")).toBeTruthy();
    expect(create).not.toHaveBeenCalled();
  });

  it("단계 목록과 금액 카운터도 적은 그대로 보낸다", async () => {
    const create = vi.spyOn(api, "createMotion").mockResolvedValue(made());
    vi.spyOn(api, "materializeLibraryAsset").mockResolvedValue({} as never);
    render(<MotionPanel projectId="project-a" />);
    await waitFor(() => expect(screen.getByRole("button", { name: "단계 목록" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "단계 목록" }));
    fireEvent.change(screen.getByLabelText("제목"), { target: { value: "처음 3단계" } });
    fireEvent.change(screen.getByLabelText("1번째 단계"), { target: { value: "소싱" } });
    fireEvent.change(screen.getByLabelText("2번째 단계"), { target: { value: "정산" } });
    make();
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    expect(create.mock.calls[0][0]).toMatchObject({ template: "step_list", variables: { title: "처음 3단계", steps: ["소싱", "정산"] } });

    fireEvent.click(screen.getByRole("button", { name: "금액 카운터" }));
    fireEvent.change(screen.getByLabelText("금액"), { target: { value: "12345678" } });
    fireEvent.click(screen.getByRole("button", { name: "$" }));
    make();
    await waitFor(() => expect(create).toHaveBeenCalledTimes(2));
    expect(create.mock.calls[1][0]).toMatchObject({ template: "money_counter", variables: { lead: "", amount: 12345678, prefix: "$", suffix: "", caption: "" } });
  });
});
```

- [ ] **Step 2: 실패를 확인한다**

```bash
(cd apps/web && npx vitest run src/features/editor/assets/MotionPanel.test.tsx -t "고를 수 있는 종류를")
```

예상: FAIL `Failed to resolve import "./MotionPanel"`.

- [ ] **Step 3: `api.ts`에 타입과 메서드를 더한다**(Interfaces 그대로, 각 메서드 위에 한 줄 주석: 목록은 화면이 베껴 적지 않으려고 서버에서, 만들기는 6초짜리가 15초쯤·30초짜리가 1분 안쪽이라 화면이 기다림을 말해야 한다).

- [ ] **Step 4: `MotionPanel.tsx`를 쓴다**

```tsx
/** 편집하다가 설명 모션 한 편을 만드는 자리 (2026-10-08 결정 2단계).
 *
 *  **정해진 세 종류에 숫자·글만 적는다.** 모양은 저장소에 있는 템플릿이 정하고, 여기서는
 *  고르기와 적기만 한다(결정 방침 1 -- 아무도 그림 코드를 쓰지 않는다).
 *
 *  **만들면 이 프로젝트로 바로 가져온다.** 자료실 영상은 편집기 목록에 바로 안 뜬다 --
 *  가져와야(`materializeLibraryAsset`) 카드가 생기고 `적용`으로 장면 화면이 된다.
 *
 *  **기본 길이는 고른 장면 길이다.** 장면보다 짧으면 B-roll 기본값(반복)이라 숫자가
 *  처음부터 다시 올라간다.
 *
 *  스타일은 인포그래픽 패널의 것을 그대로 쓴다(팔레트·CSS를 새로 만들지 않는다). */
import { useEffect, useState } from "react";

import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { api, ApiRequestError, type MotionResult, type MotionTemplate } from "../../../api";

type BarRow = { label: string; value: string };
type Prefix = "₩" | "$" | "";
const FORBIDDEN = /[<>]/;
const PREFIXES: { value: Prefix; label: string }[] = [{ value: "₩", label: "₩" }, { value: "$", label: "$" }, { value: "", label: "없음" }];

export function MotionPanel({ projectId, sceneSeconds = null, onMade }: { projectId?: string; sceneSeconds?: number | null; onMade?: () => void }) {
  const [templates, setTemplates] = useState<MotionTemplate[]>([]);
  const [key, setKey] = useState("");
  const [title, setTitle] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [unit, setUnit] = useState("");
  const [bars, setBars] = useState<BarRow[]>([{ label: "", value: "" }, { label: "", value: "" }]);
  const [lead, setLead] = useState("");
  const [amount, setAmount] = useState("");
  const [prefix, setPrefix] = useState<Prefix>("₩");
  const [suffix, setSuffix] = useState("");
  const [caption, setCaption] = useState("");
  const [steps, setSteps] = useState<string[]>(["", ""]);
  const [seconds, setSeconds] = useState("");
  const [busy, setBusy] = useState(false);
  const [made, setMade] = useState<{ result: MotionResult; inProject: boolean } | null>(null);
  const [failed, setFailed] = useState("");

  useEffect(() => {
    let alive = true;
    api.listMotionTemplates()
      .then((reply) => {
        if (!alive) return;
        setTemplates(reply.templates);
        setKey((current) => current || reply.templates[0]?.key || "");
      })
      .catch(() => { if (alive) setFailed("모션 종류를 불러오지 못했어요. 잠시 뒤 다시 열어 주세요."); });
    return () => { alive = false; };
  }, []);

  const template = templates.find((item) => item.key === key);
  const minimum = template?.min_duration_sec ?? 3;
  const maximum = template?.max_duration_sec ?? 30;
  useEffect(() => {
    if (!template) return;
    setSeconds((current) => current || String(defaultSeconds(sceneSeconds, template)));
  }, [template, sceneSeconds]);

  const limit = (name: string, fallback: number) => template?.limits[name] ?? fallback;
  const usableBars = bars.filter((row) => row.label.trim() && row.value.trim() && Number.isFinite(Number(row.value)));
  const usableSteps = steps.map((step) => step.trim()).filter(Boolean);
  const texts = key === "bar_compare" ? [title, subtitle, unit, ...bars.map((row) => row.label)]
    : key === "money_counter" ? [lead, suffix, caption] : [title, ...steps];
  const hasForbidden = texts.some((text) => FORBIDDEN.test(text));
  const duration = Number(seconds);
  const durationOk = seconds.trim() !== "" && Number.isFinite(duration) && duration >= minimum && duration <= maximum;
  const filled = key === "bar_compare" ? Boolean(title.trim()) && usableBars.length >= 2
    : key === "money_counter" ? amount.trim() !== "" && Number.isInteger(Number(amount)) && Number(amount) >= 0
    : Boolean(title.trim()) && usableSteps.length >= 2;
  const ready = Boolean(template) && filled && durationOk && !hasForbidden && !busy;

  const variables = (): Record<string, unknown> => (
    key === "bar_compare"
      ? { title: title.trim(), subtitle: subtitle.trim(), unit: unit.trim(), bars: usableBars.map((row) => ({ label: row.label.trim(), value: Number(row.value) })) }
      : key === "money_counter"
        ? { lead: lead.trim(), amount: Number(amount), prefix, suffix: suffix.trim(), caption: caption.trim() }
        : { title: title.trim(), steps: usableSteps }
  );

  const create = async () => {
    setBusy(true);
    setFailed("");
    setMade(null);
    try {
      const result = await api.createMotion({ template: key, variables: variables(), duration_sec: duration, layout: "full" });
      let inProject = false;
      if (result.library_asset_id && projectId) {
        try {
          await api.materializeLibraryAsset(result.library_asset_id, projectId);
          inProject = true;
        } catch {
          inProject = false;
        }
      }
      if (result.library_asset_id) onMade?.();
      else if (result.library_error) console.warn("motion library save failed:", result.library_error);
      setMade({ result, inProject });
    } catch (error) {
      setFailed(messageFor(error));
    } finally {
      setBusy(false);
    }
  };

  return <div className="vb-infographic vb-motion">
    {templates.length > 0 ? <div className="vb-infographic__field" role="group" aria-label="모션 종류">
      <span>모션 종류</span>
      <div className="vb-infographic__styles">
        {templates.map((item) => <Button key={item.key} type="button" variant="ghost" className="vb-infographic__style"
          aria-pressed={key === item.key} disabled={busy}
          onClick={() => { setKey(item.key); setSeconds(""); }}>{item.korean_name}</Button>)}
      </div>
      <span className="vb-infographic__hint">{template?.description ?? ""}</span>
    </div> : null}

    {key === "bar_compare" || key === "step_list" ? <label className="vb-infographic__field">
      <span>제목</span>
      <Input value={title} disabled={busy} maxLength={limit("title", 24)} placeholder={key === "bar_compare" ? "월 수익 비교" : "처음 시작하는 3단계"}
        onChange={(event) => setTitle(event.target.value)} />
    </label> : null}

    {key === "bar_compare" ? <>
      <label className="vb-infographic__field">
        <span>작은 설명(선택)</span>
        <Input value={subtitle} disabled={busy} maxLength={limit("subtitle", 40)} placeholder="2026년 9월 · 단위 만 원" onChange={(event) => setSubtitle(event.target.value)} />
      </label>
      <label className="vb-infographic__field">
        <span>단위(선택)</span>
        <Input value={unit} disabled={busy} maxLength={limit("unit", 4)} placeholder="만" onChange={(event) => setUnit(event.target.value)} />
      </label>
      <div className="vb-infographic__facts" role="group" aria-label="막대">
        <p className="vb-infographic__hint">가장 큰 값이 다른 색으로 보여요.</p>
        {bars.map((row, index) => <div className="vb-infographic__fact" key={index}>
          <Input aria-label={`${index + 1}번째 이름`} value={row.label} disabled={busy} maxLength={limit("label", 10)} placeholder="쿠팡"
            onChange={(event) => setBars(replaceAt(bars, index, { ...row, label: event.target.value }))} />
          <Input aria-label={`${index + 1}번째 값`} value={row.value} disabled={busy} inputMode="decimal" placeholder="1280"
            onChange={(event) => setBars(replaceAt(bars, index, { ...row, value: event.target.value }))} />
          <Button type="button" variant="ghost" disabled={busy || bars.length <= limit("min_items", 2)} aria-label={`${index + 1}번째 줄 지우기`}
            onClick={() => setBars(bars.filter((_, at) => at !== index))}>지우기</Button>
        </div>)}
        <Button type="button" variant="outline" disabled={busy || bars.length >= limit("max_items", 5)}
          onClick={() => setBars([...bars, { label: "", value: "" }])}>막대 한 줄 더하기</Button>
      </div>
    </> : null}

    {key === "money_counter" ? <>
      <label className="vb-infographic__field">
        <span>위 문구(선택)</span>
        <Input value={lead} disabled={busy} maxLength={limit("lead", 20)} placeholder="첫 달 순매출" onChange={(event) => setLead(event.target.value)} />
      </label>
      <label className="vb-infographic__field">
        <span>금액</span>
        <Input value={amount} disabled={busy} inputMode="numeric" placeholder="12345678" onChange={(event) => setAmount(event.target.value)} />
      </label>
      <div className="vb-infographic__field" role="group" aria-label="금액 앞 기호">
        <span>금액 앞 기호</span>
        <div className="vb-infographic__styles">
          {PREFIXES.map((item) => <Button key={item.label} type="button" variant="ghost" className="vb-infographic__style"
            aria-pressed={prefix === item.value} disabled={busy} onClick={() => setPrefix(item.value)}>{item.label}</Button>)}
        </div>
      </div>
      <label className="vb-infographic__field">
        <span>뒤에 붙일 말(선택)</span>
        <Input value={suffix} disabled={busy} maxLength={limit("suffix", 4)} placeholder="원" onChange={(event) => setSuffix(event.target.value)} />
      </label>
      <label className="vb-infographic__field">
        <span>아래 문구(선택)</span>
        <Input value={caption} disabled={busy} maxLength={limit("caption", 30)} placeholder="광고비 · 수수료 제외 후" onChange={(event) => setCaption(event.target.value)} />
      </label>
    </> : null}

    {key === "step_list" ? <div className="vb-infographic__facts" role="group" aria-label="단계">
      {steps.map((step, index) => <div className="vb-infographic__fact" key={index}>
        <Input aria-label={`${index + 1}번째 단계`} value={step} disabled={busy} maxLength={limit("step", 24)} placeholder="상품 소싱하고 가격 정하기"
          onChange={(event) => setSteps(steps.map((current, at) => (at === index ? event.target.value : current)))} />
        <Button type="button" variant="ghost" disabled={busy || steps.length <= limit("min_items", 2)} aria-label={`${index + 1}번째 단계 지우기`}
          onClick={() => setSteps(steps.filter((_, at) => at !== index))}>지우기</Button>
      </div>)}
      <Button type="button" variant="outline" disabled={busy || steps.length >= limit("max_items", 5)}
        onClick={() => setSteps([...steps, ""])}>단계 한 줄 더하기</Button>
    </div> : null}

    {template ? <label className="vb-infographic__field">
      <span>길이(초)</span>
      <Input value={seconds} disabled={busy} inputMode="decimal" onChange={(event) => setSeconds(event.target.value)} />
      {!durationOk ? <span className="vb-infographic__hint">길이는 {minimum}초에서 {maximum}초 사이로 적어 주세요.</span> : null}
    </label> : null}

    {hasForbidden ? <p className="vb-infographic__warning" role="alert">{"< > 기호는 쓸 수 없어요."}</p> : null}

    <Button type="button" disabled={!ready} onClick={create} className="vb-infographic__make">
      {busy ? "만드는 중… 1분 안쪽으로 걸려요" : "모션 만들기"}
    </Button>

    {failed ? <p className="vb-infographic__failed" role="alert">{failed}</p> : null}
    {made ? <div className="vb-infographic__made" role="status">
      <p>
        {made.result.library_asset_id
          ? made.inProject
            ? <>다 만들었어요. 이 프로젝트 영상 목록에 넣어 뒀으니 <strong>장면을 고르고 적용</strong>을 눌러 쓰세요.</>
            : <>다 만들었어요. 자료실 영상에 넣어 뒀으니 <strong>자료실에서 가져오기</strong>로 꺼내 쓰세요.</>
          : <>모션은 만들었지만 자료실에 넣지 못했어요. 잠시 뒤 다시 만들어 주세요.</>}
      </p>
      <p className="vb-infographic__hint">적은 숫자와 글만 들어가요. 영상에 쓰기 전에 한 번 보고 읽어 보세요.</p>
    </div> : null}
  </div>;
}

function defaultSeconds(sceneSeconds: number | null, template: MotionTemplate): number {
  if (sceneSeconds === null || !Number.isFinite(sceneSeconds) || sceneSeconds <= 0) return template.default_duration_sec;
  const rounded = Math.round(sceneSeconds * 10) / 10;
  return Math.min(template.max_duration_sec, Math.max(template.min_duration_sec, rounded));
}

function replaceAt(rows: BarRow[], index: number, row: BarRow): BarRow[] {
  return rows.map((current, at) => (at === index ? row : current));
}

/** 서버가 준 이유를 창작자의 말로 옮긴다(§10.13). 문제 목록이 객체로 와도 `ApiRequestError`는
 *  이유 이름만 들고 온다 -- 그래서 이유 이름으로 가른다. */
function messageFor(error: unknown): string {
  const reason = error instanceof ApiRequestError ? (error.reason ?? error.detail ?? "") : "";
  if (reason === "motion_generation_unavailable" || reason === "motion_bridge_not_configured") return "모션 만들기가 아직 꺼져 있어요. VideoBox를 다시 켜 주세요.";
  if (reason === "motion_bridge_not_running") return "모션 만드는 프로그램이 꺼져 있어요. VideoBox를 다시 켜 주세요.";
  if (reason === "motion_engine_not_prepared") return "모션 도구를 처음 한 번 준비하는 중이에요. 몇 분 뒤 다시 해 보세요.";
  if (reason === "motion_busy") return "다른 모션을 만드는 중이에요. 끝나면 다시 눌러 주세요.";
  if (reason === "motion_took_too_long") return "너무 오래 걸렸어요. 길이를 줄이고 다시 해 보세요.";
  if (reason === "motion_variables_invalid" || reason === "motion_template_unknown") return "적은 내용을 다시 확인해 주세요. 글이 너무 길 수 있어요.";
  return "만들지 못했어요. 잠시 뒤 다시 해 보세요.";
}
```

- [ ] **Step 5: 통과를 확인한다(하나 → 파일)**

```bash
(cd apps/web && npx vitest run src/features/editor/assets/MotionPanel.test.tsx -t "고를 수 있는 종류를")
(cd apps/web && npx vitest run src/features/editor/assets/MotionPanel.test.tsx)
```

예상: PASS, 그다음 전부 통과. 금액 카운터의 "$" 단추가 `getByRole("button", { name: "$" })`로 안 잡히면(아이콘 글꼴 등) 그 시험만 고치지 말고 멈춰 보고한다.

- [ ] **Step 6: 편집기에 단추와 팝업을 단다** — `EditorAssetBrowser.tsx`

1. 앵커 `import { InfographicPanel } from "./InfographicPanel";` 다음 줄: `import { MotionPanel } from "./MotionPanel";`
2. 앵커 `  const [infographicOpen, setInfographicOpen] = useState(false);` 다음 줄: `  const [motionOpen, setMotionOpen] = useState(false);`
3. 앵커 줄(`className="vb-editor-assets__infographic"`가 든 `<Button …>인포그래픽</Button>` 한 줄) 다음에:

```tsx
        {/* **설명 모션(2026-10-08 결정 2단계).** 결과가 영상 한 편이라 인포그래픽(그림 한 장)
            옆자리다. 고를 칸이 여러 줄이라 도크에 밀어 넣지 않고 팝업으로 연다. */}
        <Button type="button" variant="outline" className="vb-editor-assets__motion" onClick={() => setMotionOpen(true)}>모션</Button>
```

4. 앵커 `        <Dialog open={narrationOpen} onOpenChange={setNarrationOpen}>` **앞**에:

```tsx
        <Dialog open={motionOpen} onOpenChange={setMotionOpen}>
          <DialogContent className="vb-dialog-content">
            <DialogHeader>
              <DialogTitle>모션 만들기</DialogTitle>
              <DialogDescription>숫자와 글을 적으면 움직이는 설명 영상으로 만들어 이 프로젝트에 넣어요.</DialogDescription>
            </DialogHeader>
            <MotionPanel projectId={projectId} sceneSeconds={target ? target.endSec - target.startSec : null} onMade={onMediaAdded} />
          </DialogContent>
        </Dialog>
```

(`vb-editor-assets__motion`에는 CSS가 없다 — `vb-editor-assets__infographic`에도 전용 규칙이 있는지 `grep -n "vb-editor-assets__infographic" apps/web/src/styles/*.css`로 확인한다. 있으면 같은 선택자에 `, .vb-editor-assets__motion`을 **더하는 것은 CSS 변경이라 하지 않고** 멈춰 보고한다. 2026-10-08 기준으로는 규칙이 없다.)

`EditorAssetBrowser.test.tsx` 끝(또는 `describe("편집기에서 내레이션 열기"` 블록 다음)에:

```tsx
/** 설명 모션(2026-10-08 결정 2단계). 편집기를 떠나지 않고 연다. */
describe("편집기에서 모션 만들기 열기", () => {
  it("편집기를 떠나지 않고 모션 만들기를 연다", async () => {
    vi.spyOn(apiModule.api, "listMotionTemplates").mockResolvedValue({ templates: [] } as never);
    render(<EditorAssetBrowser cards={cards as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} projectId="project-a" />);

    fireEvent.click(screen.getByRole("button", { name: "모션" }));

    expect(await screen.findByRole("dialog", { name: "모션 만들기" })).toBeVisible();
  });

  it("프로젝트를 모르면 모션 만들기를 열지 않는다", () => {
    render(<EditorAssetBrowser cards={cards as never} target={null as never} isSaving={false} onPreview={vi.fn()} onApply={vi.fn()} onApplyOverlay={vi.fn()} />);

    expect(screen.queryByRole("button", { name: "모션" })).toBeNull();
  });
});
```

```bash
(cd apps/web && npx vitest run src/features/editor/assets/EditorAssetBrowser.test.tsx -t "모션")
```

예상: 처음엔 `Unable to find role="button" and name "모션"` — 단추를 단 뒤 다시 돌려 PASS(이 Step에서 RED→GREEN 순서로 한다: 시험을 먼저 붙이고 한 번 돌려 실패를 본 뒤 1~4를 넣는다).

- [ ] **Step 7: 좁은 확인 — 문구·조작 게이트·타입**

```bash
(cd apps/web && npx vitest run src/user-copy-policy.test.ts src/task22-parity-owners.test.ts src/features/editor/assets/InfographicPanel.test.tsx src/features/editor/assets/EditorAssetBrowser.test.tsx src/features/editor/assets/MotionPanel.test.tsx)
(cd apps/web && npx tsc --noEmit)
git diff --stat -- apps/web/src/styles
```

예상: 전부 통과(알려진 실패 없음 — 그 건은 `editor-workbench.test.tsx`다), 타입 오류 0, 스타일 diff 없음.

- [ ] **Step 8: 검증 넷과 커밋**

- 갭: Step 1~7. 실물 화면은 Task 8.
- 배선: `grep -rn "createMotion(\|listMotionTemplates(" apps/web/src --include=*.tsx | grep -v test` → `MotionPanel.tsx` 2줄. `grep -rn "<MotionPanel" apps/web/src --include=*.tsx | grep -v test` → `EditorAssetBrowser.tsx` 1줄.

```bash
git add apps/web/src/api.ts apps/web/src/features/editor/assets/MotionPanel.tsx apps/web/src/features/editor/assets/MotionPanel.test.tsx apps/web/src/features/editor/assets/EditorAssetBrowser.tsx apps/web/src/features/editor/assets/EditorAssetBrowser.test.tsx
git commit -m "$(cat <<'EOF'
feat(web): 편집기 `모션` -- 막대 비교·금액 카운터·단계 목록을 적어 만들고 이 프로젝트로 가져온다

기본 길이는 고른 장면 길이(짧으면 숫자가 처음부터 다시 돈다). 실패 이유마다 다른 말을 하고,
< > 기호는 보내기 전에 막는다. 스타일은 인포그래픽 패널 것을 그대로 쓴다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: 측정 — 30초 클립·연속 5번·동시 요청·투명 webm (실제 숫자)

**Files:**
- 없음(실측만). 숫자는 Task 8 인계에 옮긴다. 산출물은 `artifacts/motion-measure/`(gitignore).

**Interfaces:**
- Consumes: Task 2 다리(`--render-sample`, `POST /render`).
- Produces: 실측 표(시간·크기·md5·상태 코드).

기준선(스파이크): 6초 1080p30 = 12~16초, 0.3~1MB. 이 Task는 **재기만** 한다. 기준선의 1.5배(6초 클립 24초)를 넘으면 원인(작업자 수·GPU 경합·`lms ps`로 모델 적재)을 먼저 적고 멈춘다 — 고치지 않는다.

- [ ] **Step 1: 같은 것을 다섯 번 연달아(재시작 직후 첫 성공은 증거가 아니다)**

```bash
mkdir -p artifacts/motion-measure
for i in 1 2 3 4 5; do .venv/Scripts/python.exe scripts/host_motion_service.py --render-sample bar_compare --duration 6 --out artifacts/motion-measure/bar-6s-$i.mp4; done
md5sum artifacts/motion-measure/bar-6s-*.mp4
```

예상: 다섯 줄 모두 성공, 각 `elapsed_sec`를 적는다(12~16초 근처). md5가 같은지/다른지 **있는 그대로** 적는다(바이트 결정성은 결정 문서의 "아직 모르는 것").

- [ ] **Step 2: 30초 클립(셋 다)과 투명 webm**

```bash
for key in bar_compare money_counter step_list; do .venv/Scripts/python.exe scripts/host_motion_service.py --render-sample $key --duration 30 --out artifacts/motion-measure/$key-30s.mp4; done
.venv/Scripts/python.exe scripts/host_motion_service.py --render-sample bar_compare --duration 30 --layout overlay --out artifacts/motion-measure/bar-30s-overlay.webm
for f in artifacts/motion-measure/*-30s*; do ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,r_frame_rate:format=duration,size -of csv=p=0 "$f"; done
```

예상: 모두 180초 상한 안(스파이크 비율로는 약 40~60초). 길이 30.0±0.05. 크기를 적는다. 상한(180초)에 가까우면(150초 넘으면) 결정 필요 사항으로 적는다.

- [ ] **Step 3: 동시 두 요청 → 하나는 200, 하나는 409**

다리를 띄운다(Task 5 이후라면 `owner-ready`가 이미 띄웠다 — `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8202/diagnostics`가 `401`이면 떠 있는 것). 그다음:

```bash
.venv/Scripts/python.exe -c "import json;json.dump({'template':'bar_compare','variables':{'title':'동시 요청','unit':'만','bars':[{'label':'가','value':10},{'label':'나','value':5}]},'duration_sec':6,'layout':'full'},open('artifacts/motion-measure/body.json','w',encoding='utf-8'),ensure_ascii=False)"
TOKEN=$(grep -E '^VIDEOBOX_BRIDGE_TOKEN=' .env.container | head -1 | cut -d= -f2- | tr -d '\r"')
post() { curl -s -o /dev/null -w "%{http_code} %{time_total}\n" -X POST -H "X-VideoBox-Bridge-Token: $TOKEN" -H "Content-Type: application/json" --data-binary @artifacts/motion-measure/body.json http://127.0.0.1:8202/render; }
post > artifacts/motion-measure/a.txt & sleep 1; post > artifacts/motion-measure/b.txt; wait
cat artifacts/motion-measure/a.txt artifacts/motion-measure/b.txt
unset TOKEN
```

예상: 한 줄은 `200 <12~16>`, 다른 줄은 `409 <1초 미만>`(기다리지 않고 바로 거절). 둘 다 200이면 잠금이 안 걸린 것이다 — 멈추고 보고한다.

- [ ] **Step 4: 기록**

표 하나로 정리해 둔다(Task 8 인계에 그대로 붙인다): 6초×5 시간·크기·md5 같음 여부, 30초×3 시간·크기, 30초 webm 시간·크기, 동시 요청 두 줄. 이 Task는 커밋할 파일이 없다.

---

### Task 8: 실물로 닫기 — 재빌드·화면·렌더 픽셀·전체 시험·문서·인계·푸시

**Files:**
- Create: `docs/handoffs/<실행일>-motion-graphics-step2.ko.md`
- Modify: `CLAUDE.md`(`| **최신 세션 인계** | … |` 한 줄만)
- Modify: `docs/development-fast-path.ko.md`(§10.14 다리 토큰 줄)
- Modify: `THIRD_PARTY_NOTICES.md`(절 하나)
- Modify: `docs/superpowers/plans/2026-10-02-audit-00-master.ko.md`(§1 표 아래 한 줄)
- (같은 날 살아 있는 인계가 있으면) 그 문서 맨 위에 `**대체됨:** <새 문서 경로>` 한 줄

**Interfaces:**
- Consumes: Task 0~7 전부
- Produces: 실측 기록(인계 문서), 푸시

- [ ] **Step 1: 손으로 띄운 옛 모션 다리가 있으면 끈다(명령줄로 확인한 뒤에만)**

```powershell
$repo = (Resolve-Path .).Path
foreach ($listener in @(Get-NetTCPConnection -LocalPort 8202 -State Listen -ErrorAction SilentlyContinue)) {
  $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
  if ([string]$owner.CommandLine -like "*$repo\scripts\host_motion_service.py*") { Stop-Process -Id $listener.OwningProcess -Force; "stopped pid=$($listener.OwningProcess)" }
  else { "FOREIGN (끄지 않았다): pid=$($listener.OwningProcess) name=$($owner.Name)" }
}
```

예상: 없거나 `stopped …`. `FOREIGN`이면 멈추고 보고한다. 다른 다리(8199·8200·8201)는 코드가 안 바뀌었으니 건드리지 않는다. 토큰은 묶음 A 때 이미 만들어져 있어(Task 0 Step 2에서 `1`) 새 다리가 바로 쓴다.

- [ ] **Step 2: 컨테이너를 다시 짓고 다리를 띄운다**

```powershell
.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild
```

예상: 전체 `pass`, `motion_bridge` 행 `모션 다리를 백그라운드로 켰습니다`, `preparing: false`(이 컴퓨터는 준비돼 있다). 확인(값은 찍지 않는다):

```bash
docker exec 65_videobox-videobox-workspace-1 sh -c 'echo "$VIDEOBOX_MOTION_BRIDGE_URL"'
docker exec 65_videobox-videobox-workspace-1 test ! -e /app/scripts/motion-bridge && echo motion-tools-not-in-image
curl -s http://127.0.0.1:5173/api/library/motion-templates | .venv/Scripts/python.exe -c "import json,sys;print([t['key'] for t in json.load(sys.stdin)['templates']])"
curl -s -o /dev/null -w "bridge no-token %{http_code}\n" http://127.0.0.1:8202/diagnostics
```

예상: `http://host.docker.internal:8202`, `motion-tools-not-in-image`, `['bar_compare', 'money_counter', 'step_list']`, `bridge no-token 401`.

- [ ] **Step 3: 역방향 — 화면에서 owner 길로 밟는다(1440×900)**

claude-in-chrome(실제 크롬, 화면이 그려진다 — 내장 브라우저 창은 전이·rAF가 멈춰 오진한다)로 http://127.0.0.1:5173 → Ctrl+F5 → 아무 프로젝트의 편집기 → 장면 하나를 고른다 → 미디어 더하기 줄의 `모션` → `막대 비교` → 제목 `월 수익 비교`, 단위 `만`, 막대 셋(`쿠팡 1280`, `스마트스토어 860`, `자사몰 430`) → `길이(초)`가 고른 장면 길이로 차 있는지 본다 → `모션 만들기`.
- 누르는 즉시 단추가 `만드는 중… 1분 안쪽으로 걸려요`로 잠기는지(침묵 구간이 없는지) 본다.
- 끝나면 `다 만들었어요. 이 프로젝트 영상 목록에 넣어 뒀으니…`가 뜨는지, 팝업을 닫으면 영상 목록에 새 카드(`월-수익-비교.mp4`)가 있는지 본다.
- 그 카드 `적용` → 미리보기에서 그 장면이 막대 영상으로 바뀌는지 본다.
- 같은 흐름을 `금액 카운터`(금액 `12345678`, 기호 ₩)·`단계 목록`(셋)으로 한 번씩. 각 화면을 캡처해 인계에 남긴다.
- 팝업을 연 채로 창을 375 폭으로 줄여(resize) 입력칸·단추가 가로로 넘치지 않는지, 팔레트가 다크 그대로인지 본다. 캡처한다.

- [ ] **Step 4: 동작 — 자료실 파일을 재고 프레임을 눈으로 본다**

```bash
mkdir -p artifacts/motion-step2-final
curl -s "http://127.0.0.1:5173/api/library/assets?media_type=broll&limit=500" -o artifacts/motion-step2-final/broll.json
.venv/Scripts/python.exe -c "
import json,urllib.request
assets=[a for a in json.load(open('artifacts/motion-step2-final/broll.json',encoding='utf-8'))['assets'] if (a.get('provenance') or {}).get('source_kind')=='generated_motion' or 'motion' in json.dumps(a.get('user_metadata',{}))]
assets=sorted(assets,key=lambda a:a.get('created_at') or '')[-3:]
for i,a in enumerate(assets):
    data=urllib.request.urlopen('http://127.0.0.1:5173'+a['preview_url']).read()
    open(f'artifacts/motion-step2-final/m{i}.mp4','wb').write(data); print(a['library_asset_id'], a['user_metadata'].get('filename'), len(data))
"
for f in artifacts/motion-step2-final/m*.mp4; do ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,pix_fmt,width,height,r_frame_rate:format=duration -of csv=p=0 "$f"; ffmpeg -hide_banner -loglevel error -y -sseof -0.5 -i "$f" -frames:v 1 "${f%.mp4}.png"; done
```

예상: 셋, 각각 `h264,yuv420p,1920,1080,30/1,<적은 길이±0.05>`. 자료실 자산에서 생성 출처를 찾는 열쇠가 `provenance`가 아니면(`library_assets` 응답 모양에 따라) `user_metadata`·`filename`으로 찾는다 — 찾은 방법을 인계에 적는다. PNG 셋을 Read로 **눈으로** 본다: 한글이 또렷한가, 숫자·₩·쉼표가 맞는가(1,280만 / ₩12,345,678 / 단계 셋), 판 밖으로 나간 글이 없는가.

이어서 **완성본까지** 간다: Step 3에서 `적용`한 프로젝트의 결과 화면에서 평소처럼 완성본을 만든다. 나온 mp4에서 그 장면 가운데 시각의 프레임을 뽑아 모션 프레임과 같은 그림인지 본다(막대 색 `#ffb020` 근처 화소가 있는지 PIL로 한 점 재기, 위치는 가장 큰 막대 줄 `y≈355`, `x≈700`):

```bash
ffmpeg -hide_banner -loglevel error -y -ss <장면 가운데 초> -i "<완성본 경로>" -frames:v 1 artifacts/motion-step2-final/final-scene.png
.venv/Scripts/python.exe -c "from PIL import Image;im=Image.open('artifacts/motion-step2-final/final-scene.png').convert('RGB');print(im.size, im.getpixel((700,355)))"
```

예상: 크기는 출력 해상도, 화소가 주황 계열(R>200, G 140~200, B<80). 장면보다 짧은 길이로 만들었다면 반복(loop)되는 것도 그 시각에 맞춰 확인해 적는다.

- [ ] **Step 5: 배선 — 전체 grep**

```bash
grep -rn "check_request(" scripts/host_*_service.py | wc -l
grep -rn "bridge_request_headers()" packages --include=*.py | wc -l
grep -rn "MotionService(" services/api/src --include=*.py
grep -rn "createMotion(\|materializeLibraryAsset(" apps/web/src/features/editor/assets/MotionPanel.tsx
grep -rn "<MotionPanel" apps/web/src --include=*.tsx | grep -v test
grep -rn "motion_bridge" scripts/owner-ready.ps1 | wc -l
grep -rn "VIDEOBOX_MOTION_BRIDGE_URL" compose.yaml packages --include=*.py --include=*.yaml | wc -l
```

예상: `4`(다리 넷), `4`(부르는 쪽 넷), `main.py` 1, `MotionPanel.tsx` 2, `EditorAssetBrowser.tsx` 1, 1 이상, 2.

- [ ] **Step 6: 전체 시험(혼자, 마지막에)**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --ignore=tests/test_mcp_server.py tests
(cd apps/web && npx vitest run)
npm --prefix apps/web run build
```

예상: 파이썬은 알려진 1건(`test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure`)만 빨갛다(약 45분). vitest는 알려진 1건(`gives the material dock back…`)만. 빌드 성공. 다른 실패는 그 시험 **하나만** 다시 돌려 보고, 그래도 빨가면 이 계획 변경 탓인지 `git log -p`로 그 파일의 마지막 변경을 본다(세션 전 커밋 `d97cfb637`에서 같은 시험을 돌려 비교할 수 있다). 시간이 되면 e2e도 돌린다: `npm --prefix apps/web run test:e2e`(포트 4173 점거자가 있으면 먼저 비운다 — 알려진 거짓 실패).

- [ ] **Step 7: 문서 넷**

1. `docs/development-fast-path.ko.md` §10.14 — 앵커 `다리 셋(목소리 8199·캡컷 8200·그림 8201)은 공유 토큰을 요구한다(2026-10-02, owner 결정).`를 `다리 넷(목소리 8199·캡컷 8200·그림 8201·모션 8202)은 공유 토큰을 요구한다(2026-10-02, owner 결정; 모션은 2026-10-08 결정으로 추가).`로 바꾼다. 같은 항목 끝에 한 줄을 더한다: `모션 다리(8202)는 이 컴퓨터의 하이퍼프레임 0.8.140만 부르고, 렌더 중에는 네트워크를 쓰지 않는다(템플릿에 바깥 주소 없음, 죽은 프록시). 처음 준비(npm 설치·브라우저 받기)만 인터넷을 쓴다 — scripts/prepare-motion.ps1.`
2. `THIRD_PARTY_NOTICES.md` — 앵커 `## 자막 글꼴 (컨테이너에 함께 배포)` **앞**에 절 하나:

```markdown
## 설명 모션 엔진 (호스트 전용, 배포하지 않음)

`scripts/motion-bridge/package.json`이 npm `hyperframes` **0.8.140**(Apache-2.0, HeyGen)을
이 컴퓨터에만 설치한다. 컨테이너 이미지에는 들어가지 않고(`.dockerignore`), 소스를 고치거나
옮겨 싣지 않는다. 그릴 때 쓰는 브라우저(chrome-headless-shell)는 하이퍼프레임이 사용자 캐시
(`~/.cache/hyperframes`)에 받는다. 템플릿 셋(`scripts/motion-bridge/templates/`)은 VideoBox가
직접 쓴 것이다. 라이선스: https://github.com/heygen-com/hyperframes/blob/main/LICENSE
```

   그다음 `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_editor_ui_source_provenance.py`가 통과하는지 본다(표가 아니라 절이라 영향이 없어야 한다).
3. `docs/superpowers/plans/2026-10-02-audit-00-master.ko.md` §1 표 바로 아래 문단(`**계획서끼리 병렬로 돌리지 않는다.**`) 앞에 한 줄: `> 2026-10-08: 설명 모션 2단계(`2026-10-08-motion-graphics-step2.ko.md`)가 B–F보다 먼저 들어왔다. `api.ts`(타입 셋·메서드 둘), `owner-ready.ps1`(모션 다리 블록), `models.py`(모션 모델 넷), `main.py`(모션 서비스·라우터)가 바뀌었다 — 앵커는 문자열로 찾는다.`
4. 인계 문서 `docs/handoffs/<실행일>-motion-graphics-step2.ko.md`(기록체, 쉬운 말):
   - 한 일(Task별 한 줄), 실측 표(Task 2 Step 8~9, Task 5 준비 시간, Task 7 표 전체, Step 2~4 결과·캡처 경로).
   - **안 한 것·남은 것**: 유진 연결(3단계 — 세 겹: 의도·적용기·안내문, 이 계획 "3단계로 넘기는 것"을 옮겨 적는다), 투명 오버레이(Task 9 — 했으면 그 결과, 안 했으면 이유: 렌더러가 VP9 알파를 못 읽는다), 옛 export overlay 경로(`-loop 1`), 세로(9:16) 템플릿 없음, 30초 넘는 클립 없음(상한), 같은 입력 바이트 결정성(Task 7 결과 그대로), 첫 준비를 처음부터 다시 받는 시험은 안 함(270MB), 캡컷 내보내기에서 모션 클립 확인 안 함(하지 않았으면).
   - 재사용 게이트(§8.3): 재사용 — 그림 다리의 판단/껍데기 분리·`_Handler` 모양·문지기·토큰·`bridge_request_headers`·`owner-ready` 다리 블록·`InfographicHostBridge`의 주소 검사(부분 이식)·`LibraryIngestService`·`materializeLibraryAsset`·인포그래픽 패널 CSS. 새로 만든 것 — 템플릿 셋, 모션 다리, 변수 검사, 준비 스크립트. 뺀 것과 이유 — GSAP(저장소 반입은 owner 승인 필요, 없어도 오프라인으로 된다), `--variables`(스파이크에서 안 재 봤다 — `data.js`로 같은 일을 한다), 리모션(결정 그대로 exclude), open-design 템플릿(프롬프트뿐). 경계: 팔레트·사람 게이트 그대로, 네트워크는 이 기계 8202 하나가 늘었다(결정 문서 승인).
   - 결정 필요(있으면 아래 "owner에게" 목록을 옮긴다).
   - `CLAUDE.md`의 `| **최신 세션 인계** | … |` 줄을 새 문서로 바꾸고, 같은 날짜의 살아 있는 인계(예: `2026-10-08-audit-bundle-a-security-tools-rename.ko.md`)가 있으면 그 문서 맨 위에 `**대체됨:** docs/handoffs/<실행일>-motion-graphics-step2.ko.md`를 넣는다.

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_handoff_entry_point.py tests/test_editor_ui_source_provenance.py
```

예상: 통과(진입 지도가 최신을 가리키고, CLAUDE.md가 260줄·8,000자 안).

- [ ] **Step 8: 커밋과 푸시(확인과 푸시는 따로)**

```bash
git add docs/handoffs/ CLAUDE.md docs/development-fast-path.ko.md THIRD_PARTY_NOTICES.md docs/superpowers/plans/2026-10-02-audit-00-master.ko.md
git commit -m "$(cat <<'EOF'
docs: 설명 모션 2단계 인계(다리 8202·템플릿 셋·편집기 모션 만들기 실측)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
git status --short
git log --oneline -10
```

`git status`가 깨끗하고(`.anchor/` 제외) 이 계획의 커밋(Task 1~6, 8 — 템플릿 크기 수정 커밋이 있으면 그것까지)이 보이는 것을 확인한 **다음에** 따로:

```bash
git push origin main
```

`--force` 금지. 권한이 막으면 우회하지 않고 owner에게 `git push origin main` 직접 실행 또는 허용 규칙 `Bash(git push origin main)` 추가를 요청한다. 원격이 앞서 거절되면 `git pull --rebase origin main` → 좁은 시험(`tests/test_api_motions.py`, `MotionPanel.test.tsx`) → 푸시. 충돌은 멈추고 보고.

---

### Task 9 (별도, 마지막): 투명 오버레이 — 렌더러가 VP9 알파를 읽고, 화면이 `작은 창(투명)`을 연다

**왜 따로인가:** 세션 모델과 렌더 길에는 영상 오버레이(`image_overlay`, 자리·크기·페이드)가 이미 있지만, 제품 렌더 길이 webm을 `-i`로만 열어 **알파가 사라진다**(Task 0 조사 6). 그대로 열면 대표님이 `화면에 얹기`를 눌렀을 때 미리보기(브라우저)에는 투명하게 보이다가 완성본에는 바탕이 칠해진 상자가 나온다 — 화면과 결과가 어긋나는 가장 나쁜 실패다. 렌더러를 고치는 일이라 2단계 핵심(Task 0~8)과 떼어 따로 검증·커밋·푸시한다. Task 8 푸시가 끝난 뒤에 시작한다. 시작 전에 owner에게 진행 여부를 묻지 않아도 된다(결정 문서 3번 "오버레이도 쓴다" 범위 안) — 단, Step 1이 막히면 거기서 멈춘다.

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py`
- Modify: `services/api/src/videobox_api/models.py`(`MotionCreateRequest.layout`)
- Modify: `apps/web/src/api.ts`(`MotionRequest.layout`), `apps/web/src/features/editor/assets/MotionPanel.tsx`, `MotionPanel.test.tsx`
- Modify: `tests/test_api_motions.py`(Task 4의 `{"layout": "overlay"}` 거절 줄을 뒤집는다)
- Test: `tests/test_motion_overlay_alpha.py`(새 파일)

**Interfaces:**
- Consumes: `FfmpegFinalRenderer`(`_has_stream` 모양, `source_paths`, `track_overlay_indices`, `single_thread_source_indices`), `update_segment_image_overlay`, Task 4·6의 모델·패널.
- Produces: `FfmpegFinalRenderer._is_vp9_with_alpha(path: Path) -> bool`; 렌더 입력 루프에서 그 입력 앞에 `["-c:v", "libvpx-vp9"]`. API `layout: Literal["full", "overlay"]`. 화면 모양 선택 `전체 화면`·`작은 창(투명)`.

- [ ] **Step 1: 컨테이너 ffmpeg가 VP9 알파를 풀 수 있는지 본다**

```bash
docker exec 65_videobox-videobox-workspace-1 sh -c 'ffmpeg -hide_banner -decoders 2>/dev/null | grep -c libvpx-vp9'
ffmpeg -hide_banner -decoders 2>/dev/null | grep -c libvpx-vp9
```

예상: 둘 다 `1`. 컨테이너가 `0`이면 **멈춘다**(이미지 ffmpeg를 바꾸는 일은 별도 결정) — 인계에 적고 Task 9를 후속으로 남긴다.

- [ ] **Step 2: 실패하는 시험을 쓴다** — `tests/test_motion_overlay_alpha.py`

`tests/test_overlay_video_sound.py::test_plan_render_survives_a_soundless_photo_overlay_with_source_audio_kept`의 모양(실제 `LocalProjectStore`·ffmpeg로 만든 원본·`build_editing_session`·`update_segment_image_overlay`·`materialize_editing_session_timeline`·`renderer.render_timeline_to_mp4(..., composition_plan=renderer.extract_composition_plan(timeline=timeline))`)을 그대로 따른다. 다른 점:

```python
pytestmark = pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg가 있어야 잰다")

def _alpha_webm(path: Path) -> None:
    """가운데만 불투명 빨강, 나머지는 완전 투명(저장된 색은 흰색). 알파를 버리면 모서리가 하얗게 나온다."""
    _generate([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=white@0.0:s=320x240:r=15:d=4,format=yuva420p",
        "-vf", "drawbox=x=110:y=80:w=100:h=80:color=red@1.0:t=fill:replace=1",
        "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", str(path),
    ])


def test_a_transparent_motion_overlay_keeps_its_transparency_in_the_final_render(tmp_path: Path) -> None:
    ...  # 검은 broll 4초 위 scene-overlay(1~3초)에 _alpha_webm을 image_overlay로 얹고(프리셋 없음 = 화면 크기),
    ...  # 320x240·15fps로 렌더한 뒤 1.5초 프레임을 뽑는다.
    frame = tmp_path / "frame.png"
    _generate(["ffmpeg", "-y", "-ss", "1.5", "-i", str(output_path), "-frames:v", "1", str(frame)])
    from PIL import Image
    image = Image.open(frame).convert("RGB")
    corner, center = image.getpixel((10, 10)), image.getpixel((160, 120))
    assert max(corner) < 40, f"투명 자리에 바탕이 칠해졌다: {corner}"
    assert center[0] > 150 and center[1] < 90, f"불투명한 가운데가 사라졌다: {center}"


def test_an_opaque_video_overlay_is_opened_the_old_way(tmp_path: Path) -> None:
    """mp4(알파 없음)에는 디코더를 강제하지 않는다 -- VP8·H.264에 libvpx-vp9를 걸면 렌더가 죽는다."""
    renderer = FfmpegFinalRenderer(store=LocalProjectStore(tmp_path))
    clip = tmp_path / "plain.mp4"
    _generate(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64:r=15:d=1", str(clip)])
    alpha = tmp_path / "alpha.webm"
    _alpha_webm(alpha)
    assert renderer._is_vp9_with_alpha(clip) is False
    assert renderer._is_vp9_with_alpha(alpha) is True
```

(`...` 두 줄 자리는 위 참조 시험의 본문을 그대로 옮기고 원본 셋만 바꾼다: 내레이션 사인파 4초, 검은 broll 320×240 4초, 오버레이 자산은 `AssetType.BROLL_VIDEO`로 등록한 `_alpha_webm` 파일, `update_segment_image_overlay(session=…, segment_id="scene-overlay", asset_id=<webm 자산>, text="")`.)

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_motion_overlay_alpha.py::test_a_transparent_motion_overlay_keeps_its_transparency_in_the_final_render
```

예상: FAIL `투명 자리에 바탕이 칠해졌다: (2xx, 2xx, 2xx)`(알파가 버려져 흰색). 다른 이유로 실패하면(예: 렌더 자체가 죽음) 멈추고 보고한다.

- [ ] **Step 3: 렌더러를 고친다(제품 길 한 곳)**

1. `_has_visual_stream` 바로 다음에 `_is_vp9_with_alpha(self, path: Path) -> bool`: `subprocess.run([self.ffprobe_binary, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name:stream_tags=alpha_mode", "-of", "json", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)`; 실패·`FileNotFoundError`·`TimeoutExpired`면 `False`; 첫 스트림의 `codec_name == "vp9"`이고 tags에서 열쇠를 소문자로 바꾼 `alpha_mode`가 `"1"`이면 `True`. 문서 문자열에 왜(알파 webm은 디코더를 지정해야 알파가 산다, 아무 webm에나 걸면 VP8이 죽는다)를 적는다.
2. 앵커 `        single_thread_source_indices: set[int] = set()` 다음 줄: `        vp9_alpha_source_indices: set[int] = set()`.
3. 앵커 `                track_overlay_indices[item.clip_id] = len(source_paths)` **앞**에: `                if not is_image and self._is_vp9_with_alpha(source):\n                    vp9_alpha_source_indices.add(len(source_paths))`(주석: 투명 모션 오버레이, 2026-10-08).
4. 앵커 `            command += ["-threads", "1" if source_index in single_thread_source_indices else threads]` 다음 줄(같은 들여쓰기): `            if source_index in vp9_alpha_source_indices:\n                command += ["-c:v", "libvpx-vp9"]` — `-i`보다 앞이어야 한다(그 아래에서 `-i`가 붙는다).

옛 export overlay 경로(`broll_with_overlays.mp4`)는 고치지 않는다(영상 오버레이가 그 길로 안 온다 — Task 0 조사 7). 갭에 적는다.

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_motion_overlay_alpha.py
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_overlay_video_sound.py tests/test_ffmpeg_final_renderer.py tests/test_exact_preview_artifact.py tests/test_overlay_motion.py
```

예상: 새 시험 둘 통과, 기존 렌더 시험 그대로 통과(미리보기 지문 `canonical_dict`는 입력 인자를 안 담으므로 안 바뀐다).

- [ ] **Step 4: API와 화면에서 `overlay`를 연다**

- `models.py`: `layout: Literal["full"] = "full"` → `layout: Literal["full", "overlay"] = "full"`, 문서 문자열의 "2단계에서 `full`만" 문장을 "`overlay`는 투명 webm — 완성본 렌더러가 VP9 알파를 읽는다(Task 9)"로 바꾼다.
- `tests/test_api_motions.py`: `test_a_request_that_cannot_be_a_motion_is_refused_at_the_door`의 매개변수에서 `{"layout": "overlay"}`를 빼고 `{"layout": "mov"}`를 넣는다. 그리고 시험 하나: `overlay`로 보내면 `service.calls[0]["layout"] == "overlay"`.
- `api.ts`: `MotionRequest.layout?: "full" | "overlay"`.
- `MotionPanel.tsx`: `길이(초)` 위에 모양 고르기(`role="group" aria-label="모양"`, 단추 `전체 화면`·`작은 창(투명)`, `aria-pressed`, 상태 `layout`), 보낼 때 `layout`을 싣는다. 결과 문구: `overlay`면 `다 만들었어요. 이 프로젝트 영상 목록에 넣어 뒀으니 장면을 고르고 화면에 얹기를 눌러 쓰세요. 크기·자리·나타나기는 오른쪽에서 고를 수 있어요.`. 
- `MotionPanel.test.tsx`: `작은 창(투명)`을 누르면 `layout: "overlay"`로 보내고 결과 문구에 `화면에 얹기`가 있다(시험 하나).

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_api_motions.py
(cd apps/web && npx vitest run src/features/editor/assets/MotionPanel.test.tsx src/user-copy-policy.test.ts src/task22-parity-owners.test.ts)
(cd apps/web && npx tsc --noEmit)
```

- [ ] **Step 5: 실물로 닫는다**

1. `.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild`(PowerShell).
2. 화면: 편집기 → 장면 고르기 → `모션` → `단계 목록`(셋) → `작은 창(투명)` → `모션 만들기` → 카드 `화면에 얹기` → 오른쪽에서 크기 `중간`, 자리 `오른쪽 아래`, 움직임 `나타났다 사라지기`(화면에 있는 이름 그대로) → 미리보기에서 바탕 영상이 카드 둘레로 보이는지 본다.
3. 완성본을 만들고 그 장면 가운데 프레임을 뽑아 **카드 바깥(오른쪽 아래 카드의 왼쪽 위 바깥 한 점)이 바탕 영상 화소**인지(검정·흰색 단색이 아닌지), 카드 안은 어두운 반투명 위 글자인지 Read로 본다. 페이드 시작 0.15초 프레임과 가운데 프레임의 카드 안 화소 밝기를 비교해 나타나기가 실제로 걸렸는지 숫자로 적는다.
4. 캡컷 내보내기에서 이 webm 오버레이가 어떻게 되는지는 **재 보기만** 하고(초안을 열어 보이는지) 인계에 적는다. 고치지 않는다.
5. 전체 시험은 Task 8에서 돌렸으므로 여기서는 `tests/test_ffmpeg_final_renderer.py`·`tests/test_overlay_*.py`·`tests/test_exact_preview_artifact.py`·`tests/test_api_motions.py`와 웹 vitest 전체·빌드만 다시 돌린다.

- [ ] **Step 6: 인계 보탬·커밋·푸시**

Task 8 인계 문서 끝에 `## Task 9 — 투명 오버레이` 절을 더한다(실측 화소·캡처·캡컷 결과·옛 export 경로 미수정). 같은 날짜면 새 인계 문서를 만들지 않는다.

```bash
git add packages/core-engine/src/videobox_core_engine/ffmpeg_final_renderer.py tests/test_motion_overlay_alpha.py services/api/src/videobox_api/models.py tests/test_api_motions.py apps/web/src/api.ts apps/web/src/features/editor/assets/MotionPanel.tsx apps/web/src/features/editor/assets/MotionPanel.test.tsx docs/handoffs/
git commit -m "$(cat <<'EOF'
feat(motion): 투명 모션 오버레이 -- 렌더러가 VP9 알파 webm을 알파째 읽고, 화면에 작은 창(투명)을 연다

알파 webm에만 libvpx-vp9 디코더를 건다(VP8·H.264는 그대로). 미리보기와 완성본이 같게 투명하다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
git status --short
git log --oneline -3
```

확인한 다음에 따로 `git push origin main`(규칙은 Task 8 Step 8과 같다).

---

## owner에게 물을 것 (실행 중 막히면)

| 항목 | 언제 | 물을 말 |
|---|---|---|
| 첫 준비 자동 받기 | Task 5 | "다른 컴퓨터에서 처음 켤 때 모션 도구 약 400MB를 자동으로 받게 해 두었습니다. 자동이 싫으시면 수동 실행으로 바꾸겠습니다." |
| 30초 넘는 모션 | Task 7 | "모션 길이를 30초까지로 막았습니다. 더 길게 쓰실 일이 있을까요?" |
| GSAP | (필요해질 때만) | "더 부드러운 움직임이 필요하면 GSAP(무료 라이선스)를 저장소에 넣어야 합니다. 넣을까요?" |
