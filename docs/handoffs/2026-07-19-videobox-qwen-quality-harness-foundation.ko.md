# VideoBox 유진 provider qualification 기반 인수인계

**날짜:** 2026-07-19
**브랜치:** `codex/videobox-container-compatibility`
**상태:** local Qwen preflight와 GPT/Qwen 공통 quality-harness 기반 완료. Hermes bridge/OAuth/provider qualification은 미시작.

## 이번에 완료한 범위

- LM Studio listener를 `lms server stop` 후 `lms server start --bind 127.0.0.1 --port 1234`로 재기동했고, Windows listener는 exact `127.0.0.1:1234` 하나다.
- `packages/core-engine/src/videobox_core_engine/agent_quality_harness.py`를 추가했다. frozen case는 corpus, prompt schema, renderer identity를 가지며 JSON-compatible deep immutable data만 받는다.
- candidate는 strict `properties` allowlist 및 `additionalProperties: false` schema, grounded required claim, raw path·credential·tool·approval data gate를 모두 통과해야 한다. 통과해도 `shadow_only`, 그 외는 `needs_human_review`다.
- 결과도 corpus/prompt/renderer identity를 보존한다. harness는 provider endpoint·Hermes·DB·filesystem·routing을 호출하거나 mutate하지 않는다.
- 계획 SSOT `docs/implementation-plan.ko.md` §23.3A에 done/pending 경계를 반영했다.

## 아직 하면 안 되는 것

- Hermes가 LM Studio에 direct connect하도록 만들지 않는다. authenticated·pinned host bridge와 signer/network split이 먼저다.
- Qwen을 유진의 일반 대화·승인·tool selection 또는 fallback으로 쓰지 않는다.
- Hermes device OAuth, GPT request, external provider egress를 실행하지 않는다.
- Gemini provider call은 계속 0이어야 한다.

## 검증 증거

- RED: harness 모듈 부재에서 `ModuleNotFoundError` 확인.
- focused: `tests/test_agent_quality_harness.py` -> `7 passed`.
- related: `tests/test_agent_quality_harness.py tests/test_lm_studio_smoke_evidence.py tests/test_local_media_ai_providers.py` -> `47 passed`.
- collection: 전체 `1188 tests collected`.
- full suite: 120초 제한에서 완료하지 못했고, 더 긴 실행도 실미디어/E2E 구간에서 종료 시간 내 끝나지 않아 pass로 기록하지 않는다.
- production build: `docker build --file docker/workspace.Dockerfile --tag 65_videobox-videobox-workspace:quality-harness-verify .` 성공.
- reverse runtime: 해당 image를 `--network none --read-only`로 실행해 provider-neutral fixture가 `shadow_only`를 반환하고 identity를 전달함을 확인.
- code review/quality review: 발견된 P1을 모두 수정한 뒤 P0/P1 0.

## 다음 Goal

기존 `docs/implementation-plan.ko.md` §23만 갱신하며, **frozen Korean corpus와 metric aggregation/95% CI report를 구현**한다. 실제 GPT/Qwen provider call은 하지 않는다. 먼저 deterministic fixture corpus와 report schema의 RED tests를 만들고, schema-valid/grounded/policy-defect/사람 점수/correction time count와 qualification threshold 판정을 offline으로 구현한다. 이후 code review, plan gap, source-to-built-image reverse verification, focused/full tests와 production build를 다시 수행한다. authenticated host bridge/OAuth는 이 Goal 밖으로 유지한다.
