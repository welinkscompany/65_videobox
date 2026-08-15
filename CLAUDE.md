# 여기는 개발선이 아니다 — worktree로 옮겨서 시작하라

**이 파일은 안내판이다. 개발 지침이 아니다.**

지금 열려 있는 저장소 루트에는 `main`이 체크아웃돼 있고, **`main`은 실제 개발선보다 한참 뒤처져 있다.**
여기 있는 코드·문서를 근거로 제품 상태를 판단하면 틀린다.

## 실제 개발선

| 항목 | 값 |
|---|---|
| worktree | `.worktrees/videobox-container-compatibility` |
| branch | `codex/videobox-container-compatibility` (`codex/` 접두사는 과거 흔적이며 의미 없음) |
| 최상위 지침 | 그 worktree의 `CLAUDE.md` |

**작업 전에 그 worktree로 이동하고, 거기 있는 `CLAUDE.md`를 처음부터 읽어라.**
운영 규칙·SSOT·승인 기록·완료의 정의는 전부 그쪽에 있다. 이 파일에는 일부러 옮겨 적지 않았다 —
같은 지침을 두 벌 두었더니 두 벌이 서로 어긋났고, 그게 이 안내판이 생긴 이유다.

## 얼마나 뒤처졌는지 직접 확인하라

숫자를 여기 적어두면 그 숫자가 또 낡는다. 매번 직접 재라.

```bash
git rev-list --left-right --count main...codex/videobox-container-compatibility
git diff --name-only main codex/videobox-container-compatibility | wc -l
```

2026-08-15 기준으로 `main`은 189 커밋 뒤였고 206개 파일이 달랐다.
**제품 범위 정의가 서로 반대였다** — 이 파일의 옛 버전은 CapCut을 필수 후편집 단계로,
현재 지침은 선택적 경로로 규정한다. 낡은 쪽을 읽고 기능 범위를 판단하면 틀린 결론이 나온다.

## 이 worktree에서 조심할 것

**미커밋 작업물이 있다. 지우지 마라.**
`apps/web/src/app/OutputsPage.tsx`, `apps/web/src/features/review/TimelineReviewPage.tsx` 등
여러 파일에 커밋되지 않은 변경이 남아 있고, **그 내용은 개발선 branch에도 없다.**
정리 대상으로 추정하지 말고, `stash`·`reset`·`checkout`으로 되돌리지 마라. 필요하면 소유자에게 먼저 물어라.

**여기의 `.claude/launch.json`으로 개발 서버를 띄우지 마라.**
이 낡은 체크아웃을 서빙한다. 실제 owner 런타임은 컨테이너이며 `http://127.0.0.1:5173`이고,
`scripts/owner-ready.ps1`로 다룬다.

## 한 줄 요약

```
cd .worktrees/videobox-container-compatibility && cat CLAUDE.md
```
