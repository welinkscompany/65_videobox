# VideoBox 유진 편집 전용 범위 closeout

**날짜:** 2026-07-20
**브랜치:** `codex/videobox-container-compatibility`
**범위:** static/offline contract only

## 확정한 제품·에이전트 범위

VideoBox는 영상 편집·검수·CapCut 인계에 집중한다. 유진은 하나의 `yujin-video-director`이며, 선택된 프로젝트의 제한된 상태를 읽어 짧은 한국어 상태 안내·질문·실행 없는 편집 제안만 한다.

대본, 제목, 썸네일, 추천 영상, 영상 주제, 커버 이미지, 영상 설명, 해시태그 생성·제안은 현재 제품 범위 밖이다. 이 표현들은 user request와 model candidate response 모두에서 fail-closed로 거부한다.

## 고정된 유진 설정

- Prompt/policy: `yujin-prompt-v2` / `yujin-policy-v2`, pinned SHA-256 manifest
- Soul: `video_director_read_only`, `non_authorizing`
- User preferences: `ko`, `short_action_oriented`, memory opt-in `false`, scope `none`, retention `0`
- Skills: `describe_project_status`, `interview_video_goal`, `propose_without_action` — 모두 response declaration이며 executor 권한 없음
- MCP: declaration-only `get_project_status` 하나, 기본 deny, invocation 없음

Provider/OAuth/Hermes MCP transport, DB/API route, memory storage, mutation/render/export, CapCut/host bridge는 시작하지 않았다. external/Gemini provider call은 0이다.

## 검증

- TDD RED: 기본 세 표현과 동의어 우회(영상 추천·주제·커버 이미지·설명·해시태그), 고정 system prompt 범위 누락을 확인한 뒤 보완
- focused: profile/package/gateway/approval/capability `111 passed` (기존 Starlette multipart warning 1)
- `compileall`, `git diff --check` 통과
- 현재 worktree production Docker build 통과
- `--network none --read-only` container import 통과
- 독립 품질 재검토: `Critical 0 / Important 0`
- 전체 Python suite: 64초 timeout으로 종료되어 full-pass로 주장하지 않음

## 상태와 다음 경계

Task 9 사람/환경 acceptance는 별도이며 **9/22 (40.9%)**를 유지한다. 다음 작업은 이 static 유진 설정을 실제 provider나 tool에 연결하는 일이 아니다. OAuth, provider, Hermes network, memory storage, API route, mutation/render/export는 각각의 별도 gate와 명시적 범위 승인이 있기 전까지 비활성으로 유지한다.
