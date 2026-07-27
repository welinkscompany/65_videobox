# VideoBox Hermes Yujin B3 media recommendation/apply closeout

## 쉬운 말 요약

B3에서는 유진이 추천한 B-roll 영상, 배경 음악, 효과음을 Inspector에서 확인하고 사용자가 직접 하나를 고른 뒤 적용할 수 있게 했다.

추천이 화면에 나타나는 것만으로는 편집이 바뀌지 않는다. 사용자가 radio로 후보를 선택하고 적용 버튼을 눌러야 하며, 파일 준비가 끝난 뒤에도 같은 프로젝트 화면과 같은 편집본인지 다시 확인한다. 조건이 맞을 때만 기존 VideoBox 편집 명령으로 한 번 적용한다.

유진이 멈추거나 추천이 오래됐거나 파일 종류가 위조·변경되면 추천 적용을 중단하고 수동 편집을 계속할 수 있다. 이미지 B-roll, 미지원 효과, 자동 적용은 열지 않았다.

## 작업 위치와 기준

- worktree: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility`
- branch/upstream: `codex/videobox-container-compatibility` / `origin/codex/videobox-container-compatibility`
- B3 시작 HEAD: `0a55c23aa5de791525bc3ea0d0b00407b97d1fa6`
- 아래 기존 untracked 경로는 열거나 stage/remove/delete하지 않았다.
  - `.tmp-final-fence-debug/`
  - `.tmp-real-video-dogfood/`
  - `apps/web/.tmp-real-video-dogfood/`

## 실제 구현 범위

- actionable media attestation
  - B-roll은 실제 `raw_video` 또는 `broll_video`만 허용
  - BGM은 실제 `bgm`, SFX는 실제 `sfx`만 허용
  - 추천이 주장한 source kind와 현재 DB asset type을 정확히 대조
  - session revision, asset-index revision, media revision, source 존재, SHA-256, eligibility와 segment alignment 확인
- terminal 저장 경계
  - `BEGIN IMMEDIATE` transaction 안에서 current truth를 다시 CAS 확인
  - stale이면 ready proposal을 저장하지 않고 모든 write를 rollback
  - 같은 owner token으로 proposal 없는 human reply와 manual fallback을 원자적으로 terminal 저장
- typed RightDock
  - 기준 편집본, 현재 편집본, 실제 미디어 종류, 대상 장면, 지원 설정과 적용 가능 상태 표시
  - Yujin 후보는 자동 선택하지 않고 사용자 radio 선택을 요구
  - Inspector open/close에도 Route-owned conversation/candidate/player/scroll state 유지
- 명시적 적용
  - preflight → candidate materialize → post-await route/director epoch 및 current revision 재검사
  - 선택한 한 후보만 `EditorCommandPort.applyMedia`로 적용
  - B-roll `contain/cover → fit/crop`, BGM volume/fades, SFX volume만 전달
  - Yujin direct REST apply/batch는 mutation 전에 금지
  - legacy Director apply/batch는 보존
- 재생·fallback
  - RightDock에 두 번째 audio/video player를 만들지 않고 기존 PreviewStage가 sole player
  - stale, route 이동, materialize 실패, double-click과 잘못된 source kind는 편집 mutation 0
  - Eugene이 실패해도 manual editor를 계속 사용

## TDD와 독립 검토

- RED에서 mixed deferred proposal 전체 stale, wrong source-kind UI 선택, revision/status 누락을 재현했다.
- 품질·역방향 검토에서 Yujin direct REST apply/batch 우회, 실제 asset type 위조, attestation과 terminal 저장 사이 TOCTOU, 자동 첫 후보 선택, legacy controls 누락 render crash를 추가로 재현했다.
- 각 결함은 회귀 테스트를 먼저 추가하고 최소 수정했다.
- 최종 독립 spec review와 quality·gap·reverse review는 Critical 0, Important 0, Minor 0 PASS다.
- 역방향 경로는 `Hermes typed response → fresh context recheck → media attestation → terminal CAS → exact proposal reload → typed RightDock → explicit radio/click → preflight/materialize → post-await fence → EditorCommandPort → canonical session/manifest refresh → PreviewStage`로 확인했다.

## controller 최신 검증

- focused Python: **323 passed, 1 skipped**, warning 1건
- focused frontend: **5 files / 126 tests passed**
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
- 실제 PostgreSQL/Docker 동시성 실증
- 사용자 원본 영상의 재생·청취 승인
- 실제 CapCut Desktop 실증

focused Python의 1 skip은 실제 PostgreSQL 환경 미설정 경로다. 호환 코드와 회귀 테스트는 live PostgreSQL 증거를 대신하지 않는다.

## 진행률

- B3: **완료**
- Phase B: **3/5 (60.0%)**
- creator-tools child: **3/5 (60.0%), 잔여 40.0%**
- Hermes Yujin initiative: **9/20 (45.0%), 잔여 55.0%**
- 기존 VideoBox 공식 누적: **9/22 (40.9%), 잔여 59.1% 유지**

Task 9 사람/환경 acceptance와 실제 CapCut Desktop 실증은 별도다.

## 다음 goal prompt

`B4만 진행한다. B3의 명시적 단일 media apply, current revision/route epoch, terminal CAS, manual fallback과 PreviewStage sole-player 경계를 유지한다. backend가 실제 지원하는 caption, voice/TTS, overlay, output-check control만 먼저 조사해 typed recommendation과 기존 EditorCommandPort/read-only output 경계에 연결한다. backend 미지원 OpenCut effect, 이미지 B-roll, source copy, 자동 apply, provider/API 확대, Hermes-owned Mem0, SaaS는 시작하지 않는다. RED→GREEN 뒤 독립 spec/quality/gap/reverse review와 focused backend/frontend/build/static verifier를 통과시키고 SSOT/handoff를 갱신한다.`
