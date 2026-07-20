# VideoBox 유진 v3 prompt·Soul·user input audit closeout

**날짜:** 2026-07-20
**브랜치:** `codex/videobox-container-compatibility`
**범위:** static/offline contract only

## 확인·보완된 설정

- Prompt/policy: `yujin-prompt-v3` / `yujin-policy-v3`, pinned manifest SHA-256
- Soul: `video_director_read_only`, `non_authorizing`
- User preference: `ko`, `short_action_oriented`, memory opt-in `false`, scope `none`, retention `0`
- User text: `system → developer → task → user` 고정 순서의 별도 untrusted data이며 policy·Soul·tool·memory 권한을 바꾸지 못함
- 허용: 선택 project의 allowlisted 상태 설명, 편집 관련 질문, 실행 없는 제안
- 거부: 직접 편집 실행, approval, render/export, CapCut, memory, credential, 다른 project 및 대본·제목·썸네일·추천 영상·주제·커버 이미지·영상 설명·해시태그 제작

제작 요청 deny 판정은 NFKC 정규화 뒤 공백·기호를 제거해 적용하므로 `썸 네 일`, `커버-이미지`, 전각 `Ｔｈｕｍｂｎａｉｌ` 같은 표기도 우회하지 못한다. 제목·타이틀은 생성·추천·제안·작성·후보·개수·짓기·고르기 의도와 결합할 때만 차단한다. 따라서 `유튜브 쇼츠용 첫 장면을 2초 줄여줘`와 한국어·영어 `제목 카드/title card` 길이·정렬 편집은 실행 없는 제안을 허용한다. 같은 문장에 별도의 영상 제목 후보·추천이 있으면 차단한다. request와 model candidate response 모두 동일한 분류를 사용한다.

## 검증

- TDD RED: 정책 문구/허용 skill 불일치, 공백·기호·전각 우회, bare `제목`/`유튜브` 편집 문맥 false-positive, `타이틀` 동의어 false-negative, 제목 후보·개수·짓기·고르기 의도, 한국어/영어 제목 카드 편집 예외 재현
- focused profile/package/gateway/approval/capability: `130 passed` (기존 Starlette multipart warning 1)
- compileall, static v3 package import, production Docker build 통과
- container `--network none --read-only` import 통과
- 독립 품질 재검토: `Critical 0 / Important 0`
- Python 전체 suite: 64초 timeout으로 종료되어 full-pass로 주장하지 않음

provider/OAuth/Hermes network, MCP transport, DB/API route, memory storage, mutation/render/export, CapCut/host bridge는 시작하지 않았다. external/Gemini provider call은 0이다.

## 다음 권장 작업 — Task 9 사람/환경 acceptance

자동으로 진행할 수 없는 사람/환경 gate다. `B-roll Smoke Test`의 두 번째 장면에 실제 MP4를 추가하고 readiness를 다시 준비한 뒤, current-revision 합성 MP4를 사용자가 재생·승인해야 한다. 이어 대상 Windows PC의 실제 CapCut Desktop handoff 등록·열기·import 결과를 기록한다. 두 gate 전에는 Task 9를 완료 처리하거나 **9/22 (40.9%)** 진행률을 올리지 않는다.
