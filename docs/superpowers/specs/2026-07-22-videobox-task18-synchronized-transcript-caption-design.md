# VideoBox Task 18 Synchronized Transcript and Segment-aligned Caption Design

## Goal

편집 작업판에서 대본 행, 재생 위치, 내레이션 세그먼트와 연결 자막을 같은 `segment_id`로 동기화한다. 자막 시간은 독립적으로 이동하지 않으며 기존 내레이션 세그먼트의 시작·끝을 그대로 따른다.

## Design

- `EditorViewModel`의 narration clip과 caption을 `segment_id`로 묶어 읽기 전용 `TranscriptEntry`를 만든다. caption이 없거나 시간 범위가 비정상이면 행을 만들지 않고, 새 fallback ID를 추측하지 않는다.
- 새 순수 `playbackNavigation`은 현재 초를 `[0, duration]`으로 제한하고 half-open 범위의 active segment를 결정한다. 세그먼트 경계에서는 다음 세그먼트를 우선하고, 제거된/없는 범위는 건너뛴다.
- `TranscriptPanel`은 virtual window만 DOM에 유지한다. 선택 행은 현재 재생 위치로 seek하고, timeline selection도 같은 `segment_id`로 반영한다. IME 조합 중에는 shortcut을 가로채지 않는다.
- 자막 텍스트 변경은 기존 revision-bound `updateSegmentCaption` 경로만 사용한다. 시간 변경은 Task 16 narration bounds command만 사용하며, caption-only drag/resize와 Task 17 placement mutation을 사용하지 않는다.
- `CaptionLane`은 linked caption이라는 표시만 제공한다. 편집 시간은 narration track에서만 조절한다.

## Failure and scope boundaries

- Route는 기존 revision conflict/failure 뒤 manifest 재조회 규칙을 사용한다. 자동 재시도·강제 저장·preview job은 없다.
- 포함: 대본/자막 동기화, 현재 위치 navigation, caption text save, accessibility/keyboard, 1,000 caption virtual window.
- 제외: caption timing override, caption drag/resize, asset/control/스타일 변경, provider/Hermes/Mem0, OpenCut runtime/source copy, Redux/MUI/player fork, 외부 network.

## Verification

RED→GREEN으로 active boundary, list/player/timeline sync, IME guard, caption save/conflict, virtualized 1,000 row window를 검증한다. focused Python/frontend, frontend full, production build, provenance verifier, diff check를 실행한다. 전체 Python regression은 실행하지 않는다.

## Self-review

시간 권한은 narration 한 곳에만 있고, caption text 저장은 기존 command에만 연결된다. 새 UI는 현재 manifest와 session API의 typed 경계를 우회하지 않는다.
