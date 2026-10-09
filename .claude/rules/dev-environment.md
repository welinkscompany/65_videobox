# 개발 환경 (CLAUDE.md §3)

CLAUDE.md §3 에서 2026-10-09 W1428 에 원문 그대로 옮겼다. CLAUDE.md 에는 절 제목과 한 줄 안내가 남아 있다.

- **작업은 메인 체크아웃(`D:\...\65_videobox`, 브랜치 `main`)에서 직접 한다**(2026-09-19).
  이전엔 별도 활성 worktree(`.worktrees/videobox-container-compatibility`,
  브랜치 `codex/videobox-container-compatibility`)가 있었지만, main과 완전히
  합쳐진 뒤 지웠다 — 더는 존재하지 않는다.
- 병렬 작업이 필요하면 그때그때 격리된 worktree(`.claude/worktrees/agent-*`류)를
  새로 만들어 쓰고, 끝나면 병합 후 지운다. 상시 유지하는 "활성 worktree"는 없다.
- **main은 개발선과 합쳐져 있다(2026-09-07, 이후 계속 유지).** 뒤처짐을 다시
  키우지 마라(`§10.21`) — 별도 worktree에서 오래 작업하다 main에 안 합치면
  다시 벌어진다.
- backend 검증은 반드시 `.venv/Scripts/python.exe -m pytest`를 쓴다. bare `pytest`나
  시스템 Python 결과는 근거로 쓰지 않는다.
- 컨테이너 스택은 `scripts/owner-ready.ps1`로 조작한다. 직접 `docker compose`를 치지 않는다.
- `.env.container`는 gitignore 대상이다. 실제 credential을 커밋하지 않는다.
- 나머지 명령·주소·스크립트는 `docs/development-fast-path.ko.md` `## 11`.
