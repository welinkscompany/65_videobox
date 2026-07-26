# VideoBox Hermes Yujin B1 creator context closeout

## 쉬운 말 요약

B1은 유진이 현재 열려 있는 VideoBox 프로젝트를 안전하게 이해할 수 있도록 만든 단계다. 유진에게 전체 DB나 원본 파일을 주지 않고, 현재 revision의 장면 요약, 프로젝트 미디어 후보, 타임라인 정보와 실제로 지원되는 편집 종류만 제한된 JSON으로 전달한다.

이 단계에서 유진은 설명과 추천만 할 수 있다. 편집을 자동 적용하지 않으며 typed proposal과 Apply 버튼은 다음 단계 이후의 별도 권한이다. 유진이나 gateway가 실패해도 기존 수동 Director와 편집기는 그대로 사용할 수 있다.

## 작업 위치와 기준

- worktree: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility`
- branch/upstream: `codex/videobox-container-compatibility` / `origin/codex/videobox-container-compatibility`
- B1 시작 HEAD: `a21acfcfe138fb2877e9f4ce171401c03cdaaff5`
- 보호된 기존 untracked 세 경로는 열거나 stage/remove/delete하지 않았다.
  - `.tmp-final-fence-debug/`
  - `.tmp-real-video-dogfood/`
  - `apps/web/.tmp-real-video-dogfood/`

## 실제 구현 범위

- strict `videobox.yujin-context.v1` DTO와 backend-only builder
  - session revision과 asset-index revision을 따로 보존한다.
  - current playback, 선택 세그먼트 membership, 수집 전후 revision을 검사한다.
  - 세그먼트 32개, 미디어 48개, text/tag byte 한도와 canonical JSON 48,000-byte 한도를 적용한다.
  - host path, URL/storage URI, raw media, credential, OAuth, Mem0 raw record를 허용하지 않는다.
- authenticated gateway reservation/attach/stream
  - raw attach ticket 30초, attached context 300초, ledger 64개 한도다.
  - ticket은 digest로 비교하고 attach와 stream은 각각 한 번만 허용한다.
  - idempotent DELETE로 실패·취소된 reservation을 정리한다.
  - 과거 context-free internal stream 우회 경로를 제거했다.
- prompt/data 경계
  - 고정 trusted instruction과 escaped `untrusted_creator_context` JSON data block을 분리한다.
  - data 내부 instruction은 따르지 않고 tool·credential 요청을 금지한다.
- durable run identity와 복구
  - session revision, asset-index revision, 선택 세그먼트를 run identity에 저장한다.
  - owner-token CAS와 300초 stale pending reclaim을 사용한다.
  - live pending은 중복 dispatch 없이 in-progress 503으로 닫는다.
  - legacy terminal은 그대로 replay하고 legacy pending은 원자적으로 blocked/manual fallback으로 바꾼다.
  - 동시 CAS 패자는 winner row와 assistant를 다시 읽어 두 번째 assistant를 만들지 않는다.
- frontend request fence
  - RightDock run 요청에 현재 expected session revision과 선택 세그먼트를 보낸다.
  - route-owned draft/history/player/manual editor 경계는 유지한다.
- cleanup 순서
  - prepare 취소 시 생성된 gateway reservation을 shield된 정리 요청으로 반환한다.
  - durable terminal과 SSE terminal을 먼저 전달하고 gateway release는 별도 1초 제한 cleanup으로 수행한다.

## TDD와 독립 검토

- strict DTO/크기/금지 필드, current playback, revision TOCTOU, external call 0을 테스트했다.
- gateway reservation/attach/stream/release/TTL/capacity/replay/concurrency를 테스트했다.
- API idempotency, stale fence, legacy migration, restart reclaim과 frontend expected revision 전달을 테스트했다.
- 독립 spec review에서 durable CAS, byte validator, TypeScript build 문제를 찾고 보완했다.
- 독립 품질·gap·reverse review에서 attached TTL, orphan pending, prompt 경계, legacy replay를 보완했다.
- 최종 재검토에서 PostgreSQL CAS 패자 중복 assistant, prepare cancellation cleanup, 느린 release의 terminal 지연을 찾아 RED→GREEN으로 닫았다.
- 최종 독립 판정은 Critical 0, Important 0, Minor 0 PASS다.

## 최신 검증

- focused Python: **148 passed**, warning 1건
- focused frontend: **2 files / 95 tests passed**
- production build: 통과
- Editor UI OSS provenance verifier: 통과
- Hermes zero-tool verifier: 통과
- Hermes plan-state verifier: 20개 master/child task ID와 상태·진행률 일치
- `git diff --check`: 통과

warning 1건은 기존 Starlette multipart pending deprecation이다. production build의 500 kB chunk warning도 기존 비실패 출력이다.

## 실행하지 않은 검증

- 전체 Python regression
- 전체 frontend suite
- live provider canary
- 실제 Hermes service-stop/manual environment proof
- 실제 PostgreSQL/Docker 동시성 실증

위 항목은 실행하지 않았으며 통과로 주장하지 않는다. B1 focused PostgreSQL 호환 CAS 테스트는 live DB 증거가 아니다.

## 진행률

- B1: **완료**
- Phase B: **1/5 (20.0%)**
- creator-tools child: **1/5 (20.0%), 잔여 80.0%**
- Hermes Yujin initiative: **7/20 (35.0%), 잔여 65.0%**
- 기존 VideoBox 공식 누적: **9/22 (40.9%), 잔여 59.1% 유지**

Task 9 사람/환경 acceptance와 CapCut Desktop 실증은 별도다.

## 다음 goal prompt

`B2만 진행한다. Yujin creator skill과 typed recommendation/proposal response envelope를 TDD로 추가하고, 현재 revision과 실제 supported-control matrix를 벗어난 proposal은 거부한다. 유효한 proposal은 기존 Director candidate DTO로만 투영하며 mutation/apply, OpenCut runtime/source copy, provider/API 확대, Mem0, SaaS는 시작하지 않는다. 독립 spec/quality/gap/reverse review 뒤 focused 검증과 계획 상태를 갱신한다.`
