# VideoBox Hermes Yujin P0-1 감사 기준선

## 결론

P0-1은 **구현이 아니라 현재 상태를 확인한 감사 작업**이다. 공식 고정 이미지와 그 안의 source에서 필요한 Hermes CLI·JSON-RPC·WebSocket 계약을 확인했고, 제안된 세 dependency wheel도 프로젝트에 설치하지 않고 받을 수 있음을 확인했다.

다만 현재 실행 상태와 source Compose는 완전히 같지 않다. 공식 Dashboard는 현재 source와 같은 고정 이미지로 실행 중이지만, 현재 Compose에 없는 예전 `videobox-hermes-runtime` 컨테이너가 종료 상태로 남아 있고, 종료된 `videobox-hermes-agent`는 현재 pin보다 오래된 이미지다. 이 감사에서는 기존 컨테이너·volume을 삭제하거나 교체하거나 재시작하지 않았다.

HTTP 200은 두 곳에서 확인했지만 이것은 **HTTP 프로세스 준비 상태만** 뜻한다. provider, OAuth 계정, 실제 Yujin 대화, GPT 응답, Mem0 읽기·쓰기 성공은 확인하지 않았고 그렇게 추정하지 않는다. 이번 local/test external provider inference call은 0회다.

## Git·작업트리 기준선

감사 시작 시점의 결과다.

| 항목 | 결과 |
| --- | --- |
| `git status --short` | 보호된 untracked 경로 세 곳만 표시 |
| branch | `codex/videobox-container-compatibility` |
| HEAD | `387e9b5c57c34791b2996140568d517d7f37448b` |
| upstream | `387e9b5c57c34791b2996140568d517d7f37448b` |
| `HEAD...@{upstream}` | `0  0` |
| 현재 worktree | `D:/AI_Workspace_louis_office_50/10_workspace/65_videobox/.worktrees/videobox-container-compatibility` |
| 현재 worktree branch/HEAD | `codex/videobox-container-compatibility`, `387e9b5c5` |
| `git diff --check` | exit 0, 출력 없음 |

`git worktree list`에는 별도 top-level `main` worktree(`a6185842c`)도 표시됐지만, 이번 감사에서 그 worktree를 열거나 수정하지 않았다.

## source·Compose 계약

다음 파일을 읽기 전용으로 확인했다.

- `compose.yaml`
- `requirements-runtime.txt`
- `requirements-container.txt`
- `scripts/start-hermes-oauth-bootstrap.ps1`
- `scripts/verify-hermes-oauth-bootstrap.ps1`
- `services/api/src/videobox_api/main.py`

확인된 source 계약은 다음과 같다.

- `videobox-hermes-agent`, `videobox-hermes-oauth-bootstrap`, `videobox-hermes-dashboard`는 모두 `nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787`를 가리킨다.
- pre-auth agent는 `network_mode: none`이고 `/opt/data` scratch volume만 가진다.
- OAuth bootstrap은 `/opt/data` state volume과 `videobox-hermes-egress`만 사용하며 host port를 열지 않는다.
- Dashboard는 `/opt/data`, `videobox-hermes-provider-egress`, host loopback `127.0.0.1:9119`만 사용한다. VideoBox DB/media/internal network mount는 없다.
- `start-hermes-oauth-bootstrap.ps1`은 bootstrap 컨테이너만 시작하고, OAuth와 model 선택 명령은 owner가 직접 실행하도록 안내한다. 스크립트 자체는 OAuth나 model 명령을 실행하지 않는다.
- `verify-hermes-oauth-bootstrap.ps1`은 image, `/opt/data` 단일 mount, egress network, host port 없음만 검사한다. credential 내용, device code, 계정, model 선택은 검사하거나 출력하지 않는다.
- `requirements-runtime.txt`와 `requirements-container.txt`에는 제안된 `httpx==0.28.1`, `websockets==15.0.1`, `cryptography==45.0.6`가 아직 없다. 이는 P0-1에서 설치하거나 pin을 추가하지 않는 정상 상태다.
- `services/api/src/videobox_api/main.py`에는 조건부 internal Hermes capability verifier/router만 있다. P0-1 시점에는 새 Hermes conversation/gateway/SSE production route가 등록돼 있지 않다.

한 가지 문서·CLI drift도 확인했다. Compose 주석은 Dashboard의 non-loopback bind에 `--insecure`가 필요하다고 설명하지만, 고정 이미지의 `hermes serve --help`와 보완 확인한 `hermes dashboard --help`는 모두 2026년 6월 hardening 이후 `--insecure`가 **deprecated/no-op이며 인증을 끄지 않는다**고 명시한다. P0-1은 이 차이를 기록만 하며 source를 수정하지 않는다.

## 고정 이미지·CLI 근거

실행한 image 확인:

```powershell
docker image inspect nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787
```

결과는 exit 0이었다. local image ID와 RepoDigest가 모두 위 digest와 일치했고, OCI revision label은 `e89bc58a5ba80ec6be19b43beca37cbb03091afd`, architecture는 `amd64`, OS는 `linux`였다.

이미지 기본 entrypoint가 `/init /opt/hermes/docker/main-wrapper.sh`이므로 CLI 자체를 직접 확인하기 위해 `--entrypoint hermes`로 invocation shape만 바꿨다. provider 접속을 막기 위해 `--network none`도 사용했다.

```powershell
$image = 'nousresearch/hermes-agent@sha256:ad79951c26b7707c8c651f30780338d4f9bb17ddca19f6ea78eb27cbf83a3787'
docker run --rm --network none --entrypoint hermes $image --version
docker run --rm --network none --entrypoint hermes $image serve --help
docker run --rm --network none --entrypoint hermes $image profile install --help
docker run --rm --network none --entrypoint hermes $image dashboard --help
```

확인 결과:

- Hermes Agent `v0.18.2 (2026.7.7.2)`, upstream `e89bc58a`, Python `3.13.5`, OpenAI SDK `2.24.0`
- `hermes serve`: headless JSON-RPC/WebSocket gateway, 기본 host `127.0.0.1`, 기본 port `9119`; `--host`, `--port`, `--isolated`, `--stop`, `--status` 등을 제공
- `hermes profile install`: git URL 또는 local `distribution.yaml` directory를 받으며 `--name`, `--alias`, `--force`, `-y/--yes`를 제공
- `hermes dashboard`: `--no-open`을 추가로 제공하고, `--insecure`는 `serve`와 같은 deprecated/no-op 설명을 표시

## 공식 transport 계약

고정 이미지 안의 `/opt/hermes` source만 읽어 확인했다. 실제 WebSocket 연결이나 provider turn은 실행하지 않았다.

| 종류 | 확인된 계약 | image source 근거 |
| --- | --- | --- |
| REST | `POST /api/auth/ws-ticket` | `hermes_cli/dashboard_auth/routes.py` |
| ticket | 인증 session에 대해 TTL 30초, single-use | `hermes_cli/dashboard_auth/ws_tickets.py` |
| WebSocket | `/api/ws` | `hermes_cli/web_server.py` |
| JSON-RPC method | `session.create` | `tui_gateway/server.py`의 `@method("session.create")` |
| JSON-RPC method | `prompt.submit` | `tui_gateway/server.py`의 `@method("prompt.submit")` |
| JSON-RPC method | `session.interrupt` | `tui_gateway/server.py`의 `@method("session.interrupt")` |
| upstream event | `gateway.ready` | `tui_gateway/ws.py`, WS accept 직후 `method: "event"` envelope |
| upstream event | `message.delta` | `tui_gateway/server.py` stream callback |
| upstream event | `message.complete` | `tui_gateway/server.py` turn terminal emit |

`tui_gateway/ws.py`는 WebSocket 양방향에서 stdio와 같은 JSON-RPC 계약을 사용한다고 설명한다. 확인된 것은 **source/CLI transport 계약**이며, 인증 성공·session 생성 성공·provider 응답 성공·live chat 성공 증거가 아니다.

## 현재 컨테이너 상태

요구된 원문 명령은 다음과 같이 Compose 환경변수 보간에서 실패했다.

```powershell
docker compose ps -a
```

```text
error while interpolating services.videobox-postgres.environment.POSTGRES_PASSWORD:
required variable POSTGRES_PASSWORD is missing a value
```

기존 컨테이너를 변경하지 않고 상태를 확인하기 위해 Docker Compose project label 조회를 실행했다. 또한 `ps` 파싱에만 쓰이고 서비스 실행에는 쓰이지 않는 감사용 임시 환경변수를 현재 PowerShell process에 잠시 넣어 `docker compose -p 65_videobox ps -a`를 보완 실행한 뒤 바로 제거했다.

| 컨테이너 | 상태 | image/source 관계 | 관찰 |
| --- | --- | --- | --- |
| `65_videobox-videobox-hermes-dashboard-1` | running | 현재 고정 digest `ad799…`와 일치 | `/opt/data`, provider-egress, loopback 9119 |
| `65_videobox-videobox-workspace-1` | running, healthy | 현재 workspace service | loopback 5173 |
| `65_videobox-videobox-postgres-1` | running, healthy | 현재 postgres service | internal network |
| `65_videobox-videobox-hermes-runtime-1` | exited, code 127 | 현재 `compose.yaml`에 없는 예전 service | 예전 memory/provider-egress network 흔적, 삭제하지 않음 |
| `65_videobox-videobox-hermes-agent-1` | exited, code 137 | 예전 digest `3db34…`; 현재 source pin과 다름 | `network_mode: none`, 삭제하지 않음 |

OAuth bootstrap container는 현재 목록에 없었다. 기존 stopped/exited/orphan container와 volume은 삭제·교체·재시작하지 않았다.

## HTTP readiness와 실행하지 않은 live proof

read-only GET 결과:

| URL | 결과 |
| --- | --- |
| `http://127.0.0.1:9119/` | HTTP 200, `text/html; charset=utf-8` |
| `http://127.0.0.1:5173/health` | HTTP 200, `application/json` |

이 결과는 Dashboard와 VideoBox workspace HTTP endpoint가 응답했다는 뜻만 가진다.

다음은 실행하지 않았고 통과로 기록하지 않는다.

- OAuth login/account/model 선택 확인
- GPT 또는 다른 provider inference
- Hermes WebSocket live session과 실제 chat
- Yujin profile 설치·동작
- Mem0 read/write/retrieval
- provider credential 유효성

## dependency wheel 가용성

worktree 밖의 고유 TEMP directory에서 아래 명령을 실행했고 프로젝트 환경에는 설치하지 않았다.

```powershell
$dependencyAudit = 'C:\Users\atgro\AppData\Local\Temp\videobox-p0-1-wheels-6d1da07decf94482a59642633783fa33'
.\.venv\Scripts\python.exe -m pip download --only-binary=:all: --no-deps --dest $dependencyAudit httpx==0.28.1 websockets==15.0.1 cryptography==45.0.6
```

exit 0으로 세 wheel을 모두 받았다.

| wheel | bytes | SHA-256 |
| --- | ---: | --- |
| `httpx-0.28.1-py3-none-any.whl` | 73,517 | `D909FCCCC110F8C7FAF814CA82A9A4D816BC5A6DBFEA25D6591D6985B8BA59AD` |
| `websockets-15.0.1-cp312-cp312-win_amd64.whl` | 176,841 | `FCD5CF9E305D7B8338754470CF69CF81F420459DBAE8A3B40CEE57417F4614A7` |
| `cryptography-45.0.6-cp311-abi3-win_amd64.whl` | 3,403,805 | `833DC32DFC1E39B7376A87B9A6A4288A10AAE234631268486558920029B086EC` |

TEMP directory 정리는 `Remove-Item` 실행 정책에 의해 차단되어 public wheel 세 파일이 위 worktree 밖 고유 TEMP directory에 남았다. project file, credential, provider payload는 포함하지 않는다.

## 보호 경로

감사 시작과 closeout 확인에서 다음 세 경로는 같은 untracked 상태로 남아 있다.

```text
?? .tmp-final-fence-debug/
?? .tmp-real-video-dogfood/
?? apps/web/.tmp-real-video-dogfood/
```

이번 작업에서는 세 경로를 열거나 편집하거나 stage/remove/delete하지 않았다.

## 진행률과 다음 작업

- Hermes Yujin initiative: **1/20 (5.0%), 잔여 95.0%**
- Phase 0: **1/2**
- runtime/chat child: **1/6 (16.7%), 잔여 83.3%**
- 기존 공식 누적: **9/22 (40.9%), 잔여 59.1%**
- production 구현: **아직 시작하지 않음**

다음 작업은 **P0-2만** 수행한다. P0-2에서 RightDock부터 output까지의 reverse runtime trace를 기록하고, master/children의 20개 task ID·상태·진행률을 검사하는 verifier와 contract test를 TDD로 추가한다. A1 또는 그 이후 production task를 미리 시작하지 않는다.
