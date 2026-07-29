# VideoBox Hermes Yujin C1 durable conversation closeout

## 쉬운 말 요약

이제 유진 대화의 스트리밍 순서가 메모리에만 있지 않고 VideoBox DB에도 저장된다. API가 재시작돼도 완료된 답변을 마지막 cursor 다음부터 다시 읽을 수 있다. 처리 중 재시작된 대화는 provider에 몰래 다시 보내지 않고 `중단됨`과 수동 편집 fallback으로 정확히 한 번 정리한다.

연결이 끊겨도 편집 작업을 자동 취소하지 않는다. DB terminal 저장에 실패했을 때도 저장되지 않은 성공·실패 event를 지어내지 않고, 실제 저장된 내용까지만 보여 준 뒤 연결을 끝낸다.

## 실제 범위

- 기존 `director_hermes_runs`와 Director user/assistant message 재사용
- public event 네 종류만 durable 저장
  - `run_started`
  - `text_delta`
  - `blocked`
  - `run_completed`
- user/run/event begin, draft/cursor, terminal/assistant/proposal 원자 transaction
- `pending`, `streaming`, `completed`, `blocked`, `interrupted` 상태
- process restart completed/interrupted replay
- strict `Last-Event-ID` suffix와 400/404/409/410 경계
- disconnect non-cancel과 stale pending redispatch 제거
- terminal 직후 및 periodic 30일/최신 128개 payload retention
- SQLite/PostgreSQL pre-C1 terminal replay migration

## 역방향 동작

```text
API startup
→ orphan pending/streaming을 interrupted로 exactly once 정리
→ POST user + run + run_started 원자 저장
→ gateway visible draft
→ text_delta + cursor를 delivery 전에 저장
→ Last-Event-ID 이후 durable suffix 전달
→ terminal remainder + assistant/proposal + terminal event CAS
→ 반복 GET 또는 process restart replay
→ 30일/128개 밖 payload는 410 tombstone
```

## 코드리뷰·갭 검증

독립 리뷰에서 아래를 실제 RED로 재현해 수정했다.

1. terminal commit이 event list와 status 조회 사이에 끼면 terminal suffix가 빠지는 경쟁조건
2. 30일과 최신 128개 retention이 두 상한이 아니라 교집합으로만 정리되던 문제
3. draft DB commit 직후 cancel이 겹치면 durable `streaming`과 local terminal이 갈라지는 문제
4. retention이 startup에서만 실행돼 장기 실행 process에서 상한을 넘는 문제
5. terminal DB 저장 실패 뒤 가짜 local terminal과 durable active가 갈라져 SSE가 무한 대기하는 문제
6. 실제 PostgreSQL legacy backfill 자동 회귀 누락

최종 독립 spec review와 quality·gap·reverse review는 **Critical 0 / Important 0 / Minor 0, PASS**다.

## 최신 검증

- C1 focused: **92 passed**
- full Python: **2168 passed, 25 skipped**
- 실제 PostgreSQL + compatibility: **31 passed**
- targeted real-store terminal failure: **2 passed**
- full frontend: **50 files / 657 passed**
- production build: 통과
- Hermes profile/runtime/plan-state/zero-tools verifier: 통과
- Editor UI OSS provenance/UI-system verifier: 통과
- Python `py_compile`: 통과
- `git diff --check`: 통과
- 기존 Starlette multipart pending deprecation warning 1건은 비실패 출력

## 실행하지 않은 검증

- 실제 Hermes/provider 호출
- C2 browser reconnect/backoff/cancel/retry
- 사용자 원본 영상 재생·청취
- 실제 CapCut Desktop 사람 검증

## 진행률

- C1: **완료**
- Phase C: **1/4 (25.0%), 잔여 75.0%**
- realtime-reliability child: **1/4 (25.0%), 잔여 75.0%**
- Hermes Yujin initiative: **12/20 (60.0%), 잔여 40.0%**
- 기존 VideoBox 공식 누적: **9/22 (40.9%), 잔여 59.1% 유지**

## 다음 goal prompt

`C2만 진행한다. C1의 durable event cursor, completed/interrupted replay, explicit Apply 전 mutation 0, current route/session/revision fence, manual fallback과 local/test external provider call 0을 유지한다. 브라우저 SSE reconnect/backoff, cancel/retry, duplicate event suppression과 stale-run fencing을 TDD acceptance matrix와 reverse runtime trace로 먼저 고정한다. C3 capability lifecycle, C4 dashboard operations, D1-D4 Mem0는 이번 범위에서 시작하지 않는다. 독립 spec/quality/gap/reverse review, focused/full relevant suites, build, provenance, SSOT/handoff, commit/push까지 닫는다.`
