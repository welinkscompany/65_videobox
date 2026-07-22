# VideoBox Task 20 Eugene/Inspector closeout

## 완료 범위

- RightDock은 durable Director conversation/message/proposal DTO를 route epoch와 operation fence 아래에서 읽는다.
- 새 대화는 사용자 명시 행동으로만 생성하며 send/apply 중복과 Retry-After 재시도를 안전하게 처리한다.
- candidate preview는 기존 PreviewStage 단일 player로만 전달하고 explicit apply는 preflight 뒤 current revision batch endpoint를 한 번만 호출한다.
- Inspector는 BGM/SFX fade, caption, supported overlay만 노출한다. B-roll renderer control은 current manifest response가 round-trip하지 못하므로 API 확장 승인 전에는 노출하지 않는다.
- Eugene 실패/차단은 manual asset/transcript editing을 막지 않는다.

## 검증

- focused RightDock/workbench/route: 40 tests passed.
- full frontend: 52 files / 505 tests passed.
- production build, Editor UI OSS provenance verifier, git diff --check passed.
- 전체 Python regression은 실행하거나 통과로 주장하지 않았다.

## 경계와 다음 작업

- provider/API expansion, Hermes, Mem0, OpenCut runtime/source copy, automatic apply는 추가하지 않았다.
- 보호 대상 ?? .tmp-final-fence-debug/는 stage/remove하지 않았다.
- Task 9 사람/환경 acceptance와 CapCut Desktop 실증은 별도다.
- 공식 누적은 9/22 (40.9%), 잔여 59.1%다.
- next goal: Task 21 deterministic responsive/a11y/visual/performance/network gates.

