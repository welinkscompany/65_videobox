# VideoBox offline provider qualification report 인수인계

**날짜:** 2026-07-19
**브랜치:** `codex/videobox-container-compatibility`
**상태:** fixed Korean shadow corpus와 offline metric/CI report 기반 완료. 실제 provider 비교·OAuth·bridge는 미시작.

## 완료 범위

- `korean_shadow_evaluation_v1.json`은 sanitised 한국어 3 case만 담고, 외부 Python version constant의 SHA-256까지 맞아야 로드된다. JSON 내부 digest와 payload를 같이 바꾸어도 거부된다.
- report는 caller가 만든 `CandidateEvaluation` flag를 받지 않는다. exact frozen case와 captured `CandidateResult`를 받은 뒤 내부 validator를 다시 실행한다.
- object/array/string/number/integer/boolean/null의 제한된 JSON schema subset만 지원하고, 모르는 keyword/type은 fail-closed다. input·response schema·candidate output의 raw path, credential, tool, approval data도 거부한다.
- report는 schema-valid/grounded/critical defect, paired human-score delta, correction-time delta, Wilson/paired 95% CI, point thresholds를 기록한다. `thresholds_passed`가 true여도 `route_state`는 항상 `needs_human_review`다.
- 이 module은 provider endpoint, Hermes, DB, filesystem mutation, router를 호출하지 않는다.

## 검증

- TDD RED: report API import 부재를 확인한 뒤 구현했다.
- focused: harness + LM Studio evidence/local provider 관련 `56 passed`.
- 전체 suite: `1197 tests collected`; 장기 E2E 구간이 idle 상태로 완료하지 않아 종료했고 full-pass로 기록하지 않는다.
- production build: `docker build --file docker/workspace.Dockerfile --tag 65_videobox-videobox-workspace:quality-report-verify .` 성공.
- reverse: 그 image를 `--network none --read-only`로 실행해 fixture digest loader와 3-case corpus load를 확인했다.
- review: spec review와 code-quality review 모두 P0/P1 0.

## 다음 Goal

기존 §23만 사용해, **captured provider evidence import contract와 immutable audit report persistence**를 설계/구현한다. 단, Hermes host bridge, GPT OAuth, 실제 GPT/Qwen 호출은 시작하지 않는다. 먼저 provider capture를 어떤 파일/ledger 형식으로 허용할지와 사람 score attestation bind를 TDD로 고정하고, real provider output 없이 synthetic capture fixture만 import한다.
