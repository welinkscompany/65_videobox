# VideoBox Task 23A HEVC browser-preview proxy closeout

## 쉬운 말 요약

이제 편집기에서 HEVC 영상을 눌러도 검은 화면에 머물지 않는다. VideoBox가 그 영상을 실제 적용하거나 원본을 바꾸지 않고, 브라우저가 볼 수 있는 가벼운 H264 미리보기 파일을 한 번 만든 뒤 재사용한다. 이미 브라우저가 볼 수 있는 영상과 음악·효과음·이미지는 기존처럼 바로 연다.

## 실제 구현 범위

- `raw_video`와 `broll_video`만 preview 준비 API를 사용할 수 있다.
- 원본이 MP4/H264/yuv420p/AAC 또는 무음이면 변환 job 없이 기존 content URL을 반환한다.
- HEVC 등 비호환 영상은 H264/yuv420p/AAC/faststart, 긴 변 1280 이하의 project-local cache를 만든다.
- 같은 source SHA/profile의 동시 요청은 durable job 하나만 실행한다. 서버 재시작 중 멈춘 job은 failed로 복구되고 사용자가 다시 준비할 수 있다.
- 출력 게시 직전에 source stat/SHA와 출력 codec/크기를 다시 검사한다. 원본 revision이 바뀌면 낡은 프록시를 current로 제공하지 않는다.
- Route가 start/poll/AbortSignal/route epoch를, Workbench가 최신 클릭 sequence와 카드별 상태를 소유한다. `PreviewStage`는 계속 유일한 player다.
- 실패해도 자산 적용, 수동 편집, 정확한 편집본 미리보기 갱신을 계속할 수 있다.

## 검증 근거

- 관련 backend: `81 passed`, 기존 multipart warning 1건.
- frontend focused: `7 files / 231 passed`.
- frontend full: `52 files / 733 passed`.
- production build 성공. 기존 500kB chunk warning만 남았다.
- Editor UI OSS provenance verifier와 `git diff --check` 성공.
- 합성 HEVC 자동 verifier 성공: HEVC→H264/yuv420p, Range 206, source 불변, external provider call 0.
- 사용자 read-only 샘플 `20260612_091959.mp4` 실제 성공: HEVC/AAC 10.33초→H264/yuv420p, Range 206, source size/mtime/SHA 불변.
- PostgreSQL 실DB atomic claim test는 `VIDEOBOX_TEST_POSTGRES_URL` 부재로 1개가 명시적으로 skip됐다.
- 전체 Python regression은 실행하지 않았고 통과로 주장하지 않는다.

## 리뷰와 경계

spec/quality/gap/reverse review에서 API 상태를 durable `pending/running`과 맞추고, same-origin 요청의 redirect 외부 이탈을 막았다. 성공 job의 cache 파일이 사라져도 거짓 `ready`를 반환하지 않고 `PREVIEW_CACHE_MISSING`으로 재시도하게 했다. 실제 한글 샘플에서 발견한 UTF-8 ffprobe 디코딩과 Windows 260자 임시 경로 문제도 보완했다. 최종 open Critical/Important는 0이다.

source copy, OpenCut runtime, 외부 provider/API, Hermes, Mem0, SaaS, 게시, 자동 apply는 추가하지 않았다. 사용자 샘플 원본과 보호된 `.tmp-final-fence-debug/`, `.tmp-real-video-dogfood/`, `apps/web/.tmp-real-video-dogfood/`는 stage/remove/delete하지 않았다.

## 진행률과 다음 goal

Task 23 production slice는 **1/4 (25.0%)**, 잔여 **75.0%**다.

다음 goal prompt:

> Task 23B owner one-click 실행·진단을 진행해. 기본 Check는 read-only로 현재 worktree/도구/FFmpeg/Docker/Compose/loopback health/data-root/path headroom을 쉬운 말로 진단하고, Start·Smoke·Open·OpenCapCut은 명시적 모드로 분리해. credential 생성·출력, provider/Mem0 실호출, 기존 project mutation은 금지하고 TDD→리뷰→focused 검증→문서→커밋·푸시까지 닫아.
