# VideoBox offline provider evidence ledger 인수인계

**날짜:** 2026-07-19
**브랜치:** `codex/videobox-container-compatibility`
**상태:** synthetic capture import와 tamper-evident audit persistence 기반 완료. 실제 provider capture/OAuth/bridge는 미시작.

## 완료 범위

- `provider_qualification_evidence.py`는 현재 checked-in Korean corpus의 external SHA-256, exact case identity, provider/runtime/model, canonical candidate payload SHA-256, opaque human attestation을 같이 확인한다.
- import는 raw media/path, credential, tool, approval 데이터를 거부한다. capture ID와 attestation ID replay도 ledger append에서 거부한다.
- ledger는 canonical JSON record hash와 previous-record hash로 순서·내용 변조를 검출하고, write lock과 atomic replace로 cooperating writer의 read-verify-write 손실을 막는다.
- audit artifact는 write-once이며 ordered record snapshot과 canonical report를 다시 계산한다. 정상적인 이후 append는 과거 audit을 무효화하지 않지만, **그 audit snapshot이 참조한** record/report의 변조·누락·순서 변경은 거부한다.
- 이는 application-contract 수준의 tamper-evident persistence다. signing key나 external anchor가 없으므로 OS/adversary-proof immutable storage라고 주장하지 않는다.
- 모든 persisted report는 `needs_human_review`이며 route를 활성화하지 않는다.

## 검증

- TDD RED: module import 부재, attestation replay, corpus SHA 누락/불일치, unsafe field family/path, historical snapshot, report scalar type-spoof를 각각 먼저 재현했다.
- focused: `tests/test_provider_qualification_evidence.py` `28 passed`.
- 통합 focused: harness/LM Studio/local provider 포함 `84 passed` (기존 Starlette multipart PendingDeprecationWarning 1건).
- independent spec review와 code-quality review: P0/P1/P2 0.
- `git diff --check` 통과.
- full Python suite는 `1225 tests collected`까지 확인했지만 `pytest -q` 재실행이 124초 동안 출력 없이 timeout되어 full-pass로 기록하지 않는다.
- production build와 `--network none --read-only` container 역방향 검증에서 pinned 3-case corpus와 ledger module import를 확인했다.

## 다음 Goal

기존 `docs/implementation-plan.ko.md` §23 범위 안에서 **실제 provider 호출을 시작하지 않고**, owner-authorized evidence intake의 consent/budget/gateway preflight contract를 먼저 설계한다. capture import가 허용하는 sanitized artifact와 금지 데이터, owner audit, 실패 시 side effect 0을 TDD로 고정한다. Hermes host bridge, GPT OAuth, 실제 GPT/Qwen/Gemini call, DB/API route activation은 이 다음 gate 전까지 시작하지 않는다.
