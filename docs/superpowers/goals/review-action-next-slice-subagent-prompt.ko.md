# Review Action Next Slice Subagent Prompt

아래 프롬프트를 다음 구현 goal의 기본값으로 사용한다.

```text
브랜치: codex/tts-approved-runtime
저장소: D:\AI_Workspace_louis_office_50\10_workspace\65_videobox

이번 goal은 review action family를 더 빠르게 닫기 위한 다음 최소 slice 1개만 진행한다.
반드시 reuse-first, strict TDD, subagent-driven으로 진행하고, 기존 계약을 깨뜨리지 않는다.

먼저 읽을 문서:
- docs/session-context-2026-06-30-review-recommendation-approve.ko.md
- docs/development-status-2026-06-29.ko.md
- docs/implementation-plan.ko.md
- docs/development-fast-path.ko.md
- docs/superpowers/plans/2026-06-30-review-action-family-acceleration.md

현재 확인된 상태:
- approve persistence 첫 slice 완료
- approve reverse verification hardening 추가됨
- mark for manual edit는 기존 editor flow 재사용으로 연결됨
- reject persistence는 들어갔지만 timeline-local truth를 기준으로 더 좁고 안전하게 닫아야 한다
- focused/backend/frontend/build/full regression green 이력은 있으나, 새 slice 후 다시 확인해야 한다

이번 goal의 범위:
1. review action family의 다음 최소 slice 1개만 선택한다
2. 선택 우선순위는 "현재 코드 기준 가장 작은 변경"이다
3. failing test 1개부터 시작한다
4. minimal GREEN 이후 focused verification만 먼저 돌린다
5. task가 닫히면 필요한 broader verification을 다시 돌린다

현재 추천 slice:
- reject recommendation timeline-local persistence hardening

반드시 지킬 것:
- editing-session SSOT 유지
- review/output rules 유지
- Gemini fallback 유지
- provider trace audit 유지
- persistence behavior를 project-wide row truth로 다시 되돌리지 말 것
- 프런트 UI 확장은 최소로 유지
- non-target recommendation / review flag 보존 규칙을 깨뜨리지 말 것

실행 규칙:
- plan reconcile -> RED -> minimal GREEN -> focused verification -> broader verification
- reviewer는 slice green 이후에만 붙인다
- review-action 검증은 scripts/review-action-fast-path.ps1 을 우선 사용한다
- 필요하면 override pattern으로 더 좁은 RED/focused gate를 사용한다

기본 명령:
- ./scripts/review-action-fast-path.ps1 -Mode status
- ./scripts/review-action-fast-path.ps1 -Mode backend-focused
- ./scripts/review-action-fast-path.ps1 -Mode frontend-focused
- ./scripts/review-action-fast-path.ps1 -Mode broader

override 예시:
- ./scripts/review-action-fast-path.ps1 -Mode backend-focused -BackendPattern "reject_pending_recommendation"
- ./scripts/review-action-fast-path.ps1 -Mode frontend-focused -FrontendPattern "marked for manual edit"

완료 보고 형식:
- 이번에 닫은 slice
- 추가/수정한 failing test
- 바꾼 파일
- focused verification 결과
- broader verification 결과
- 남은 리스크
- 다음 최소 slice 제안 1개
```
