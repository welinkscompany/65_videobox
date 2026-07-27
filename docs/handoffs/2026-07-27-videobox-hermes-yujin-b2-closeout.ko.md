# VideoBox Hermes Yujin B2 typed creator proposal closeout

## 쉬운 말 요약

B2는 유진의 추천을 바로 편집 명령으로 실행하지 않고, 먼저 안전한 “편집 후보 카드”로 만드는 단계다. 유진이 보내는 응답이 VideoBox가 실제 지원하는 B-roll, BGM, 효과음, 자막, 음성, 오버레이, 출력 확인 계약과 정확히 맞을 때만 기존 Director 후보로 저장한다.

후보는 아직 읽기 전용이다. 화면 버튼을 숨기는 데 그치지 않고 서버의 미리보기·재료 준비·적용 API도 `candidate_only`를 거부한다. 유진이 잘못된 JSON, 경로, URL, 비밀키나 credential을 섞어 보내거나 현재 revision이 바뀌면 후보를 버리고 수동 편집 fallback을 남긴다.

## 작업 위치와 기준

- worktree: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility`
- branch/upstream: `codex/videobox-container-compatibility` / `origin/codex/videobox-container-compatibility`
- B2 시작 HEAD: `a649e4c427ae39f2c53461e7d6420b9a176ade0e`
- 보호된 기존 untracked 세 경로는 열거나 stage/remove/delete하지 않았다.
  - `.tmp-final-fence-debug/`
  - `.tmp-real-video-dogfood/`
  - `apps/web/.tmp-real-video-dogfood/`

## 실제 구현 범위

- `videobox-creator` skill과 strict typed response
  - exact trailing `videobox-yujin-response` fence
  - operation 최대 16개
  - `broll/bgm/sfx/caption/voice/overlay/output_check` 7종
  - kind별 exact target, track, control mode, parameter와 current base token
  - 모델 ID 대신 trusted project/run hash 기반 proposal/candidate ID
- 안전한 live conversation
  - visible prefix를 owner-fenced `assistant_draft_text` CAS로 먼저 저장한 뒤 SSE 공개
  - terminal 전 event count·serialized-byte 예산 확인
  - 완료·차단·취소·timeout의 DB assistant, delta 합계, terminal text 일치
  - terminal CAS에서 proposal, assistant link, draft clear를 원자 처리
- 기존 Director DTO 재사용
  - 새 frontend protocol을 만들지 않고 `DirectorProposal`/`DirectorCandidate`에 투영
  - 정확한 terminal `hermes_run_id`가 연결한 proposal만 reload
  - proposal 없는 새 답은 과거 candidate/selection을 제거
- 실행 권한 차단
  - `candidate_only`는 RightDock에서 읽기 전용 표시
  - preview/materialize/apply control 0
  - REST preflight·preview·materialize·apply·batch-apply도 mutation 전 `409 proposal_not_ready`
- fail-closed와 manual fallback
  - malformed JSON/fence/assignment, CRLF와 모든 chunk split의 raw machine bytes 차단
  - embedded URI·host path·UNC·credential·private key·JWT 차단
  - current context 변경과 proposal ID collision 시 proposal 폐기
  - Eugene 실패 시 기존 manual Director/editor 유지

## TDD와 독립 검토

- RED에서 실시간 delta 퇴행, terminal byte-cap 우회, cross-kind identifier smuggling, terminal 후 proposal 미표시, 불완전 skill schema를 재현했다.
- 후속 독립 리뷰에서 candidate-only REST 우회, event-budget DB/SSE 불일치, 취소·timeout terminal 불일치, 과거 proposal 부활, malformed credential/embedded URL 누출을 추가로 재현했다.
- 각 결함은 회귀 테스트를 먼저 추가한 뒤 최소 수정했고, 최종 독립 spec review와 quality·gap·reverse review는 Critical 0, Important 0, Minor 0 PASS다.
- 역방향 흐름은 `RightDock send → Hermes API run → gateway chunks → durable draft CAS → safe SSE → typed parser/current-context recheck → candidate_only proposal terminal CAS → exact run proposal reload → read-only candidate/manual fallback`으로 확인했다.

## controller 최신 검증

- focused Python: **291 passed, 1 skipped**, warning 1건
- focused frontend: **3 files / 104 tests passed**
- production build: 통과
- Hermes Yujin profile verifier: 통과
- Hermes Yujin 20-ID plan-state verifier: 통과
- Hermes Yujin zero-tools verifier: 통과
- Editor UI OSS provenance verifier: 통과
- `git diff --check`: 통과

warning 1건은 기존 Starlette multipart pending deprecation이다. production build의 500 kB chunk warning도 기존 비실패 출력이다.

## 실행하지 않은 검증

- 전체 Python regression
- 전체 frontend suite
- live provider canary
- 실제 Hermes service-stop/manual environment proof
- 실제 PostgreSQL/Docker integration

관련 확장 검증에서 PostgreSQL integration 13건은 `VIDEOBOX_TEST_POSTGRES_URL` 미설정으로 skip됐고, 별도 1건은 현재 Windows 계정의 symlink 생성 권한 제한이다. 호환 SQL·migration 테스트는 live PostgreSQL 증거를 대체하지 않는다.

## 진행률

- B2: **완료**
- Phase B: **2/5 (40.0%)**
- creator-tools child: **2/5 (40.0%), 잔여 60.0%**
- Hermes Yujin initiative: **8/20 (40.0%), 잔여 60.0%**
- 기존 VideoBox 공식 누적: **9/22 (40.9%), 잔여 59.1% 유지**

Task 9 사람/환경 acceptance와 실제 CapCut Desktop 실증은 별도다.

## 다음 goal prompt

`B3만 진행한다. B2의 candidate-only proposal을 기존 Director Inspector에 연결하고, 사용자에게 recommendation과 세부 candidate를 보여 주되 명시적 Apply 전 mutation 0을 유지한다. current session revision, route epoch, exact proposal status, one-player PreviewStage, manual fallback을 다시 확인한다. 자동 apply, OpenCut runtime/source copy, provider/API 확대, Mem0, SaaS는 시작하지 않는다. RED→GREEN 뒤 독립 spec/quality/gap/reverse review와 focused backend/frontend/build/static verifier를 통과시키고 계획 상태를 갱신한다.`
