# VideoBox Agent Foundation 세션 인수인계

**날짜:** 2026-07-20
**브랜치:** `codex/videobox-container-compatibility`
**정확한 HEAD/upstream:** `019a9a6c98ba037ed38070da0b33a8ef6645abbc`
**worktree:** clean, upstream 동기화됨

## 이번 세션에서 확정한 것

1. 유진 profile/prompt는 `1cc3d10`에서 versioned manifest와 `system → developer → task → user` priority, selected-project read-only context, structured fallback을 갖는다.
2. `e384ec4`의 ToolSpec/Gateway는 `get_project_status` 선언 하나만 허용한다. model output은 권한이 아니며, static acceptance도 executor 권한이 없다.
3. `eda1411`의 audit/retry는 redacted in-memory nonpersistent contract다. raw prompt/media/credential/model claim은 기록하지 않으며 retry/conflict는 non-executing이다. durable ledger/signature가 아니다.
4. `ce341de`의 approval workflow는 chat의 긍정 문구를 승인으로 보지 않는다. approval card는 static/non-executing이며 pending→applied를 허용하지 않는다.
5. `019a9a6`의 Agent Package v1은 Soul, canonical user preference/consent, response-only skill 3개, declaration-only `get_project_status` MCP 한 개를 package manifest로 고정한다. memory opt-in은 false, scope none, retention 0이고 MCP는 default deny다.

## 계속 금지된 범위

- Hermes MCP transport, provider 실행, device-code OAuth, egress open, GPT/Qwen/Gemini call
- DB/API route activation, memory storage, filesystem/shell/DB/renderer/CapCut/raw HTTP MCP
- editing mutation, render/export, host bridge, SaaS auth/billing

external/Gemini provider call은 계속 0이다. mem0는 유진 보조기억일 뿐 VideoBox SSOT가 아니다.

## 검증 현황

- 최신 package/profile/gateway/workflow/evidence focused: `158 passed` (기존 Starlette multipart warning 1건).
- production workspace build 및 `--network none --read-only` image import 통과.
- Python 전체 suite는 64초 timeout과 pytest stdout `OSError`로 끝나므로 full-pass로 기록하지 않는다.

## 다음 세션 시작 절차

1. 이 handoff, `docs/implementation-plan.ko.md`의 §23.1–23.6, `docs/development-status-2026-06-29.ko.md`의 §274를 먼저 읽는다.
2. `git status --short`, HEAD/upstream, `docker compose -p 65_videobox ps`를 먼저 확인한다.
3. 다음 goal은 실제 OAuth/provider가 아니라 **§23.2 durable capability issuer/revocation source와 gateway-only network split의 static fail-closed contract**다. existing `GET /internal/hermes/projects/{project_id}/status` conditional route가 이미 가진 durable consume/replay boundary를 재사용·대조하되, signing secret delivery, Hermes network, OAuth, provider call, ordinary `/api/*` 접근은 활성화하지 않는다.
4. TDD → independent spec/quality review → plan gap → source-to-runtime image import → focused/full attempt → SSOT → commit/push 순서로 닫는다.

## Task 9 상태

Task 9의 사람/환경 acceptance와 실제 CapCut Desktop evidence는 아직 별도 미완료다. 누적은 **9/22 (40.9%)**, 잔여 **59.1%**다.
