# VideoBox §23.2 capability authority static contract handoff

**날짜:** 2026-07-20
**기준 브랜치:** `codex/videobox-container-compatibility`
**시작 HEAD/upstream:** `902e54a2e9bf4c8d878c08dcb77ed0a7771741bb`

## 이번에 닫은 범위

- §23.2의 실제 OAuth/provider 실행 전 static fail-closed contract만 추가했다.
- canonical Python contract와 Compose extension은 전 필드가 일치해야 한다.
- issuer는 future `videobox-agent-gateway` 하나로 이름만 고정했고, issuance는 `false`, secret delivery와 ordinary `/api/*`는 `forbidden`이다.
- existing `LocalProjectStore.revoke_hermes_capability`는 durable revoke storage primitive다. owner-authorized revoke writer는 `not_deployed`이며, default app에는 capability/revoke/issue route가 없다.
- existing conditional `GET /internal/hermes/projects/{project_id}/status`의 durable consume/replay boundary와 대조했다. Hermes pre-auth는 `network_mode: none`을 유지하고, named future gateway service/network는 Compose에 존재하지 않는다.

## 명시적으로 하지 않은 일

- signer, signing secret delivery, key lifecycle, revoke writer, gateway audit
- Hermes network/service/route, device-code OAuth, GPT/Qwen/Gemini/provider call, MCP transport
- DB/API activation, mem0, mutation/render/export, CapCut/host bridge

external Gemini provider call은 계속 0이다. Task 9 사람/환경 acceptance는 별도이며 **9/22 (40.9%)**, 잔여 **59.1%**를 유지한다.

## 검증

- TDD RED: authority field 부재와 source/Compose drift를 확인한 뒤 최소 구현했다.
- focused: authority/status/Compose/profile/gateway `72 passed` (기존 multipart warning 1건).
- Compose config: dummy env로 `docker compose -p 65_videobox config --quiet` 통과.
- source-to-runtime: production workspace image build와 `--network none --read-only` image import 통과.
- full Python suite: 64초 timeout으로 종료되어 full-pass로 주장하지 않는다.
- independent spec review와 quality re-review: P0/P1/P2 0.

## 남은 gate와 다음 goal

정적 declaration은 activation authority가 아니다. 다음에는 owner-authorized revocation writer 또는 actual gateway route/network를 시작하기 전에 §23.1 egress, secret/key lifecycle, gateway audit, runtime service/network approval의 선행 gate를 다시 결정해야 한다. 별도 승인 없이는 이 영역을 구현하거나 활성화하지 않는다.
