# VideoBox Hermes Yujin Phase D closeout handoff

작성일: 2026-07-30

worktree: `videobox-container-compatibility`

상태: D4와 Phase D 기술 closeout 완료

F1 후속 상태: gap remediation 및 독립 재검토 완료, 최종 기술 closeout

## 결론

D4의 production producer, approved+stored retrieval, bounded creator-context
injection, 장애 fallback, 비-Live smoke를 구현했다. 독립
spec/quality/gap/reverse review는 `Critical 0 / Important 0 / Minor 0`으로
통과해 D4와 Phase D 기술 범위를 완료했다. 실제 Mem0 live
add/search/delete canary는 별도 환경·자격증명·명시 승인이 없어 실행하지
않았다.

## 구현된 경계

- 현재 RightDock의 명시적 `기억 후보 만들기`만 기존 candidate POST를
  호출한다. 입력은 현재 owned conversation의 완료 durable message ID
  1–8개와 정책 category, scope, 280자 이하 candidate다.
- page load, run/provider 완료, approve, store, retry는 자동 candidate
  create/approve/store를 하지 않는다. late route/project/conversation/epoch
  결과는 현재 conversation 목록을 갱신하지 않는다.
- 새 owned durable dispatch 이후에만 prompt당 최대 한 번, top 5, 750ms로
  검색한다. 전체 원문 prompt가 unsafe하거나 exact create action이면
  검색하지 않는다.
- provider 결과는 현재 project+conversation의 local approved+stored
  private mapping과 exact 대조한다. ID 없는
  `user_approved_preference`만 최대 5개·총 1,400자로 주입하고 48KiB
  context 예산 초과 시 memory를 먼저 버린다.
- malformed, oversize, duplicate, unrelated, non-approved/non-stored,
  timeout, outage는 제외하거나 `memories=()`로 수렴한다. 자동
  writeback/apply/store는 없고 chat/manual editor fallback을 유지한다.

## RED→GREEN 증거

- backend retrieval 최초 RED: missing helper/context로 `5 failed`
- frontend producer 최초 RED: `4 failed, 169 passed`
- 전체 원문 unsafe tail RED: secret/path/URL/bearer 네 경우에서 search가
  호출됨
- focused backend memory: `149 passed, 1 warning`
- 직접 영향 creator-context/Gateway/Hermes/API: `188 passed, 1 warning`
- focused frontend API/RightDock/Route: `3 files, 173 passed`
- 전체 frontend: `52 files, 724 passed`
- disposable PostgreSQL 16 retrieval-row SQLite parity: `1 passed, 1 warning`;
  exact container `videobox-d4-retrieval-parity-20260730` 삭제와 부재 확인
- production frontend build: success
- default smoke:
  `HERMES_YUJIN_MEM0_NON_LIVE network_calls=0 provider_calls=0 credentials_printed=false`

warning 1건은 기존 Starlette multipart PendingDeprecationWarning이다.

- independent spec/quality/gap/reverse review:
  `Critical 0 / Important 0 / Minor 0`, PASS
- Hermes Yujin plan-state verifier와 `git diff --check`: PASS

## F1 gap remediation final closeout (2026-07-30)

- completed-run authority: 같은 project+conversation의 completed Hermes
  run이 소유한 user/assistant message만 memory candidate source로 허용한다.
  pending/streaming/blocked/interrupted/legacy source는 candidate와 audit 전에
  거부한다.
- Route list supersession: post-create refresh가 이전 initial list보다 새
  operation을 소유하므로 역순 완료가 candidate/action/draft/scroll을
  지우지 못한다.
- SQLite migration concurrency: exact duplicate-column race만 schema
  재확인 뒤 성공으로 수렴하고 다른 오류는 삼키지 않는다.
- API fixture는 TestClient의 50ms orphan recovery와 경쟁하는 synthetic
  `begin -> complete` 창을 제거하고 원하는 durable authority row를 직접
  seed한다. current-conversation-before-limit aggregate는 즉시 recovery가
  회수할 pending run이 없다는 것도 확인한다.
- 현재 GREEN: F1 focused backend `920 passed, 1 skipped`, frontend
  API/RightDock/panel/Route `4 files / 183 passed`, backend memory store/API
  `52 passed`, memory store/service/retrieval/API aggregate `81 passed`, API
  전체 `14 passed`를 `5/5` 반복, current-conversation-before-limit
  `20/20`, Route `117 passed`, SQLite migration file `3 passed`, exact D2
  race `10/10`, disposable PostgreSQL 16 Yujin-memory parity `6 passed`. 전용 container
  `videobox-f1-source-authority-20260730`은 삭제와 부재를 확인했다.
- 독립 spec/quality/gap/reverse 재검토는 `C0/I0/M0 PASS`다. 최종
  mandatory gate는 focused backend `920 passed, 1 skipped`, 전체 Python
  `2640 passed, 47 skipped`, 전체 frontend `52 files / 725 passed`,
  자동 editor E2E `35/35`, build/provenance/UI/runtime/profile/plan/network,
  SBOM과 PostgreSQL parity까지 통과했다. 상세 근거는 final handoff를
  따른다.

## 리뷰 시 우선 확인할 항목

1. 완료 durable message ID 판정과 late Route epoch fence가 소유권 변경을
   넘지 않는지 확인한다.
2. 검색 admission이 new owned durable dispatch 뒤에만 있고 replay,
   unsafe full prompt, exact create action에서 provider search `0`인지
   확인한다.
3. provider/local exact cross-check가 다른 상태·conversation·malformed
   record를 한 건도 context에 넣지 않는지 확인한다.
4. 750ms timeout/outage 뒤에도 provider run과 수동 편집 fallback이
   계속되는지 확인한다.
5. smoke의 live 분기가 명시적 `-Live -ApproveDisposableAdd`와 disposable
   add 승인 없이는 네트워크를 사용하지 않고 credential/raw body를
   출력하지 않는지 확인한다.

## 미실행·다음 단계

- 실제 Mem0/provider add/search/delete 및 삭제 후 부재 확인: 미실행
- 브라우저 사람 E2E, 사용자 원본 미디어·CapCut 사람 검증: 미실행
- commit/push: 이 handoff 작성 시점에는 미실행

현재 authoritative 진행률은 Phase D `4/4 (100.0%)`, Mem0 child
`5/5 (100.0%)`, Hermes Yujin `20/20 (100.0%)`, 잔여 `0.0%`다. 별도
환경과 권한이 있을 때만 live canary를 `-Live -ApproveDisposableAdd`로
실행한다. 기존 VideoBox 공식 누적은 `9/22 (40.9%)`, 잔여 `59.1%`로
유지한다.
