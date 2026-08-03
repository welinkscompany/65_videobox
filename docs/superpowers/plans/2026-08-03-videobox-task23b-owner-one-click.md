# Task 23B Owner One-Click Check, Start, and Diagnosis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기본 실행은 완전한 read-only 진단이고, 사용자가 명시한 모드에서만 VideoBox 시작·비실시간 smoke·브라우저·CapCut 열기를 수행하는 하나의 안전한 owner 진입점을 만든다.

**Architecture:** `scripts/owner-ready.ps1`이 기존 Git/도구/Compose/loopback/CapCut/data-root 정보를 bounded check로 모으고 모든 항목을 `pass|blocked|fail + 쉬운 복구 행동`으로 정규화한다. `Start`는 base Compose의 두 VideoBox service만, `Smoke`는 기존 non-live/static verifier 여섯 개만 실행하며 raw stdout/stderr 대신 sanitized receipt만 남긴다. `Open`과 `OpenCapCut`은 별도 명시 모드이고 default `Check`에서는 `docker compose up`이나 `Start-Process`가 절대 실행되지 않는다.

**Tech Stack:** Windows PowerShell 5.1+, Python 3.12 pytest subprocess fixtures, Docker Compose, loopback HTTP, existing VideoBox/Hermes static and non-live verifiers

---

## 실행 상태

- [ ] Task 1 기본 Check와 결과/비밀정보 경계
- [ ] Task 2 도구·Compose·loopback·CapCut·data-root 진단
- [ ] Task 3 명시적 Start와 bounded health
- [ ] Task 4 sanitized Smoke receipt와 Open 모드
- [ ] Task 5 실제 환경 검증·리뷰·SSOT·commit/push

## 고정 경계

- default `Check`는 파일·서비스·앱·프로젝트를 생성, 수정, 삭제, 시작하지 않는다. 버전/상태를 읽기 위한 bounded child process는 허용하지만 `docker compose up`, `Start-Process`, write probe는 금지한다.
- `Start`는 `compose.yaml`의 `videobox-postgres`, `videobox-workspace`만 명시해 시작한다. Hermes profile/service, provider, credential 생성/주입, env 파일 수정은 금지한다.
- `Smoke`는 기존 script를 `-Live` 없이 호출하고 profile/runtime에는 `-StaticOnly`를 강제한다. 외부 provider call은 0이며 기존 project를 바꾸지 않는다.
- `Open` URL은 exact loopback VideoBox root만 허용한다. `OpenCapCut`은 발견한 `CapCut.exe`만 열며 project open/edit/export 인자를 전달하지 않는다.
- stdout, stderr, receipt에는 env 값, command raw output, credential, container ID, filesystem 절대 경로를 기록하지 않는다.
- 사용자 샘플과 `.tmp-final-fence-debug/`, `.tmp-real-video-dogfood/`, `apps/web/.tmp-real-video-dogfood/`를 열거나 stage/remove/delete하지 않는다.

### Task 1: 기본 Check와 결과/비밀정보 경계

**Files:**
- Create: `scripts/owner-ready.ps1`
- Create: `tests/test_owner_ready_script.py`

- [ ] `tests/test_owner_ready_script.py`에 임시 repo와 fake `git/docker/node/npm/ffmpeg/ffprobe/python` 실행 파일을 만드는 fixture를 작성한다. fake command는 호출 인자와 의도적 secret stderr를 별도 test log에 쓰되 제품 출력에는 절대 노출되지 않아야 한다.
- [ ] 인자 없이 실행하면 `mode=Check`, 각 결과가 exact `id/status/summary/action/evidence` shape, overall이 `pass|blocked|fail`이고 JSON에 `password`, `token`, fake stderr, 전체 command line이 없는 실패 테스트를 작성한다.
- [ ] default Check의 command log에 `compose up`, `start`, `Start-Process`, smoke script 호출이 0개이며 repository/test path에 새 파일이 생기지 않는 실패 테스트를 작성한다.
- [ ] exact 보호 residue 세 개만 있으면 허용 evidence count로 집계하고, tracked dirty 또는 unknown untracked는 경로를 노출하지 않는 `blocked`가 되는 테스트를 작성한다.
- [ ] non-loopback `-VideoBoxUri`/`-HermesDashboardUri`, URL user-info/query/fragment, detached branch, upstream divergence가 bounded `fail|blocked`이고 외부 HTTP를 호출하지 않는 테스트를 작성한다.
- [ ] 실패 테스트를 실행한다.

Run: `.venv\Scripts\python.exe -m pytest tests/test_owner_ready_script.py -q`

- [ ] `owner-ready.ps1`에 다음 public contract와 helper를 최소 구현한다.

```powershell
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet("Check", "Start", "Smoke", "Open", "OpenCapCut")]
    [string]$Mode = "Check",
    [switch]$Json,
    [Uri]$VideoBoxUri = "http://127.0.0.1:5173/",
    [Uri]$HermesDashboardUri = "http://127.0.0.1:9119/",
    [ValidateRange(1, 180)][int]$TimeoutSec = 30,
    [string]$DockerExecutable = "docker",
    [string]$GitExecutable = "git",
    [string]$NodeExecutable = "node",
    [string]$NpmExecutable = "npm",
    [string]$FfmpegExecutable = "ffmpeg",
    [string]$FfprobeExecutable = "ffprobe",
    [string]$LocalAppData,
    [string]$ReceiptRoot
)

function New-OwnerReadyResult {
    param([string]$Id, [ValidateSet("pass", "blocked", "fail")][string]$Status,
          [string]$Summary, [string]$Action, [hashtable]$Evidence)
    [pscustomobject]@{ id=$Id; status=$Status; summary=$Summary; action=$Action; evidence=$Evidence }
}
```

- [ ] process wrapper는 `UseShellExecute=false`, stderr discard, timeout/kill, bounded stdout만 사용하고 exception/command text를 결과에 싣지 않는다.
- [ ] Git check는 script parent의 repo root와 `git rev-parse --show-toplevel` 일치, named branch, matching upstream, divergence 0/0을 확인한다. `git status --short`는 exact 보호 residue count와 그 외 dirty count만 반환한다.
- [ ] JSON과 쉬운 한국어 console renderer를 구현하되 모두 normalized result만 소비하게 한다.
- [ ] 테스트를 다시 실행한다.

### Task 2: 도구·Compose·loopback·CapCut·data-root 진단

**Files:**
- Modify: `scripts/owner-ready.ps1`
- Modify: `tests/test_owner_ready_script.py`

- [ ] Python `.venv`, Node, npm, FFmpeg, ffprobe, Docker CLI/daemon의 성공과 각각의 missing/timeout `blocked` action을 fake executable로 검증하는 실패 테스트를 작성한다. version output은 엄격한 짧은 pattern만 evidence로 허용한다.
- [ ] `docker compose -f compose.yaml --env-file .env.container.example config --quiet`만 정적 parse에 사용하며 raw config를 출력하지 않는 테스트를 작성한다. 실제 `.env.container`이 없으면 별도 `container_env=blocked`이고 compose syntax check는 계속 가능해야 한다.
- [ ] VideoBox health와 Hermes dashboard probe는 proxy/redirect를 끄고 exact loopback URL, bounded body/timeout만 허용한다. 200은 pass, 연결 불가는 `서비스가 아직 꺼져 있습니다` action의 blocked, redirect/oversize/invalid response는 fail인 테스트를 작성한다.
- [ ] CapCut check가 `%LOCALAPPDATA%/CapCut/Apps/**/CapCut.exe`의 최신 numeric version을 read-only로 찾고 project root 존재 여부만 읽으며 `.videobox-write-check-*`를 만들지 않는 테스트를 작성한다.
- [ ] `.env.container`에서는 exact `VIDEOBOX_CONTAINER_DATA_ROOT` key 하나만 읽고 path를 출력하지 않은 채 configured/existence/readability/attributes/runtime/snapshot metadata를 반환하는 테스트를 작성한다. secret key/value는 receipt에 없어야 한다.
- [ ] legacy Windows 259자 한계에서 `runtime/projects/<uuid>/cache/browser/<asset-hash>/<fingerprint>.mp4` reserve와 최소 20자 여유를 계산하고, 짧은 root는 pass, 긴 root는 `더 짧은 전용 데이터 폴더` action의 blocked가 되는 테스트를 작성한다.
- [ ] 실패 테스트를 실행하고, 각 check를 독립 함수로 최소 구현한 뒤 다시 통과시킨다.

Run: `.venv\Scripts\python.exe -m pytest tests/test_owner_ready_script.py -q`

### Task 3: 명시적 Start와 bounded health

**Files:**
- Modify: `scripts/owner-ready.ps1`
- Modify: `tests/test_owner_ready_script.py`

- [ ] `Mode Start`에서 `.env.container`, Docker daemon, compose parse, data root가 준비되지 않으면 `blocked`로 끝나고 fake Docker log에 `up`이 없는 실패 테스트를 작성한다.
- [ ] 준비된 Start는 exact command `compose -f compose.yaml --env-file <env> up -d videobox-postgres videobox-workspace` 한 번만 호출하고 Hermes service/profile 이름, credential 값, `--remove-orphans`를 포함하지 않는 테스트를 작성한다.
- [ ] Start 후 exact VideoBox loopback `/health`를 bounded poll하고 ready이면 pass, timeout이면 fail과 `docker 상태를 확인` recovery action을 반환하는 테스트를 작성한다.
- [ ] `-WhatIf` Start는 Compose를 시작하지 않고 의도만 안전하게 출력하는 테스트를 작성한다.
- [ ] 실패 테스트를 실행한 뒤 `$PSCmdlet.ShouldProcess()`와 deadline/poll을 사용하는 최소 구현으로 통과시킨다.

Run: `.venv\Scripts\python.exe -m pytest tests/test_owner_ready_script.py -q`

### Task 4: sanitized Smoke receipt와 Open 모드

**Files:**
- Modify: `scripts/owner-ready.ps1`
- Modify: `tests/test_owner_ready_script.py`

- [ ] Smoke가 다음 여섯 checked-in script만 정확히 한 번 호출하는 실패 테스트를 작성한다.

```text
smoke-hermes-yujin-creator-flow.ps1
smoke-hermes-yujin-chat.ps1
smoke-hermes-yujin-mem0.ps1
verify-hermes-yujin-plan-state.ps1
verify-hermes-yujin-profile.ps1 -StaticOnly
verify-hermes-yujin-runtime.ps1 -StaticOnly
```

- [ ] 모든 smoke 호출에 `-Live`, credential, project/session ID가 없고 child stdout/stderr가 secret을 써도 receipt에는 id/status/action, `external_provider_calls=0`, timestamp, commit short SHA만 남는 테스트를 작성한다.
- [ ] default receipt root가 ignored `artifacts/owner-ready`, 파일명이 timestamp+commit으로 bounded하며 temp→replace 원자 게시를 사용하는 테스트를 작성한다. child 하나 실패 시 overall fail이지만 나머지 verifier도 실행해 전체 복구 정보를 남겨야 한다.
- [ ] `Open`은 exact VideoBox loopback root만 `Start-Process`하고, `OpenCapCut`은 발견한 exact `CapCut.exe`를 argument 없이 여는 계약을 `-WhatIf`로 검증한다. 다른 모드에서는 둘 다 호출되지 않아야 한다.
- [ ] 실패 테스트를 실행한 뒤 기존 script를 raw output capture 없이 호출하는 최소 orchestrator와 atomic JSON receipt를 구현하고 다시 통과시킨다.

Run: `.venv\Scripts\python.exe -m pytest tests/test_owner_ready_script.py -q`

### Task 5: 실제 환경 검증·리뷰·closeout

**Files:**
- Modify: `docs/development-status-2026-06-29.ko.md`
- Modify: `docs/implementation-plan.ko.md`
- Modify: `docs/superpowers/plans/2026-08-03-videobox-task23b-owner-one-click.md`
- Create: `docs/handoffs/2026-08-03-videobox-task23b-owner-one-click-closeout.ko.md`

- [ ] `Check -Json`을 현재 worktree에서 실행해 실제 pass/blocked/fail을 기록한다. missing env/Docker/CapCut/health는 blocked일 수 있으며 자동으로 고치거나 서비스를 시작하지 않는다.
- [ ] `Smoke`를 실행해 six verifier receipt를 생성·검사하고 `git status`에서 ignored artifact임을 확인한다. 외부 provider call과 기존 project mutation은 0이어야 한다.
- [ ] code quality, plan-gap, default Check의 명령 log 역추적, Smoke receipt→exact script→static/non-live boundary 역추적을 수행한다. Critical/Important finding은 수정하고 관련 RED/GREEN을 재실행한다.
- [ ] focused pytest, 관련 기존 Hermes script tests, Compose contract tests, production-adjacent static verifier를 실행한다. Task 23 최종 전체 회귀는 23D 뒤 final audit에서 실행하며 이번에 실행하지 않은 범위는 통과로 주장하지 않는다.
- [ ] `git diff --check`, branch/upstream divergence, worktree list, 보호 residue를 확인한다.
- [ ] SSOT와 handoff에 실제 상태·검증·미실행 경계와 Task 23 누적 `2/4 (50.0%)`, 잔여 `50.0%`를 기록한다.
- [ ] 논리적으로 닫힌 변경만 커밋하고 `origin/codex/videobox-container-compatibility`에 push한다.

## Acceptance matrix

| 경로 | 기대 결과 | 자동 근거 |
|---|---|---|
| 기본 실행 | Check read-only, service/app start 0, write probe 0 | fake command log + filesystem snapshot |
| missing tool/env/CapCut | precise blocked + 쉬운 recovery | pytest subprocess cases |
| unsafe URI/redirect | fail closed, external call 0 | loopback server tests |
| Compose parse | example env로 `config --quiet`, secret/config body 0 | fake Docker log + output audit |
| data root/path | path/value 비노출, existence/read metadata, 20자 headroom | temp path tests |
| Start | base service 두 개만 up, bounded health | fake Docker + loopback health tests |
| Smoke | exact six static/non-live scripts, atomic sanitized receipt | fake child scripts + JSON schema assertions |
| Open | VideoBox loopback root만 열기 | `-WhatIf` contract test |
| OpenCapCut | exact executable, argument 0 | `-WhatIf` contract test |

## Reverse runtime trace

1. `owner-ready.ps1` default invocation은 mode를 `Check`로 고정한다.
2. 각 checker는 bounded child process 또는 loopback HTTP로 상태만 읽고 normalized result를 만든다.
3. renderer는 normalized result만 console/JSON으로 내보내므로 raw stderr, env 값, command line이 경계를 넘지 못한다.
4. `Start`만 exact base Compose 두 service를 명시하고 health URL까지 추적한다.
5. `Smoke` receipt의 각 row는 exact checked-in script와 static/non-live 인자로 역추적된다.
6. `Open`/`OpenCapCut`은 mode branch와 `ShouldProcess`를 모두 통과해야만 사용자 앱을 연다.

## Plan self-review

- approved Task 23 spec의 Check/Start/Smoke/Open/OpenCapCut, pass/blocked/fail, secret redaction, no-write-probe, zero-provider-call 요구를 각각 테스트와 구현 step에 연결했다.
- default Check의 child process는 상태 조회용으로만 허용하고 service/app start 금지와 구분했다.
- missing credential/env는 local MVP 실패가 아니라 blocked로 고정했다.
- Start와 Smoke를 분리해 provider/Hermes live나 기존 project mutation으로 범위가 넓어지지 않게 했다.
- placeholder, 자동 apply, source copy, SaaS, 외부 URL, live Mem0 항목은 없다.
