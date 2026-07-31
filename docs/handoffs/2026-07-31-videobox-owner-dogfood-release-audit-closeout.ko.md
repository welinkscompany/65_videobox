# VideoBox owner dogfood 자동 검증 및 release audit closeout

## 결론

- 사용자가 모바일 원격 상태에서도 AI가 수행할 수 있는 자동 검증, 실제 로컬 runtime 확인, 코드리뷰·gap·역방향·전체 시스템·문서·잔재 분류의 6개 완료 gate를 수행했다.
- 사용자 원본 5개는 read-only로 유지했다. 샘플 5개 중 4개인 HEVC 원본은 Chromium에서 소리와 재생 시간은 진행해도 화면이 표시되지 않을 수 있어, source audition이 이를 감지하고 적용 후 exact 편집본 미리보기로 안내하도록 TDD로 보완했다.
- Critical/Important 미해결은 `0`이다. 임의의 깊은 custom data root가 Windows 260자 path를 넘을 수 있는 제약 1건은 기본 MVP 경로에 영향을 주지 않는 Minor 운영 제약으로 기록했다.

## 실제 범위와 결과

- `C:\Users\atgro\OneDrive\바탕 화면\영상샘플` 원본은 수정·이동·삭제하지 않았다.
- 짧은 HEVC 원본을 격리 data root에 등록해 원본/복사본 SHA-256 일치와 HTTP Range `206`, 정확한 1,024 byte 반환을 확인했다.
- H264 파생 5초 clip은 Chromium에서 `1920x1080` visible playback을 확인했다. 같은 HEVC 원본은 dimensions `0x0`으로 검출되어 새 안내 경로를 사용한다.
- 기존 loop/crop/audio 600초 final MP4 3개는 H264/AAC `1080x1920`, SRT, timeline, editing session, CapCut draft를 역방향으로 확인했다.
- 짧은 격리 root `artifacts/ra31`에서 voice upload, TTS listening approval, BGM/SFX, B-roll, caption/SRT, overlay, loop, final과 CapCut draft를 fresh smoke로 재생성했다.
- 로컬 VideoBox `/projects`, 인증 전 Hermes `/login`을 Chromium으로 확인했고 console error, failed request, external request는 모두 `0`이었다.
- 실제 CapCut Desktop `9.0.0.3858`에서 VideoBox 10분 프로젝트를 열어 narration/TTS, BGM, SFX, caption/text track 표시를 확인했다. 편집·export는 하지 않았다.

## 검증

- 전체 Python: **2640 passed, 47 skipped**
- 전체 frontend: **52 files / 727 passed**
- 자동 Chromium editor E2E: **35/35 passed**
- production build: PASS
- Editor UI OSS provenance/UI-system: PASS
- Hermes runtime/profile/plan static verifier: PASS
- non-live memory smoke: external network/provider call `0`
- `git diff --check`: PASS

첫 E2E 병렬 실행에서 전체 Python 부하와 겹쳐 exact-preview 1개가 component mount 전 5초 timeout으로 실패했다. 부하가 사라진 뒤 isolated **5/5**, 전체 **35/35**를 다시 실행해 최종 통과를 확인했다. 기존 Starlette multipart warning과 500kB bundle warning은 비실패 출력이다.

## 보존·제외 경계

- `artifacts/owner-dogfood-20260731`, `artifacts/release-audit-20260731-smoke`, `artifacts/ra31`은 검증 증거로 보존하며 Git 추적 대상이 아니다.
- `.tmp-final-fence-debug/`, `.tmp-real-video-dogfood/`, `apps/web/.tmp-real-video-dogfood/`는 기존 범위 밖 보호 잔재이므로 stage/remove/delete하지 않는다.
- `.env.container`가 없어 인증된 Hermes provider 실대화와 live Mem0 add/search/delete는 실행하지 않았다.
- AI가 CapCut 프로젝트를 실제로 연 것은 runtime 증거다. 사람의 영상·음악·효과음 취향, 청취 품질, 저작권/게시 승인, 최종 export acceptance를 대신하지 않는다.

## 진행률과 다음 goal prompt

- Hermes Yujin 기술 initiative: **20/20 (100.0%)**
- VideoBox 공식 누적: **9/22 (40.9%)**
- 잔여: **59.1%**

다음 goal prompt:

`VideoBox만 작업해. 지정된 container-compatibility worktree와 branch만 사용하고 보호된 untracked 폴더와 사용자 영상 원본은 절대 stage/remove/delete하지 마. 먼저 최신 status §317과 2026-07-31 owner dogfood release-audit handoff를 읽어. 사용자가 데스크톱으로 복귀하면 fresh 600초 대표 결과물의 영상·BGM·SFX·TTS·caption을 직접 보고 듣는 Task 9 사람 acceptance를 기록하고 실제 CapCut에서 edit/export 결과를 확인해. 인증 정보가 별도로 준비된 경우에만 Hermes provider 실대화와 live Mem0 canary를 local/test external-call 경계 안에서 수행해. 사람 승인과 인증 live 검증을 자동 테스트로 대체하거나 통과로 주장하지 마.`
