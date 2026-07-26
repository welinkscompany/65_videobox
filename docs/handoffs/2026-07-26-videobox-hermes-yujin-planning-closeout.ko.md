# VideoBox Hermes Yujin A2 profile closeout

## 쉬운 말 요약

Phase 0과 A1 격리 runtime 위에 A2의 versioned Yujin Soul/profile/skills package를 추가했다. package source는 opt-in overlay에서 read-only로만 보이고, 설치는 named Hermes container 안에서만 수행한다. 실제 계정 정보가 없으므로 컨테이너·profile install·대화는 시작하지 않았다. 다음 A3에서만 gateway의 인증 Hermes transport와 API SSE 경계를 구현하며 RightDock live chat은 A4까지 열지 않는다.

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
- A1 startup validation: Compose rendered model의 정확한 resolved env만 신뢰하고, 고정 Hermes 이미지의 공식 `_verify_password`를 network none으로 실행해 plaintext/hash 관계를 검증
- A1 startup streaming: captured config/password 검사는 stdout/stderr를 비동기로 동시에 drain하고 실제 targeted `up`은 native argument array와 inherited streaming을 사용
- A2 profile package: exact `videobox-yujin` 1.0.0 manifest, 한국어 우선 Soul, 대화·확인 질문·수동 fallback 전용 첫 skill
- A2 package honesty: 자동 적용, VideoBox 근거 없는 preview/export 성공 주장, 미지원 effect의 실행 가능 제안, Phase B creator proposal을 열지 않음
- A2 mount/install: profile source는 `/opt/videobox-yujin-profile:ro`, OAuth state는 별도 `/opt/data`; host profile이 아닌 named one-off installer container 안에서 `--force -y` 설치 후 runtime은 `-p videobox-yujin`을 명시
- A2 fail-closed verifier: exact ownership, undeclared executable, secret/API/OAuth/password/Mem0/local absolute user path, traversal·reparse point 검사
- A2 start order: `ValidateOnly`는 mutation 0, 실제 경로는 static verify → one-off container install → Yujin profile Hermes 시작 → gateway 시작
- workspace secret boundary: environment key뿐 아니라 전체 resolved value에서 gateway username/plaintext/hash가 0회인지 start/static verifier가 검사
- workspace alias semantics: 공용 helper가 key를 제외한 scalar value만 ordinal-exact 비교해 exact username/plaintext/hash alias는 거부하고 정상 substring은 허용하며 non-scalar map은 fail-closed
- alias false-positive RED/GREEN: start/static benign key·substring 각 **1 failed** → exact alias 3종 포함 각 **4 passed**; 최종 관련 gate **62 passed**
- array flatten RED/GREEN: workspace property `[]`, `[benign]`, `[a,b]`가 password verify까지 통과하던 **3 failed** → raw value 선검사로 fail-closed; 최종 관련 gate **72 passed**
- composite secret/length RED-GREEN: start password/hash prefix·suffix **4 failed**, 길이 1–11 **11 failed**, static composite **4 failed** → username exact/password·hash substring 분리와 최소 12자 강제; static 두 capture 동시 async drain; 최종 관련 gate **93 passed**
- capability authority: A1 topology/health-only gateway 배치와 issuance·signer·revocation writer·capability route 미배치를 별도 상태로 고정
- Phase 0: **2/2 완료**
- Phase A: **2/4 완료**
- production implementation: A1부터 시작
- Hermes Yujin initiative: **4/20 (20.0%), 잔여 80.0%**
- runtime/chat child: **4/6 (66.7%), 잔여 33.3%**
- creator child: **0/5**, reliability child: **0/4**, memory/final child: **0/5**
- 기존 공식 누적: **9/22 (40.9%), 잔여 59.1%**
- Task 9 사람/환경 acceptance와 실제 CapCut Desktop 실증: 별도
- A1 RED/GREEN: 서비스·파일 부재 **10 failed, 6 passed** → **16 passed**; build-context follow-up **1 failed, 16 passed** → **17 passed**
- review follow-up RED/GREEN: opt-in topology **8 failed, 10 passed** → **18 passed**; capability authority **2 failed, 3 passed** → **5 passed**
- credential RED/GREEN: malformed/resolved env **3 failed, 8 passed**; 기존 raw parser가 unresolved value를 fake Docker까지 넘겨 exit 0인 characterization RED → Compose rendered model/고정 Hermes verifier 적용 뒤 **12 passed**
- final verification: A1 focused **23 passed**, Compose/plan-state 포함 관련 gate **45 passed**, 전체 Python **1597 passed, 20 skipped**; child-process dummy env의 Compose config, A1 static verifier, plan-state verifier, `git diff --check` 통과
- quality follow-up RED: 1 MiB stderr captured/정상 start/실패 start **3 timeout**, workspace credential alias **3 fail-open**, capability 주석/static alias **2 failed**
- quality follow-up GREEN: startup/alias **6 passed**, capability 주석/static alias **2 passed**, capability authority 포함 최종 관련 gate **58 passed**; 이번 follow-up 전체 Python suite는 미실행이며 기존 **1597 passed, 20 skipped**는 직전 commit 근거
- supply-chain future: gateway `python:3.12-slim` base digest pin과 A1 전용 Python SBOM은 이번 fix 범위 밖의 비차단 후속이며 완료로 주장하지 않음
- A2 RED/GREEN: package·mount·verifier·installer·start ordering 부재 **17 failed**; 대문자 executable 우회와 install 뒤 profile 미선택 RED 2건 → A2와 기존 Yujin contract **99 passed, 1 skipped**
- A2 final verification: A1 topology/start/authority/plan 회귀 포함 **193 passed, 1 skipped**, profile/runtime/plan-state static verifier와 `git diff --check` 통과
- live service start/profile install/HTTP/OAuth/provider/chat/Mem0: real auth env 부재로 미실행

## 보호 대상

다음 경로는 기존 범위 밖이며 stage/remove/delete하지 않는다.

- `.tmp-final-fence-debug/`
- `.tmp-real-video-dogfood/`
- `apps/web/.tmp-real-video-dogfood/`

## 다음 goal

**`A3`만** 실행한다. 전용 gateway가 소유하는 최소 인증 Hermes JSON-RPC/WebSocket client와 VideoBox API의 좁은 SSE run boundary를 fake HTTP/WebSocket 기반 TDD로 구현한다. A4 RightDock live chat과 Phase B creator proposal/apply를 미리 시작하지 않는다.

## 다음 세션용 prompt

```text
VideoBox worktree에서 Hermes Yujin master plan의 A3만 실행해.
A1의 두 internal network와 provider-egress 분리, A2의 read-only profile/container-only install, gateway-only transport ownership을 유지하면서 인증 Hermes JSON-RPC/WebSocket client와 VideoBox API SSE run boundary를 strict RED-GREEN TDD로 구현해.
fake HTTP/WebSocket만 사용하고 실제 service/provider를 시작하지 말며, caller-supplied credential/tool/path/provider field를 fail-closed 해. VideoBox DB/media mount 금지와 local/test external provider call 0을 유지해.
보호된 임시 폴더 3개는 건드리지 마.
검증 뒤 A3만 [x]로 동기화하고 A4를 next goal로 남겨. A4/Phase B production task는 미리 시작하지 마.
```
