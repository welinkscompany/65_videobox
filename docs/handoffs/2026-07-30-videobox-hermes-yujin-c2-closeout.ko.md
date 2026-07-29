# VideoBox Hermes Yujin C2 realtime recovery closeout

## 쉬운 말 요약

유진 답변 도중 잠깐 연결이 끊겨도 같은 실행의 저장된 다음 부분부터 제한된 횟수만 다시 연결한다. 이미 받은 문장은 중복해서 붙이지 않는다. 사용자가 중단을 누르면 실제 Hermes session interrupt와 VideoBox DB의 `interrupted` 상태가 한 번만 기록된다.

오른쪽 유진 창을 닫아도 답변 작업은 계속된다. 반대로 다른 프로젝트로 이동하거나 편집 화면을 떠나면 그 화면이 소유한 실행만 정확히 한 번 취소한다. 연결을 끝내 복구하지 못해도 수동 편집과 기존 실행 중단은 남고, 새 유진 요청이나 예전 Director 분석을 겹쳐 시작하지 않는다.

## 실제 범위

- 최초 open을 포함한 SSE reconnect와 `100/250/500ms` backoff
- durable `Last-Event-ID` replay와 duplicate event suppression
- route-owned run cancel, Dock close non-cancel, terminal/explicit-cancel ownership release
- official Hermes `session.interrupt`
- cancel race의 public terminal 1회와 durable `interrupted`
- blocked/interrupted source만 허용하는 explicit linked retry
- exact project/conversation/session revision/asset-index/segment identity CAS
- prompt acceptance 전 exact expired ticket 한 번만 갱신
- stable public failure code와 내부 오류 비노출
- SQLite/PostgreSQL `retry_of_run_id`와 durable `message_order` migration
- 동일 timestamp user/assistant 순서와 exact idempotent replay
- stale route/Director operation/conversation/revision message·proposal publication 차단

## 역방향 동작

```text
RightDock send
→ route-owned run handle
→ VideoBox run/user/run_started 원자 저장
→ Agent Gateway ticket + Hermes session + prompt acceptance
→ public delta를 durable cursor 뒤에 저장
→ browser Last-Event-ID suffix reconnect + duplicate suppression
→ terminal/assistant/proposal 원자 CAS
→ 일치하는 run handle만 해제

명시적 cancel
→ scoped VideoBox cancel endpoint
→ concurrent call single owner
→ Agent Gateway official session.interrupt 1회
→ public blocked terminal 최대 1회
→ durable interrupted 1회

명시적 Retry
→ blocked/interrupted source와 exact scope/identity 재검증
→ 새 user/run/run_started 원자 저장
→ retry_of_run_id로 이전 run 연결
```

## 코드리뷰·갭 검증

독립 spec review와 독립 quality·gap·reverse review에서 아래를 실제 RED로 재현해 수정했다.

1. route 이동·unmount가 브라우저 구독만 끊고 upstream 실행을 취소하지 않던 문제
2. 최초 SSE open이 reconnect helper 밖에 있어 첫 연결 실패를 복구하지 못하던 문제
3. reconnect 소진 뒤 실행 소유권을 버리거나 새 요청·legacy 분석을 겹쳐 시작하던 문제
4. same-route Director operation/revision 변경 뒤 늦은 terminal이 handle을 남기던 문제
5. `session.create`와 prompt acceptance 전 ticket 만료 분류·재발급 경계
6. cancel과 즉시 upstream blocked terminal 경쟁에서 durable status가 blocked로 오염되던 문제
7. 실제 PostgreSQL에서 SQLite 전용 `rowid` 정렬이 실패하던 문제
8. 같은 timestamp의 여러 수동 대화가 user/user/assistant/assistant로 재정렬되던 문제
9. 부분 답변 뒤 영문 기술 오류가 일반 UI에 남던 문제

최종 판정은 **Critical 0 / Important 0 / Minor 0, PASS**다.

## 최신 검증

- C2 focused Python: **194 passed**
- C2 focused frontend: **2 files / 137 passed**
- full Python: **2192 passed, 29 skipped**
- real PostgreSQL store: **23 passed**
- full frontend: **50 files / 668 passed**
- production build: 통과
- Hermes profile/runtime/plan-state/zero-tools verifier: 통과
- Editor UI OSS provenance/UI-system verifier: 통과
- Python `py_compile`: 통과
- `git diff --check`: 통과
- 기존 Starlette warning, React `act(...)`, jsdom navigation, intentional ErrorBoundary stderr와 500kB bundle warning은 비실패 출력

## 실행하지 않은 검증

- 실제 Hermes/provider 호출
- 브라우저 사람 E2E와 실제 service-stop drill
- 사용자 원본 영상 재생·청취
- 실제 CapCut Desktop 사람 검증
- C3 capability, C4 dashboard, D1–D4 Mem0

## 진행률

- C2: **완료**
- Phase C: **2/4 (50.0%), 잔여 50.0%**
- realtime-reliability child: **2/4 (50.0%), 잔여 50.0%**
- Hermes Yujin initiative: **13/20 (65.0%), 잔여 35.0%**
- 기존 VideoBox 공식 누적: **9/22 (40.9%), 잔여 59.1% 유지**

## 다음 goal prompt

`C3만 진행한다. 먼저 현재 Editor/API→Agent Gateway attach/stream topology, 기존 capability signer/verifier/ledger, cancel/retry terminal transaction을 다시 읽고 source-grounded C3 plan amendment를 확정한다. 한 capability는 read_context 또는 publish_proposal 중 정확히 한 action만 허용하고, issue/consume/replay/revoke와 redacted audit를 durable하게 검증한다. 임의 gateway→API callback, apply/render/export/DB/filesystem/raw-media capability, source copy, OpenCut runtime, provider/API 확대, Mem0, 자동 apply는 추가하지 않는다. explicit Apply 전 mutation 0, current route/session/revision fence, manual fallback, local/test external provider call 0을 유지한다. TDD acceptance matrix와 reverse runtime trace 뒤 독립 spec/quality/gap/reverse review, focused/full relevant suites, build, provenance, SSOT/handoff, commit/push까지 닫는다.`
