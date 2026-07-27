# VideoBox Hermes Yujin B4 supported controls closeout

## 쉬운 말 요약

B4에서는 유진이 자막 문구와 모양, 이미 듣고 승인한 TTS 음성, 설명·이미지·표 오버레이를 추천할 수 있게 했다. 추천이 화면에 나타나도 편집은 바뀌지 않으며, 사용자가 radio로 하나를 고르고 적용 버튼을 눌러야 기존 VideoBox 편집 명령이 한 번 실행된다.

출력 검사는 현재 타임라인의 빈 구간 수만 읽기 전용으로 보여 준다. 모델이 “출력 준비 완료”라고 써도 검사 결과에는 사용하지 않으며, 검사 카드에는 Apply가 없다. 미지원 효과, 임의 음성 생성, 자동 적용은 열지 않았다.

## 작업 위치와 기준

- worktree: `D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility`
- branch/upstream: `codex/videobox-container-compatibility` / `origin/codex/videobox-container-compatibility`
- B4 시작 HEAD: `b51ee9cd27d0dd01884c7b091857b0aae200ee9a`
- 기존 untracked 세 경로는 열거나 stage/remove/delete하지 않았다.

## 실제 구현 범위

- 자막
  - current segment 문구 변경
  - `current_caption` 범위의 완전한 11필드 스타일
  - 독립 timing과 top/middle/bottom placement는 거부
- 음성
  - persisted `tts_candidate_*`
  - technical `accepted`, listening review `approved`
  - exact segment/asset/type/revision/SHA를 context와 terminal에서 재검증
  - free-text 합성, speed, sample/provider 직접 선택은 거부
- 오버레이
  - explanation-card `title/body/text`
  - image `asset_id/text`
  - table `columns/rows/text`
  - image는 실제 project image type/source/revision/SHA를 재검증
  - x/y/opacity와 generic effect payload는 거부
- output
  - current playback의 `timeline_gaps`만 backend가 다시 계산
  - 모델 preview 문구 폐기
  - read-only 카드에는 radio/Apply/render/export 호출 없음
- 적용 경계
  - Yujin 초기 선택 없음
  - explicit radio 한 개 → preflight → route/director epoch와 revision fence
  - 기존 typed `EditorCommandPort` 명령 정확히 한 개
  - B3+B4 mixed mode에서도 B3 media만 preview/materialize
  - B4 후보와 forged actual asset type은 422, asset copy 0
  - legacy Director와 sole PreviewStage 유지

## TDD와 독립 검토

- 최초 backend RED는 **17 failed / 6 passed**, frontend RED는 **8 failed / 86 passed**였다.
- spec review에서 untrusted output 문구, terminal exact payload 재검증 누락, Hermes skill overlay `text` 누락 3건을 찾고 TDD로 수정했다.
- quality·gap·reverse review에서 gateway TTS DTO drift, terminal gap SSOT 불일치, generalized mixed-mode materialize guard 우회 3건을 real-store/API로 재현하고 수정했다.
- 최종 독립 spec review와 quality·gap·reverse review는 Critical 0, Important 0, Minor 0 PASS다.
- 역방향 경로는 `typed response → fresh context → strict gateway attach → activation → terminal CAS → reload → RightDock mutation 0 → explicit radio → preflight/epoch/revision fence → one EditorCommandPort mutation → session/manifest refresh → sole PreviewStage`로 확인했다.

## controller 최신 검증

- focused Python: **373 passed, 1 skipped**, warning 1건
- 전체 frontend: **50 files / 648 passed**
- production build: 통과
- Hermes profile/runtime static verifier: 통과
- Hermes 20-ID plan-state verifier: 통과
- Hermes zero-tools verifier: 통과
- Editor UI OSS provenance/UI-system verifier: 통과
- provenance Python: **21 passed**
- `git diff --check`: 통과

warning 1건은 기존 Starlette multipart pending deprecation이다. frontend의 React `act(...)`, jsdom navigation, intentional ErrorBoundary stderr와 build의 500 kB chunk warning은 exit 0인 기존 비실패 출력이다.

## 실행하지 않은 검증

- 전체 Python regression
- editor Playwright E2E
- live provider canary
- 실제 Hermes service-stop/manual environment proof
- 실제 PostgreSQL/Docker integration
- 사용자 원본 영상의 재생·청취 승인
- 실제 CapCut Desktop 실증

## 진행률

- B4: **완료**
- Phase B: **4/5 (80.0%)**
- creator-tools child: **4/5 (80.0%), 잔여 20.0%**
- Hermes Yujin initiative: **10/20 (50.0%), 잔여 50.0%**
- 기존 VideoBox 공식 누적: **9/22 (40.9%), 잔여 59.1% 유지**

Task 9 사람/환경 acceptance와 실제 CapCut Desktop 실증은 별도다.

## 다음 goal prompt

`B5만 진행한다. B4까지의 typed supported-control, terminal/gateway CAS, explicit single Apply, manual fallback과 PreviewStage sole-player 경계를 유지한다. explicit Apply 전 mutation 0, Inspector close/open conversation·selection·player·scroll state 보존, stale materialize/route change/Hermes stopped/output-not-ready의 mutation 0을 UI/E2E로 먼저 고정한다. fake Hermes response와 real local VideoBox API/store를 쓰는 non-live creator smoke로 typed response→proposal→explicit Apply→preview manifest→기존 output route 역방향을 증명한다. 전체 Python/frontend, editor E2E, build, profile/runtime/plan/zero-tools/provenance verifier와 독립 spec/quality/gap/reverse review를 통과해 Phase B를 closeout한다. -Live smoke는 별도 local Hermes/provider credential이 준비된 경우에만 실행하며 source media를 덮어쓰지 않는다.`
