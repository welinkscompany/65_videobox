# VideoBox Hermes Yujin planning closeout

## 쉬운 말 요약

유진을 VideoBox에 붙이는 설계 승인과 Phase 0 감사·기준선 뒤 첫 production 작업 A1을 완료했다. 공식 Hermes runtime과 아주 좁은 gateway가 Compose에 들어갔지만, 실제 계정 정보가 없으므로 컨테이너나 대화는 시작하지 않았다. 다음 A2에서 유진의 versioned Soul/profile/skills package만 설치·검증하고, 실제 통신과 대화는 A3/A4까지 열지 않는다.

## 계획 문서

- 총괄: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-master-plan.md`
- 런타임/대화: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-runtime-chat-vertical-slice.md`
- creator tools: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-creator-tools.md`
- realtime reliability: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-realtime-reliability.md`
- Mem0: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-mem0-memory.md`

## 고정 경계

- Hermes에 직접 붙는 주체는 전용 `videobox-agent-gateway`다.
- workspace↔gateway와 gateway↔Hermes는 서로 다른 internal network다. 하나로 합치면 workspace가 Hermes를 우회 호출할 수 있으므로 합치지 않는다.
- Hermes만 provider egress에 연결하며 Docker forwarding은 사용하지 않는다.
- Hermes와 Gateway에 VideoBox DB/media mount를 주지 않는다.
- 사용자가 Apply를 누르기 전에는 편집을 바꾸지 않는다.
- 실제 적용은 기존 current-revision `EditorCommandPort`만 사용한다.
- RightDock는 별도 player를 만들지 않고 기존 `PreviewStage` 한 개를 유지한다.
- Hermes/Mem0 장애 시 수동 편집을 계속한다.
- Mem0는 승인된 유진 보조기억이며 VideoBox SSOT가 아니다.
- SaaS, OpenCut source/runtime, generic provider/API 확대, 자동 apply는 제외한다.
- local/test external provider call은 0이고 live canary는 별도로 기록한다.

## 현재 상태

- written design: 승인 완료
- detailed master/child plans: 작성·자체 검토 완료
- P0-1 audit: 완료
- P0-2 reverse trace/plan-state verifier: 완료
- A1 isolated Hermes/gateway topology와 deterministic static verifier: 완료
- A1 Compose activation: base는 기존 호환, `compose.hermes-yujin.yaml` + `hermes-yujin` profile만 opt-in
- A1 gateway build context: Dockerfile 전용 deny-all allowlist로 Dockerfile·requirements·gateway source만 허용
- Phase 0: **2/2 완료**
- Phase A: **1/4 완료**
- production implementation: A1부터 시작
- Hermes Yujin initiative: **3/20 (15.0%), 잔여 85.0%**
- runtime/chat child: **3/6 (50.0%), 잔여 50.0%**
- creator child: **0/5**, reliability child: **0/4**, memory/final child: **0/5**
- 기존 공식 누적: **9/22 (40.9%), 잔여 59.1%**
- Task 9 사람/환경 acceptance와 실제 CapCut Desktop 실증: 별도
- A1 RED/GREEN: 서비스·파일 부재 **10 failed, 6 passed** → **16 passed**; build-context follow-up **1 failed, 16 passed** → **17 passed**
- static verification: child-process dummy env의 Compose config와 A1 verifier 통과
- live service start/HTTP/OAuth/provider/chat/Mem0: real auth env 부재로 미실행

## 보호 대상

다음 경로는 기존 범위 밖이며 stage/remove/delete하지 않는다.

- `.tmp-final-fence-debug/`
- `.tmp-real-video-dogfood/`
- `apps/web/.tmp-real-video-dogfood/`

## 다음 goal

**`A2`만** 실행한다. versioned Yujin Soul/profile/skills package를 기존 OAuth state와 격리 경계 안에 설치하고 ownership·digest·secret-free contents를 TDD로 검증한다. A3 gateway/RPC/SSE와 A4 RightDock live chat을 미리 시작하지 않는다.

## 다음 세션용 prompt

```text
VideoBox worktree에서 Hermes Yujin master plan의 A2만 실행해.
A1의 두 internal network와 provider-egress 분리, 기존 OAuth state 단일 mount, gateway-only transport ownership을 유지하면서 versioned Yujin Soul/profile/skills package와 installer/verifier를 strict RED-GREEN TDD로 구현해.
profile artifact의 ownership·digest·secret-free contents를 검증하고 VideoBox DB/media mount 금지와 local/test external provider call 0을 유지해.
보호된 임시 폴더 3개는 건드리지 마.
검증 뒤 A2만 [x]로 동기화하고 A3를 next goal로 남겨. A3/A4 production task는 미리 시작하지 마.
```
