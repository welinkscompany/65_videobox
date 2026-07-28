# VideoBox Hermes Yujin Phase B creator flow closeout

## 쉬운 말 요약

이제 유진이 현재 편집 상태를 보고 VideoBox가 실제로 지원하는 B-roll, 배경음악, 효과음, 자막, 승인된 TTS, 설명·이미지·표 오버레이를 추천할 수 있다. 추천이 보이거나 radio를 고르는 것만으로 영상은 바뀌지 않는다. 사용자가 Apply를 눌렀을 때만 최신 편집본인지 다시 확인하고 기존 편집 명령 하나를 실행한다.

유진이 멈추거나 잘못된 후보를 보내도 기존 수동 편집기는 계속 쓸 수 있다. 대화창을 닫았다 열어도 대화, 입력 초안, 선택 후보, 스크롤과 재생 상태가 남고, 영상 player는 기존 PreviewStage 하나만 사용한다.

## 작업 위치와 기준

- worktree: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility`
- branch/upstream: `codex/videobox-container-compatibility` / `origin/codex/videobox-container-compatibility`
- 시작 HEAD: `fa3feeef22784c1fabf452843c2cd0cb8c961926`
- 기존 untracked 세 경로는 열거나 stage/remove/delete하지 않았다.

## 실제 범위

- B4 보완
  - caption Y 0..100과 safe-area 활성 시 Y=94 clamp
  - table column/row/cell 길이·개수·UTF-8 byte 제한
  - image proposal/candidate/asset/revision/SHA의 server-side terminal attestation
  - apply/batch/image terminal transaction의 SQLite/PostgreSQL 공통 CAS·lock order
  - exact candidate identity를 유지한 canonical whitespace 저장
- B5 creator checkpoint
  - persistent Hermes conversation에서 연결된 typed candidate 표시
  - explicit radio/Apply 전 mutation 0
  - Apply 뒤 typed command 정확히 1회와 revision/session/manifest refresh
  - forged candidate와 Hermes unavailable의 mutation 0·manual fallback
  - Inspector close/open conversation/draft/selection/scroll/player 보존
  - sole PreviewStage ownership과 Outputs read-only reverse path
- creator smoke
  - fake typed Hermes + real local VideoBox create_app/LocalProjectStore
  - conversation/run/SSE/proposal/preflight/caption apply/playback manifest/output readiness
  - output job 0, external provider call 0
  - 별도 Live 경로는 이중 승인, loopback, disposable root/sample copy, source SHA 보존
  - 첫 POST 전과 Apply 전후에 supplied root session JSON과 API exact session을 대조하며 mismatch면 POST 0

## 코드리뷰·갭·역방향 검증

최초 검토에서 아래 문제를 실제 테스트로 재현하고 수정했다.

1. caption safe-area와 table bounds 계약 누락
2. Yujin image Apply의 persisted candidate server binding 누락
3. terminal attestation과 editing-session CAS의 transaction race
4. PostgreSQL proposal/asset/session truth 직렬화 잠금 부족
5. candidate text canonical whitespace 불일치
6. Live smoke가 이름이 같은 다른 loopback 프로젝트에 쓰기 가능한 root/session binding gap

최종 독립 spec review와 quality·gap·reverse review는 **Critical 0 / Important 0 / Minor 0, READY**다.

역방향 흐름은 아래와 같다.

```text
current revision creator context
→ typed Hermes response
→ strict gateway/proposal validation
→ linked persisted candidate
→ Inspector display and selection, mutation 0
→ explicit Apply
→ preflight + route/director epoch + current revision fence
→ exactly one EditorCommandPort mutation
→ refreshed session/playback manifest
→ sole PreviewStage
→ existing output readiness/route, output mutation 0
```

## 최신 검증

- focused frontend: **7 files / 236 passed**
- full frontend: **50 files / 657 passed**
- editor Playwright E2E: **9 passed**
- production build: 통과
- focused creator smoke: **5 passed**
- direct non-live creator smoke: 통과
  - `session_file_bound=true`
  - `mutation_before_apply=0`
  - `session_revision_delta=1`
  - `caption_changes=1`
  - `output_jobs=0`
  - `external_provider_calls=0`
- full Python regression: **2139 passed, 21 skipped**, warning 1건
- Hermes profile/runtime/20-ID plan-state/zero-tools verifier: 통과
- Editor UI OSS provenance/UI-system verifier: 통과
- `git diff --check`: 통과

warning 1건은 기존 Starlette multipart pending deprecation이다. frontend의 React `act(...)`, jsdom navigation, intentional ErrorBoundary stderr와 production build의 500 kB chunk warning은 exit 0인 기존 비실패 출력이다.

## 실행하지 않은 검증

- 실제 `-Live` creator smoke happy path
- live Hermes/provider 호출
- 실제 PostgreSQL 동시성 integration
- Docker 환경 실증
- 사용자 원본 영상 재생·청취
- 실제 CapCut Desktop 사람 검증

복잡한 non-empty timeline placement override/output freshness를 API가 정확히 노출하지 않는 세션은 Live smoke가 안전하게 차단한다. Task 9 사람/환경 acceptance와 CapCut 실증은 이번 자동 검증으로 대체하지 않는다.

## 진행률

- B5: **완료**
- Phase B: **5/5 (100.0%)**
- creator-tools child: **5/5 (100.0%)**
- Hermes Yujin initiative: **11/20 (55.0%), 잔여 45.0%**
- 기존 VideoBox 공식 누적: **9/22 (40.9%), 잔여 59.1% 유지**

## 다음 goal prompt

`C1만 진행한다. Phase B의 explicit Apply 전 mutation 0, route/director epoch와 current revision fence, sole PreviewStage, manual fallback, local/test external provider call 0을 유지한다. durable run/event cursor를 저장하고 브라우저 reload·RightDock close/open·API process restart 뒤 final 또는 interrupted conversation state를 정확히 복구하는 TDD acceptance matrix와 reverse runtime trace를 먼저 고정한다. duplicate terminal/assistant 생성과 stale session/run 연결을 fail-closed로 막는다. C2 reconnect/cancel/retry 전체, C3 capability lifecycle, C4 dashboard operations, D1–D4 Mem0는 이번 범위에서 시작하지 않는다. 독립 spec/quality/gap/reverse review, focused/full relevant suites, build, provenance, SSOT/handoff, commit/push까지 닫는다.`
