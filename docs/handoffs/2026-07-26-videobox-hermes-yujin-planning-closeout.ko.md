# VideoBox Hermes Yujin planning closeout

## 쉬운 말 요약

유진을 VideoBox에 붙이는 설계 승인이 끝났고, 실제 구현 순서를 총 20개 작업으로 고정했다. 먼저 편집기 오른쪽 대화창에서 유진과 실제 대화가 되게 만들고, 다음에 음악·효과음·B-roll·자막·TTS 등 현재 VideoBox가 지원하는 편집만 추천·선택 적용하게 한다. 연결 복구와 Mem0는 작동하는 편집 흐름 뒤에 붙인다.

## 계획 문서

- 총괄: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-master-plan.md`
- 런타임/대화: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-runtime-chat-vertical-slice.md`
- creator tools: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-creator-tools.md`
- realtime reliability: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-realtime-reliability.md`
- Mem0: `docs/superpowers/plans/2026-07-26-videobox-hermes-yujin-mem0-memory.md`

## 고정 경계

- Hermes에 직접 붙는 주체는 전용 `videobox-agent-gateway`다.
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
- production implementation: 시작 전
- Hermes Yujin initiative: **1/20 (5.0%), 잔여 95.0%**
- 기존 공식 누적: **9/22 (40.9%), 잔여 59.1%**
- Task 9 사람/환경 acceptance와 실제 CapCut Desktop 실증: 별도

## 보호 대상

다음 경로는 기존 범위 밖이며 stage/remove/delete하지 않는다.

- `.tmp-final-fence-debug/`
- `.tmp-real-video-dogfood/`
- `apps/web/.tmp-real-video-dogfood/`

## 다음 goal

`P0-2`만 시작한다. P0-1 baseline handoff를 바탕으로 RightDock 입력부터 API persistence, Hermes transport, SSE, final persistence, optional proposal, explicit apply, PreviewCoordinator, output까지 reverse runtime trace를 기록한다. master와 네 child의 정확히 20개 task ID·상태·진행률을 검사하는 verifier와 contract test를 TDD로 추가한다. production 기능 구현은 P0-2 기준선 뒤 A1부터 시작한다.

## 다음 세션용 prompt

```text
VideoBox worktree에서 Hermes Yujin master plan의 P0-2만 실행해.
P0-1 audit baseline을 읽고 RightDock부터 output까지 reverse runtime trace를 기록해.
master/children의 정확히 20개 task ID, mirror status, reported progress를 검사하는 verifier와 contract test를 TDD로 추가해.
보호된 임시 폴더 3개는 건드리지 말고, external provider call은 0으로 유지해.
검증 뒤 P0-2만 [x]로 동기화하고 A1을 next goal로 남겨. production task는 미리 시작하지 마.
```
