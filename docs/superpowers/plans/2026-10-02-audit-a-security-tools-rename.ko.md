# 점검 후속 묶음 A — 개발 도구 패치·다리 토큰·인포그래픽 스크립트 금지·자료실 이름 바꾸기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 2026-10-01 전체 점검에서 남은 작은 것 넷(A1~A4)을 닫는다. vite·vitest를 패치 버전으로 올리고 배포 묶음에서 vite를 뺀다. 이 컴퓨터의 다리 셋(목소리 8199·캡컷 8200·그림 8201)이 공유 토큰·JSON·Host 검사 없이는 요청을 받지 않게 한다. 인포그래픽 HTML에 실행 코드가 들어가면 그리기 전에 거절한다. 자료실에서 이름을 바꿀 수 있게 하고, 글자가 깨진 이름 24개를 한 번에 되살린다.

**Architecture:** A1은 `apps/web/package.json`·`package-lock.json`만 바꾼다. A2는 받는 쪽에 표준 라이브러리만 쓰는 문지기 `scripts/host_bridge_guard.py`를 새로 두고 세 다리 스크립트가 요청마다 이를 먼저 부른다. 부르는 쪽 셋(`HostTTSBridgeProvider`, `CapCutHostBridge`, `InfographicHostBridge`)은 `videobox_provider_interfaces.host_bridge_auth.bridge_request_headers()`로 헤더를 만든다. 토큰은 `.env.container`의 `VIDEOBOX_BRIDGE_TOKEN` 한 줄이다. `owner-ready.ps1 -Mode Start`가 없을 때 한 번만 만들고, compose가 컨테이너에 넘기며, 다리는 같은 파일을 직접 읽는다. `.env.container`가 이미지에 실려 들어가던 구멍은 **맨 앞 Task 0**에서 따로, 가장 먼저 막는다(`.dockerignore`, 아래 "이번 조사에서 새로 찾은 것"). 마지막에 분위기 태그에 문장 조각이 섞이던 백엔드 원인(Task 9)을 고치고, 실물 검증은 Task 10이다. A3은 `check_infographic_html`이 `<script`·`on*=`·`javascript:`를 거절한다. A4는 `PATCH /api/library/assets/{asset_id}/filename`(store `rename_asset`)과 미리보기 칸의 인라인 편집, 그리고 실행 중인 API를 부르는 한 번용 수리 스크립트로 나뉜다.

**Tech Stack:** Python 3.12(FastAPI, pydantic v2, sqlite3, `http.server`, urllib), React 19 + TypeScript + vitest 2.1 + Testing Library, PowerShell 5.1(`owner-ready.ps1`), Docker compose(`owner-ready.ps1` 경유로만 조작).

**Spec:** docs/superpowers/2026-10-02-audit-follow-up-plan.ko.md + docs/decisions/2026-10-02-audit-follow-up-decisions.ko.md

## Global Constraints

- 작업 위치는 메인 체크아웃 `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`, 브랜치 `main`이다. 첫 단계에서 `git status --short`, `git log --oneline -3`을 확인한다. `.anchor/`는 이번 일과 무관한 미추적 폴더라 건드리지 않는다.
- 백엔드 시험은 반드시 `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider <file>::<test>`로 돌린다. bare `pytest`나 시스템 파이썬 결과는 근거로 쓰지 않는다. 전체 시험(약 50분)은 마지막 Task에서 혼자 돌리고, `--ignore=tests/test_mcp_server.py`를 붙인다(수집 에러로 0건이 되는 알려진 문제).
- 명령 예시는 **저장소 루트에서** 한 셸로 차례대로 친다고 가정한다(Git Bash). 웹 명령은 늘 괄호 subshell `(cd apps/web && ...)`로 감싼다. 괄호 없이 `cd apps/web`을 치면 그다음 줄의 `npm --prefix apps/web`·`.venv/...` 경로가 전부 틀어진다.
- 웹 시험은 `apps/web`에서 돌린다: `(cd apps/web && npx vitest run <file>)`. 저장소 루트에서 돌리면 jsdom이 깨진다. 타입 검사는 `(cd apps/web && npx tsc --noEmit)`, 빌드는 `npm --prefix apps/web run build`.
- 이미 알려진 실패 둘은 고치려 들지 않는다: `apps/web/src/features/editor/workbench/editor-workbench.test.tsx`의 "gives the material dock back the same way, without needing a second click", `tests/test_owner_ready_script.py::test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure`.
- 컨테이너는 `.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild`(PowerShell)로만 다시 짓고 켠다. `docker compose`를 직접 치지 않는다. 화면 주소는 http://127.0.0.1:5173이고, 재빌드 뒤에는 브라우저에서 Ctrl+F5를 한 번 누른다.
- `apps/web/src/task22-parity-owners.test.ts`는 파일마다 `data-native-control` 목록을 **정렬된 배열로 정확히** 대조한다. 새 단추·입력칸은 거기에 더한다(Task 7에 정확한 배열이 있다).
- `apps/web/src/user-copy-policy.test.ts`가 화면 문구의 금지어(provider, runtime, model, job, revision, pipeline, 시스템, 모델, 파이프라인 등)를 막는다. 화면 문구는 이름꼴 이름표와 짧은 해요체만 쓴다(`docs/development-fast-path.ko.md` §10.13).
- API는 Host·Origin 검사가 전역이다(`services/api/src/videobox_api/csrf_guard.py`). TestClient의 `testserver`는 허용되고, `videobox.test` 같은 이름은 400이다. 브라우저 밖 호출(curl·파이썬 urllib)은 Origin을 안 붙이므로 통과한다. 수리 스크립트는 이 점을 이용한다.
- 시험은 소켓을 못 연다(`tests/conftest.py`가 막는다). 다리 서버는 판단 함수와 HTTP 껍데기를 떼어 두었고, 이번에도 그 방식을 지킨다. 핸들러 배선 시험은 소켓 없이 핸들러 객체를 직접 만들어 부른다(Task 2).
- `docs/oss/editor-ui-source-map.json`이 `apps/web/package-lock.json`의 런타임 의존성 버전을 대조한다. A1 뒤에 `tests/test_editor_ui_source_provenance.py`를 꼭 돌린다. `ProductShell.tsx`는 이번 묶음에서 건드리지 않는다.
- 다리 코드를 바꾼 뒤 **이미 떠 있는 다리 프로세스는 옛 코드로 계속 돈다.** `owner-ready.ps1`은 포트가 열려 있으면 다시 띄우지 않는다(`scripts/owner-ready.ps1:1156-1168`, `:1206-1217`, `:1248-1259`). 그래서 Task 10에서 8199·8200·8201을 쥔 프로세스를 **명령줄로 VideoBox 다리인지 확인한 뒤** 직접 끄고 다시 띄운다.
- **배포 순서(끊김 없이):** 옛 다리는 토큰 헤더를 무시하고 다 받는다. 그래서 (1) 먼저 컨테이너를 새 코드로 다시 짓는다 — 이때 owner-ready가 토큰을 만들고 컨테이너는 토큰을 실어 보내기 시작하지만, 옛 다리가 그대로 받으므로 아무것도 안 깨진다. (2) 그다음 옛 다리를 끄고 owner-ready를 재빌드 없이 다시 돌려 새 다리를 띄운다. 거꾸로(새 다리 먼저, 옛 컨테이너가 토큰 없이 부름) 하면 더빙·캡컷·그림이 전부 401이 된다. Task 10 Step 1~4가 이 순서다.
- **중간에 멈추지 않는다.** Task 2~4가 커밋된 뒤 Task 10 Step 4가 끝나기 전에 컴퓨터를 다시 켜거나 바탕화면 VideoBox 아이콘(`Start-VideoBox.ps1` → `owner-ready.ps1 -Mode Start`, 재빌드 없음)을 누르면, 새 다리(토큰 요구)가 옛 이미지 컨테이너(토큰 없음)와 만나 401이 난다. 이 계획은 Task 2부터 Task 10 Step 4까지 한 세션에서 이어서 한다. 어쩔 수 없이 멈췄으면 다시 시작할 때 Task 10 Step 1부터 한다.
- 유진에게 "이름 바꾸기"를 여는 일(의도·적용기·프로필 안내문)은 **이 계획 밖**이다. 묶음 F(유진 계획서)에서 한다. 이 계획은 화면과 API까지만 한다. 갭 보고에 그렇게 적는다.
- 커밋은 Task마다 한다. 메시지는 한국어로 쓰고 맨 끝 줄은 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`이다. 푸시는 마지막 Task의 검증이 끝난 뒤 `git push origin main`(--force 금지)으로 한다. **도구 권한이 푸시를 막으면 우회하지 않는다**(다른 명령·다른 원격·설정 변경 금지). 멈추고 owner에게 `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`에서 `git push origin main`을 직접 실행하거나 허용 규칙 `Bash(git push origin main)`을 더해 달라고 알린다.
- 모든 Task는 닫을 때 검증 넷을 한다. **갭**: 이 계획의 Step과 대조하고 안 한 것을 적는다. **역방향**: 실제 런타임에서 확인한다. **동작**: 결과를 잰다. **배선**: grep으로 실제 부르는 자리를 센다. 역방향·동작은 컨테이너 재빌드가 필요하므로 Task 10에서 한꺼번에 하고(Task 0은 예외로 그 자리에서 재빌드·확인한다), Task 1~9에서는 갭·배선과 좁은 시험까지만 한다.
- 비밀값(`.env.container`의 값, 다리 토큰)은 화면·로그·커밋·인계 어디에도 찍지 않는다. `cat .env.container`를 치지 않는다. 키 이름과 줄 수만 다룬다.

### 이번 조사에서 새로 찾은 것 (Task 0에서 따로, 가장 먼저 고친다)

`.dockerignore`에 `.env.container`가 없다. `docker/workspace.Dockerfile:40`의 `COPY --exclude=assets/fonts . .`가 실제 `.env.container`를 이미지 안 `/app/.env.container`에 넣는다. 2026-10-02에 실행 중인 컨테이너에서 확인했다. 파일은 16줄이고 `POSTGRES_PASSWORD`, `HERMES_YUJIN_GATEWAY_PASSWORD`, `VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN` 같은 키가 들어 있다(값은 열어 보지 않았다). 다리 토큰을 이 파일에 넣으면 같은 길로 새어 나가므로, **다리 토큰을 만들기(Task 4) 전에** 막는다. 이미 만들어진 옛 이미지 층에는 값이 남아 있다. 비밀값을 바꿀지는 owner가 정한다(이 컴퓨터 밖으로 이미지를 내보낸 적이 없다면 위험은 낮다). **owner 승인 없이 비밀값을 바꾸거나 옛 이미지를 지우지 않는다.** 인계 문서에 결정 필요 사항으로 적는다.

같은 실측(2026-10-02, 리뷰)에서 `/app/.venv-chatterbox`(윈도우용 목소리 파이썬, **1.9GB**)도 이미지에 실려 있었다. `.dockerignore`의 `**/.venv`는 이름이 정확히 `.venv`인 것만 거른다. 컨테이너 안에서 이 폴더를 읽는 코드는 없다(`grep -rn "venv-chatterbox"` → 호스트 스크립트 `start-voice.ps1`·`host_tts_service.py` 문서뿐). Task 0에서 함께 뺀다.

## Review Focus

해피 패스 시험이 안 잡는, 실제로 터지기 쉬운 입력 다섯이다. 각각 맡은 Task에 시험이 있다.

1. **토큰이 빈 다리**(Task 2): 기대 토큰이 `""`이고 헤더도 없으면 `hmac.compare_digest(b"", b"")`가 참이라 통과해 버린다. `check_request`는 기대값이 비면 503으로 거절하고, 다리는 토큰이 없으면 아예 뜨지 않는다.
2. **`.env.container`의 모양**(Task 2·4): BOM, CRLF, 따옴표로 감싼 값, 이미 있는 빈 `VIDEOBOX_BRIDGE_TOKEN=` 줄. 파이썬 쪽 읽기와 `owner-ready.ps1` 쓰기가 같은 한 줄을 봐야 한다. 쓰기 쪽은 BOM과 줄바꿈을 지키고, 줄이 두 개가 되면 안 된다.
3. **인포그래픽 실행 코드의 대소문자·변형**(Task 5): `<SCRIPT>`, `< script`, `ONLOAD =`, `href="JavaScript:..."`는 거절한다. 반대로 주석 안의 계산식이나 평범한 CSS는 오탐하면 안 된다.
4. **수리 스크립트의 잘못 고치기**(Task 8): 진짜 라틴 문자 이름(`café.mp3`), 이미 한국어인 이름, 라틴1→cp949로 풀리지만 한글이 안 나오는 이름은 건드리면 안 된다. 되돌릴 목록은 PATCH **전에** 써야 한다.
5. **이름 바꾸기 입력**(Task 6·7): 공백만 있는 이름, `/`·`\`, 줄바꿈 같은 제어 문자, `..`, 256자, 앞뒤 공백. 이름을 바꿔도 같은 `user_metadata` 안의 `favorite`·`tags`는 그대로 남아야 한다.

---

### Task 0: 비밀값 파일이 이미지에 실리는 구멍을 막는다 (`.dockerignore`) — 가장 먼저, 혼자

이 Task는 **다른 Task와 상관없이 바로 실행할 수 있게** 혼자 닫힌다. 다른 Task의 코드에 기대지 않는다.

**Files:**
- Modify: `.dockerignore:52` (마지막 줄 `**/*.mp3` 다음에 덧붙임)
- Modify: `tests/test_compose_contract.py` (파일 끝에 시험 하나 추가)

**Interfaces:**
- Consumes: 없음
- Produces: 없음(이미지 내용만 바뀐다). 컨테이너는 원래도 값을 compose `environment:`로만 받는다(`compose.yaml`). 컨테이너 안에서 `/app/.env.container`나 `/app/.venv-chatterbox`를 읽는 코드는 없다(2026-10-02 리뷰에서 `grep -rn "\.env\.container\|venv-chatterbox" packages services docker`로 확인. 나온 것은 주석과 호스트 스크립트뿐).

배경(2026-10-02 실측): `docker exec 65_videobox-videobox-workspace-1 sh -c 'ls -a /app'`에 `.env.container`, `.env.container.example`, `.venv-chatterbox`가 있다. `docker/workspace.Dockerfile:40`의 `COPY --exclude=assets/fonts . .`가 빌드 컨텍스트를 통째로 싣는데, `.dockerignore`에 `.env*`가 없고, `**/.venv`는 `.venv-chatterbox`를 못 거른다(1.9GB). 빌드하는 이미지는 `videobox-workspace` 하나뿐이다(`compose.yaml`의 `build:`는 한 곳. `agent-gateway`는 자기 전용 허용 목록 `docker/agent-gateway.Dockerfile.dockerignore`를 쓴다).

- [ ] **Step 1: 출발 상태를 확인한다**

```bash
git status --short
test -e scripts/host_bridge_guard.py && echo "bridge-guard-exists" || echo "bridge-guard-absent"
docker exec 65_videobox-videobox-workspace-1 sh -c 'test -e /app/.env.container && echo env-present || echo env-absent; test -e /app/.venv-chatterbox && echo venv-present || echo venv-absent'
docker image ls --format '{{.Repository}}:{{.Tag}} {{.Size}}' | grep '^65_videobox-videobox-workspace:latest'
```

예상: `git status`에는 `.anchor/`와 `docs/superpowers/plans/` 아래 계획서만 보인다. `bridge-guard-absent`. `env-present`, `venv-present`. 이미지 크기(2026-10-02에 7.38GB)를 적어 둔다.

- `git status`에 제품 코드 변경(다른 Task가 만든 것)이 있으면, 그 변경까지 이미지에 실린다. 멈추고 그 변경이 어느 Task 것인지 보고한다.
- `bridge-guard-exists`면 Task 2가 이미 들어온 것이다. 이때 Step 6의 재빌드는 하지 않는다. owner-ready가 꺼진 다리를 **새 코드로** 띄우는데 토큰이 아직 없어 다리가 안 뜰 수 있다. Step 1~5와 Step 8만 하고, 재빌드·확인(Step 6~7)은 Task 10 Step 2에서 함께 한다.

- [ ] **Step 2: 실패하는 시험을 쓴다**

`tests/test_compose_contract.py` 끝에 더한다(`ROOT`는 이 파일 15줄에 이미 있다):

```python
def test_the_build_context_never_carries_real_env_files_or_host_only_venvs() -> None:
    """2026-10-02 실측: `COPY . .`가 `.env.container`를 이미지 안 `/app/.env.container`에
    넣고 있었다(DB 암호·게이트웨이 토큰). 컨테이너는 값을 compose `environment:`로만 받는다.

    같은 자리에 윈도우용 목소리 파이썬 `.venv-chatterbox`(1.9GB)도 실려 있었다.
    `**/.venv`는 이름이 정확히 `.venv`인 폴더만 거른다.

    예시 파일(`.env.container.example`)은 비밀값이 없어 예외로 다시 넣는다. dockerignore는
    **뒤에 오는 줄이 이긴다**. 그래서 예외 줄은 거르는 줄보다 뒤에 있어야 한다.
    """
    patterns = [
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert "**/.env" in patterns
    assert "**/.env.*" in patterns
    assert "**/.venv-*" in patterns
    assert "!.env.container.example" in patterns
    assert patterns.index("!.env.container.example") > patterns.index("**/.env.*")
```

- [ ] **Step 3: 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_compose_contract.py::test_the_build_context_never_carries_real_env_files_or_host_only_venvs
```

예상: FAIL, `AssertionError: assert '**/.env' in [...]`.

- [ ] **Step 4: `.dockerignore`를 고친다**

`.dockerignore` 마지막 줄(52줄 `**/*.mp3`) 다음에 덧붙인다:

```
# 실제 비밀값 파일. 2026-10-02 실측: `COPY . .`가 `.env.container`를 이미지 안
# `/app/.env.container`에 넣고 있었다(DB 암호·게이트웨이 토큰). 컨테이너는
# compose `environment:`로만 값을 받는다. 예시 파일은 비밀값이 없어 다시 넣는다.
# 예외(`!`) 줄은 거르는 줄보다 뒤에 있어야 이긴다.
**/.env
**/.env.*
!.env.container.example

# 호스트에서만 도는 파이썬 환경. `.venv-chatterbox`(윈도우용 목소리 엔진, 1.9GB)가
# `**/.venv`에 안 걸려 이미지에 실려 있었다(2026-10-02 실측). 컨테이너는 안 읽는다.
**/.venv-*
```

- [ ] **Step 5: 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_compose_contract.py
```

예상: 전부 통과(기존 `**/` 시험 포함).

- [ ] **Step 6: 커밋한 뒤 다시 짓는다**

```bash
git add .dockerignore tests/test_compose_contract.py
git commit -m "$(cat <<'EOF'
fix(security): .env.container·.venv-chatterbox를 이미지에서 뺀다(.dockerignore)

실측으로 /app/.env.container(비밀값)와 /app/.venv-chatterbox(1.9GB)가 이미지에
실려 있었다. 컨테이너는 값을 compose environment로만 받는다. 예시 파일은 남긴다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

PowerShell에서(Step 1에서 `bridge-guard-exists`였으면 건너뛴다):

```powershell
.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild
```

예상: 전체 `pass`, `rebuild`가 `pass`.

- [ ] **Step 7: 역방향·동작 — 컨테이너 안에 파일이 없는지, 값은 여전히 들어오는지 잰다**

```bash
docker exec 65_videobox-videobox-workspace-1 test ! -e /app/.env.container && echo env-absent
docker exec 65_videobox-videobox-workspace-1 test ! -e /app/.venv-chatterbox && echo venv-absent
docker exec 65_videobox-videobox-workspace-1 test -e /app/.env.container.example && echo example-present
docker exec 65_videobox-videobox-workspace-1 sh -c 'test -n "$VIDEOBOX_DATABASE_URL"' && echo env-still-injected
curl -s -o /dev/null -w "health %{http_code}\n" http://127.0.0.1:5173/health
docker image ls --format '{{.Repository}}:{{.Tag}} {{.Size}}' | grep '^65_videobox-videobox-workspace:latest'
```

예상: `env-absent`, `venv-absent`, `example-present`, `env-still-injected`, `health 200`. 이미지 크기가 Step 1보다 작아졌다(재기만 한다. 값은 인계에 적는다). 값 자체(`$VIDEOBOX_DATABASE_URL`)는 찍지 않는다. `docker exec`는 읽기만 하는 확인이고 compose 조작이 아니다.

화면: 브라우저 http://127.0.0.1:5173 → Ctrl+F5 → 프로젝트 목록이 뜨고 아무 프로젝트나 열린다(DB 연결이 env로 그대로 들어온다는 owner 길 확인).

- [ ] **Step 8: owner 결정이 필요한 것을 남긴다(비밀값은 바꾸지 않는다)**

이 Task는 **새 이미지**에서만 파일을 뺀다. 옛 이미지 층·빌드 캐시·다른 태그의 이미지(`docker image ls`에 `videobox-verify-a912-videobox-workspace` 등 VideoBox 이미지가 여럿 있다)에는 옛 `.env.container` 값이 남아 있을 수 있다. 다음 둘은 **owner 승인 없이 하지 않는다**:

1. 비밀값 교체(`POSTGRES_PASSWORD`, `HERMES_YUJIN_GATEWAY_PASSWORD`, `VIDEOBOX_AGENT_GATEWAY_SERVICE_TOKEN` 등 `.env.container`의 키). 이미지를 이 컴퓨터 밖(레지스트리·파일·다른 사람)으로 내보낸 적이 없다면 위험은 낮다. 내보낸 적이 있는지는 owner만 안다.
2. 옛 이미지·빌드 캐시 정리(`docker image rm`, `docker builder prune`). 지우면 되돌릴 수 없다.

이 Task를 혼자 실행했으면 턴 종료 보고에 위 두 줄을 "결정 필요"로 적는다. 묶음 전체를 실행하면 Task 10 Step 10의 인계 문서 "결정 필요"에 옮긴다.

---

### Task 1: A1 — vite 5.4.21·vitest 2.1.9로 패치 올리기, `@tailwindcss/vite`를 개발 의존성으로

**Files:**
- Create: `tests/test_web_dependency_floor.py`
- Modify: `apps/web/package.json:14-39` (`dependencies`의 `"@tailwindcss/vite"` 줄 15, `devDependencies`의 `"vite"` 줄 38, `"vitest"` 줄 39)
- Modify: `apps/web/package-lock.json` (npm이 다시 쓴다. 손으로 고치지 않는다)

**Interfaces:**
- Consumes: 없음
- Produces: 없음(빌드 도구 버전만 바뀐다)

배경(2026-10-02 실측): `npm --prefix apps/web audit --omit=dev`가 high 3·moderate 1(vite·postcss·nanoid·esbuild)을 낸다. 원인은 `@tailwindcss/vite`가 `dependencies`에 있어서, 그 peer인 vite와 그 아래 postcss·nanoid가 배포 묶음으로 잡히는 데 있다. vite 5.4.21도 advisory 범위(`<=6.4.2`) 안이다. 그래서 **패치만으로는 vite 경고가 안 사라지고, 개발 의존성으로 옮겨야 배포 묶음에서 빠진다.** 이미지 빌드는 `npm ci`(`docker/workspace.Dockerfile:5`)라 개발 의존성도 설치되므로 빌드는 그대로 된다. 전체 `npm audit`(개발 포함)에는 vite·vitest 경고가 남는다. owner 결정이 "패치 버전만"이라 메이저를 올리지 않는다. 이 둘은 이 컴퓨터에서만 도는 개발 도구이고, vitest UI 서버는 쓰지 않는다. 인계 문서에 남은 위험으로 적는다.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`tests/test_web_dependency_floor.py`:

```python
"""웹 개발 도구의 바닥 버전과 배포 묶음 경계 (2026-10-02, 점검 후속 A1).

`@tailwindcss/vite`가 `dependencies`에 있으면 그 peer인 vite가 배포 묶음으로 잡혀
`npm audit --omit=dev`에 high가 뜬다. vite 5.4.x는 패치로도 advisory 범위를 못 벗어나므로
(owner 결정: 패치 버전만), 배포 묶음에서 빼는 것이 이 경고를 닫는 실제 방법이다.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("-")[0].split("."))


def test_dev_tools_are_patched_and_stay_out_of_the_shipped_tree() -> None:
    manifest = json.loads((ROOT / "apps/web/package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "apps/web/package-lock.json").read_text(encoding="utf-8"))["packages"]

    assert "@tailwindcss/vite" not in manifest["dependencies"]
    assert "@tailwindcss/vite" in manifest["devDependencies"]
    assert lock["node_modules/@tailwindcss/vite"].get("dev") is True
    assert lock["node_modules/vite"].get("dev") is True

    assert (5, 4, 21) <= _version(lock["node_modules/vite"]["version"]) < (5, 5, 0)
    vitest = lock["node_modules/vitest"]["version"]
    assert (2, 1, 9) <= _version(vitest) < (2, 2, 0)
    # vitest는 자기 짝 패키지와 같은 버전이어야 한다. 하나만 올라가면 실행 중에 깨진다.
    for name in ("@vitest/expect", "@vitest/mocker", "@vitest/runner", "@vitest/snapshot", "@vitest/spy", "@vitest/utils", "vite-node"):
        assert lock[f"node_modules/{name}"]["version"] == vitest, name
```

- [ ] **Step 2: 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_web_dependency_floor.py::test_dev_tools_are_patched_and_stay_out_of_the_shipped_tree
```

예상: FAIL. 메시지는 `assert '@tailwindcss/vite' not in {...}`이다.

- [ ] **Step 3: `package.json`을 고친다**

`apps/web/package.json`에서 아래를 바꾼다.

옛 `dependencies` 첫 줄(15):
```json
    "@tailwindcss/vite": "^4.2.2",
    "@tanstack/react-router": "1.168.22",
```
새:
```json
    "@tanstack/react-router": "1.168.22",
```

옛 `devDependencies`(29-39):
```json
  "devDependencies": {
    "@playwright/test": "1.61.1",
    "@testing-library/jest-dom": "^6.6.3",
    ...
    "vite": "^5.4.10",
    "vitest": "^2.1.3"
  }
```
새(가운데 줄은 그대로 두고 아래 세 곳만 바꾼다):
```json
  "devDependencies": {
    "@playwright/test": "1.61.1",
    "@tailwindcss/vite": "^4.2.2",
    "@testing-library/jest-dom": "^6.6.3",
    ...
    "vite": "^5.4.21",
    "vitest": "^2.1.9"
  }
```

- [ ] **Step 4: 잠금 파일을 다시 쓴다**

```bash
npm --prefix apps/web install
npm --prefix apps/web update postcss nanoid
npm --prefix apps/web ls vite vitest @vitest/mocker postcss nanoid
```

예상: `vite@5.4.21`, `vitest@2.1.9`, `@vitest/mocker@2.1.9`, `postcss@8.5.28`(또는 그 뒤 8.5.x), `nanoid@3.3.19`(또는 그 뒤 3.3.x). `npm update postcss nanoid`는 범위 안 패치라 결정과 맞는다(개발 쪽 경고를 조금이라도 줄인다).

- [ ] **Step 5: 잠금 파일이 엉뚱한 곳까지 바뀌지 않았는지 본다**

```bash
git diff --stat apps/web/package-lock.json
git diff apps/web/package-lock.json | grep -E '^[-+]\s+"node_modules/' | sort -u
```

예상: 바뀐 항목은 vite, vitest, `@vitest/*`, vite-node, postcss, nanoid, esbuild 계열, `@tailwindcss/*`(dev 표시), 그리고 그 의존 몇 개뿐이다. `radix-ui`·`lucide-react`·`react` 같은 런타임 패키지의 `"version"`이 바뀌었으면 멈추고 원인을 본다(출처 검증이 그 버전을 고정한다).

- [ ] **Step 6: 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_web_dependency_floor.py
npm --prefix apps/web audit --omit=dev
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_editor_ui_source_provenance.py
```

예상: 1 passed. `found 0 vulnerabilities`. 출처 시험 전부 통과.

- [ ] **Step 7: 넓은 검증**

```bash
(cd apps/web && npx tsc --noEmit && npx vitest run)
npm --prefix apps/web run build
npm --prefix apps/web audit
```

예상: 타입 검사 통과. vitest는 알려진 실패 1건(material dock)만 빨갛다. 빌드 성공. 전체 audit에는 vite·vitest(개발 의존성)만 남는다. 남은 항목 이름과 등급을 기록해 인계에 옮긴다.

- [ ] **Step 8: 커밋**

```bash
git add apps/web/package.json apps/web/package-lock.json tests/test_web_dependency_floor.py
git commit -m "$(cat <<'EOF'
build(web): vite 5.4.21·vitest 2.1.9로 패치, @tailwindcss/vite를 개발 의존성으로

배포 묶음 audit(--omit=dev) high 0. vite는 5.4.x 패치로도 advisory 범위 안이라
배포 묶음에서 빼는 것이 실제 해결이다. 전체 audit에 남는 vite·vitest는 개발 도구.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: A2(받는 쪽) — 다리 셋에 문지기 `host_bridge_guard`를 세운다

**Files:**
- Create: `scripts/host_bridge_guard.py`
- Create: `tests/test_host_bridge_guard.py`
- Modify: `scripts/host_tts_service.py:70-79` (경로 설정 뒤), `:138-221` (`_Handler`), `:223-229` (`main`)
- Modify: `scripts/host_capcut_service.py:47-51` (import 뒤), `:142-186` (`_Handler`·`build_server`), `:189-214` (`main`)
- Modify: `scripts/host_infographic_service.py:40-52` (import 뒤), `:271-316` (`_Handler`·`build_server`), `:319-338` (`main`)

**Interfaces:**
- Produces (`scripts/host_bridge_guard.py`):
  - `TOKEN_HEADER: str = "X-VideoBox-Bridge-Token"`
  - `TOKEN_ENV: str = "VIDEOBOX_BRIDGE_TOKEN"`
  - `MINIMUM_TOKEN_LENGTH: int = 32`
  - `class BridgeTokenMissing(RuntimeError)`
  - `read_env_file_value(env_file: Path, name: str) -> str`
  - `load_bridge_token(environ: Mapping[str, str], env_file: Path) -> str`(없거나 짧으면 `BridgeTokenMissing`)
  - `check_request(*, method: str, headers: Any, port: int, expected_token: str, require_token: bool = True) -> tuple[int, dict[str, object]] | None`(`headers`는 `.get(name)`이 되는 것. 다리에서는 `self.headers`(`http.client.HTTPMessage`, 이름 대소문자 무시))
  - 세 다리의 `_Handler.bridge_token: str` 클래스 속성
  - `host_capcut_service.build_server(*, port: int, allowed_roots: tuple[Path, ...], bridge_token: str)`
  - `host_infographic_service.build_server(*, port: int, browser: Path | None, bridge_token: str)`
- Consumes: 없음(표준 라이브러리만)

정한 것과 이유:
- 검사 순서는 **Host → 토큰 → JSON**이다. Host로 DNS 리바인딩을 먼저 막고, 토큰이 없는 요청에는 본문 형식을 알려 주지 않는다.
- 목소리 다리의 `GET /health`만 토큰 없이 연다. `scripts/Start-VideoBox.ps1:28,61`이 토큰 없이 켜졌는지 묻는다. 돌려주는 것은 엔진 이름·라이선스뿐이다. Host 검사는 받는다. 캡컷·그림의 `GET /diagnostics`는 토큰을 요구한다. 부르는 쪽이 컨테이너 클라이언트뿐이고(`capcut_handoff.py`, `main.py:1342`), 캡컷 쪽은 이 컴퓨터의 경로를 돌려준다. `owner-ready.ps1`은 TCP 연결로만 살아 있는지 본다(`:1158-1163`).
- 토큰은 환경 변수가 먼저고, 없으면 저장소 루트 `.env.container`를 직접 읽는다. 세 시작 스크립트(`start-voice.ps1`·`start-capcut.ps1`·`start-infographic.ps1`)를 고치지 않아도 된다. 같은 값을 읽는 자리가 파이썬 한 곳으로 모인다.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`tests/test_host_bridge_guard.py`:

```python
"""호스트 다리 셋의 문지기 (2026-10-02, 점검 후속 A2).

목소리(8199)·캡컷(8200)·그림(8201) 다리는 127.0.0.1에만 묶여 있지만, 이 컴퓨터의
아무 프로세스나 브라우저의 아무 웹페이지나 부를 수 있었다. owner 결정은 "공유 토큰까지"다.

**소켓은 안 연다**(`tests/conftest.py`가 막는다). 판단 함수(`check_request`)를 그대로
부르고, 배선은 핸들러 객체를 소켓 없이 만들어 `do_GET`/`do_POST`를 직접 부른다.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from http.client import HTTPMessage
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "k3Y-" + "a1B2c3D4e5F6g7H8i9J0" * 2  # 44자


def _load(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "scripts" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # 목소리 다리의 dataclass는 정의한 모듈을 sys.modules에서 찾는다
    # (`tests/test_host_tts_engine_licence.py::_bridge`와 같은 이유).
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


guard = _load("videobox_host_bridge_guard_under_test", "host_bridge_guard.py")


# --------------------------------------------------------------------------
# 1. 판단 함수
# --------------------------------------------------------------------------


def test_a_request_without_the_token_is_refused() -> None:
    refusal = guard.check_request(
        method="POST",
        headers={"Host": "127.0.0.1:8199", "Content-Type": "application/json"},
        port=8199,
        expected_token=TOKEN,
    )
    assert refusal == (401, {"error": "bridge_token_required"})


def test_a_wrong_token_is_refused() -> None:
    refusal = guard.check_request(
        method="POST",
        headers={"Host": "127.0.0.1:8199", "Content-Type": "application/json", guard.TOKEN_HEADER: TOKEN[:-1] + "x"},
        port=8199,
        expected_token=TOKEN,
    )
    assert refusal == (401, {"error": "bridge_token_required"})


def test_text_with_the_right_token_is_refused_as_not_json() -> None:
    refusal = guard.check_request(
        method="POST",
        headers={"Host": "127.0.0.1:8201", "Content-Type": "text/plain", guard.TOKEN_HEADER: TOKEN},
        port=8201,
        expected_token=TOKEN,
    )
    assert refusal == (415, {"error": "json_required"})


@pytest.mark.parametrize("content_type", ["application/json", "application/json; charset=utf-8", "Application/JSON"])
def test_json_with_the_right_token_from_the_container_passes(content_type: str) -> None:
    assert guard.check_request(
        method="POST",
        headers={"Host": "host.docker.internal:8200", "Content-Type": content_type, guard.TOKEN_HEADER: TOKEN},
        port=8200,
        expected_token=TOKEN,
    ) is None


@pytest.mark.parametrize("host", ["evil.example:8199", "127.0.0.1:9999", "127.0.0.1", "", "localhost.evil.example:8199"])
def test_a_foreign_host_is_refused_even_with_the_token(host: str) -> None:
    headers = {"Content-Type": "application/json", guard.TOKEN_HEADER: TOKEN}
    if host:
        headers["Host"] = host
    refusal = guard.check_request(method="POST", headers=headers, port=8199, expected_token=TOKEN)
    assert refusal == (400, {"error": "host_not_allowed"})


def test_an_empty_expected_token_never_lets_an_empty_header_through() -> None:
    """`compare_digest(b"", b"")`는 참이다. 토큰 없이 뜬 다리가 아무나 받으면 안 된다."""
    refusal = guard.check_request(
        method="POST",
        headers={"Host": "127.0.0.1:8199", "Content-Type": "application/json", guard.TOKEN_HEADER: ""},
        port=8199,
        expected_token="",
    )
    assert refusal == (503, {"error": "bridge_token_not_configured"})


def test_an_open_read_still_checks_the_host() -> None:
    assert guard.check_request(
        method="GET", headers={"Host": "localhost:8199"}, port=8199, expected_token=TOKEN, require_token=False
    ) is None
    assert guard.check_request(
        method="GET", headers={"Host": "evil.example:8199"}, port=8199, expected_token=TOKEN, require_token=False
    ) == (400, {"error": "host_not_allowed"})


def test_the_token_comes_from_the_environment_first(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.container"
    env_file.write_text(f"VIDEOBOX_BRIDGE_TOKEN={'f' * 40}\n", encoding="utf-8")
    assert guard.load_bridge_token({guard.TOKEN_ENV: TOKEN}, env_file) == TOKEN


def test_the_token_falls_back_to_the_env_file_with_bom_crlf_and_quotes(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.container"
    env_file.write_bytes(
        b"\xef\xbb\xbf# comment\r\nPOSTGRES_DB=videobox\r\n"
        + f'VIDEOBOX_BRIDGE_TOKEN="{TOKEN}"\r\n'.encode("utf-8")
    )
    assert guard.load_bridge_token({}, env_file) == TOKEN


@pytest.mark.parametrize(
    "content", ["", "VIDEOBOX_BRIDGE_TOKEN=\n", "VIDEOBOX_BRIDGE_TOKEN=short\n", "#VIDEOBOX_BRIDGE_TOKEN=" + "z" * 40 + "\n"]
)
def test_a_missing_or_short_token_stops_the_bridge(tmp_path: Path, content: str) -> None:
    env_file = tmp_path / ".env.container"
    env_file.write_text(content, encoding="utf-8")
    with pytest.raises(guard.BridgeTokenMissing):
        guard.load_bridge_token({}, env_file)


def test_a_missing_env_file_stops_the_bridge(tmp_path: Path) -> None:
    with pytest.raises(guard.BridgeTokenMissing):
        guard.load_bridge_token({}, tmp_path / "nope.env")


# --------------------------------------------------------------------------
# 2. 배선 -- 세 다리가 실제로 문지기를 부르는가
# --------------------------------------------------------------------------

tts = _load("videobox_host_tts_service_guard_test", "host_tts_service.py")
capcut = _load("videobox_host_capcut_service_guard_test", "host_capcut_service.py")
infographic = _load("videobox_host_infographic_service_guard_test", "host_infographic_service.py")

_TTS_HANDLER = type("TtsHandler", (tts._Handler,), {"bridge_token": TOKEN, "engine_choice": tts.resolve_engine({})})
_CAPCUT_HANDLER = type("CapCutHandler", (capcut._Handler,), {"bridge_token": TOKEN, "allowed_roots": ()})
_INFOGRAPHIC_HANDLER = type("InfographicHandler", (infographic._Handler,), {"bridge_token": TOKEN, "browser": None})


def _call(handler_class, *, method: str, path: str, port: int, headers: dict[str, str], body: bytes = b""):
    """소켓 없이 핸들러를 만들어 한 요청을 흘린다."""
    handler = handler_class.__new__(handler_class)
    message = HTTPMessage()
    for key, value in headers.items():
        message[key] = value
    if body:
        message["Content-Length"] = str(len(body))
    handler.headers = message
    handler.command = method
    handler.path = path
    handler.request_version = "HTTP/1.1"
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.client_address = ("127.0.0.1", 50000)
    handler.server = SimpleNamespace(server_address=("127.0.0.1", port))
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    handler.close_connection = True
    getattr(handler, f"do_{method}")()
    head, _, payload = handler.wfile.getvalue().partition(b"\r\n\r\n")
    status = int(head.split(b" ")[1])
    return status, (json.loads(payload.decode("utf-8")) if payload else None)


_POSTS = [
    (_TTS_HANDLER, "/synthesize", 8199),
    (_CAPCUT_HANDLER, "/register", 8200),
    (_INFOGRAPHIC_HANDLER, "/render", 8201),
]


@pytest.mark.parametrize(("handler_class", "path", "port"), _POSTS)
def test_every_bridge_refuses_a_post_without_the_token(handler_class, path: str, port: int) -> None:
    status, _ = _call(
        handler_class, method="POST", path=path, port=port,
        headers={"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"}, body=b"{}",
    )
    assert status == 401


@pytest.mark.parametrize(("handler_class", "path", "port"), _POSTS)
def test_every_bridge_refuses_text_even_with_the_token(handler_class, path: str, port: int) -> None:
    status, _ = _call(
        handler_class, method="POST", path=path, port=port,
        headers={"Host": f"127.0.0.1:{port}", "Content-Type": "text/plain", guard.TOKEN_HEADER: TOKEN}, body=b"x",
    )
    assert status == 415


@pytest.mark.parametrize(("handler_class", "path", "port"), _POSTS)
def test_every_bridge_refuses_a_foreign_host(handler_class, path: str, port: int) -> None:
    status, _ = _call(
        handler_class, method="POST", path=path, port=port,
        headers={"Host": "evil.example", "Content-Type": "application/json", guard.TOKEN_HEADER: TOKEN}, body=b"{}",
    )
    assert status == 400


def test_the_header_name_is_matched_without_case() -> None:
    status, payload = _call(
        _INFOGRAPHIC_HANDLER, method="GET", path="/diagnostics", port=8201,
        headers={"Host": "host.docker.internal:8201", "x-videobox-bridge-token": TOKEN},
    )
    assert status == 200
    assert payload["status"] == "browser_not_found"


def test_diagnostics_need_the_token() -> None:
    status, payload = _call(
        _CAPCUT_HANDLER, method="GET", path="/diagnostics", port=8200, headers={"Host": "127.0.0.1:8200"},
    )
    assert status == 401
    assert payload == {"error": "bridge_token_required"}


def test_voice_health_stays_open_for_the_start_script_but_checks_the_host() -> None:
    """`Start-VideoBox.ps1`이 토큰 없이 `/health`로 켜졌는지 묻는다."""
    status, payload = _call(_TTS_HANDLER, method="GET", path="/health", port=8199, headers={"Host": "127.0.0.1:8199"})
    assert status == 200
    assert payload["engine"] == "chatterbox"
    status, _ = _call(_TTS_HANDLER, method="GET", path="/health", port=8199, headers={"Host": "evil.example:8199"})
    assert status == 400


def test_a_passing_post_reaches_the_bridges_own_checks() -> None:
    """문지기를 통과하면 다리 자기 검사로 간다 -- 여기서는 브라우저가 없다는 503."""
    status, payload = _call(
        _INFOGRAPHIC_HANDLER, method="POST", path="/render", port=8201,
        headers={"Host": "127.0.0.1:8201", "Content-Type": "application/json", guard.TOKEN_HEADER: TOKEN}, body=b"{}",
    )
    assert (status, payload) == (503, {"error": "browser_not_found"})
```

마지막 시험에서 503인 이유: 그림 다리는 브라우저가 없으면(`browser=None`) html 검사보다 먼저 `browser_not_found`를 낸다(`host_infographic_service.py:211-212`). 문지기를 통과했다는 증거로 충분하다.

- [ ] **Step 2: 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_host_bridge_guard.py::test_a_request_without_the_token_is_refused
```

예상: 수집 단계 에러. `FileNotFoundError`(또는 `spec_from_file_location`이 `None`을 내서 `AssertionError`)로, `scripts/host_bridge_guard.py`가 아직 없다.

- [ ] **Step 3: 문지기를 만든다**

`scripts/host_bridge_guard.py`:

```python
"""호스트 다리 셋(목소리 8199·캡컷 8200·그림 8201)이 같이 쓰는 문지기 (2026-10-02).

2026-10-01 보안 점검: 세 다리는 127.0.0.1에만 묶여 있지만 **이 컴퓨터의 아무
프로세스나, 브라우저의 아무 웹페이지나** 부를 수 있었다(text/plain POST는 CORS
사전 확인 없이 나간다). owner 결정(2026-10-02)은 "공유 토큰까지"다.

세 가지를 이 차례로 본다.

1. **Host**: `127.0.0.1:<포트>`·`localhost:<포트>`·`host.docker.internal:<포트>`만 받는다.
   DNS 리바인딩으로 들어온 요청은 Host에 남의 이름이 실린다.
2. **토큰**: `X-VideoBox-Bridge-Token`이 `VIDEOBOX_BRIDGE_TOKEN`과 같아야 한다. 웹페이지가
   이 헤더를 붙이면 사전 확인(OPTIONS)을 먼저 보내는데, 다리는 그것에 답하지 않는다.
   비교는 `hmac.compare_digest`로 한다.
3. **JSON만**: POST는 `application/json`만 받고, 아니면 415를 낸다.

표준 라이브러리만 쓴다. 목소리 다리는 chatterbox 전용 파이썬(`.venv-chatterbox`)에서 돈다.
판단(`check_request`)은 소켓과 떼어 두었다. 시험이 연결을 못 열기 때문이다.

토큰은 `.env.container`의 한 줄이다. `scripts/owner-ready.ps1 -Mode Start`가 없을 때만
만들고, compose가 컨테이너에 넘기며(`compose.yaml`), 다리는 같은 파일을 여기서 직접 읽는다.
부르는 쪽 헤더는 `videobox_provider_interfaces.host_bridge_auth`가 만든다. 두 곳의 이름은
`tests/test_host_bridge_guard.py`가 대조한다.
"""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from pathlib import Path
from typing import Any

TOKEN_HEADER = "X-VideoBox-Bridge-Token"
TOKEN_ENV = "VIDEOBOX_BRIDGE_TOKEN"
#: `owner-ready.ps1`은 32바이트를 base64url로 적는다(43자). 사람이 손으로 넣은 짧은 값은 받지 않는다.
MINIMUM_TOKEN_LENGTH = 32
_ALLOWED_HOST_NAMES = ("127.0.0.1", "localhost", "host.docker.internal")


class BridgeTokenMissing(RuntimeError):
    """토큰이 없거나 너무 짧다. 다리는 이때 뜨지 않는다. 아무나 받는 것보다 안 뜨는 편이 안전하다."""


def read_env_file_value(env_file: Path, name: str) -> str:
    """`.env.container`에서 `name=` 한 줄의 값을 읽는다. BOM·CRLF·따옴표를 견딘다. 없으면 `""`."""

    try:
        text = Path(env_file).read_text(encoding="utf-8-sig")
    except OSError:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() == name:
            return value.strip().strip('"').strip("'").strip()
    return ""


def load_bridge_token(environ: Mapping[str, str], env_file: Path) -> str:
    token = str(environ.get(TOKEN_ENV) or "").strip() or read_env_file_value(env_file, TOKEN_ENV)
    if len(token) < MINIMUM_TOKEN_LENGTH:
        raise BridgeTokenMissing(
            f"{TOKEN_ENV}가 없거나 너무 짧습니다({MINIMUM_TOKEN_LENGTH}자 이상 필요). "
            "PowerShell에서 .\\scripts\\owner-ready.ps1 -Mode Start 를 한 번 실행하면 "
            ".env.container에 만들어집니다."
        )
    return token


def check_request(
    *,
    method: str,
    headers: Any,
    port: int,
    expected_token: str,
    require_token: bool = True,
) -> tuple[int, dict[str, object]] | None:
    """막아야 하면 `(상태 코드, 답)`을, 통과면 `None`을 돌려준다.

    `headers`는 `.get(name)`이 되는 것이면 된다. 다리에서는 `self.headers`
    (`http.client.HTTPMessage`)를 넘기고, 그쪽은 이름의 대소문자를 가리지 않는다.
    """

    host = str(headers.get("Host") or "").strip().lower()
    if host not in {f"{name}:{port}" for name in _ALLOWED_HOST_NAMES}:
        return 400, {"error": "host_not_allowed"}
    if require_token:
        if not expected_token:
            return 503, {"error": "bridge_token_not_configured"}
        supplied = str(headers.get(TOKEN_HEADER) or "")
        if not hmac.compare_digest(supplied.encode("utf-8"), expected_token.encode("utf-8")):
            return 401, {"error": "bridge_token_required"}
    if method.upper() == "POST":
        content_type = str(headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return 415, {"error": "json_required"}
    return None


__all__ = [
    "MINIMUM_TOKEN_LENGTH",
    "TOKEN_ENV",
    "TOKEN_HEADER",
    "BridgeTokenMissing",
    "check_request",
    "load_bridge_token",
    "read_env_file_value",
]
```

- [ ] **Step 4: 판단 함수 시험이 통과하는지 본다(배선 시험은 아직 빨갛다)**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_host_bridge_guard.py -k "not every_bridge and not header_name and not diagnostics_need and not voice_health and not passing_post"
```

예상: 1번 묶음 시험이 모두 통과한다. `-k`로 빼낸 배선 시험은 다음 Step에서 다룬다(모듈 위쪽의 `_TTS_HANDLER` 등은 이미 import되므로, 다리 스크립트가 `bridge_token` 속성이 없어도 수집은 된다. `type(...)`이 속성을 덧붙이기 때문이다).

- [ ] **Step 5: 목소리 다리에 단다 — `scripts/host_tts_service.py`**

(a) 경로 설정 뒤(줄 77 `sys.path.insert(0, str(src_path))` 다음, 줄 79 `HOST = "127.0.0.1"` 앞)에 넣는다:

```python
# 다리 셋이 같이 쓰는 문지기. 표준 라이브러리만 쓰므로 목소리 전용 파이썬에서도 뜬다.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from host_bridge_guard import BridgeTokenMissing, check_request, load_bridge_token  # noqa: E402
```

(b) `_Handler`의 속성 줄(옛 줄 139-140):
```python
    provider = None
    engine_choice: EngineChoice | None = None
```
새:
```python
    provider = None
    engine_choice: EngineChoice | None = None
    #: `main()`이 `.env.container`에서 읽어 채운다. 비어 있으면 문지기가 503으로 막는다.
    bridge_token: str = ""
```

(c) `_fail` 메서드 바로 아래(옛 줄 153-154 뒤)에 넣는다:

```python
    def _refused(self, *, require_token: bool) -> bool:
        """문지기(`host_bridge_guard`)가 막으면 답을 보내고 `True`를 돌려준다."""
        refusal = check_request(
            method=self.command,
            headers=self.headers,
            port=self.server.server_address[1],
            expected_token=self.bridge_token,
            require_token=require_token,
        )
        if refusal is None:
            return False
        code, payload = refusal
        self._fail(code, str(payload["error"]))
        return True
```

(d) `do_GET`의 첫 줄(옛 줄 156-157):
```python
    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
```
새:
```python
    def do_GET(self) -> None:  # noqa: N802
        # `/health`만 연다. `Start-VideoBox.ps1`이 토큰 없이 켜졌는지 묻는다(Host는 본다).
        if self._refused(require_token=False):
            return
        if self.path != "/health":
```

(e) `do_POST`의 첫 줄(옛 줄 166-167):
```python
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/synthesize":
```
새:
```python
    def do_POST(self) -> None:  # noqa: N802
        # 본문을 읽기 **전에** 막는다. 목소리 샘플이 실린 요청이다.
        if self._refused(require_token=True):
            return
        if self.path != "/synthesize":
```

(f) `main()`(옛 줄 223-229):
```python
def main() -> None:
    choice = resolve_engine(os.environ)
    _Handler.provider = _build_provider(choice)
```
새:
```python
def main() -> None:
    choice = resolve_engine(os.environ)
    try:
        _Handler.bridge_token = load_bridge_token(os.environ, REPO_ROOT / ".env.container")
    except BridgeTokenMissing as exc:
        # 모델(2GB)을 올리기 전에 멈춘다. 토큰 없이 뜬 다리는 아무나 받는다.
        print(f"[voice-bridge] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    _Handler.provider = _build_provider(choice)
```

모듈 docstring의 "## 밖으로 안 나간다" 절(옛 줄 21-24) 끝에 한 문단을 더한다:

```
요청은 `scripts/host_bridge_guard.py`가 먼저 본다(2026-10-02): Host 검사, 공유 토큰
(`X-VideoBox-Bridge-Token`), JSON만. `/health`만 토큰 없이 열려 있다.
```

- [ ] **Step 6: 캡컷 다리에 단다 — `scripts/host_capcut_service.py`**

(a) import 블록 뒤(옛 줄 51 `)` 다음, 줄 53 `DEFAULT_PORT = 8200` 앞)에 넣는다:

```python
# 다리 셋이 같이 쓰는 문지기(`scripts/host_bridge_guard.py`).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from host_bridge_guard import BridgeTokenMissing, check_request, load_bridge_token  # noqa: E402
```

(b) `_Handler` 속성(옛 줄 143-144):
```python
    server_version = "VideoBoxCapCutBridge/1.0"
    allowed_roots: tuple[Path, ...] = ()
```
새:
```python
    server_version = "VideoBoxCapCutBridge/1.0"
    allowed_roots: tuple[Path, ...] = ()
    bridge_token: str = ""
```

(c) `_payload` 메서드 바로 아래(옛 줄 157-162 뒤)에 넣는다:

```python
    def _refused(self) -> bool:
        """문지기가 막으면 답을 보내고 `True`를 돌려준다. 캡컷 다리는 읽기(`/diagnostics`)도
        토큰을 요구한다. 이 컴퓨터의 경로를 돌려주고, 부르는 쪽은 컨테이너뿐이다."""
        refusal = check_request(
            method=self.command,
            headers=self.headers,
            port=self.server.server_address[1],
            expected_token=self.bridge_token,
        )
        if refusal is None:
            return False
        self._reply(*refusal)
        return True
```

(d) `do_GET`·`do_POST`(옛 줄 164-181):
```python
    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/diagnostics":
            ...
    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = self._payload()
```
새(각 메서드 맨 앞에 두 줄을 넣는다):
```python
    def do_GET(self) -> None:  # noqa: N802
        if self._refused():
            return
        if self.path != "/diagnostics":
            ...
    def do_POST(self) -> None:  # noqa: N802
        if self._refused():
            return
        try:
            payload = self._payload()
```

(e) `build_server`(옛 줄 184-186):
```python
def build_server(*, port: int, allowed_roots: tuple[Path, ...]) -> ThreadingHTTPServer:
    handler = type("_BoundHandler", (_Handler,), {"allowed_roots": allowed_roots})
    return ThreadingHTTPServer((BIND_HOST, port), handler)
```
새:
```python
def build_server(*, port: int, allowed_roots: tuple[Path, ...], bridge_token: str) -> ThreadingHTTPServer:
    handler = type("_BoundHandler", (_Handler,), {"allowed_roots": allowed_roots, "bridge_token": bridge_token})
    return ThreadingHTTPServer((BIND_HOST, port), handler)
```

(f) `main`(옛 줄 199-200):
```python
    roots = tuple(Path(value) for value in arguments.allow_root if str(value).strip())
    server = build_server(port=arguments.port, allowed_roots=roots)
```
새:
```python
    roots = tuple(Path(value) for value in arguments.allow_root if str(value).strip())
    try:
        token = load_bridge_token(os.environ, _REPOSITORY_ROOT / ".env.container")
    except BridgeTokenMissing as exc:
        print(f"[capcut-bridge] {exc}", file=sys.stderr, flush=True)
        return 2
    server = build_server(port=arguments.port, allowed_roots=roots, bridge_token=token)
```

- [ ] **Step 7: 그림 다리에 단다 — `scripts/host_infographic_service.py`**

(a) import 블록 뒤(옛 줄 52 `from pathlib import Path` 다음, 줄 54 `DEFAULT_PORT = 8201` 앞)에 넣는다:

```python
# 다리 셋이 같이 쓰는 문지기(`scripts/host_bridge_guard.py`).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from host_bridge_guard import BridgeTokenMissing, check_request, load_bridge_token  # noqa: E402

_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
```

(b) `_Handler` 속성(옛 줄 272-273):
```python
    server_version = "VideoBoxInfographicBridge/1.0"
    browser: Path | None = None
```
새:
```python
    server_version = "VideoBoxInfographicBridge/1.0"
    browser: Path | None = None
    bridge_token: str = ""
```

(c) `_payload` 메서드 아래(옛 줄 286-291 뒤)에 Step 6 (c)와 같은 `_refused` 메서드를 넣는다. docstring만 아래로 바꾼다:

```python
    def _refused(self) -> bool:
        """문지기가 막으면 답을 보내고 `True`를 돌려준다. 읽기(`/diagnostics`)도 토큰을 요구한다.
        부르는 쪽은 컨테이너뿐이다(`infographic_host_bridge.py`)."""
        refusal = check_request(
            method=self.command,
            headers=self.headers,
            port=self.server.server_address[1],
            expected_token=self.bridge_token,
        )
        if refusal is None:
            return False
        self._reply(*refusal)
        return True
```

(d) `do_GET`(옛 줄 293)과 `do_POST`(옛 줄 299)의 맨 앞에 Step 6 (d)와 같은 두 줄을 넣는다:
```python
        if self._refused():
            return
```
`do_POST`에서는 `if self.path not in ("/render", "/measure"):` **앞**에 둔다.

(e) `build_server`(옛 줄 314-316):
```python
def build_server(*, port: int, browser: Path | None) -> ThreadingHTTPServer:
    handler = type("_BoundHandler", (_Handler,), {"browser": browser})
```
새:
```python
def build_server(*, port: int, browser: Path | None, bridge_token: str) -> ThreadingHTTPServer:
    handler = type("_BoundHandler", (_Handler,), {"browser": browser, "bridge_token": bridge_token})
```

(f) `main`(옛 줄 328-329):
```python
    browser = find_browser(arguments.browser)
    server = build_server(port=arguments.port, browser=browser)
```
새:
```python
    browser = find_browser(arguments.browser)
    try:
        token = load_bridge_token(os.environ, _REPOSITORY_ROOT / ".env.container")
    except BridgeTokenMissing as exc:
        print(f"[infographic-bridge] {exc}", file=sys.stderr, flush=True)
        return 2
    server = build_server(port=arguments.port, browser=browser, bridge_token=token)
```

모듈 docstring의 "## HTML은 인터넷에 못 나간다" 절 앞에 한 문단을 더한다:

```
## 아무나 못 부른다 (2026-10-02)

요청은 `scripts/host_bridge_guard.py`가 먼저 본다. Host 검사, 공유 토큰
(`X-VideoBox-Bridge-Token`), JSON만 받는다. 읽기(`/diagnostics`)도 토큰이 필요하다.
```

- [ ] **Step 8: 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_host_bridge_guard.py
```

예상: 전부 통과.

- [ ] **Step 9: 넓은 검증(기존 다리 시험)**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_host_tts_engine_licence.py tests/test_capcut_host_service.py tests/test_infographic_host_service.py tests/test_start_videobox_script.py
```

예상: 전부 통과. 판단 함수(`register_payload`, `render_request_payload` 등)는 바뀌지 않았다.

- [ ] **Step 10: 배선 확인(grep)**

```bash
grep -n "_refused(" scripts/host_tts_service.py scripts/host_capcut_service.py scripts/host_infographic_service.py
grep -n "load_bridge_token(" scripts/host_*_service.py
```

예상: 목소리 3곳(정의 1·GET 1·POST 1), 캡컷 3곳, 그림 3곳. `load_bridge_token(`은 세 파일의 `main`에 하나씩이다.

- [ ] **Step 11: 커밋**

```bash
git add scripts/host_bridge_guard.py scripts/host_tts_service.py scripts/host_capcut_service.py scripts/host_infographic_service.py tests/test_host_bridge_guard.py
git commit -m "$(cat <<'EOF'
fix(security): 다리 셋(8199·8200·8201)에 Host·공유 토큰·JSON 문지기

토큰 없는 요청 401, JSON 아닌 POST 415, 남의 Host 400. 토큰은 .env.container의
VIDEOBOX_BRIDGE_TOKEN이고 없으면 다리가 뜨지 않는다. 목소리 /health만 토큰 없이 연다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: A2(부르는 쪽) — 컨테이너가 토큰을 실어 보낸다

`.env.container`를 이미지에서 빼는 일은 Task 0이 이미 했다. 시작 전에 `grep -n '^\*\*/\.env$' .dockerignore`가 한 줄을 내는지 본다. 안 나오면 **멈추고 Task 0부터 한다.** 토큰을 `.env.container`에 넣는 Task 4가 그 구멍이 열린 채로 돌면 토큰이 이미지에 실린다.

**Files:**
- Create: `packages/provider-interfaces/src/videobox_provider_interfaces/host_bridge_auth.py`
- Modify: `packages/provider-interfaces/src/videobox_provider_interfaces/host_tts_bridge_provider.py:35-36` (import), `:107-112` (`_post`의 `Request`)
- Modify: `packages/core-engine/src/videobox_core_engine/capcut_host_bridge.py:37` (import 뒤), `:137-142` (`_request`의 `Request`)
- Modify: `packages/core-engine/src/videobox_core_engine/infographic_host_bridge.py:30` (import 뒤), `:133-138` (`_request`의 `Request`)
- Modify: `compose.yaml:183` (`VIDEOBOX_INFOGRAPHIC_BRIDGE_URL` 줄 다음)
- Modify: `.env.container.example:63` (`#VIDEOBOX_CAPCUT_SUPPORTED_VERSIONS=...` 다음)
- Modify: `apps/web/src/features/editor/workbench/voiceFailureMessage.ts:21-30`
- Test: `tests/test_host_bridge_guard.py`(이름 대조 하나 추가), `tests/test_host_tts_bridge.py`, `tests/test_capcut_host_bridge.py`, `tests/test_infographic_host_bridge.py`, `tests/test_compose_contract.py`, `apps/web/src/features/editor/workbench/voiceFailureMessage.test.ts`

**Interfaces:**
- Produces: `videobox_provider_interfaces.host_bridge_auth.TOKEN_HEADER: str`, `TOKEN_ENV: str`, `bridge_request_headers(environ: Mapping[str, str] | None = None) -> dict[str, str]`
- Consumes: Task 2의 `scripts/host_bridge_guard.TOKEN_HEADER`·`TOKEN_ENV`(이름이 같아야 한다)

- [ ] **Step 1: 실패하는 시험을 쓴다**

(a) `tests/test_host_tts_bridge.py` 끝에 더한다:

```python
def test_the_bridge_token_rides_along_when_it_is_set(tmp_path: Path, monkeypatch) -> None:
    """다리는 토큰 없는 요청을 401로 거절한다(`scripts/host_bridge_guard.py`)."""
    from videobox_provider_interfaces.host_bridge_auth import TOKEN_ENV, TOKEN_HEADER

    monkeypatch.setenv(TOKEN_ENV, "k" * 43)
    seen: dict[str, Any] = {}

    def client(request: Any, timeout: int) -> bytes:
        seen["token"] = request.get_header(TOKEN_HEADER.capitalize())
        seen["type"] = request.get_header("Content-type")
        return b"RIFF-spoken-audio"

    HostTTSBridgeProvider(http_client=client).synthesize(_request(tmp_path))
    assert seen == {"token": "k" * 43, "type": "application/json"}


def test_no_token_header_is_invented_when_none_is_set(tmp_path: Path, monkeypatch) -> None:
    from videobox_provider_interfaces.host_bridge_auth import TOKEN_ENV, TOKEN_HEADER

    monkeypatch.delenv(TOKEN_ENV, raising=False)
    seen: dict[str, Any] = {}

    def client(request: Any, timeout: int) -> bytes:
        seen["has"] = request.has_header(TOKEN_HEADER.capitalize())
        return b"RIFF-spoken-audio"

    HostTTSBridgeProvider(http_client=client).synthesize(_request(tmp_path))
    assert seen == {"has": False}
```

(b) `tests/test_capcut_host_bridge.py` 끝에 더한다:

```python
def test_the_bridge_token_rides_along_on_every_capcut_call(monkeypatch) -> None:
    from videobox_provider_interfaces.host_bridge_auth import TOKEN_ENV, TOKEN_HEADER

    monkeypatch.setenv(TOKEN_ENV, "c" * 43)
    tokens: list[str | None] = []

    def client(request, timeout):  # noqa: ANN001, ARG001
        tokens.append(request.get_header(TOKEN_HEADER.capitalize()))
        return json.dumps({"status": "ready", "removed": True}).encode("utf-8")

    bridge = CapCutHostBridge(http_client=client)
    bridge.diagnose()
    bridge.cleanup(export_id="e1", registered_host_path="C:/x", ownership_token="o1")
    assert tokens == ["c" * 43, "c" * 43]
```

(c) `tests/test_infographic_host_bridge.py` 끝에 더한다:

```python
def test_the_bridge_token_rides_along_on_measure(monkeypatch) -> None:
    from videobox_provider_interfaces.host_bridge_auth import TOKEN_ENV, TOKEN_HEADER

    monkeypatch.setenv(TOKEN_ENV, "g" * 43)
    tokens: list[str | None] = []

    def client(request, timeout):  # noqa: ANN001, ARG001
        tokens.append(request.get_header(TOKEN_HEADER.capitalize()))
        return json.dumps({"title": "<title>ok</title>"}).encode("utf-8")

    assert InfographicHostBridge(http_client=client).measure(html="<p>x</p>") == "<title>ok</title>"
    assert tokens == ["g" * 43]
```

(d) `tests/test_host_bridge_guard.py` 끝에 더한다:

```python
def test_the_sender_and_the_receiver_use_the_same_names() -> None:
    """받는 쪽(스크립트)과 보내는 쪽(패키지)이 이름을 따로 들고 있다. 어긋나면 전부 401이다."""
    from videobox_provider_interfaces import host_bridge_auth

    assert host_bridge_auth.TOKEN_HEADER == guard.TOKEN_HEADER
    assert host_bridge_auth.TOKEN_ENV == guard.TOKEN_ENV
```

(e) `tests/test_compose_contract.py` 끝에 더한다:

```python
def test_the_container_carries_the_bridge_token_without_requiring_it_to_parse() -> None:
    """다리 셋은 토큰 없는 요청을 거절한다(2026-10-02). 컨테이너가 같은 값을 받아야 부를 수 있다.

    `:?`(필수)로 두지 않는다. 필수 값은 예시 env로 하는 설정 검사(`owner-ready.ps1`의
    `config --quiet`)까지 깨뜨린다. 값은 `owner-ready.ps1 -Mode Start`가 채운다.
    """
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    environment = compose["services"]["videobox-workspace"]["environment"]
    assert environment["VIDEOBOX_BRIDGE_TOKEN"] == "${VIDEOBOX_BRIDGE_TOKEN:-}"
```

(`.dockerignore` 시험은 Task 0에 있다. 여기서 다시 쓰지 않는다.)

(f) `apps/web/src/features/editor/workbench/voiceFailureMessage.test.ts`의 `describe` 블록 안 마지막에 더한다:

```ts
  it("목소리 프로그램이 요청을 거절하면 VideoBox를 다시 켜라고 한다", () => {
    expect(
      voiceFailureMessage('Voice bridge failed (401): {"detail": "bridge_token_required"}'),
    ).toBe("목소리 프로그램이 VideoBox 요청을 받지 않았어요. 바탕화면의 VideoBox 시작 아이콘을 다시 실행해 주세요.");
  });
```

- [ ] **Step 2: 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_host_tts_bridge.py::test_the_bridge_token_rides_along_when_it_is_set
```

예상: FAIL, `ModuleNotFoundError: No module named 'videobox_provider_interfaces.host_bridge_auth'`.

- [ ] **Step 3: 보내는 쪽 헤더 모듈을 만든다**

`packages/provider-interfaces/src/videobox_provider_interfaces/host_bridge_auth.py`:

```python
"""컨테이너에서 이 컴퓨터의 다리 셋(목소리 8199·캡컷 8200·그림 8201)을 부를 때 붙이는 헤더.

받는 쪽 문지기는 `scripts/host_bridge_guard.py`다(2026-10-02, owner 결정 "공유 토큰까지").
두 곳의 이름(헤더·환경 변수)은 같아야 하고, `tests/test_host_bridge_guard.py`가 대조한다.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

TOKEN_HEADER = "X-VideoBox-Bridge-Token"
TOKEN_ENV = "VIDEOBOX_BRIDGE_TOKEN"


def bridge_request_headers(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """JSON 헤더에, 토큰이 있으면 토큰 헤더를 더한다.

    토큰이 없으면 **지어내지 않는다.** 다리가 401로 거절하고 그 사유가 그대로 올라간다.
    조용히 넘어가면 무엇을 고쳐야 하는지 아무도 모른다.
    """

    source = os.environ if environ is None else environ
    headers = {"Content-Type": "application/json"}
    token = str(source.get(TOKEN_ENV) or "").strip()
    if token:
        headers[TOKEN_HEADER] = token
    return headers


__all__ = ["TOKEN_ENV", "TOKEN_HEADER", "bridge_request_headers"]
```

- [ ] **Step 4: 부르는 쪽 셋에 단다**

(a) `host_tts_bridge_provider.py` import(옛 줄 35-36):
```python
from videobox_provider_interfaces.gtts_provider import TTSSynthesisError
from videobox_provider_interfaces.tts import TTSRequest, TTSResult
```
새:
```python
from videobox_provider_interfaces.gtts_provider import TTSSynthesisError
from videobox_provider_interfaces.host_bridge_auth import bridge_request_headers
from videobox_provider_interfaces.tts import TTSRequest, TTSResult
```
`_post`(옛 줄 107-112):
```python
        http_request = Request(
            self._endpoint(path),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
```
새:
```python
        http_request = Request(
            self._endpoint(path),
            data=json.dumps(payload).encode("utf-8"),
            # 다리는 공유 토큰이 없으면 401로 거절한다(`scripts/host_bridge_guard.py`).
            headers=bridge_request_headers(),
            method="POST",
        )
```

(b) `capcut_host_bridge.py` import(옛 줄 37 `from urllib.request import HTTPRedirectHandler, Request, build_opener` 다음)에 더한다:
```python

from videobox_provider_interfaces.host_bridge_auth import bridge_request_headers
```
`_request`(옛 줄 137-142)의 `headers={"Content-Type": "application/json"},`를 아래로 바꾼다:
```python
            # 다리는 공유 토큰이 없으면 401로 거절한다(`scripts/host_bridge_guard.py`).
            headers=bridge_request_headers(),
```

(c) `infographic_host_bridge.py` import(옛 줄 30 다음)와 `_request`(옛 줄 133-138)를 (b)와 똑같이 고친다.

- [ ] **Step 5: compose·예시 env를 고친다**

(a) `compose.yaml` 183줄(`VIDEOBOX_INFOGRAPHIC_BRIDGE_URL: ...`) 바로 다음에 넣는다(들여쓰기 6칸):

```yaml
      # **다리 셋(8199·8200·8201)의 공유 토큰**(owner 결정 2026-10-02). 다리는 이 값이
      # 실린 요청만 받는다. `.env.container`의 같은 줄을 다리도 직접 읽는다.
      # 값은 `owner-ready.ps1 -Mode Start`가 없을 때 한 번 만든다. 필수(`:?`)로 두지
      # 않는 것은 예시 env로 하는 설정 검사까지 깨지 않기 위해서다.
      VIDEOBOX_BRIDGE_TOKEN: ${VIDEOBOX_BRIDGE_TOKEN:-}
```

(b) `.env.container.example` 63줄(`#VIDEOBOX_CAPCUT_SUPPORTED_VERSIONS=8.7.,8.9.,9.3.`) 다음에 넣는다:

```

# 이 컴퓨터의 다리 셋(목소리 8199·캡컷 8200·그림 8201)이 요구하는 공유 토큰.
# **적지 않아도 된다.** `scripts/owner-ready.ps1 -Mode Start`가 처음 켤 때 한 번 만들어
# 이 파일에 넣는다. 컨테이너(compose)와 다리(`scripts/host_bridge_guard.py`)가 같은 줄을 읽는다.
# 바꾸면 다리 셋을 끄고 다시 켜야 한다.
#VIDEOBOX_BRIDGE_TOKEN=
```

- [ ] **Step 6: 더빙 실패 안내에 한 줄을 더한다**

`apps/web/src/features/editor/workbench/voiceFailureMessage.ts`의 첫 `if`(옛 줄 21-23):
```ts
  if (detail.includes("Voice bridge is not answering")) {
    return "목소리를 만드는 프로그램이 꺼져 있어요. 이 컴퓨터에서 목소리 프로그램을 켠 뒤 다시 시도해 주세요.";
  }
```
바로 다음에 넣는다:
```ts
  // 다리는 살아 있는데 공유 토큰이 안 맞는다(2026-10-02). VideoBox를 다시 켜면
  // owner-ready가 토큰을 맞추고 다리를 다시 띄운다.
  if (detail.includes("bridge_token_required") || detail.includes("bridge_token_not_configured")) {
    return "목소리 프로그램이 VideoBox 요청을 받지 않았어요. 바탕화면의 VideoBox 시작 아이콘을 다시 실행해 주세요.";
  }
```

- [ ] **Step 7: 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_host_tts_bridge.py tests/test_capcut_host_bridge.py tests/test_infographic_host_bridge.py tests/test_host_bridge_guard.py tests/test_compose_contract.py tests/test_hermes_yujin_compose_contract.py tests/test_tts_provider_selection.py
(cd apps/web && npx vitest run src/features/editor/workbench/voiceFailureMessage.test.ts)
```

예상: 전부 통과.

- [ ] **Step 8: 새 import가 순환을 만들지 않는지 새 인터프리터에서 본다**

```bash
PYTHONPATH="packages/provider-interfaces/src;packages/core-engine/src;packages/domain-models/src;packages/storage-abstractions/src;packages/capcut-export/src" .venv/Scripts/python.exe -c "import videobox_core_engine.capcut_host_bridge, videobox_core_engine.infographic_host_bridge, videobox_provider_interfaces.host_tts_bridge_provider; print('ok')"
```

예상: `ok`.

- [ ] **Step 9: 배선 확인(grep)**

```bash
grep -rn "bridge_request_headers()" packages/ --include=*.py
grep -rn "VIDEOBOX_BRIDGE_TOKEN" compose.yaml .env.container.example
grep -rn 'headers={"Content-Type": "application/json"}' packages/core-engine/src/videobox_core_engine/capcut_host_bridge.py packages/core-engine/src/videobox_core_engine/infographic_host_bridge.py packages/provider-interfaces/src/videobox_provider_interfaces/host_tts_bridge_provider.py
```

예상: 첫 줄은 정확히 3곳(목소리·캡컷·그림). 둘째 줄은 compose 1곳과 예시 1곳. 셋째 줄은 0건이다(옛 헤더가 남아 있으면 그 다리는 401을 받는다).

- [ ] **Step 10: 커밋**

```bash
git add packages/provider-interfaces/src/videobox_provider_interfaces/host_bridge_auth.py packages/provider-interfaces/src/videobox_provider_interfaces/host_tts_bridge_provider.py packages/core-engine/src/videobox_core_engine/capcut_host_bridge.py packages/core-engine/src/videobox_core_engine/infographic_host_bridge.py compose.yaml .env.container.example apps/web/src/features/editor/workbench/voiceFailureMessage.ts apps/web/src/features/editor/workbench/voiceFailureMessage.test.ts tests/test_host_tts_bridge.py tests/test_capcut_host_bridge.py tests/test_infographic_host_bridge.py tests/test_host_bridge_guard.py tests/test_compose_contract.py
git commit -m "$(cat <<'EOF'
fix(security): 컨테이너가 다리 토큰을 실어 보낸다

부르는 쪽 셋이 bridge_request_headers()로 X-VideoBox-Bridge-Token을 붙인다.
compose가 VIDEOBOX_BRIDGE_TOKEN을 넘긴다(.dockerignore는 Task 0에서 이미 막았다).
더빙 401은 창작자 말로 옮긴다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: A2(토큰 만들기) — `owner-ready.ps1 -Mode Start`가 토큰을 한 번만 만든다

**Files:**
- Modify: `scripts/owner-ready.ps1:1084-1087` (`if ($preflightStatus -cne "pass") {...}` 블록과 `$actualComposeResult = ...` 사이)
- Modify: `docs/development-fast-path.ko.md:389-390` (§10.14 2-C의 "근거가 아니다(조항 4 유지)." 줄 다음)
- Test: `tests/test_owner_ready_script.py`(끝에 셋 추가)

**Interfaces:**
- Consumes: `.env.container`(경로는 `$EnvFile`)
- Produces: `.env.container`의 한 줄 `VIDEOBOX_BRIDGE_TOKEN=<43자 base64url>`. Task 2의 `load_bridge_token`과 compose가 읽는다.

정한 것과 이유: 기존 `new-hermes-yujin-secrets.ps1`은 유진 전용이다. 관리 키가 env에 **이미 있어야** 하고(`env_missing_keys`로 멈춘다), docker로 해시를 계산한다. 다리 토큰은 VideoBox를 켤 때마다 있어야 하므로, 켜는 자리(`owner-ready.ps1` Start)에서 없을 때만 만든다. 파이썬을 부르지 않고 PowerShell 안에서 만든다. 시험이 가짜 파이썬으로 Start를 돌리기 때문이다(`tests/test_owner_ready_script.py`의 `_run`).

- [ ] **Step 1: 실패하는 시험을 쓴다**

`tests/test_owner_ready_script.py` 끝에 더한다:

```python
_BRIDGE_TOKEN_LINE = re.compile(r"(?m)^VIDEOBOX_BRIDGE_TOKEN=([A-Za-z0-9_-]+)\s*$")


def test_start_writes_one_bridge_token_once_and_never_prints_it(tmp_path: Path) -> None:
    """다리 셋의 공유 토큰(2026-10-02). 켤 때 없으면 한 번 만들고, 다시 켜도 바꾸지 않는다.
    바꾸면 이미 떠 있는 다리와 어긋나 더빙·캡컷·그림이 전부 401이 된다."""
    fixture = _fixture_repository(tmp_path)
    with _health_server() as video_uri:
        first = _run(fixture, mode="Start", video_uri=video_uri)
    assert first.returncode == 0, _why_it_failed(first)
    tokens = _BRIDGE_TOKEN_LINE.findall(fixture["env_file"].read_text(encoding="utf-8-sig"))
    assert len(tokens) == 1 and len(tokens[0]) >= 43
    assert tokens[0] not in first.stdout and tokens[0] not in first.stderr

    with _health_server() as video_uri:
        second = _run(fixture, mode="Start", video_uri=video_uri)
    assert second.returncode == 0, _why_it_failed(second)
    assert _BRIDGE_TOKEN_LINE.findall(fixture["env_file"].read_text(encoding="utf-8-sig")) == tokens


def test_start_replaces_an_empty_bridge_token_line_and_keeps_bom_and_crlf(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    original = fixture["env_file"].read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n")
    fixture["env_file"].write_bytes(
        codecs.BOM_UTF8 + (original + "\nVIDEOBOX_BRIDGE_TOKEN=\n").replace("\n", "\r\n").encode("utf-8")
    )
    with _health_server() as video_uri:
        result = _run(fixture, mode="Start", video_uri=video_uri)
    assert result.returncode == 0, _why_it_failed(result)
    raw = fixture["env_file"].read_bytes()
    assert raw.startswith(codecs.BOM_UTF8)
    text = raw.decode("utf-8-sig")
    assert "\n" not in text.replace("\r\n", "")
    assert len(re.findall(r"(?m)^VIDEOBOX_BRIDGE_TOKEN=", text)) == 1
    assert len(_BRIDGE_TOKEN_LINE.findall(text)) == 1


def test_start_whatif_leaves_the_env_file_alone(tmp_path: Path) -> None:
    fixture = _fixture_repository(tmp_path)
    before = fixture["env_file"].read_bytes()
    result = _run(fixture, mode="Start", extra=["-WhatIf"])
    assert result.returncode == 0, _why_it_failed(result)
    assert fixture["env_file"].read_bytes() == before
```

두 번째 시험이 BOM이 있는 env로도 Start를 통과하는지는 Step 2에서 먼저 확인한다. 만약 Start 전 검사가 BOM env를 막는다면(옛 동작), 그 시험에서 BOM 부분만 빼고 CRLF만 시험한다. 이렇게 고쳤다면 갭 보고에 적는다. 확인 근거는 `test_smoke_credential_classifier_accepts_strict_utf8_bom`(BOM UTF-8을 받는다)이다.

- [ ] **Step 2: 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_owner_ready_script.py::test_start_writes_one_bridge_token_once_and_never_prints_it
```

예상: FAIL, `assert 0 == 1`(토큰 줄이 없다). 이어서 BOM 시험도 돌려, 실패 이유가 "토큰 줄 없음"인지(정상) 아니면 Start가 BOM 때문에 막혔는지 본다:

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_owner_ready_script.py::test_start_replaces_an_empty_bridge_token_line_and_keeps_bom_and_crlf
```

- [ ] **Step 3: 토큰 만들기를 넣는다**

`scripts/owner-ready.ps1`의 Start 블록에서 아래(옛 줄 1084-1087)를 찾는다:

```powershell
    if ($preflightStatus -cne "pass") {
        Write-OwnerReadyPayload -Checks $checks
    }
    $actualComposeResult = Invoke-CapturedProcess -FilePath $DockerExecutable -Arguments @(
```

`}`와 `$actualComposeResult` 사이에 넣는다:

```powershell
    # **다리 셋(8199·8200·8201)의 공유 토큰** (owner 결정 2026-10-02).
    # 컨테이너(compose `VIDEOBOX_BRIDGE_TOKEN`)와 다리(`scripts/host_bridge_guard.py`)가
    # 이 파일의 같은 줄을 읽는다. **없을 때만** 한 번 만들고 그 뒤로는 바꾸지 않는다.
    # 바꾸면 이미 떠 있는 다리와 어긋난다. 값은 화면에도 결과에도 찍지 않는다.
    # BOM과 줄바꿈 모양은 원래대로 지킨다.
    if (-not $PSBoundParameters.ContainsKey("WhatIf")) {
        $bridgeEnvPath = (Resolve-Path -LiteralPath $EnvFile).Path
        $bridgeEnvBytes = [IO.File]::ReadAllBytes($bridgeEnvPath)
        $bridgeEnvHasBom = $bridgeEnvBytes.Length -ge 3 -and $bridgeEnvBytes[0] -eq 0xEF -and $bridgeEnvBytes[1] -eq 0xBB -and $bridgeEnvBytes[2] -eq 0xBF
        $bridgeEnvOffset = if ($bridgeEnvHasBom) { 3 } else { 0 }
        $bridgeEnvText = (New-Object System.Text.UTF8Encoding($false)).GetString($bridgeEnvBytes, $bridgeEnvOffset, $bridgeEnvBytes.Length - $bridgeEnvOffset)
        if ($bridgeEnvText -notmatch '(?m)^[ \t]*VIDEOBOX_BRIDGE_TOKEN[ \t]*=[ \t]*[A-Za-z0-9_\-]{32,}[ \t]*\r?$') {
            $bridgeTokenBytes = New-Object byte[] 32
            $bridgeRandom = [System.Security.Cryptography.RandomNumberGenerator]::Create()
            try { $bridgeRandom.GetBytes($bridgeTokenBytes) } finally { $bridgeRandom.Dispose() }
            $bridgeTokenValue = [Convert]::ToBase64String($bridgeTokenBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
            $bridgeNewline = if ($bridgeEnvText.Contains("`r`n")) { "`r`n" } else { "`n" }
            $bridgeWithout = [regex]::Replace($bridgeEnvText, '(?m)^[ \t]*VIDEOBOX_BRIDGE_TOKEN[ \t]*=[^\n]*(\n|$)', '')
            if ($bridgeWithout.Length -gt 0 -and -not $bridgeWithout.EndsWith("`n")) { $bridgeWithout += $bridgeNewline }
            $bridgeUpdated = $bridgeWithout + "VIDEOBOX_BRIDGE_TOKEN=" + $bridgeTokenValue + $bridgeNewline
            [IO.File]::WriteAllText($bridgeEnvPath, $bridgeUpdated, (New-Object System.Text.UTF8Encoding($bridgeEnvHasBom)))
            Remove-Variable -Name bridgeTokenValue, bridgeUpdated -ErrorAction SilentlyContinue
        }
    }
```

검토할 점: `[^\n]*(\n|$)`는 CRLF 줄의 `\r`까지 함께 지운다. 빈 `VIDEOBOX_BRIDGE_TOKEN=` 줄이나 짧은 값 줄은 지우고 새 줄 하나로 바꾼다. 주석 줄(`#VIDEOBOX_BRIDGE_TOKEN=`)은 `^[ \t]*VIDEOBOX`에 안 맞아 그대로 남는다.

- [ ] **Step 4: 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_owner_ready_script.py::test_start_writes_one_bridge_token_once_and_never_prints_it tests/test_owner_ready_script.py::test_start_replaces_an_empty_bridge_token_line_and_keeps_bom_and_crlf tests/test_owner_ready_script.py::test_start_whatif_leaves_the_env_file_alone
```

예상: 3 passed.

- [ ] **Step 5: 넓은 검증**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_owner_ready_script.py tests/test_start_videobox_script.py tests/test_new_hermes_yujin_secrets_script.py
```

예상: 알려진 실패 1건(`test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure`) 말고는 전부 통과.

- [ ] **Step 6: 운영 규정에 한 문단을 더한다**

`docs/development-fast-path.ko.md` 389-390줄을 찾는다:
```
   - 이 승인은 **호스트의 ComfyUI를 부르는 경로에만** 적용된다. 다른 host bridge의
     근거가 아니다(조항 4 유지).
```
바로 다음에 넣는다:
```
   - **다리 셋(목소리 8199·캡컷 8200·그림 8201)은 공유 토큰을 요구한다(2026-10-02, owner 결정).**
     세 가지를 본다: `X-VideoBox-Bridge-Token` 헤더, JSON만, Host 검사(`scripts/host_bridge_guard.py`).
     토큰은 `.env.container`의 `VIDEOBOX_BRIDGE_TOKEN` 한 줄이다. `owner-ready.ps1 -Mode Start`가
     없을 때만 만든다. 컨테이너는 compose로 받고, 다리는 같은 파일을 직접 읽는다.
     목소리 `/health`만 토큰 없이 열려 있다(`Start-VideoBox.ps1`이 켜졌는지 묻는 자리).
     다리 코드나 토큰을 바꾸면 **이미 떠 있는 다리를 끄고** 다시 켜야 한다.
     `owner-ready`는 포트가 열려 있으면 다시 띄우지 않는다.
```

- [ ] **Step 7: 커밋**

```bash
git add scripts/owner-ready.ps1 tests/test_owner_ready_script.py docs/development-fast-path.ko.md
git commit -m "$(cat <<'EOF'
feat(owner-ready): 켤 때 다리 공유 토큰을 없을 때만 한 번 만든다

.env.container에 VIDEOBOX_BRIDGE_TOKEN(32바이트 base64url)을 넣고, BOM·줄바꿈을 지키며,
값은 찍지 않는다. -WhatIf에서는 쓰지 않는다. §10.14에 다리 토큰 규정을 적는다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: A3 — 인포그래픽 HTML에 실행 코드가 있으면 그리기 전에 거절한다

**Files:**
- Modify: `packages/core-engine/src/videobox_core_engine/infographic_brief.py:205` (프롬프트 "지켜야 할 것" 11번 다음), `:215` (`_CSS_IMPORT` 다음에 정규식), `:282-283` (`check_infographic_html`의 바깥 주소 검사 다음)
- Modify: `tests/test_infographic_brief.py:127-132` (`test_numbers_inside_a_script_are_not_made_up_numbers`의 계약이 바뀐다)

**Interfaces:**
- Consumes: 없음
- Produces: `check_infographic_html(html, facts)`가 새 문제 문구 `"실행 코드가 들어 있다 — <script>·on...= 속성·javascript: 주소는 쓰지 않는다"`를 낼 수 있다. `InfographicService.generate`는 이 문구를 재시도 프롬프트(`_retry_prompt`)로 모델에게 돌려준다.

정한 것과 이유(CSP 메타 주입이 아니라 거절을 고른 까닭): 다리에 `script-src 'none'` CSP를 넣으면 **우리 측정 스크립트도 막힌다.** `infographic_layout_audit.py:52-118`이 검사를 통과한 HTML에 `<script id="videobox-audit">`를 끼워 `/measure`로 보내고, 그 결과로 겹침·넘침을 잰다. 거절은 모델이 쓴 HTML만 본다(`infographic_service.py:151-156`에서 검사가 측정보다 먼저다). 그래서 측정은 그대로 돌고, 움직이지 않는 그림 한 장에는 실행 코드가 필요 없다. 다리 쪽 2차 방어(이름 풀이 차단, 빈 프로필)는 그대로 둔다.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`tests/test_infographic_brief.py`의 127-132줄 시험 전체를 아래로 **바꾼다**(옛 시험은 `<script>`가 든 HTML이 통과해야 한다고 고정하고 있었다. 이 계약이 바뀐다):

```python
def test_numbers_inside_a_script_are_not_made_up_numbers() -> None:
    """`<script>` 안의 숫자는 사람이 읽는 자리가 아니다. 그래서 숫자로 걸리지는 않는다.
    다만 2026-10-02부터 스크립트 자체가 거절된다(아래 시험). 둘은 다른 문제로 보고된다."""

    html = _page("<p>94.6%</p><script>var frames=[0,17,42,60];</script>")
    problems = check_infographic_html(html, FACTS)
    assert not any("준 적 없는 숫자" in problem for problem in problems)
    assert any("실행 코드" in problem for problem in problems)


@pytest.mark.parametrize(
    "fragment",
    [
        "<script>alert(1)</script>",
        "<SCRIPT src='x.js'></SCRIPT>",
        "< script>fetch('/x')</script>",
        "<img src='a.png' onerror='alert(1)'>",
        "<div ONLOAD = \"x()\">94.6%</div>",
        "<body onload=go()>",
        "<a href=\"JavaScript:alert(1)\">94.6%</a>",
        "<svg><a href='javascript :x'>3.4</a></svg>",
    ],
)
def test_code_that_would_run_in_the_browser_is_refused(fragment: str) -> None:
    """그림은 이 컴퓨터의 크롬이 그린다(2026-10-01 보안 점검 M3 부속). 움직이지 않는
    한 장이라 실행 코드는 쓸 데가 없다. 측정용 스크립트는 우리가 검사 **뒤에** 붙인다."""

    problems = check_infographic_html(_page(f"<p>94.6%</p>{fragment}"), FACTS)
    assert any("실행 코드" in problem for problem in problems), problems


@pytest.mark.parametrize(
    "fragment",
    [
        "<!-- 계산: onload=없음, <script> 안 씀, 360*0.946=340.56 -->",
        "<p style='font-family:sans-serif'>온라인 수수료 3.4%</p>",
        "<p>one = 1이 아니다, 94.6%</p>",
        "<div class='donut' data-on='true'>94.6%</div>",
    ],
)
def test_ordinary_html_is_not_mistaken_for_code(fragment: str) -> None:
    problems = check_infographic_html(_page(fragment), FACTS)
    assert not any("실행 코드" in problem for problem in problems), problems


def test_the_brief_tells_the_writer_not_to_use_code() -> None:
    prompt = build_infographic_prompt(topic="수수료 구조", facts=FACTS, style="editorial")
    assert "<script>" in prompt and "onload" in prompt
```

참고: `data-on='true'`는 `\son[a-z]+\s*=`에 안 맞는다(`data-on` 앞이 공백이 아니라 `-`이고, `on` 뒤에 글자가 없다). 주석 안의 `onload=`·`<script>`는 주석을 먼저 지우므로 거절하지 않는다(주석은 실행되지 않는다).

- [ ] **Step 2: 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider "tests/test_infographic_brief.py::test_code_that_would_run_in_the_browser_is_refused"
```

예상: 8개 모두 FAIL, `AssertionError: ()`(문제 없음)처럼 빈 문제 목록이 찍힌다.

- [ ] **Step 3: 최소 구현**

(a) `infographic_brief.py` 215줄 `_CSS_IMPORT = re.compile(r"@import\b", re.IGNORECASE)` 다음에 넣는다:

```python
#: 그림은 **움직이지 않는 한 장**이고, 이 컴퓨터의 크롬이 그린다. 실행 코드는 쓸 데가
#: 없다(2026-10-01 보안 점검 M3 부속, 2026-10-02 고침). 측정용 스크립트
#: (`infographic_layout_audit`)는 이 검사를 통과한 **뒤에** 우리가 붙인다. 그래서 CSP로
#: 막지 않고 여기서 거절한다. CSP는 그 측정까지 막는다.
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_SCRIPT_TAG = re.compile(r"<\s*script\b", re.IGNORECASE)
_EVENT_HANDLER = re.compile(r"<[^>]*\son[a-z]+\s*=", re.IGNORECASE | re.DOTALL)
_JAVASCRIPT_URL = re.compile(r"javascript\s*:", re.IGNORECASE)
```

(b) `check_infographic_html`의 바깥 주소 검사(옛 282-283줄):
```python
    if _EXTERNAL.search(html) or _CSS_IMPORT.search(html):
        problems.append("바깥 주소를 부른다 — 인터넷 없이 그려야 한다")
```
바로 다음에 넣는다:
```python
    # 주석은 실행되지 않는다. 브리핑이 계산을 주석에 남기라고 시키므로 주석 안은 보지 않는다.
    code_view = _COMMENT.sub(" ", html)
    if _SCRIPT_TAG.search(code_view) or _EVENT_HANDLER.search(code_view) or _JAVASCRIPT_URL.search(code_view):
        problems.append("실행 코드가 들어 있다 — <script>·on...= 속성·javascript: 주소는 쓰지 않는다")
```

(c) 프롬프트의 "지켜야 할 것"(옛 205줄 `11. 한국어로 쓴다.`) 다음 줄에 넣는다:
```
12. **실행 코드를 넣지 마라.** `<script>`, `onload=` 같은 `on...=` 속성, `javascript:` 주소가
   하나라도 있으면 거절한다. 움직이지 않는 그림 한 장이다.
```

- [ ] **Step 4: 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_infographic_brief.py
```

예상: 전부 통과.

- [ ] **Step 5: 넓은 검증**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_infographic_service.py tests/test_infographic_layout_audit.py tests/test_api_infographics.py tests/test_infographic_host_service.py
```

예상: 전부 통과. 측정용 스크립트 시험(`test_infographic_layout_audit.py`)은 `check_infographic_html`을 지나지 않으므로 영향이 없다.

- [ ] **Step 6: 배선 확인(grep)**

```bash
grep -rn "check_infographic_html(" packages/ services/ --include=*.py
```

예상: 정의 1곳(`infographic_brief.py`)과 부르는 자리 1곳(`infographic_service.py:152`). 그 부르는 자리가 `self._render(html)`보다 앞에 있는지 눈으로 본다.

- [ ] **Step 7: 커밋**

```bash
git add packages/core-engine/src/videobox_core_engine/infographic_brief.py tests/test_infographic_brief.py
git commit -m "$(cat <<'EOF'
fix(security): 인포그래픽 HTML에 <script>·on*=·javascript:가 있으면 그리기 전에 거절

CSP 주입은 우리 측정 스크립트(infographic_layout_audit)까지 막아서 고르지 않았다.
주석 안은 보지 않는다. 브리핑에도 실행 코드 금지를 적는다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: A4(API) — `PATCH /api/library/assets/{asset_id}/filename`

**Files:**
- Create: `tests/test_library_asset_rename.py`
- Modify: `services/api/src/videobox_api/models.py:1686` (`CorrectLibraryAssetMediaTypeRequest` 앞)
- Modify: `services/api/src/videobox_api/routers/library_assets.py:26-32` (import), `:689-690` (`/favorite` 라우트 다음, `/restore` 라우트 앞)
- Modify: `packages/storage-abstractions/src/videobox_storage/library_user_asset_store.py:401-403` (`set_favorite` 끝과 `update_media_type` 사이)

**Interfaces:**
- Produces:
  - `RenameLibraryAssetRequest(BaseModel)`: `filename: str`(앞뒤 공백을 지우고 1~255자. `/`·`\`·제어 문자·`.`·`..` 거절, `extra="forbid"`)
  - `LibraryUserAssetStore.rename_asset(self, library_asset_id: str, *, filename: str) -> LibraryUserAsset`(없으면 `KeyError`, 기본 소재팩 줄이면 `ValueError("builtin_asset_immutable")`, 빈 이름이면 `ValueError("filename_empty")`)
  - 라우트 `PATCH /api/library/assets/{asset_id}/filename` → `{"asset": <public_user>}`. 404 `asset_missing`, 409 `{"code": "builtin_asset_immutable"}`, 422(형식)
- Consumes: 기존 `find_asset`, `public_user`(`library_assets.py:140-195`)

배경: 자료실이 보여 주는 이름은 `user_metadata.filename`이다(`apps/web/src/features/library/LibraryPreviewPane.tsx:5`, `VideoAssetGrid.tsx:4`, `AudioAssetRows.tsx:4`, `library_ingest.py:166`). 파일 바이트와 `managed_relative_path`는 해시로 찾으므로 이름과 상관없다. 의미 색인도 이 이름을 읽지 않는다. `library_audio_indexer.py:244`의 `asset_name`은 자산 id다. 그래서 이름을 바꿔도 다시 색인할 필요가 없다. 단어 검색(`/api/library/search`의 `haystack`, `library_assets.py:412`)과 목록 검색(`q`)은 바뀐 이름으로 바로 찾는다.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`tests/test_library_asset_rename.py`:

```python
"""자료실 이름 바꾸기 (2026-10-02, 점검 후속 A4).

2026-10-01 점검에서 자료실 이름 24개가 `³ìÀ½ 2026-...` 꼴로 깨져 있었다(cp949 바이트를
라틴1로 읽은 것). 고칠 길이 없었다. 이름은 `user_metadata.filename`에 있다.
파일과 관리 경로는 해시로 찾으므로 이름을 바꿔도 손대지 않는다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videobox_api.main import create_app
from videobox_domain_models.library_assets import LibraryMediaType
from videobox_storage.library_user_asset_store import LibraryUserAssetStore
from videobox_storage.media_library_store import MediaLibraryStore

BROKEN = "\xb3\xec\xc0\xbd 2026-02-07 163617.mp4"
FIXED = "녹음 2026-02-07 163617.mp4"


def _client(tmp_path: Path) -> TestClient:
    app = create_app(
        projects_root=tmp_path / "projects",
        media_library_store=MediaLibraryStore(tmp_path / "library"),
        media_analysis_poll_interval_seconds=3600,
    )
    app.state.media_library_store.user_asset_store.register_asset(
        library_asset_id="user_clip_1",
        media_type=LibraryMediaType.BROLL,
        origin="user",
        content_sha256="c" * 64,
        managed_relative_path="assets/broll/cc/clip.mp4",
        byte_count=10,
        mime_type="video/mp4",
        user_metadata={"filename": BROKEN, "favorite": True, "tags": ["도시"]},
    )
    return TestClient(app)


def test_the_owner_can_rename_an_own_asset_and_the_other_notes_stay(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.patch("/api/library/assets/user_clip_1/filename", json={"filename": f"  {FIXED} "})

    assert response.status_code == 200, response.text
    metadata = response.json()["asset"]["user_metadata"]
    assert metadata == {"filename": FIXED, "favorite": True, "tags": ["도시"]}
    again = client.get("/api/library/assets/user_clip_1").json()["asset"]
    assert again["user_metadata"]["filename"] == FIXED
    assert again["managed_relative_path"] == "assets/broll/cc/clip.mp4"


def test_the_renamed_asset_is_found_by_its_new_name(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.patch("/api/library/assets/user_clip_1/filename", json={"filename": FIXED})

    found = client.get("/api/library/assets", params={"q": "녹음"}).json()["assets"]

    assert [asset["library_asset_id"] for asset in found if asset["origin"] == "user"] == ["user_clip_1"]


@pytest.mark.parametrize("bad", ["", "   ", "a/b.mp4", "a\\b.mp4", "줄\n바꿈.mp4", "탭\t.mp4", ".", "..", "x" * 256])
def test_a_name_that_is_not_a_plain_file_name_is_refused(tmp_path: Path, bad: str) -> None:
    client = _client(tmp_path)

    response = client.patch("/api/library/assets/user_clip_1/filename", json={"filename": bad})

    assert response.status_code == 422, response.text
    assert client.get("/api/library/assets/user_clip_1").json()["asset"]["user_metadata"]["filename"] == BROKEN


def test_unknown_fields_are_refused(tmp_path: Path) -> None:
    response = _client(tmp_path).patch(
        "/api/library/assets/user_clip_1/filename", json={"filename": FIXED, "managed_relative_path": "x"}
    )
    assert response.status_code == 422


def test_an_unknown_asset_is_404(tmp_path: Path) -> None:
    response = _client(tmp_path).patch("/api/library/assets/user_nope/filename", json={"filename": FIXED})
    assert response.status_code == 404


def test_a_builtin_row_is_never_renamed_in_the_store(tmp_path: Path) -> None:
    store = LibraryUserAssetStore(tmp_path)
    store.register_asset(
        library_asset_id="builtin_1",
        media_type=LibraryMediaType.MUSIC,
        origin="builtin",
        content_sha256="e" * 64,
        managed_relative_path="assets/music/ee/x.mp3",
        byte_count=1,
        mime_type="audio/mpeg",
        user_metadata={"filename": "x.mp3"},
    )
    with pytest.raises(ValueError, match="builtin_asset_immutable"):
        store.rename_asset("builtin_1", filename="y.mp3")
    assert store.get_asset("builtin_1").user_metadata["filename"] == "x.mp3"
```

- [ ] **Step 2: 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_library_asset_rename.py::test_the_owner_can_rename_an_own_asset_and_the_other_notes_stay
```

예상: FAIL, `assert 405 == 200`(PATCH 라우트가 없다. 같은 경로의 GET `/{derivative_kind}`만 있어서 405가 난다).

- [ ] **Step 3: 요청 모델을 더한다**

`services/api/src/videobox_api/models.py` 1686줄 `class CorrectLibraryAssetMediaTypeRequest(BaseModel):` **앞**에 넣는다:

```python
class RenameLibraryAssetRequest(BaseModel):
    """자료실에 보이는 이름을 바꾼다 (2026-10-02, 점검 후속 A4).

    이름은 표시용이라 파일 경로가 되지 않는다. 그래도 경로처럼 보이는 값(`/`·`\\`)과
    제어 문자는 받지 않는다. 화면·검색·캡컷 초안 어디에 찍혀도 모양이 깨지지 않게 하려는 것이다.
    """

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255)

    @field_validator("filename")
    @classmethod
    def _plain_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("filename_empty")
        if cleaned in {".", ".."} or any(ch in cleaned for ch in "/\\"):
            raise ValueError("filename_invalid")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in cleaned):
            raise ValueError("filename_invalid")
        return cleaned
```

`"x" * 256`은 `max_length=255`에 먼저 걸린다. `"   "`는 `min_length`를 넘기지만 검사기에서 `filename_empty`로 걸린다.

- [ ] **Step 4: store 메서드를 더한다**

`library_user_asset_store.py`에서 `set_favorite`의 끝(옛 줄 397-401):
```python
        except Exception:
            connection.rollback(); raise
        finally:
            connection.close()

    def update_media_type(self, library_asset_id: str, media_type: LibraryMediaType | str) -> LibraryUserAsset:
```
`connection.close()`와 `def update_media_type` 사이에 넣는다:

```python
    def rename_asset(self, library_asset_id: str, *, filename: str) -> LibraryUserAsset:
        """자료실에 보이는 이름(`user_metadata.filename`)을 바꾼다 (2026-10-02, 점검 후속 A4).

        파일 바이트와 `managed_relative_path`는 건드리지 않는다. 파일은 해시로 찾는다.
        같은 `user_metadata` 안의 즐겨찾기·태그는 그대로 둔다. 기본 소재팩 줄은 고치지 않는다.
        """
        cleaned = str(filename).strip()
        if not cleaned:
            raise ValueError("filename_empty")
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM library_user_assets WHERE library_asset_id = ?", (library_asset_id,)).fetchone()
            if row is None:
                raise KeyError(library_asset_id)
            if str(row["origin"]) == LibraryAssetOrigin.BUILTIN.value:
                raise ValueError("builtin_asset_immutable")
            user_metadata = dict(LibraryUserAsset.from_row(dict(row)).user_metadata)
            user_metadata["filename"] = cleaned
            connection.execute(
                "UPDATE library_user_assets SET user_json = ?, updated_at = ? WHERE library_asset_id = ?",
                (_json(user_metadata), _now(), library_asset_id),
            )
            updated = connection.execute("SELECT * FROM library_user_assets WHERE library_asset_id = ?", (library_asset_id,)).fetchone()
            connection.commit()
            assert updated is not None
            return LibraryUserAsset.from_row(dict(updated))
        except Exception:
            connection.rollback(); raise
        finally:
            connection.close()
```

- [ ] **Step 5: 라우트를 더한다**

(a) `routers/library_assets.py` import(옛 26-32줄):
```python
from videobox_api.models import (
    CorrectLibraryAssetMediaTypeRequest,
    UpdateLibraryAssetFavoriteRequest,
```
새:
```python
from videobox_api.models import (
    CorrectLibraryAssetMediaTypeRequest,
    RenameLibraryAssetRequest,
    UpdateLibraryAssetFavoriteRequest,
```

(b) `/favorite` 라우트의 마지막 줄(옛 689줄):
```python
        return {"asset": public_user(user_asset_store.set_favorite(asset_id, favorite=payload.favorite))}
```
다음, `@router.post("/api/library/assets/{asset_id}/restore")`(691줄) 앞에 넣는다:

```python
    @router.patch("/api/library/assets/{asset_id}/filename")
    def rename_library_asset(asset_id: str, payload: RenameLibraryAssetRequest) -> dict[str, Any]:
        """자료실에 보이는 이름을 바꾼다 (2026-10-02, 점검 후속 A4).

        2026-10-01 점검에서 이름 24개가 깨져 있었는데 고칠 길이 없었다. 파일과 관리 경로는
        그대로 두고 `user_metadata.filename`만 바꾼다. 의미 색인은 이 이름을 읽지 않으므로
        다시 색인할 필요가 없다(`library_audio_indexer`의 `asset_name`은 자산 id다).
        """
        asset, builtin = find_asset(asset_id)
        if builtin is not None:
            raise HTTPException(status_code=409, detail={"code": "builtin_asset_immutable"})
        try:
            updated = user_asset_store.rename_asset(asset_id, filename=payload.filename)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": str(exc)}) from exc
        return {"asset": public_user(updated)}
```

- [ ] **Step 6: 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_library_asset_rename.py
```

예상: 전부 통과.

- [ ] **Step 7: 넓은 검증**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_library_asset_favorite.py tests/test_api_library_assets.py tests/test_media_library_store.py tests/test_api_asset_waveform.py
```

예상: 전부 통과.

- [ ] **Step 8: 커밋**

```bash
git add services/api/src/videobox_api/models.py services/api/src/videobox_api/routers/library_assets.py packages/storage-abstractions/src/videobox_storage/library_user_asset_store.py tests/test_library_asset_rename.py
git commit -m "$(cat <<'EOF'
feat(library): 자료실 이름 바꾸기 API(PATCH .../filename)

user_metadata.filename만 바꾸고 파일·관리 경로·즐겨찾기·태그는 그대로 둔다.
경로 구분자·제어 문자·빈 이름·256자 이상은 422, 기본 소재팩은 409.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: A4(화면) — 미리보기 칸에서 이름을 바로 바꾼다

**Files:**
- Modify: `apps/web/src/api.ts:2342` (`setLibraryAssetFavorite` 블록이 끝나는 `),` 다음)
- Modify: `apps/web/src/features/library/LibraryPreviewPane.tsx:67-72` (상태), `:76-85` (함수), `:86` (머리말 `<h2>{name}</h2>`)
- Modify: `apps/web/src/features/library/library.css:11` (줄 끝에 규칙 덧붙임)
- Modify: `apps/web/src/task22-parity-owners.test.ts:147-149`
- Test: `apps/web/src/features/library/LibraryPage.test.tsx`(끝 `describe` 안에 셋 추가)

**Interfaces:**
- Consumes: Task 6의 `PATCH /api/library/assets/{asset_id}/filename`
- Produces: `api.renameLibraryAsset(libraryAssetId: string, filename: string): Promise<{ asset: LibraryAsset }>`. 화면 네이티브 컨트롤 `button:library-rename`, `button:library-rename-save`, `button:library-rename-cancel`, `input:library-rename-input`

화면 규칙: 대표님 자산(`origin !== "builtin"`)이고 휴지통에 있지 않을 때만 `이름 바꾸기`를 보인다. 누르면 제목 자리가 입력칸으로 바뀌고, 지금 이름이 채워져 있다. Enter는 저장, Esc는 취소다. `/`나 `\`가 들어가면 저장 단추가 꺼지고 이유를 한 줄로 알린다. 저장이 성공하면 목록을 다시 읽는다(`onChanged`). `LibraryPage.load()`가 고른 자산을 새 값으로 바꾼다(`LibraryPage.tsx`의 `setSelected(previous => nextAssets.find(...))`). 확장자는 따로 지키지 않는다. 표시용 이름이라 파일과 무관하기 때문이다(Task 6 배경).

- [ ] **Step 1: 실패하는 시험을 쓴다**

`apps/web/src/features/library/LibraryPage.test.tsx`의 `describe("LibraryPage", () => {` 블록 **안** 마지막(닫는 `});` 앞)에 더한다:

```tsx
  it("renames an own asset from the preview pane and reloads the list", async () => {
    // 2026-10-01 점검: 깨진 이름 24개를 고칠 길이 없었다(점검 후속 A4).
    const rename = vi.spyOn(api, "renameLibraryAsset").mockResolvedValue({
      asset: asset({ user_metadata: { filename: "도시 걷기.mp4", tags: ["도시"] } }),
    });
    render(<LibraryPage />);
    await screen.findAllByText("walk.mp4");
    const listCallsBefore = vi.mocked(api.listLibraryAssets).mock.calls.length;

    fireEvent.click(screen.getByRole("button", { name: "walk.mp4 이름 바꾸기" }));
    const input = screen.getByLabelText("새 이름") as HTMLInputElement;
    expect(input.value).toBe("walk.mp4");
    fireEvent.change(input, { target: { value: "  도시 걷기.mp4 " } });
    fireEvent.click(screen.getByRole("button", { name: "이름 저장" }));

    await waitFor(() => expect(rename).toHaveBeenCalledWith("user_asset_1", "도시 걷기.mp4"));
    await waitFor(() => expect(vi.mocked(api.listLibraryAssets).mock.calls.length).toBeGreaterThan(listCallsBefore));
    await waitFor(() => expect(screen.queryByLabelText("새 이름")).toBeNull());
  });

  it("refuses a slash and keeps the old name when renaming is cancelled", async () => {
    const rename = vi.spyOn(api, "renameLibraryAsset");
    render(<LibraryPage />);
    await screen.findAllByText("walk.mp4");

    fireEvent.click(screen.getByRole("button", { name: "walk.mp4 이름 바꾸기" }));
    const input = screen.getByLabelText("새 이름");
    fireEvent.change(input, { target: { value: "a/b.mp4" } });
    expect(screen.getByRole("button", { name: "이름 저장" })).toBeDisabled();
    expect(screen.getByText("이름에 / 나 \\ 는 쓸 수 없어요.")).toBeInTheDocument();
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.keyDown(input, { key: "Escape" });

    expect(screen.queryByLabelText("새 이름")).toBeNull();
    expect(rename).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { level: 2, name: "walk.mp4" })).toBeInTheDocument();
  });

  it("offers no rename for a built-in starter asset", async () => {
    vi.mocked(api.listLibraryAssets).mockResolvedValue({ assets: [asset({ origin: "builtin" })], total: 1 });
    render(<LibraryPage />);
    await screen.findAllByText("walk.mp4");
    expect(screen.queryByRole("button", { name: /이름 바꾸기/ })).toBeNull();
  });
```

- [ ] **Step 2: 실패를 확인한다**

```bash
(cd apps/web && npx vitest run src/features/library/LibraryPage.test.tsx -t "renames an own asset")
```

예상: FAIL. `vi.spyOn`이 `renameLibraryAsset does not exist`류로 실패한다(`api`에 메서드가 없다).

- [ ] **Step 3: api 메서드를 더한다**

`apps/web/src/api.ts`의 아래 블록(옛 2338-2342줄):
```ts
  setLibraryAssetFavorite: (libraryAssetId: string, favorite: boolean) =>
    request<{ asset: LibraryAsset }>(
      `/api/library/assets/${encodeURIComponent(libraryAssetId)}/favorite`,
      { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ favorite }) },
    ),
```
바로 다음에 넣는다:
```ts
  /** 자료실에 보이는 이름을 바꾼다(2026-10-02, 점검 후속 A4). 파일과 경로는 그대로다. */
  renameLibraryAsset: (libraryAssetId: string, filename: string) =>
    request<{ asset: LibraryAsset }>(
      `/api/library/assets/${encodeURIComponent(libraryAssetId)}/filename`,
      { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filename }) },
    ),
```

- [ ] **Step 4: 미리보기 칸을 고친다 — `LibraryPreviewPane.tsx`**

(a) 상태. 옛 70줄:
```tsx
  useEffect(() => { setConfirmPermanentDelete(false); }, [asset?.library_asset_id]);
```
**바로 앞**에 넣는다(훅은 71-73줄의 이른 `return`보다 앞에 있어야 한다):
```tsx
  // 이름 바꾸기(2026-10-02, 점검 후속 A4). 고른 자산이 바뀌면 열어 둔 편집을 닫는다.
  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);
  useEffect(() => { setRenaming(false); setRenameError(null); }, [asset?.library_asset_id]);
```

(b) 함수. 옛 85줄:
```tsx
  const rightsEditable = asset.origin !== "builtin" && asset.lifecycle !== "trashed";
```
**다음**에 넣는다:
```tsx
  const renameEditable = asset.origin !== "builtin" && asset.lifecycle !== "trashed";
  const trimmedDraft = nameDraft.trim();
  const nameDraftInvalid = /[\\/]/.test(trimmedDraft);
  const canSaveName = trimmedDraft.length > 0 && !nameDraftInvalid && trimmedDraft !== name;
  function startRename() { setNameDraft(name); setRenameError(null); setRenaming(true); }
  async function saveName() {
    if (!canSaveName) return;
    setBusy(true); setRenameError(null);
    try { await api.renameLibraryAsset(assetId, trimmedDraft); setRenaming(false); onChanged?.(); }
    catch { setRenameError("이름을 바꾸지 못했어요. 다시 해 주세요."); }
    finally { setBusy(false); }
  }
```

(c) 머리말. 86줄 안의 아래 조각:
```tsx
<div className="vb-library-preview__heading"><p className="vb-eyebrow">미리보기</p><h2>{name}</h2>{isVideo && asset.lifecycle !== "trashed" ? <a
```
을 아래로 바꾼다(`{isVideo && ...` 뒤는 그대로):
```tsx
<div className="vb-library-preview__heading"><p className="vb-eyebrow">미리보기</p>{renaming ? <div className="vb-library-rename-row"><input data-native-control="library-rename-input" aria-label="새 이름" value={nameDraft} autoFocus onChange={(event) => setNameDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void saveName(); } else if (event.key === "Escape") { event.preventDefault(); setRenaming(false); } }} disabled={busy} aria-invalid={nameDraftInvalid} /><button data-native-control="library-rename-save" type="button" onClick={() => void saveName()} disabled={busy || !canSaveName}>이름 저장</button><button data-native-control="library-rename-cancel" type="button" onClick={() => setRenaming(false)} disabled={busy}>취소</button>{nameDraftInvalid ? <p role="alert">이름에 / 나 \ 는 쓸 수 없어요.</p> : null}{renameError ? <p role="alert">{renameError}</p> : null}</div> : <h2>{name}</h2>}{renameEditable && !renaming ? <button data-native-control="library-rename" type="button" className="vb-library-kind-fix" onClick={startRename} aria-label={`${name} 이름 바꾸기`}>이름 바꾸기</button> : null}{isVideo && asset.lifecycle !== "trashed" ? <a
```

JSX 문자열 `이름에 / 나 \ 는 쓸 수 없어요.`의 `\`는 JSX 텍스트 노드라 그대로 한 글자로 찍힌다(시험은 `"...\\ 는..."`, 곧 백슬래시 한 개로 찾는다).

- [ ] **Step 5: 모양 규칙을 더한다**

`apps/web/src/features/library/library.css` 11줄은 한 줄로 이어진 규칙 묶음이다. 그 줄 **끝**에 그대로 덧붙인다(색은 이미 정의된 토큰만 쓴다. 팔레트는 바꾸지 않는다. 경고 글씨는 `--destructive`(`ui-system.css:122`)다. `--vb-danger`는 정의된 적이 없는 이름이라 쓰지 않는다. `src/styles/theme-tokens.test.ts`가 library.css의 날값 간격·모서리를 막으므로 간격은 `--vb-space-*`, 모서리는 `--vb-radius-sm`만 쓴다):

```css
.vb-library-rename-row{display:flex;flex-wrap:wrap;align-items:center;gap: var(--vb-space-2);margin-top: var(--vb-space-1)}.vb-library-rename-row input{flex:1 1 12rem;min-width:0;min-height:36px;padding:0 var(--vb-space-2);border:1px solid var(--vb-border);border-radius: var(--vb-radius-sm);background:var(--vb-panel);color:var(--vb-text);font:inherit}.vb-library-rename-row button{min-height:36px;padding:0 var(--vb-space-3);border:1px solid var(--vb-border);border-radius: var(--vb-radius-sm);background:var(--vb-panel);color:var(--vb-text);font:inherit;cursor:pointer}.vb-library-rename-row button:disabled{cursor:not-allowed;opacity:.5}.vb-library-rename-row p{flex-basis:100%;margin:0;color:var(--destructive);font-size: var(--vb-text-sm)}
```

- [ ] **Step 6: 네이티브 컨트롤 목록을 고친다**

`apps/web/src/task22-parity-owners.test.ts` 148-149줄을 아래로 바꾼다(배열은 정렬 순서 그대로):

```ts
    controls: ["button:library-correct-media-type", "button:library-favorite", "button:library-permanent-delete", "button:library-permanent-delete-confirm", "button:library-rename", "button:library-rename-cancel", "button:library-rename-save", "button:library-restore", "button:library-rights-save", "button:library-trash", "input:library-rename-input", "input:library-rights-license-note", "select:library-rights-source"],
    reason: "The library preview pane owns the explicit restore, trash, and two-stage permanent-delete lifecycle actions for a trashed asset, plus the kind correction the owner needs because VideoBox now sorts one drop folder by content (owner decision 2026-09-07), the rights source (own footage / AI / licensed third party) that unlocks monetized upload approval (AK W1215-4, 2026-09-28), and the inline rename that repairs broken file names (audit follow-up A4, 2026-10-02).",
```

- [ ] **Step 7: 통과를 확인한다**

```bash
(cd apps/web && npx vitest run src/features/library/LibraryPage.test.tsx src/task22-parity-owners.test.ts src/user-copy-policy.test.ts src/styles/theme-tokens.test.ts)
```

예상: 전부 통과.

- [ ] **Step 8: 넓은 검증**

```bash
(cd apps/web && npx tsc --noEmit && npx vitest run)
```

예상: 타입 통과. vitest는 알려진 실패 1건만 빨갛다.

- [ ] **Step 9: 배선 확인(grep)**

```bash
grep -rn "renameLibraryAsset" apps/web/src --include=*.ts --include=*.tsx | grep -v "\.test\."
```

예상: 정의 1곳(`api.ts`)과 부르는 자리 1곳(`LibraryPreviewPane.tsx`의 `saveName`).

- [ ] **Step 10: 커밋**

```bash
git add apps/web/src/api.ts apps/web/src/features/library/LibraryPreviewPane.tsx apps/web/src/features/library/library.css apps/web/src/task22-parity-owners.test.ts apps/web/src/features/library/LibraryPage.test.tsx
git commit -m "$(cat <<'EOF'
feat(library): 미리보기 칸에서 이름 바꾸기(Enter 저장·Esc 취소)

대표님 자산만, 휴지통 밖에서만 연다. / 와 \ 는 막고 이유를 한 줄로 알린다.
유진에게 여는 일은 묶음 F에서 한다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: A4(일괄 복구) — 깨진 이름 24개를 되살리는 한 번용 스크립트

**Files:**
- Create: `scripts/repair_mojibake_library_filenames.py`
- Create: `tests/test_repair_mojibake_library_filenames.py`

**Interfaces:**
- Consumes: 실행 중인 API(기본 `http://127.0.0.1:5173`). `GET /api/library/assets?media_type=<종류>&include_trashed=true&limit=500`, Task 6의 `PATCH /api/library/assets/{id}/filename`
- Produces (스크립트 모듈):
  - `repaired_name(name: str) -> str | None`
  - `plan_repairs(send: Transport) -> list[dict[str, str]]`(각 항목 키: `library_asset_id`, `media_type`, `before`, `after`)
  - `apply_renames(send: Transport, renames: Sequence[Mapping[str, str]], *, key_to: str = "after") -> list[dict[str, str]]`(실패 목록)
  - `http_transport(base_url: str) -> Transport`
  - `main(argv: Sequence[str] | None = None, *, send: Transport | None = None, now: datetime | None = None) -> int`
  - `Transport = Callable[[str, str, dict[str, Any] | None], dict[str, Any]]`(메서드, 경로, 본문 → JSON 답)

정한 것과 이유: 저장소(sqlite)를 직접 열지 않고 **실행 중인 API를 부른다.** 실제 데이터는 컨테이너가 쥔 `media_library.sqlite`이고, 호스트에서 같은 파일을 동시에 쓰면 잠금이 겹친다. 새 PATCH 라우트를 지나면 검증(Task 6)도 똑같이 받는다. 브라우저 밖 호출이라 Origin이 없고, Host는 `127.0.0.1:5173`이라 전역 검사를 통과한다. 2026-10-02 실측: 영상(broll) 70개 중 24개가 대상이고 24개 모두 풀린다. `녹음 …` 2개, `화면 녹화 중 …` 21개, `완성본.mp4` 1개다. 그림·음악·효과음에는 없다.

**다시 돌려도 안전하다(멱등).** 이미 고친 이름은 `repaired_name`이 `None`을 내 계획에 안 든다. 고칠 것이 0개면 `--apply`도 아무것도 안 쓰고 0으로 끝난다. 일부만 실패했으면 다시 돌릴 때 남은 것만 계획에 들고, 되돌릴 목록은 **새 파일**로 쓴다. 이미 있는 되돌릴 목록은 `open("x")`로 절대 덮어쓰지 않는다(덮어쓰면 첫 실행의 원래 이름이 사라진다. 이때 종료 코드 2). Host·Origin 검사(`csrf_guard.py`): urllib은 Origin을 안 붙이고 Host는 `127.0.0.1:5173`이라 통과한다. 다른 주소(`--base-url http://videobox.test` 등)는 400으로 막힌다.

되돌릴 목록은 `artifacts/library-filename-repair/revert-<UTC>.json`에 **PATCH 전에** 쓴다. `artifacts/`는 보통 다시 만들 수 있는 것을 지우는 자리지만(§10.16), 이 파일은 다시 만들 수 없다. 원래 이름은 PATCH 뒤에는 어디에도 남지 않는다. 그래서 지우지 않는다. 스크립트 docstring과 인계 문서에 그렇게 적는다.

- [ ] **Step 1: 실패하는 시험을 쓴다**

`tests/test_repair_mojibake_library_filenames.py`:

```python
"""깨진 자료실 이름 일괄 복구 (2026-10-02, 점검 후속 A4).

소켓은 안 연다(`tests/conftest.py`). `send`(메서드, 경로, 본문 → 답)를 손으로 준다.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "repair_mojibake_library_filenames.py"
_spec = importlib.util.spec_from_file_location("videobox_repair_mojibake_under_test", _PATH)
assert _spec is not None and _spec.loader is not None
repair = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(repair)


@pytest.mark.parametrize(
    ("broken", "fixed"),
    [
        ("\xb3\xec\xc0\xbd 2026-02-07 163617.mp4", "녹음 2026-02-07 163617.mp4"),
        ("\xc8\xad\xb8\xe9 \xb3\xec\xc8\xad \xc1\xdf 2025-07-24 233828.mp4", "화면 녹화 중 2025-07-24 233828.mp4"),
        ("\xbf\xcf\xbc\xba\xba\xbb.mp4", "완성본.mp4"),
    ],
)
def test_names_read_as_latin1_come_back_as_korean(broken: str, fixed: str) -> None:
    assert repair.repaired_name(broken) == fixed


@pytest.mark.parametrize(
    "name",
    [
        "walk.mp4",            # 고칠 것이 없다
        "녹음 2026-02-07.mp4",  # 이미 한국어다
        "café.mp3",            # 진짜 라틴 문자. cp949로 안 풀린다
        "naïve résumé.wav",    # 진짜 라틴 문자
        "\xa1\xa1.mp4",        # 풀리지만(전각 공백) 한글이 안 나온다
    ],
)
def test_names_that_are_not_broken_korean_are_left_alone(name: str) -> None:
    assert repair.repaired_name(name) is None


class _FakeApi:
    def __init__(self, assets_by_type: dict[str, list[dict]], *, total_bonus: int = 0, fail_ids: set[str] | None = None) -> None:
        self.assets_by_type = assets_by_type
        self.total_bonus = total_bonus
        self.fail_ids = fail_ids or set()
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method: str, path: str, body: dict | None) -> dict:
        self.calls.append((method, path, body))
        if method == "GET":
            media_type = path.split("media_type=")[1].split("&")[0]
            assets = self.assets_by_type.get(media_type, [])
            return {"assets": assets, "total": len(assets) + self.total_bonus}
        asset_id = path.split("/api/library/assets/")[1].split("/")[0]
        if asset_id in self.fail_ids:
            raise OSError("connection reset")
        return {"asset": {"library_asset_id": asset_id, "user_metadata": {"filename": body["filename"]}}}


def _asset(asset_id: str, name: str, origin: str = "user") -> dict:
    return {"library_asset_id": asset_id, "origin": origin, "user_metadata": {"filename": name}}


BROKEN = "\xb3\xec\xc0\xbd 2026-02-07 163617.mp4"


def test_the_plan_lists_only_own_broken_names_across_every_kind() -> None:
    api = _FakeApi({
        "broll": [_asset("user_1", BROKEN), _asset("user_2", "walk.mp4"), _asset("pack:1", BROKEN, origin="builtin")],
        "music": [_asset("user_3", "café.mp3")],
    })
    plans = repair.plan_repairs(api)
    assert plans == [{"library_asset_id": "user_1", "media_type": "broll", "before": BROKEN, "after": "녹음 2026-02-07 163617.mp4"}]
    assert [path for method, path, _ in api.calls if method == "GET"] == [
        f"/api/library/assets?media_type={kind}&include_trashed=true&limit=500" for kind in ("broll", "image", "music", "sfx")
    ]


def test_the_plan_stops_when_one_page_cannot_hold_everything() -> None:
    with pytest.raises(SystemExit):
        repair.plan_repairs(_FakeApi({"broll": [_asset("user_1", BROKEN)]}, total_bonus=1))


def test_a_dry_run_changes_nothing(tmp_path: Path, capsys) -> None:
    api = _FakeApi({"broll": [_asset("user_1", BROKEN)]})
    assert repair.main(["--revert-file", str(tmp_path / "r.json")], send=api) == 0
    assert all(method == "GET" for method, _, _ in api.calls)
    assert not (tmp_path / "r.json").exists()
    assert "고칠 이름 1개" in capsys.readouterr().out


def test_apply_writes_the_revert_list_before_renaming(tmp_path: Path) -> None:
    revert = tmp_path / "revert.json"
    seen_on_first_patch: list[bool] = []
    api = _FakeApi({"broll": [_asset("user_1", BROKEN)]})

    def send(method: str, path: str, body: dict | None) -> dict:
        if method == "PATCH" and not seen_on_first_patch:
            seen_on_first_patch.append(revert.exists())
        return api(method, path, body)

    code = repair.main(["--apply", "--revert-file", str(revert)], send=send, now=datetime(2026, 10, 2, tzinfo=timezone.utc))

    assert code == 0
    assert seen_on_first_patch == [True]
    saved = json.loads(revert.read_text(encoding="utf-8"))
    assert saved["renamed"] == [{"library_asset_id": "user_1", "media_type": "broll", "before": BROKEN, "after": "녹음 2026-02-07 163617.mp4"}]
    assert ("PATCH", "/api/library/assets/user_1/filename", {"filename": "녹음 2026-02-07 163617.mp4"}) in api.calls


def test_one_failure_does_not_hide_the_others_and_the_exit_code_says_so(tmp_path: Path, capsys) -> None:
    api = _FakeApi({"broll": [_asset("user_1", BROKEN), _asset("user_2", BROKEN)]}, fail_ids={"user_1"})
    code = repair.main(["--apply", "--revert-file", str(tmp_path / "r.json")], send=api)
    assert code == 1
    assert ("PATCH", "/api/library/assets/user_2/filename", {"filename": "녹음 2026-02-07 163617.mp4"}) in api.calls
    assert "user_1" in capsys.readouterr().out


def test_a_second_apply_after_success_does_nothing(tmp_path: Path) -> None:
    """다시 돌려도 안전해야 한다. 이미 고친 이름은 계획에 안 들고, 되돌릴 목록도 새로 안 쓴다."""
    api = _FakeApi({"broll": [_asset("user_1", "녹음 2026-02-07 163617.mp4")]})
    assert repair.main(["--apply", "--revert-file", str(tmp_path / "again.json")], send=api) == 0
    assert all(method == "GET" for method, _, _ in api.calls)
    assert not (tmp_path / "again.json").exists()


def test_an_existing_revert_list_is_never_overwritten(tmp_path: Path) -> None:
    revert = tmp_path / "revert.json"
    revert.write_text('{"renamed": [{"library_asset_id": "user_0", "before": "원본"}]}', encoding="utf-8")
    api = _FakeApi({"broll": [_asset("user_1", BROKEN)]})
    assert repair.main(["--apply", "--revert-file", str(revert)], send=api) == 2
    assert all(method == "GET" for method, _, _ in api.calls)
    assert "user_0" in revert.read_text(encoding="utf-8")


def test_undo_puts_the_old_names_back(tmp_path: Path) -> None:
    revert = tmp_path / "revert.json"
    revert.write_text(json.dumps({"renamed": [{"library_asset_id": "user_1", "media_type": "broll", "before": BROKEN, "after": "녹음.mp4"}]}, ensure_ascii=False), encoding="utf-8")
    api = _FakeApi({})
    assert repair.main(["--undo", str(revert)], send=api) == 0
    assert api.calls == [("PATCH", "/api/library/assets/user_1/filename", {"filename": BROKEN})]
```

- [ ] **Step 2: 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider "tests/test_repair_mojibake_library_filenames.py::test_names_read_as_latin1_come_back_as_korean"
```

예상: 수집 에러 `FileNotFoundError`(스크립트가 없다).

- [ ] **Step 3: 스크립트를 만든다**

`scripts/repair_mojibake_library_filenames.py`:

```python
"""자료실의 깨진 파일 이름을 되살린다 (2026-10-02, 점검 후속 A4, 한 번 쓰는 수리 도구).

2026-10-01 점검: 자료실 영상 이름 24개가 `³ìÀ½ 2026-02-07 163617.mp4` 꼴이었다.
윈도우가 cp949로 적은 이름 바이트를 라틴1로 읽은 것이다. 거꾸로 하면 돌아온다.
`name.encode("latin-1").decode("cp949")`.

고치는 것은 셋이 모두 맞을 때뿐이다.
1. 원래 이름에 U+0080~U+00FF 글자가 있다.
2. 라틴1→cp949로 오류 없이 풀린다.
3. 풀린 이름에 한글 음절이 있고 U+0080~U+00FF 글자가 남지 않는다.
그래서 `café.mp3` 같은 진짜 라틴 이름은 건드리지 않는다.

**실행 중인 VideoBox API를 부른다**(기본 http://127.0.0.1:5173). 컨테이너가 쥔 데이터베이스를
호스트에서 직접 열지 않는다. 이름 바꾸기는 화면과 같은 길(`PATCH .../filename`)을 지난다.

    .venv/Scripts/python.exe scripts/repair_mojibake_library_filenames.py            # 미리보기
    .venv/Scripts/python.exe scripts/repair_mojibake_library_filenames.py --apply    # 실제로 바꾸기
    .venv/Scripts/python.exe scripts/repair_mojibake_library_filenames.py --undo <되돌릴 목록.json>

`--apply`는 바꾸기 **전에** 되돌릴 목록을 `artifacts/library-filename-repair/`에 쓴다.
**이 파일은 지우지 않는다.** 원래 이름은 바꾼 뒤에는 어디에도 남지 않아 다시 만들 수 없다
(`docs/development-fast-path.ko.md` §10.16의 "다시 만들 수 있는가" 기준).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://127.0.0.1:5173"
MEDIA_TYPES = ("broll", "image", "music", "sfx")
#: API가 한 번에 주는 최대 개수(`/api/library/assets`의 `limit` 상한).
PAGE_LIMIT = 500
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REVERT_DIR = REPO_ROOT / "artifacts" / "library-filename-repair"

Transport = Callable[[str, str, "dict[str, Any] | None"], "dict[str, Any]"]


def _has_latin1_range(text: str) -> bool:
    return any("\x80" <= ch <= "\xff" for ch in text)


def repaired_name(name: str) -> str | None:
    """되살린 이름. 고칠 것이 아니면 `None`."""

    if not _has_latin1_range(name):
        return None
    try:
        fixed = name.encode("latin-1").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    if fixed == name or _has_latin1_range(fixed):
        return None
    if not any("\uac00" <= ch <= "\ud7a3" for ch in fixed):
        return None
    return fixed


def http_transport(base_url: str) -> Transport:
    root = base_url.rstrip("/")

    def send(method: str, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        request = Request(root + path, data=data, method=method, headers=headers)
        with urlopen(request, timeout=30) as response:  # noqa: S310 - 이 컴퓨터의 VideoBox만 부른다
            return json.loads(response.read().decode("utf-8"))

    return send


def plan_repairs(send: Transport) -> list[dict[str, str]]:
    plans: list[dict[str, str]] = []
    for media_type in MEDIA_TYPES:
        page = send("GET", f"/api/library/assets?media_type={media_type}&include_trashed=true&limit={PAGE_LIMIT}", None)
        assets = list(page.get("assets") or [])
        if int(page.get("total") or 0) > len(assets):
            raise SystemExit(f"{media_type} 자산이 {PAGE_LIMIT}개를 넘어 한 번에 다 못 읽었습니다. 아무것도 바꾸지 않고 멈춥니다.")
        for asset in assets:
            if asset.get("origin") != "user":
                continue
            before = str((asset.get("user_metadata") or {}).get("filename") or "")
            after = repaired_name(before)
            if after:
                plans.append({"library_asset_id": str(asset["library_asset_id"]), "media_type": media_type, "before": before, "after": after})
    return plans


def apply_renames(send: Transport, renames: Sequence[Mapping[str, str]], *, key_to: str = "after") -> list[dict[str, str]]:
    """하나씩 바꾼다. 하나가 실패해도 나머지는 계속하고, 실패는 모아서 돌려준다."""

    failures: list[dict[str, str]] = []
    for item in renames:
        target = str(item[key_to])
        path = f"/api/library/assets/{quote(str(item['library_asset_id']), safe='')}/filename"
        try:
            reply = send("PATCH", path, {"filename": target})
        except Exception as exc:  # noqa: BLE001 - 한 줄의 실패가 나머지를 가리면 안 된다. 아래에서 전부 보고한다
            failures.append({**item, "error": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        saved = str(((reply.get("asset") or {}).get("user_metadata") or {}).get("filename") or "")
        if saved != target:
            failures.append({**item, "error": "name_not_saved"})
    return failures


def main(argv: Sequence[str] | None = None, *, send: Transport | None = None, now: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(description="자료실의 깨진(라틴1로 읽힌) 한국어 파일 이름을 되살린다.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--apply", action="store_true", help="실제로 바꾼다. 없으면 미리보기만 한다.")
    parser.add_argument("--revert-file", default=None, help="되돌릴 목록을 쓸 자리. 기본은 artifacts/library-filename-repair/.")
    parser.add_argument("--undo", default=None, help="되돌릴 목록 파일을 주면 원래 이름으로 돌린다.")
    arguments = parser.parse_args(argv)
    transport = send or http_transport(arguments.base_url)

    if arguments.undo:
        renamed = json.loads(Path(arguments.undo).read_text(encoding="utf-8"))["renamed"]
        failures = apply_renames(transport, renamed, key_to="before")
        print(f"되돌림 {len(renamed) - len(failures)}/{len(renamed)}")
        for failure in failures:
            print(f"실패: {failure['library_asset_id']} {failure['error']}")
        return 1 if failures else 0

    plans = plan_repairs(transport)
    for item in plans:
        print(f"{item['library_asset_id']}  {ascii(item['before'])}  ->  {item['after']}")
    print(f"고칠 이름 {len(plans)}개")
    if not arguments.apply:
        print("미리보기만 했습니다. 실제로 바꾸려면 --apply 를 붙이세요.")
        return 0
    if not plans:
        return 0

    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    revert_path = Path(arguments.revert_file) if arguments.revert_file else DEFAULT_REVERT_DIR / f"revert-{stamp}.json"
    revert_path.parent.mkdir(parents=True, exist_ok=True)
    # "x": 이미 있는 되돌릴 목록을 **절대 덮어쓰지 않는다.** 앞서 돌린 목록이 원래 이름의
    # 유일한 기록이다. 같은 초에 두 번 돌리거나 같은 --revert-file을 다시 주면 멈춘다.
    try:
        with revert_path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps({"base_url": arguments.base_url, "created_at": stamp, "renamed": plans}, ensure_ascii=False, indent=2))
    except FileExistsError:
        print(f"되돌릴 목록이 이미 있습니다: {revert_path}. 덮어쓰지 않고 멈춥니다. 다른 --revert-file을 주세요.")
        return 2
    print(f"되돌릴 목록: {revert_path}  (지우지 마세요)")

    failures = apply_renames(transport, plans)
    print(f"바꿈 {len(plans) - len(failures)}/{len(plans)}")
    for failure in failures:
        print(f"실패: {failure['library_asset_id']} {failure['error']}")
    return 1 if failures else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
```

- [ ] **Step 4: 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_repair_mojibake_library_filenames.py
```

예상: 전부 통과.

- [ ] **Step 5: 실행 중인 VideoBox에 미리보기로만 돌린다(바꾸지 않는다)**

지금 떠 있는 컨테이너에는 아직 PATCH 라우트가 없다. 미리보기는 GET만 쓰므로 지금 돌려도 된다.

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/repair_mojibake_library_filenames.py
```

예상: 24줄 다음에 `고칠 이름 24개`가 나온다. 개수가 다르면 멈추고 목록을 인계에 적는다(그사이 자산이 늘었을 수 있다). `--apply`는 Task 10에서 재빌드한 뒤에 한다.

- [ ] **Step 6: 커밋**

```bash
git add scripts/repair_mojibake_library_filenames.py tests/test_repair_mojibake_library_filenames.py
git commit -m "$(cat <<'EOF'
feat(library): 깨진 자료실 이름 일괄 복구 스크립트(미리보기 기본·--apply·--undo)

라틴1→cp949로 풀리고 한글이 나오는 이름만 고친다. 실행 중인 API의 PATCH를 지나며,
바꾸기 전에 되돌릴 목록을 artifacts/library-filename-repair/에 남긴다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: 분위기 태그에 문장 조각이 섞이는 백엔드 원인을 막는다

**Files:**
- Modify: `packages/storage-abstractions/src/videobox_storage/_store_media_analysis.py:17-26` (import에 `re`), `:29` (`def sha256_file` 앞에 도움 함수), `:243-246` (`review_media_analysis`의 태그 합치기), `:331-341` (`_merge_analysis_tags_onto_asset`)
- Modify: `packages/core-engine/src/videobox_core_engine/recommenders.py:98-103` (`KeywordBrollRecommender`가 자산 낱말을 모으는 자리)
- Test: `tests/test_media_analysis_store.py`(끝에 둘 추가), `tests/test_photo_recommendation_actually_matches.py`(끝에 하나 추가)

**Interfaces:**
- Produces:
  - 모듈 함수 `_store_media_analysis._split_analysis_tag_values(values: Iterable[object]) -> tuple[list[str], list[str]]` — (짧은 태그, 긴 문구). 클래스 멤버가 아니라서 `tests/store_public_surface.json`(클래스 `dir()` 스냅샷)에 걸리지 않는다.
  - 프로젝트 자산 `metadata.analysis_phrases: list[str]` — 분석 갈래 값 중 태그 모양이 아닌 것(문장·문장 조각). 검색용이다.
- Consumes: 없음

배경(2026-10-01 실화면): 편집기 자료 칸에 `분위기 장면 1 : 화면 중앙에 직사각형 돌바닥 보행로가 가까운 곳에서 멀리까지 빼기`, `분위기 흐림. 빼기`, `분위기 + 빼기` 같은 단추가 생겼다. 원인은 셋이 겹친 것이다.

1. 분석 응답 스키마가 갈래 값을 `maxLength: 40`으로만 묶는다(`packages/provider-interfaces/src/videobox_provider_interfaces/vision.py:40`). 모델이 문장을 40자씩 끊어 넣는다.
2. 저장소가 갈래 값을 **거르지 않고** 자산 `metadata.tags`에 합친다(`_store_media_analysis.py:243-246` 사람 검토 길, `:331-341` 바로 성공 길).
3. 화면은 `metadata.tags`를 전부 분위기 단추로 그렸다. 2026-10-01에 `isChipTag`(`apps/web/src/features/editor/assets/EditorAssetBrowser.tsx:179-188`)로 화면만 막았다.

`broll_scene_candidates.py:81`도 설명 문장을 `tags`에 넣지만, 그건 추천기에 넘기는 **메모리 안 사본**이다(저장 안 함, 화면에 안 감. 부르는 자리는 `local_pipeline.py:1284`, `_pipeline_private_helpers.py:966`뿐). 이번에 바꾸지 않는다.

정한 것과 이유:
- 태그로 남기는 값: 앞뒤 공백을 뺀 뒤 1~20자, `.:;!?。,，`와 줄바꿈이 없고, 글자(`\p{L}`에 해당하는 `str.isalpha()`)가 하나 이상 있고, `+`로 시작하지 않는다. 화면 `isChipTag`와 **같은 규칙**이다(20자도 `CHIP_TAG_MAX_LENGTH`와 같다).
- 태그가 아닌 값은 **버리지 않고** `metadata.analysis_phrases`로 옮긴다. 글자가 하나도 없는 값(`+`)만 버린다. 이유: 검색과 추천이 그 낱말을 쓴다. 편집기 검색(`editorAssetProjection.ts:271-287`)은 `JSON.stringify(brollMetadata)`로 메타데이터 전체를 훑으므로 새 칸도 그대로 찾는다. 추천기(`recommenders.py:98-103`)는 `title`과 `tags`만 읽으므로, 같은 Task에서 `analysis_phrases`도 읽게 한다. 안 그러면 `돌바닥`·`보행로` 같은 낱말로 맞던 자산이 추천에서 빠진다.
- **이미 저장된 태그는 다시 쓰지 않는다(되채우기 없음).** 새로 분석하거나 사람이 검토할 때만 새 규칙이 적용된다. 옛 데이터의 문장 조각은 화면 필터 `isChipTag`가 계속 가린다. 그래서 그 필터는 **지우지 않는다**(방어 겹). 되채우기를 하지 않는 이유: 옛 조각은 이미 화면에서 안 보이고, 추천에는 오히려 낱말을 보태며, 자산 메타데이터를 일괄로 고치는 일은 되돌리기 어렵다.

- [ ] **Step 1: 실패하는 시험을 쓴다**

(a) `tests/test_media_analysis_store.py` 끝에 더한다(이 파일 위쪽에 `_store`, `AssetType`, `MediaAnalysisStatus`, `sha256`, `Path`가 이미 있다):

```python
# 2026-10-01 실화면에 분위기 단추로 나온 조각들 그대로다.
_SENTENCE_FRAGMENT = "장면 1 : 화면 중앙에 직사각형 돌바닥 보행로가 가까운 곳에서 멀리까지"
_JUNK = (_SENTENCE_FRAGMENT, "흐림.", "+")


def _analysed_asset(tmp_path: Path, store, project_id: str, *, status: MediaAnalysisStatus, layers: dict[str, list[str]]):
    source = tmp_path / "walk.mp4"
    source.write_bytes(b"walk-footage")
    asset = store.register_asset(project_id=project_id, asset_type=AssetType.BROLL_VIDEO, source_path=source)
    digest = sha256(source.read_bytes()).hexdigest()
    job = store.create_media_analysis(project_id=project_id, asset_id=asset.asset_id, idempotency_key=f"{digest}:v1", cache_key="cache-v1")
    claim = store.claim_media_analysis(project_id=project_id, analysis_id=job["analysis_id"])
    assert claim is not None
    completed = store.complete_media_analysis(
        project_id=project_id,
        analysis_id=job["analysis_id"],
        expected_attempt=claim["attempt"],
        result={"tags": {"layers": layers}},
        status=status,
    )
    assert completed is not None
    return asset, job


def test_sentence_fragments_from_analysis_never_become_tags(tmp_path: Path) -> None:
    """분석 갈래 값 중 문장 조각은 태그가 아니다(2026-10-01 실화면: `분위기 흐림. 빼기`).

    버리지는 않는다. 검색·추천이 그 낱말을 쓰므로 `analysis_phrases`로 옮긴다.
    글자가 하나도 없는 `+`만 버린다.
    """
    store, project_id = _store(tmp_path)
    asset, _ = _analysed_asset(
        tmp_path, store, project_id,
        status=MediaAnalysisStatus.SUCCEEDED,
        layers={"scene": [_SENTENCE_FRAGMENT], "weather": ["흐림."], "action": ["+", "산책"]},
    )

    metadata = store.get_asset(project_id=project_id, asset_id=asset.asset_id)["metadata"]
    assert "산책" in metadata["tags"]
    assert [tag for tag in metadata["tags"] if tag in _JUNK] == []
    assert metadata["analysis_phrases"] == [_SENTENCE_FRAGMENT, "흐림."]


def test_the_owner_review_path_filters_the_same_way(tmp_path: Path) -> None:
    store, project_id = _store(tmp_path)
    asset, job = _analysed_asset(
        tmp_path, store, project_id,
        status=MediaAnalysisStatus.NEEDS_REVIEW,
        layers={"scene": [], "weather": []},
    )

    store.review_media_analysis(
        project_id=project_id,
        analysis_id=job["analysis_id"],
        tags={"scene": [_SENTENCE_FRAGMENT, "산책"], "weather": ["흐림.", "+"]},
    )

    metadata = store.get_asset(project_id=project_id, asset_id=asset.asset_id)["metadata"]
    assert "산책" in metadata["tags"]
    assert [tag for tag in metadata["tags"] if tag in _JUNK] == []
    assert metadata["analysis_phrases"] == [_SENTENCE_FRAGMENT, "흐림."]
```

(b) `tests/test_photo_recommendation_actually_matches.py` 끝에 더한다(`_recommend`가 이 파일에 이미 있다):

```python
def test_words_moved_out_of_tags_still_reach_the_recommender() -> None:
    """분석 문장은 태그에서 빠져 `analysis_phrases`로 간다(2026-10-02). 추천기가 그 칸을
    안 읽으면 `돌바닥`·`보행로`로 맞던 자산이 추천에서 사라진다.

    자산 순서를 바다 → 산책으로 둔다. 낱말이 하나도 안 맞으면 돌려쓰기가 첫 자산(바다)을
    고르므로, 이 시험은 고치기 전에 빨갛다."""
    segments = [{"segment_id": "s1", "text": "돌바닥 보행로를 천천히 걸었다."}]
    assets = [
        {"asset_id": "clip_sea", "metadata": {"tags": ["바다"]}},
        {"asset_id": "clip_walk", "metadata": {"tags": ["산책"], "analysis_phrases": ["직사각형 돌바닥 보행로"]}},
    ]

    pick = _recommend(segments, assets)[0]

    assert pick.selected_asset_id == "clip_walk", pick
    assert pick.reason.startswith("Matched keywords"), pick.reason
```

- [ ] **Step 2: 실패를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_media_analysis_store.py::test_sentence_fragments_from_analysis_never_become_tags
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_photo_recommendation_actually_matches.py::test_words_moved_out_of_tags_still_reach_the_recommender
```

예상: 첫째는 FAIL, `assert [...] == []`에 `'장면 1 : 화면 중앙에 ...'`, `'흐림.'`, `'+'`가 찍힌다. 둘째는 FAIL, `assert 'clip_sea' == 'clip_walk'`.

- [ ] **Step 3: 저장소에 거르는 함수를 넣는다**

(a) `_store_media_analysis.py`의 import(옛 18-25줄)에 `re`를 더한다:
```python
import hashlib
import json
import math
import shutil
import sqlite3
import uuid
```
새:
```python
import hashlib
import json
import math
import re
import shutil
import sqlite3
import uuid
```
`from collections.abc import Iterable`도 `from typing import Any` 바로 위에 더한다.

(b) `def sha256_file(path: Path) -> str:`(옛 29줄) **앞**에 넣는다:

```python
#: 분위기 단추(`EditorAssetBrowser.tsx`의 `isChipTag`)와 같은 규칙이다. 둘을 같이 고친다.
_TAG_MAX_LENGTH = 20
_SENTENCE_MARKS = re.compile(r"[.:;!?。,，\n]")


def _split_analysis_tag_values(values: Iterable[object]) -> tuple[list[str], list[str]]:
    """분석 갈래 값을 (짧은 태그, 긴 문구)로 나눈다 (2026-10-02, 점검 후속).

    모델이 갈래 값에 설명 문장을 40자씩 끊어 넣는 일이 있다(`vision.py`의 `maxLength: 40`).
    그 조각이 태그로 합쳐져 `분위기 흐림. 빼기` 같은 단추가 됐다(실화면 2026-10-01).
    문구는 버리지 않는다 -- 검색과 추천이 그 낱말을 쓴다. 글자가 하나도 없는 값(`+`)만 버린다.
    """
    tags: list[str] = []
    phrases: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not any(character.isalpha() for character in text):
            continue
        if len(text) <= _TAG_MAX_LENGTH and not _SENTENCE_MARKS.search(text) and not text.startswith("+"):
            tags.append(text)
        else:
            phrases.append(text)
    return tags, phrases
```

(c) `review_media_analysis`의 끝(옛 243-246줄):
```python
        searchable_tags = [tag for values in merged_layers.values() for tag in values]
        asset = self.get_asset(project_id=project_id, asset_id=str(current["asset_id"]))
        existing_tags = asset["metadata"].get("tags") if isinstance(asset["metadata"].get("tags"), list) else []
        self.update_asset_metadata(project_id=project_id, asset_id=str(current["asset_id"]), metadata_patch={"tags": list(dict.fromkeys([*existing_tags, *searchable_tags]))})
        return reviewed
```
새:
```python
        searchable_tags, phrases = _split_analysis_tag_values(tag for values in merged_layers.values() for tag in values)
        asset = self.get_asset(project_id=project_id, asset_id=str(current["asset_id"]))
        self.update_asset_metadata(
            project_id=project_id,
            asset_id=str(current["asset_id"]),
            metadata_patch=_merged_tag_patch(asset["metadata"], searchable_tags, phrases),
        )
        return reviewed
```

(d) `_merge_analysis_tags_onto_asset`(옛 331-341줄) 전체:
```python
    def _merge_analysis_tags_onto_asset(self, *, project_id: str, asset_id: str, result: dict[str, Any]) -> None:
        layers = dict(((result.get("tags") or {}).get("layers")) or {})
        searchable_tags = [tag for values in layers.values() if isinstance(values, list) for tag in values if isinstance(tag, str)]
        if not searchable_tags:
            return
        try:
            asset = self.get_asset(project_id=project_id, asset_id=asset_id)
        except KeyError:
            return
        existing_tags = asset["metadata"].get("tags") if isinstance(asset["metadata"].get("tags"), list) else []
        self.update_asset_metadata(project_id=project_id, asset_id=asset_id, metadata_patch={"tags": list(dict.fromkeys([*existing_tags, *searchable_tags]))})
```
새:
```python
    def _merge_analysis_tags_onto_asset(self, *, project_id: str, asset_id: str, result: dict[str, Any]) -> None:
        layers = dict(((result.get("tags") or {}).get("layers")) or {})
        searchable_tags, phrases = _split_analysis_tag_values(
            tag for values in layers.values() if isinstance(values, list) for tag in values
        )
        if not searchable_tags and not phrases:
            return
        try:
            asset = self.get_asset(project_id=project_id, asset_id=asset_id)
        except KeyError:
            return
        self.update_asset_metadata(
            project_id=project_id,
            asset_id=asset_id,
            metadata_patch=_merged_tag_patch(asset["metadata"], searchable_tags, phrases),
        )
```

(e) (b)에서 넣은 `_split_analysis_tag_values` 바로 아래에 두 길이 같이 쓰는 합치기 함수를 넣는다:

```python
def _merged_tag_patch(metadata: dict[str, Any], tags: list[str], phrases: list[str]) -> dict[str, Any]:
    """이미 있는 `tags`·`analysis_phrases`에 새 값을 순서대로, 겹치지 않게 더한다.

    **이미 저장된 값은 고치지 않는다**(되채우기 없음). 옛 문장 조각은 화면 `isChipTag`가 가린다.
    """
    existing_tags = metadata.get("tags") if isinstance(metadata.get("tags"), list) else []
    patch: dict[str, Any] = {"tags": list(dict.fromkeys([*existing_tags, *tags]))}
    existing_phrases = metadata.get("analysis_phrases") if isinstance(metadata.get("analysis_phrases"), list) else []
    # 문구가 없던 자산에 빈 칸을 새로 만들지 않는다(메타데이터 모양을 쓸데없이 바꾸지 않는다).
    if phrases or existing_phrases:
        patch["analysis_phrases"] = list(dict.fromkeys([*existing_phrases, *phrases]))
    return patch
```

- [ ] **Step 4: 추천기가 새 칸도 읽게 한다**

`packages/core-engine/src/videobox_core_engine/recommenders.py`의 (옛 98-103줄):
```python
                asset_tokens = _tokenize(
                    " ".join(
                        [str(metadata.get("title", ""))]
                        + [str(tag) for tag in metadata.get("tags", [])]
                    )
                )
```
새:
```python
                asset_tokens = _tokenize(
                    " ".join(
                        [str(metadata.get("title", ""))]
                        + [str(tag) for tag in metadata.get("tags", [])]
                        # 분석 문장은 태그에서 빠져 여기로 온다(2026-10-02). 낱말은 그대로 쓴다.
                        + [str(phrase) for phrase in metadata.get("analysis_phrases", [])]
                    )
                )
```

- [ ] **Step 5: 통과를 확인한다**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_media_analysis_store.py tests/test_photo_recommendation_actually_matches.py
```

예상: 전부 통과(기존 `test_media_analysis_success_writes_scene_tags_back_onto_asset_metadata`의 `park`·`riverside_green`은 짧은 태그라 그대로 태그다).

- [ ] **Step 6: 넓은 검증**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_store_split_preserves_the_surface.py tests/test_recommendations.py tests/test_broll_recommendation_includes_photos.py tests/test_broll_range_recommendation.py
grep -rln "media_analysis\|analysis_status" tests/*.py | head -20
```

둘째 줄이 낸 시험 파일 중 `_store_media_analysis`나 분석 결과 태그를 다루는 것(`test_media_analysis*.py`, `test_api_media_analysis*.py` 등 이름에 `media_analysis`가 든 것)을 한 번에 돌린다:

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider $(ls tests/test_*media_analysis*.py)
```

예상: 전부 통과. 실패하면 그 시험이 문장 조각을 `metadata.tags`에서 기대하는지 본다. 그렇다면 계약이 바뀐 것이니 그 기대를 `analysis_phrases`로 옮기고 갭 보고에 적는다. 다른 이유면 멈추고 보고한다.

- [ ] **Step 7: 배선 확인(grep) — 화면 방어 겹이 남아 있는가, 새 칸을 읽는 자리가 있는가**

```bash
grep -n "filter(isChipTag)" apps/web/src/features/editor/assets/EditorAssetBrowser.tsx
grep -rn "_split_analysis_tag_values(\|_merged_tag_patch(" packages/storage-abstractions/src --include=*.py
grep -rn "analysis_phrases" packages services apps/web/src --include=*.py --include=*.ts --include=*.tsx | grep -v test
```

예상: 첫 줄 1건(화면 필터는 그대로다). 둘째 줄은 정의 2 + 부르는 자리 각 2(검토 길·바로 성공 길). 셋째 줄은 저장소(`_store_media_analysis.py`)와 추천기(`recommenders.py`)다. 편집기 검색은 `JSON.stringify(brollMetadata)`로 읽으므로 이름이 안 나온다. 이 사실을 갭 보고에 적는다.

- [ ] **Step 8: 커밋**

```bash
git add packages/storage-abstractions/src/videobox_storage/_store_media_analysis.py packages/core-engine/src/videobox_core_engine/recommenders.py tests/test_media_analysis_store.py tests/test_photo_recommendation_actually_matches.py
git commit -m "$(cat <<'EOF'
fix(library): 분석 문장 조각이 분위기 태그가 되지 않게 한다

갈래 값 중 20자 넘거나 문장 부호가 든 값은 metadata.tags가 아니라
metadata.analysis_phrases로 옮긴다(검색·추천용). 글자 없는 '+'는 버린다.
추천기는 analysis_phrases도 읽는다. 옛 데이터는 되채우지 않고 화면 isChipTag가 가린다.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: 검증 넷과 실물 적용 — 재빌드·다리 재시작·실측·화면·인계

**Files:**
- Create: `docs/handoffs/<실행일>-audit-bundle-a-security-tools-rename.ko.md`
- Modify: `CLAUDE.md:52` (`| **최신 세션 인계** | ... |` 줄)
- (같은 날 살아 있는 인계 문서가 이미 있으면) 그 문서 첫머리에 `**대체됨:** <새 문서 경로>` 줄

**Interfaces:**
- Consumes: Task 0~9 전부
- Produces: 실측 기록(인계 문서)

Step 1~4의 순서가 **끊김 없는 배포 순서**다(Global Constraints "배포 순서"). 바꾸지 않는다.

- [ ] **Step 1: 컨테이너를 먼저 새 코드로 다시 짓는다(옛 다리는 그대로 둔다)**

```bash
.venv/Scripts/python.exe -c "import socket;[print(p, 'up' if socket.socket().connect_ex(('127.0.0.1',p))==0 else 'down') for p in (8199,8200,8201)]"
```

지금 다리가 몇 개 떠 있는지 적어 둔다(보통 셋 다 `up`). 그다음 PowerShell:

```powershell
.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory -Rebuild
```

예상: 전체 `pass`, `rebuild` `pass`. 떠 있던 다리는 `already_running: true`다(옛 코드 그대로 — 토큰 헤더를 무시하고 받는다). owner-ready는 compose를 부르기 **전에** `.env.container`에 토큰을 만든다(Task 4가 넣은 자리, `$actualComposeResult` 앞). 그래서 새 컨테이너는 토큰을 받는다. 확인(값은 찍지 않는다):

```bash
grep -c '^VIDEOBOX_BRIDGE_TOKEN=' .env.container
docker exec 65_videobox-videobox-workspace-1 sh -c 'test -n "$VIDEOBOX_BRIDGE_TOKEN" && echo token-set'
docker exec 65_videobox-videobox-workspace-1 test ! -e /app/.env.container && echo env-absent
curl -s http://127.0.0.1:5173/api/capcut/handoff-diagnostics | .venv/Scripts/python.exe -c "import json,sys;d=json.load(sys.stdin);print('project_root_exists', d.get('project_root_exists'))"
```

예상: `1`, `token-set`, `env-absent`, `project_root_exists True`(새 컨테이너 → **옛** 캡컷 다리가 토큰 헤더를 무시하고 받았다. 이 시점에 아무것도 안 깨졌다는 증거다). `False`면 멈추고 다리 로그(`%TEMP%\videobox-capcut-bridge.log.err`)를 본다.

- [ ] **Step 2: 옛 다리를 끈다 — 포트를 쥔 프로세스가 VideoBox 다리인지 명령줄로 확인한 뒤에만**

PowerShell(저장소 루트에서):

```powershell
$repo = (Resolve-Path .).Path
$expected = @{ 8199 = "host_tts_service.py"; 8200 = "host_capcut_service.py"; 8201 = "host_infographic_service.py" }
$foreign = @()
foreach ($port in 8199, 8200, 8201) {
  foreach ($listener in @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) {
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    $commandLine = [string]$owner.CommandLine
    if ($commandLine -like "*$repo\scripts\$($expected[$port])*") {
      Stop-Process -Id $listener.OwningProcess -Force
      "stopped port=$port pid=$($listener.OwningProcess)"
    } else {
      $foreign += "port=$port pid=$($listener.OwningProcess) name=$($owner.Name)"
    }
  }
}
if ($foreign.Count -gt 0) { "FOREIGN (끄지 않았다): $($foreign -join '; ')" }
foreach ($i in 1..20) {
  if (-not (Get-NetTCPConnection -LocalPort 8199,8200,8201 -State Listen -ErrorAction SilentlyContinue)) { "all-free"; break }
  Start-Sleep -Milliseconds 500
}
```

예상: 떠 있던 다리마다 `stopped port=... pid=...` 한 줄, 그리고 `all-free`. 2026-10-02 리뷰 시점 명령줄 예: `...\Python312\python.exe D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\scripts\host_capcut_service.py --port 8200 --allow-root ...`(목소리 다리는 `.venv-chatterbox` 실행기가 띄운 시스템 파이썬이라 경로가 `Python312`로 보인다. 그래도 스크립트 경로로 맞춘다). `FOREIGN`이 나오면 **그 프로세스는 끄지 않는다.** 다른 프로젝트가 포트를 쥔 것이다. 멈추고 owner에게 보고한다. `all-free`가 안 나오면 멈추고 보고한다.

- [ ] **Step 3: 새 다리를 띄운다(재빌드 없이)**

```powershell
.\scripts\owner-ready.ps1 -Mode Start -WithYujinMemory
```

예상: 전체 `pass`. `voice_bridge`·`capcut_bridge`·`infographic_bridge`가 "백그라운드로 켰습니다"(`already_running: false`)다. 컨테이너는 설정이 같아 다시 만들어지지 않는다. 목소리 다리는 모델을 싣느라 수십 초 걸린다. 아래로 다리가 다 떴는지, 토큰 오류가 없는지 본다:

```bash
for i in $(seq 1 60); do .venv/Scripts/python.exe -c "import socket,sys;sys.exit(0 if all(socket.socket().connect_ex(('127.0.0.1',p))==0 for p in (8199,8200,8201)) else 1)" && { echo all-up; break; }; sleep 2; done
grep -l "너무 짧습니다\|bridge_token" "$TEMP"/videobox-*-bridge.log.err 2>/dev/null || echo "no-token-errors"
```

예상: `all-up`, `no-token-errors`. 목소리 엔진(chatterbox)이 이 컴퓨터에 없어 8199가 안 뜨면, 그 사실을 인계에 적고 8200·8201로만 다음 Step을 한다.

바탕화면 아이콘 길도 같은 토큰을 쓰는지 본다(`Start-VideoBox.ps1` → `owner-ready.ps1 -Mode Start` → 다리는 `.env.container`를 직접 읽는다. 목소리 `/health`는 토큰 없이 열려 있어 시작 스크립트의 확인이 통과한다):

```powershell
.\scripts\Start-VideoBox.ps1 -SkipBrowser -Json
```

예상: `"overall": "ready"`. `voice` 단계가 `pass`(이미 대답함). 다리가 이미 떠 있으므로 아무것도 다시 띄우지 않는다.

- [ ] **Step 4: 역방향(다리) — 실제 다리를 curl로 친다**

Git Bash(토큰은 변수로만 다루고 화면에 찍지 않는다):

```bash
cd /d/AI_Workspace_louis_office_50/10_workspace/65_videobox
TOKEN=$(grep -E '^VIDEOBOX_BRIDGE_TOKEN=' .env.container | head -1 | cut -d= -f2- | tr -d '\r"')
for target in "8199 /synthesize" "8200 /register" "8201 /render"; do
  set -- $target
  printf "%s no-token: " "$1";  curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Content-Type: application/json" --data '{}' "http://127.0.0.1:$1$2"
  printf "%s text:     " "$1";  curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "X-VideoBox-Bridge-Token: $TOKEN" -H "Content-Type: text/plain" --data 'x' "http://127.0.0.1:$1$2"
  printf "%s host:     " "$1";  curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Host: evil.example:$1" -H "X-VideoBox-Bridge-Token: $TOKEN" -H "Content-Type: application/json" --data '{}' "http://127.0.0.1:$1$2"
  printf "%s ok-json:  " "$1";  curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "X-VideoBox-Bridge-Token: $TOKEN" -H "Content-Type: application/json" --data '{}' "http://127.0.0.1:$1$2"
done
curl -s -o /dev/null -w "voice health: %{http_code}\n" http://127.0.0.1:8199/health
curl -s -o /dev/null -w "capcut diag no-token: %{http_code}\n" http://127.0.0.1:8200/diagnostics
unset TOKEN
```

예상: 셋 모두 `no-token 401`, `text 415`, `host 400`이다. `ok-json`은 문지기를 통과해 각 다리 자기 검사로 간다. 목소리는 `400`(text is required), 캡컷은 `400`(draft_host_path_and_export_id_are_required), 그림은 `400`(html_is_required)이다. `voice health 200`, `capcut diag no-token 401`. 결과 표를 인계 문서에 옮긴다.

이어서 컨테이너 → **새** 다리가 토큰으로 통과하는지 본다:

```bash
curl -s http://127.0.0.1:5173/api/capcut/handoff-diagnostics | .venv/Scripts/python.exe -c "import json,sys;d=json.load(sys.stdin);print('project_root_exists', d.get('project_root_exists'))"
```

예상: `project_root_exists True`. `False`면 컨테이너가 토큰 없이 불렀거나 값이 어긋난 것이다(새 다리가 401을 냈다). 멈추고 Step 1의 `token-set`과 `.env.container`의 줄 수를 다시 본다. `docker exec`·`curl`은 읽기만 하는 확인이고 compose 조작이 아니다.

- [ ] **Step 5: 동작(더빙·캡컷·그림 한 번씩) — 화면에서 owner 길로 밟는다**

브라우저 http://127.0.0.1:5173, Ctrl+F5 한 번.

1. **그림**: 아무 프로젝트의 편집기 → `인포그래픽 만들기` → 주제 하나와 숫자 두세 개 → 만들기. "그리는 중… 1~2분 걸려요"가 보이고 그림이 나와야 한다. 나온 그림을 잰다. 자료실에서 새 그림 자산의 `preview_url`을 내려받아 PNG 머리에서 크기를 읽는다:
   ```bash
   curl -s "http://127.0.0.1:5173/api/library/assets?media_type=image&limit=500" -o "$TEMP/img.json"
   .venv/Scripts/python.exe -c "import json,os,struct,urllib.request;a=max(json.load(open(os.path.join(os.environ['TEMP'],'img.json'),encoding='utf-8'))['assets'],key=lambda x:x.get('created_at') or '');b=urllib.request.urlopen('http://127.0.0.1:5173'+a['preview_url']).read();print(a['library_asset_id'],struct.unpack('>II',b[16:24]),len(b))"
   ```
   예상: `(1920, 1080)`, 바이트 수 수만 이상. 실행 코드 거절이 실제 모델 출력에서 오탐을 내지 않았다는 증거이기도 하다. 오탐이면 재시도 프롬프트에 "실행 코드" 문구가 찍히고 실패한다. 그 경우 API 로그에서 `infographic_did_not_pass_checks`를 찾아 원문을 인계에 남긴다.
2. **캡컷**: 같은 프로젝트에서 캡컷 초안 내보내기 → 캡컷으로 넘기기. 오류 없이 "넘겼어요"류 상태가 떠야 한다. 이 컴퓨터의 `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft`에 새 폴더가 생긴다(`dir`로 개수를 전후로 센다).
3. **더빙**: 편집기에서 `목소리 더빙`을 한 장면에 건다(목소리 샘플이 있는 프로젝트). 기다림 표시 뒤에 완료돼야 한다. 결과 소리를 음량으로 잰다. 더빙된 wav/mp4의 평균 음량이 무음(-91dB)이 아닌지 본다:
   ```bash
   ffmpeg -hide_banner -i "<더빙 결과 파일>" -af volumedetect -f null - 2>&1 | grep -E "mean_volume|max_volume"
   ```
   예상: `mean_volume`이 -40dB보다 크다. 더빙 결과 파일 위치는 작업 상태 응답(`/api/projects/{project_id}/editing-sessions/{session_id}/dubbing/{job_id}`)에서 찾는다. 목소리 샘플이 있는 프로젝트가 없으면 "검증 못 함"으로 인계에 정직하게 적는다. 대신 Step 3의 `ok-json 400`(문지기 통과)과 Step 4로 갈음한 사실을 함께 적는다.

- [ ] **Step 6: 깨진 이름 24개를 실제로 고친다**

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/repair_mojibake_library_filenames.py
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/repair_mojibake_library_filenames.py --apply
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/repair_mojibake_library_filenames.py
ls artifacts/library-filename-repair/
```

예상: 첫 미리보기는 `고칠 이름 24개`. `--apply`는 `되돌릴 목록: ...revert-<UTC>.json`과 `바꿈 24/24`, 종료 코드 0. 다시 미리보기하면 `고칠 이름 0개`. 되돌릴 목록 파일이 있다(지우지 않는다).

서버 쪽에서도 확인한다(화면 입력칸이 아니라 서버 값을 본다):

```bash
curl -s "http://127.0.0.1:5173/api/library/assets?media_type=broll&limit=500" | .venv/Scripts/python.exe -c "import json,sys;d=json.load(sys.stdin);n=[a['user_metadata'].get('filename','') for a in d['assets'] if a.get('origin')=='user'];print(sum(x.startswith('녹음 ') for x in n),sum(x.startswith('화면 녹화 중 ') for x in n),sum(x=='완성본.mp4' for x in n),sum(any('\x80'<=c<='\xff' for c in x) for x in n))"
```

예상: `2 21 1 0`.

- [ ] **Step 7: 화면에서 이름 바꾸기를 밟는다**

브라우저 → 자료실 → 영상 → `녹음 2026-02-07 163617.mp4` 카드를 고른다. 미리보기 제목이 한국어로 보여야 한다(깨진 글자가 없다). `이름 바꾸기` → 입력칸에 지금 이름이 채워져 있다 → 끝에 ` 확인`을 붙여 Enter → 제목과 카드 이름이 바뀐다. 서버 값을 확인한다:

```bash
curl -s "http://127.0.0.1:5173/api/library/assets?q=%ED%99%95%EC%9D%B8&limit=500" | .venv/Scripts/python.exe -c "import json,sys;print([a['user_metadata']['filename'] for a in json.load(sys.stdin)['assets'] if a.get('origin')=='user'])"
```

예상: `['녹음 2026-02-07 163617.mp4 확인']`. 그다음 다시 `이름 바꾸기` → ` 확인`을 지우고 저장해서 원래 이름으로 되돌린다. 같은 확인을 `q=%EB%85%B9%EC%9D%8C`(녹음)으로 해서 원래 이름을 확인한다. 입력칸에 `a/b`를 넣으면 `이름 저장`이 꺼지고 안내가 한 줄 뜨는지, Esc로 닫히는지도 본다. 기본 소재팩 자산(있다면)에는 `이름 바꾸기`가 없어야 한다. 화면을 캡처해 인계에 남긴다.

- [ ] **Step 8: 배선(전체 grep)**

```bash
grep -rn "check_request(" scripts/host_*_service.py | wc -l
grep -rn "bridge_request_headers()" packages --include=*.py | wc -l
grep -rn "renameLibraryAsset(" apps/web/src --include=*.tsx | grep -v test
grep -rn "/filename\"" services/api/src/videobox_api/routers/library_assets.py
grep -c "filter(isChipTag)" apps/web/src/features/editor/assets/EditorAssetBrowser.tsx
grep -rn "analysis_phrases" packages --include=*.py | grep -v test | wc -l
```

예상: `3`(다리마다 `_refused` 안에 1). `3`(부르는 쪽 셋). `LibraryPreviewPane.tsx` 1줄. 라우트 1줄. `1`(화면 방어 겹이 남아 있다). 2 이상(저장소와 추천기).

- [ ] **Step 9: 전체 시험(혼자, 마지막에)**

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --ignore=tests/test_mcp_server.py tests
(cd apps/web && npx vitest run)
npm --prefix apps/web run build
npm --prefix apps/web audit --omit=dev
```

예상: 파이썬은 알려진 실패 1건(`test_smoke_timeout_kills_the_child_tree_and_returns_bounded_failure`)만 빨갛다. vitest도 알려진 1건만 빨갛다. 빌드 성공. audit `found 0 vulnerabilities`. 다른 실패가 나오면 먼저 이 묶음의 변경 탓인지 본다(`git stash` 없이 `git log`로 해당 파일의 마지막 변경을 확인하고, 필요하면 이전 커밋에서 그 시험 하나만 다시 돌린다).

- [ ] **Step 10: 갭 — 계획과 대조해 안 한 것을 적는다**

인계 문서 `docs/handoffs/<실행일>-audit-bundle-a-security-tools-rename.ko.md`에 아래를 쓴다(쉬운 말, 존댓말 아님, 기록체).

- 한 일: Task 0(이미지에서 `.env.container`·`.venv-chatterbox` 제외, 이미지 크기 전후), A1~A4 각각의 결과와 실측 값(Step 1 확인 넷, Step 2 끈 프로세스, Step 4 표와 `project_root_exists`, Step 5 크기·음량, Step 6 숫자 넷), 분위기 태그 원인(Task 9).
- **안 한 것·남은 것**:
  - 유진 "이름 바꾸기" 의도·적용기·안내문은 묶음 F다(이 계획 밖).
  - 전체 `npm audit`에 남은 vite·vitest 경고(개발 도구, 패치만 한다는 결정). 남은 이름과 등급을 적는다.
  - 옛 이미지 층·빌드 캐시·다른 태그 이미지에 남아 있을 수 있는 `.env.container` 비밀값. 바꿀지, 옛 이미지를 지울지는 owner가 정한다(Task 0 Step 8). 승인 없이 하지 않았다.
  - 분위기 태그: 새 규칙은 **새로 분석하거나 사람이 검토할 때만** 적용된다. 이미 저장된 문장 조각 태그는 되채우지 않았다(화면 `isChipTag`가 가린다). 새 분석으로 실화면을 재 보지 못했으면 그 사실을 적는다(분석 한 번에 수 분 걸린다).
  - 디렉터 후보 순위(`media_ranking.rank_candidates`)는 `analysis_phrases`를 읽지 않는다. 그 길의 자산 모양은 이번에 확인하지 않았다.
  - 더빙 401 안내문("바탕화면 아이콘을 다시 실행")은 토큰이 바뀐 채 옛 다리가 떠 있는 경우는 못 고친다. 그때는 Task 10 Step 2~3(다리 끄고 다시 켜기)이 필요하다.
  - 다리 코드가 바뀌면 떠 있는 다리를 손으로 꺼야 하는 점. `owner-ready`는 포트가 열려 있으면 다시 띄우지 않는다.
  - 더빙 실측을 못 했으면 그 사실.
  - 깨진 이름이 생긴 원인(넣는 쪽)은 고치지 않았다. 이름이 바이트째 깨져 들어온 경로가 무엇이었는지는 확인하지 못했다(추정: 윈도우 도구가 multipart 파일 이름을 cp949로 보냈다).
- 재사용 게이트(§8.3): 재사용한 것은 `/favorite` 라우트·`set_favorite` 패턴, `new-hermes-yujin-secrets.ps1`의 "없을 때만·값 안 찍기" 규칙, 다리의 판단/껍데기 분리다. 새로 만든 것은 문지기 하나와 헤더 함수 하나다. 뺀 것은 CSP 주입(측정 스크립트를 막는다)과 시작 스크립트 셋 수정(파이썬 한 곳에서 읽는다)이다. 경계: 팔레트·네트워크 경계·사람 게이트는 그대로다.
- 결정 필요: (1) `.env.container` 비밀값 교체 여부, (2) 옛 VideoBox 이미지·빌드 캐시 정리 여부. 둘 다 owner 승인 전에는 하지 않는다.

`CLAUDE.md` 52줄을 새 문서로 바꾼다:
```
| **최신 세션 인계** | `docs/handoffs/<실행일>-audit-bundle-a-security-tools-rename.ko.md` |
```
같은 날짜로 살아 있는 인계 문서가 이미 있으면, 그 문서 맨 위에 `**대체됨:** docs/handoffs/<실행일>-audit-bundle-a-security-tools-rename.ko.md` 한 줄을 넣는다.

```bash
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_handoff_entry_point.py
```

예상: 통과.

- [ ] **Step 11: 커밋과 푸시(확인과 푸시를 한 명령에 묶지 않는다)**

```bash
git add docs/handoffs/ CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: 점검 후속 묶음 A 인계(다리 토큰·도구 패치·인포그래픽 거절·이름 바꾸기 실측)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
git status --short
git log --oneline -10
```

`git status`가 깨끗하고(`.anchor/`와 다른 묶음 계획서 제외), 로그에 이 묶음의 커밋 11개(Task 0~10, 각 하나)가 보이는 것을 확인한 **다음에** 따로 푸시한다:

```bash
git push origin main
```

`--force`는 쓰지 않는다. 도구 권한이 이 명령을 막으면 **우회하지 않는다**(다른 원격·다른 명령·설정 변경 금지). 멈추고 owner에게 이렇게 알린다: "`D:\AI_Workspace_louis_office_50\10_workspace\65_videobox`에서 `git push origin main`을 직접 실행해 주시거나, 허용 규칙 `Bash(git push origin main)`을 더해 주세요." 푸시가 거절되면(원격이 앞서 있음) `git pull --rebase origin main` 뒤 Step 9의 좁은 시험을 다시 돌리고 푸시한다. 충돌이 나면 멈추고 보고한다.
