# VideoBox Task 22 release parity closeout handoff

## 쉬운 요약

VideoBox의 새 화면에서 프로젝트 생성부터 영상 편집, BGM·효과음·TTS·자막, 최종 MP4와 CapCut 초안 생성까지 이어지는 기술 경로를 닫았다.

자동 테스트는 버튼이 보이는지만 확인한 것이 아니다. 10분짜리 타임라인을 실제 FFmpeg로 렌더하고, BGM 볼륨·페이드·더킹, 효과음, B-roll 반복·크롭·패딩, 이미지 오버레이, 수정 자막, 승인된 TTS가 최종 MP4와 CapCut 초안에 들어가는지 확인했다.

오래된 편집 revision이나 과거 승인 결과가 최신 출력으로 잘못 보이지 않도록 editing session, review, subtitle, final, CapCut이 같은 session/revision을 가리키는지도 확인했다. Windows에서 경로가 길 때 실패하던 임시 파일·폴더 이름도 짧게 고쳤다.

중단된 final/CapCut worker 재개와 thread 시작 실패 복구는 현재 로컬 단일 API 프로세스 범위다. 여러 API 프로세스를 동시에 운영하는 분산 worker lease까지 지원한다고 주장하지 않는다.

## 실제 범위

- canonical editor/output route parity와 legacy owner 제거 후 전체 release audit
- current-revision TTS apply/clear, BGM/SFX edit·clear, rejected SFX 재등장 방지
- subtitle/final/CapCut source-session lineage와 review/freshness publish fence
- SQLite/PostgreSQL publish lock, final-render/CapCut 중단 worker와 thread-start 실패 복구, migration/backfill
- one-player ownership, route epoch, manual fallback, local/test external call 0
- 600초 smoke와 `loop`/`crop_pad_overlay`/`audio_ducking` 3프로필 FFmpeg/PyCapCut QA

제외한 것은 source copy, OpenCut runtime, provider/API 확장, Hermes, Mem0, cloud/billing, 자동 apply다.

## 검증

- focused frontend: `6 files / 161 passed`
- full frontend: `49 files / 581 passed`
- full Playwright E2E: `34 passed`, snapshot manifest verifier passed
- production build: passed; 기존 500 kB bundle warning은 비실패 출력
- current-focused: backend output `24 passed`, backend preflight `59 passed`, frontend preflight `5 passed`
- Editor UI OSS provenance/UI-system verifier: passed
- external-runtime/network guard: `2 files / 6 passed`
- package-lock CycloneDX SBOM: `272 components`
- 최종 full Python: `1559 passed, 20 skipped`; final-render worker 복구 RED→GREEN/wiring `4 passed`, 관련 회귀 `34 passed`
- `./scripts/dev-fast-path.ps1 -Mode smoke`: passed
- `./scripts/dev-fast-path.ps1 -Mode long-form-capcut-qa`: 3 profiles passed
- independent spec/quality/gap/reverse review: final open Critical/Important 0
- `git diff --check`: closeout 직전 재실행

기존 React `act(...)`, jsdom navigation, intentional ErrorBoundary stderr, Starlette multipart deprecation, bundle size warning은 exit 0인 비실패 출력이다.

## 실제 산출물과 역방향 확인

- smoke final: `artifacts/task5-smoke/projects/projects/production-readiness-korean-smoke-loop/exports/final_render/export_001/output.mp4`
- smoke final SHA-256: `a0d7d4ae5f2ef768b7e58385bb6b88086c68bc9141d69758eb1a27632e5007d9`
- long-form root: `artifacts/lfqa/`
- `loop`, `crop_pad_overlay`, `audio_ducking` 프로필의 artifact directory 별칭은 각각 `loop`, `crop`, `audio`다. 세 final은 모두 1080×1920, video/audio 600초다.
- 세 프로필의 current SRT/final/CapCut row는 각각 같은 `editing_session_001`, `timeline_002`, revision 8 또는 9를 가리킨다.
- audio 프로필은 BGM gain/fade/ducking과 SFX/TTS를 확인했다. CapCut native ducking 미지원은 가져온 뒤 수동 적용 경고로 남긴다.

## 아직 사람이 해야 하는 것

자동 검증은 실제 귀로 듣는 품질 판단과 실제 CapCut Desktop 조작을 대신하지 않는다.

- 사용자 원본 영상의 권리 확인
- 복사본 프로젝트에서 current-revision 영상을 직접 재생·청취하고 승인
- 실제 CapCut Desktop에서 같은 revision 초안을 열어 import/edit/export 확인
- Task 9 사람/환경 acceptance

공식 누적은 사용자 지시대로 **9/22 (40.9%)**, 잔여 **59.1%**다.

보호된 `?? .tmp-final-fence-debug/`, `?? .tmp-real-video-dogfood/`, `?? apps/web/.tmp-real-video-dogfood/`, QA artifacts와 사용자 원본 샘플은 stage/remove/delete하지 않는다.

## 다음 goal prompt

`VideoBox만 작업해. D:\AI_Workspace_louis_office_50\10_workspace\65_videobox\.worktrees\videobox-container-compatibility와 codex/videobox-container-compatibility만 사용해. AGENTS.md, development-fast-path §10, development-status §300, implementation-plan current next goal, docs/handoffs/2026-07-24-videobox-task22-release-parity-closeout.ko.md를 먼저 읽고 branch/HEAD/upstream/status/worktree/diff-check를 확인해. 보호된 임시 폴더 3개와 C:\Users\atgro\OneDrive\바탕 화면\영상샘플 원본은 절대 stage/remove/delete하지 마. 다음은 새 기능 개발이 아니라 owner dogfood다. 원본을 read-only로 두고 복사본 프로젝트에서 대표 영상 하나를 ingest해 B-roll/BGM/SFX/TTS/caption을 직접 적용하고 current-revision exact/final을 재생·청취 승인해. 그 다음 같은 revision의 CapCut draft를 실제 CapCut Desktop에서 열어 import 결과를 기록해. 자동 검증을 사람 승인으로 과장하지 말고 provider/Hermes/Mem0/cloud/자동 apply 범위를 넓히지 마. 공식 누적은 9/22 (40.9%), 잔여 59.1%를 유지해.`
