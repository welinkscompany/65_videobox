# VideoBox handoff — 2026-07-11 production-readiness blocker slice 1

## 현재 상태

- 브랜치: `codex/production-readiness-blocker-slice-1`
- 구현 closeout: `2c033be feat: close production readiness blocker slice 1`
- 이 handoff commit은 closeout 이후 기록 전용이다.
- worktree는 handoff commit 이후 clean 상태여야 한다.

## 완료한 범위

1. 빈 첫 화면에서 프로젝트 생성, narration/script ingest, 실패 항목별 retry, 새로고침 뒤 기존 프로젝트의 소스 재등록 진입점을 구현했다.
2. 실제 asset 없는 BGM recommendation은 timeline media clip에 자동 적용하지 않는다.
3. final render/real CapCut draft의 nullable failure artifact와 UI recovery/ErrorBoundary를 처리한다.
4. partial regeneration caption은 candidate timeline, SRT, final MP4 subtitle stream까지 유지한다.
5. short B-roll/TTS는 FFmpeg loop/pad/trim, CapCut draft B-roll repetition/persistent silence material로 target duration을 채운다.
6. export overlay text/image는 FFmpeg frame과 real CapCut draft material에 반영한다.

## 최신 검증 근거

- frontend: `Push-Location apps\\web; npm test -- --run; npm run build; Pop-Location` → 82 passed, build success.
- backend: `& .\\.venv\\Scripts\\python.exe -m pytest -q -p no:cacheprovider` → Python 3.12.10, 621 passed.
- real Korean smoke: `tmp\\production-readiness-smoke-korean-rerun` 아래의 final MP4가 600.000초이며 SHA-256은 `45e430cae559e94b0b62eb2bf5f8178f74c0472a9fbadebb134ccb9bf9425c79`다.
- fixture: `D:\\AI_Workspace_louis_office_50\\20_project\\65_videobox-project\\smoke_sources\\production-readiness-korean-10m.wav`, 600.000초, SHA-256 `a0c7f05a7052be735dce56df38a45ae167a9b24cad122a3c518ef9025701ee0f`.
- smoke는 ingest, assetless BGM exclusion, edit/approval, revised SRT, MP4 duration, overlay frame change, observable B-roll loop, muxed MP4 subtitle, artifact hash를 검증한다.

## 남은 제품 작업

전체 implementation milestone 39개 중 36 완료, 3 부분이다. strict 92.3%, partial=0.5 weighted 96.2%다.

부분 항목:

- 개인 음성 clone TTS 품질 acceptance
- SFX recommendation/선택/output materialization
- 다중 10분 프로젝트의 실제 CapCut open/edit/export UX QA

## 다음 세션 첫 행동

새 기능을 섞지 말고 personal voice TTS acceptance slice의 설계와 RED contract부터 시작한다. provider 품질 기준, 실패 fallback, target duration, operator review, 10분 프로젝트 sample acceptance를 명시한다.
