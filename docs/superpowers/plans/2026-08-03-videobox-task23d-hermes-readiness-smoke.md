# Task 23D Hermes Readiness Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 Hermes 정적·비실시간 검증을 하나의 비밀정보 없는 owner-ready receipt로 묶고, 로컬 준비와 자격증명 차단과 실제 live 성공을 서로 오인하지 않게 한다.

**Architecture:** 새 Hermes runtime이나 provider를 만들지 않는다. `scripts/owner-ready.ps1 -Mode Smoke`가 기존 six-gate의 exact script/argument/성공 marker를 검증하고, checked-in script SHA와 bounded evidence만 `videobox-hermes-readiness-v1` receipt에 기록한다. dashboard는 기존 exact-loopback probe만 사용하고 gateway/profile/SOUL mount는 `verify-hermes-yujin-runtime.ps1 -StaticOnly` 및 profile verifier에 역추적한다. `.env.container`는 required key의 존재·중복·빈 값·명백한 placeholder 여부만 process-local로 분류하고 값은 출력·receipt·child argument에 싣지 않는다. 이 모드는 live canary 입력과 `-Live` 전달 경로가 없으므로 `live_ready`를 만들 수 없다.

**Tech Stack:** Windows PowerShell 5.1+, Python 3.12 pytest subprocess fixtures, existing Hermes Yujin static/non-live verifiers, loopback HTTP, Docker Compose contracts

---

## 실행 상태

- [x] Task 1 readiness schema·상태 우선순위·six-gate marker TDD
- [x] Task 2 dashboard/credential boundary와 sanitized receipt 구현
- [x] Task 3 manual fallback·reverse trace·실제 non-live 검증
- [ ] Task 4 Task 23 통합 회귀·독립 리뷰·SSOT·commit/push

## 고정 경계

- 외부 provider, OAuth, GPT, Mem0 provider, live chat/creator/Mem0 canary 호출은 0이다. `live_ready`는 Task 23D 코드 경로에서 도달 불가다.
- child allowlist는 아래 여섯 개뿐이다. chat/creator/Mem0/plan에는 인자 0개, profile/runtime에는 `-StaticOnly`만 허용한다. `start-hermes-yujin.ps1`, `get-hermes-yujin-status.ps1`, `verify-hermes-yujin-zero-tools.ps1`는 호출하지 않는다.
- raw stdout/stderr, command line, env 값, credential, absolute path, container ID는 console/receipt에 기록하지 않는다.
- `MEM0_API_KEY`는 optional Hermes auxiliary memory credential이며 local readiness 필수 credential로 세지 않는다. Mem0는 VideoBox persistence/SSOT가 아니다.
- dashboard probe는 exact loopback root, proxy/redirect-follow off, bounded timeout/body만 허용한다. gateway/Hermes/memory adapter host port를 새로 열지 않는다.
- profile/SOUL은 checked-in `config/hermes/yujin` source와 pinned read-only mount 계약으로만 확인한다. runtime verifier의 dummy child environment는 실제 credential 성공 증거가 아니다.
- Hermes 실패·미설정 상태에서도 기존 redacted 503/blocked terminal과 `유진 없이도 편집을 계속` manual fallback을 보존한다. 자동 apply, project mutation, memory write는 0이다.
- 사용자 샘플과 `.tmp-final-fence-debug/`, `.tmp-real-video-dogfood/`, `apps/web/.tmp-real-video-dogfood/`를 열거나 stage/remove/delete하지 않는다.

## 상태 모델과 우선순위

Receipt는 local 검증과 live 경계를 분리해 다음 필드를 갖는다.

```json
{
  "schema_version": "videobox-hermes-readiness-v1",
  "readiness_status": "credential_blocked",
  "static_non_live_checks_passed": true,
  "dashboard_status": "not_running",
  "credential_status": "missing",
  "live_canary_status": "not_run",
  "external_provider_calls": 0,
  "external_network_calls": 0
}
```

우선순위는 다음과 같다.

1. six-gate marker/exit/SHA 검증 실패 또는 malformed dashboard 응답은 `not_ready`다.
2. required env/key가 missing, duplicate, blank, placeholder이면 `credential_blocked`다. 현재 `.env.container` 부재의 예상 상태다.
3. required key metadata가 준비됐지만 dashboard가 아직 꺼져 있으면 `not_ready`다.
4. six-gate와 dashboard가 pass하고 required credential metadata가 준비되면 `local_ready`다. 이는 provider/live 성공을 뜻하지 않는다.
5. `live_ready`는 별도 승인·관찰된 canary receipt만 만들 수 있으므로 Task 23D에서는 항상 `live_canary_status=not_run`이고 절대 반환하지 않는다.

### Task 1: readiness schema·상태 우선순위·six-gate marker TDD

**Files:**
- Modify: `tests/test_owner_ready_script.py`
- Modify: `scripts/owner-ready.ps1`

- [x] fake six scripts가 실제 script별 exact success marker와 의도적 secret noise를 출력하게 fixture를 확장한다.
- [x] Smoke가 exact six relative script를 한 번씩, exact 허용 인자로만 실행하고 `-Live`, approval, project/session/conversation ID, credential argument가 0개인 RED test를 작성한다.
- [x] exit 0이어도 marker가 없거나 malformed/duplicate/unknown key/zero-call 값이 아닌 child는 fail closed하고 나머지 gate는 계속 실행하는 RED test를 작성한다.
- [x] receipt check가 exact `{id, mode, status, marker, script_sha256, action}`만 가지며 script SHA가 현재 checked-in child로 역추적되는 RED test를 작성한다.
- [x] child raw stdout/stderr, secret, repository/receipt/env absolute path가 console JSON과 receipt 어디에도 없는 RED test를 작성한다.
- [x] timeout이면 child tree를 종료하고 marker를 성공으로 추정하지 않는 기존 회귀를 새 schema에 맞춰 유지한다.
- [x] missing credential, failed gate, dashboard off, fully local-ready 조합의 상태 우선순위를 RED test로 고정하고 정적 입력만으로 `live_ready`가 나올 수 없음을 source/output 양쪽에서 검사한다.
- [x] RED를 실행한다.

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_owner_ready_script.py -q`

Expected: readiness schema, marker parsing, credential/dashboard state mapping 부재로 FAIL.

- [x] `owner-ready.ps1`에 script별 exact marker parser와 bounded public marker ID를 구현한다. raw line은 저장하지 않는다.
- [x] child exit, exact marker, checked-in SHA가 모두 맞아야 pass가 되게 하고 receipt에 static/non-live mode를 명시한다.
- [x] `videobox-hermes-readiness-v1` atomic receipt를 구현하고 기존 temp cleanup/timeout/continue-after-failure를 보존한다.
- [x] GREEN을 실행한다.

### Task 2: dashboard/credential boundary와 sanitized receipt 구현

**Files:**
- Modify: `tests/test_owner_ready_script.py`
- Modify: `scripts/owner-ready.ps1`

- [x] Hermes dashboard exact loopback 200 또는 same-loopback `/login` 302는 pass, connection refused는 `not_running`, 외부 redirect/malformed/oversize는 fail인 RED test를 작성한다. 외부 URL 요청 수는 0이어야 한다.
- [x] `.env.container`가 없으면 key value를 읽지 않고 `missing`; required key 누락·중복·blank·placeholder면 path/value를 노출하지 않는 `invalid`; exact required key metadata는 `present_unverified`인 RED test를 작성한다.
- [x] required key 목록은 Hermes gateway username/password/hash, gateway service token, capability private/public key/key ID, memory-adapter token만 포함하고 `MEM0_API_KEY`는 제외하는 테스트를 작성한다.
- [x] credential 분류는 `start-hermes-yujin.ps1 -ValidateOnly`, Docker run/pull, compose up, live status API를 호출하지 않는 fake command-log test를 작성한다.
- [x] receipt가 `static_non_live_checks_passed`, `dashboard_status`, `credential_status`, `live_canary_status=not_run`, `external_provider_calls=0`, `external_network_calls=0`, commit/timestamp를 기록하고 raw env/key value는 기록하지 않는 RED test를 작성한다.
- [x] RED를 실행한 뒤 loopback probe와 metadata-only env classifier를 최소 구현하고 GREEN을 실행한다.

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_owner_ready_script.py -q`

### Task 3: manual fallback·reverse trace·실제 non-live 검증

**Files:**
- Modify: `tests/test_owner_ready_script.py`
- Test: `tests/test_smoke_hermes_yujin_creator_flow_script.py`
- Test: `tests/test_api_hermes_conversation.py`
- Test: `apps/web/src/features/editor/workbench/right-dock.test.tsx`
- Test: `apps/web/src/features/jobs/HermesYujinStatus.test.tsx`

- [x] creator non-live가 in-process VideoBox→gateway→fake Hermes conversation/SSE를 통과하고 apply 전 mutation 0, current revision, output job 0, external provider 0인 focused test를 실행한다.
- [x] chat/Mem0 non-live marker가 exact zero-call/credential-redaction contract를 유지하는 owner-ready subprocess test를 실행한다. hardcoded marker는 live/provider 성공 증거로 승격하지 않는다.
- [x] API gateway unavailable은 redacted 503/blocked terminal로 닫히고 credential/path/provider body를 노출하지 않는 focused test를 실행한다.
- [x] Inspector/RightDock와 status UI가 Eugene 실패 시 수동 편집 CTA를 유지하고 editor command/automatic apply/memory write를 만들지 않는 focused frontend test를 실행한다.
- [x] 실제 worktree에서 `owner-ready.ps1 -Mode Smoke -Json`을 실행한다. 현재 `.env.container` 부재와 dashboard 상태는 사실대로 기록하고 서비스를 시작하거나 credential을 만들지 않는다.
- [x] receipt→script SHA/marker→profile/runtime static verifier→pinned read-only profile/SOUL mount→dashboard exact-loopback boundary→creator zero-external-call run 순서로 reverse trace한다.
- [x] code quality, plan-gap, reverse-runtime, receipt redaction review를 독립 관점으로 수행하고 Critical/Important finding을 수정·재검증한다.

### Task 4: Task 23 통합 회귀·독립 리뷰·SSOT·commit/push

**Files:**
- Modify: `docs/development-status-2026-06-29.ko.md`
- Modify: `docs/implementation-plan.ko.md`
- Modify: `docs/superpowers/plans/2026-08-03-videobox-task23d-hermes-readiness-smoke.md`
- Create: `docs/handoffs/2026-08-03-videobox-task23d-hermes-readiness-smoke-closeout.ko.md`
- Create: `docs/handoffs/2026-08-03-videobox-task23-owner-ready-mvp-polish-closeout.ko.md`

- [ ] Task 23D focused PowerShell/Python/Hermes/API/frontend tests와 실제 sanitized receipt 검증을 통과시킨다.
- [ ] Task 23 final gate로 전체 Python, 전체 frontend, production build, full editor E2E, provenance/UI-system, Compose/profile/runtime/network guard를 fresh 실행한다.
- [ ] 23C r4 package의 manifest/artifact/source hash reverse 검증을 다시 실행하되 사용자 sample source는 read-only로만 비교한다.
- [ ] six-gate release audit에서 automation, human visual/listening/taste, rights, CapCut Desktop, authenticated Hermes provider/live Mem0를 별도 표시한다. 실행하지 않은 사람/live gate는 통과로 주장하지 않는다.
- [ ] independent spec, code quality, gap, reverse-runtime review에서 Critical/Important 0을 확인한다.
- [ ] `git diff --check`, status, branch/HEAD/upstream divergence, worktree list, 보호 residue를 확인한다.
- [ ] SSOT/handoff에 실제 결과와 미실행 경계, Task 23 누적 `4/4 (100.0%)`, 잔여 `0.0%`를 기록한다. 이는 Task 9 사람 acceptance나 live provider 완료를 뜻하지 않는다.
- [ ] 계획 체크박스를 실제 완료 시점마다 갱신하고 논리적 변경을 커밋한 뒤 `origin/codex/videobox-container-compatibility`에 push한다.

## Acceptance matrix

| 경로 | 기대 결과 | 자동 근거 |
|---|---|---|
| six-gate allowlist | exact scripts/args once, Live/ID/credential args 0 | fake child command log |
| child evidence | exit 0 + exact marker + checked-in SHA만 pass | malformed/duplicate/unknown marker tests |
| credential absent/invalid | `credential_blocked`, value/path 비노출 | env metadata fixtures + JSON audit |
| dashboard boundary | exact loopback only; off와 malformed 구분 | bounded local HTTP fixtures |
| local ready | six-gate + dashboard + credential metadata pass, live는 not_run | state-matrix tests |
| live boundary | Task 23D에서 `live_ready` 도달 불가 | source/output assertion |
| profile/SOUL | pinned checked-in source의 read-only mount로만 역추적 | profile/runtime StaticOnly marker+SHA |
| manual fallback | Eugene 실패에도 수동 편집 유지, auto apply/memory write 0 | API/frontend focused tests |
| receipt | atomic, sanitized, reverse-resolvable | receipt schema/SHA tests |
| final audit | full regressions + package/release audit | fresh commands and handoff |

## Reverse runtime trace

1. `owner-ready.ps1 -Mode Smoke`는 exact six definition을 구성하며 `-Live` 전달 경로가 없다.
2. 각 child는 bounded process에서 실행되고 exit 0, exact allowlisted marker, current checked-in SHA가 모두 맞아야 sanitized row가 된다.
3. profile/runtime row는 `verify-hermes-yujin-profile.ps1 -StaticOnly`와 `verify-hermes-yujin-runtime.ps1 -StaticOnly`를 거쳐 exact SOUL/profile source, pinned image, OAuth volume, read-only profile mount, internal-only gateway/adapter 계약으로 돌아간다.
4. dashboard evidence는 exact loopback probe 하나로만 만들며 외부 redirect/proxy를 거부한다. gateway host port를 만들거나 직접 외부에서 probe하지 않는다.
5. creator row는 in-process VideoBox API→gateway→fake Hermes SSE와 apply 전 mutation 0, provider 0으로 역추적된다. chat/Mem0 zero marker는 non-live guard 증거일 뿐 live 성공이 아니다.
6. env classifier는 required key metadata만 process-local로 분류하고 값과 path를 버린다. missing/invalid는 `credential_blocked`에서 끝난다.
7. receipt의 `live_canary_status=not_run`에서 역추적이 끝나며 Task 23D 안에는 `live_ready` 생성 경로가 없다.
8. Eugene이 막히면 API/UI의 redacted blocked 상태가 수동 editor fallback으로 돌아가며 timeline/session 자동 변경은 없다.

## Plan self-review

- approved Task 23 master design의 23D 상태 세 가지를 local/static 상태와 live boundary로 분리해, credential 부재와 dashboard off와 verifier failure가 서로 섞이지 않게 했다.
- 기존 six-gate를 재사용하며 새 provider/runtime/API를 만들지 않는다.
- 실제 credential 관계 검증 script는 image pull 가능성이 있어 default path에서 제외했다. 이 선택은 `present_unverified`가 live 성공을 뜻하지 않게 명시한다.
- runtime/profile verifier가 이미 pinned image, SOUL/profile ownership, read-only mount, network/credential ownership을 검사하므로 이를 복제하지 않고 marker+SHA로 역추적한다.
- chat/Mem0의 얕은 non-live marker 한계를 숨기지 않고 creator in-process flow와 manual fallback focused tests로 보완한다.
- receipt의 external call 0은 child marker와 strict allowlist에서 도출하며, dashboard loopback probe는 별도 local evidence로 구분한다.
- human visual/listening/taste/rights/CapCut Desktop와 authenticated provider/live Mem0는 Task 23 closeout의 미실행 gate로 남긴다.
- placeholder, source copy, OpenCut runtime, SaaS, auto apply, VideoBox memory SSOT 확장은 없다.
