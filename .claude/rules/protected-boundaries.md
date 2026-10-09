# 보호 경계 (CLAUDE.md §5)

CLAUDE.md §5 에서 2026-10-09 W1428 에 원문 그대로 옮겼다. CLAUDE.md 에는 절 제목과 한 줄 안내가 남아 있다. `.claude/settings.json` 의 permissions.deny 도 같은 폴더를 막는다.

아래는 열거나 수정하지 않는다.

- `.tmp-final-fence-debug/`, `.tmp-real-video-dogfood/`, `apps/web/.tmp-real-video-dogfood/`
- 사용자 원본 영상 샘플 디렉터리 (read-only)

`artifacts/`는 **다시 만들 수 있는가**로 판단해 지운다(owner 승인 2026-08-09).
기준과 예외는 `§10.16`.
