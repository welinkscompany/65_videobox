#!/usr/bin/env bash
# SessionStart hook -- reports git worktree sync status against main so
# finished/stale worktrees don't sit unnoticed for days (2026-09-19: found
# ~15 leftover .claude/worktrees/agent-* dirs, one holding a full day of
# unmerged work). Read-only: only prints a summary, never deletes or merges.
set -u
cd "${CLAUDE_PROJECT_DIR:-$PWD}" || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
git show-ref --verify --quiet refs/heads/main || exit 0

toplevel="$(git rev-parse --show-toplevel)"
merged=() unmerged=() dirty=()

while IFS= read -r path && IFS= read -r branch; do
  [ "$path" = "$toplevel" ] && continue
  branch="${branch#refs/heads/}"
  [ -z "$branch" ] && continue
  if [ -n "$(git -C "$path" status --porcelain 2>/dev/null)" ]; then
    dirty+=("$branch")
  elif git merge-base --is-ancestor "$branch" main 2>/dev/null; then
    merged+=("$branch")
  else
    unmerged+=("$branch")
  fi
done < <(git worktree list --porcelain 2>/dev/null | awk '
  /^worktree /{p=substr($0,10)}
  /^branch /{b=substr($0,8); print p; print b; p=""; b=""}
  /^detached$/{if (p != "") {print p; print ""; p=""}}
')

total=$((${#merged[@]} + ${#unmerged[@]} + ${#dirty[@]}))
[ "$total" -eq 0 ] && exit 0

join() { local IFS=", "; echo "$*"; }

msg="git worktree 동기화 점검 (main 기준):"
[ ${#merged[@]} -gt 0 ] && msg="$msg 이미 main에 merge됨(정리 후보, ${#merged[@]}개: $(join "${merged[@]}"))."
[ ${#unmerged[@]} -gt 0 ] && msg="$msg main에 없는 고유 커밋 있음(검토 후보, ${#unmerged[@]}개: $(join "${unmerged[@]}"))."
[ ${#dirty[@]} -gt 0 ] && msg="$msg 미변경 상태 아님(손대지 말 것, ${#dirty[@]}개: $(join "${dirty[@]}"))."

python_bin=""
for p in "$toplevel/.venv/Scripts/python.exe" "$toplevel/.venv/bin/python" python3 python; do
  command -v "$p" >/dev/null 2>&1 && { python_bin="$p"; break; }
done
if [ -n "$python_bin" ]; then
  "$python_bin" -c 'import json,sys; print(json.dumps({"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":sys.argv[1]}}))' "$msg"
else
  esc="${msg//\\/\\\\}"; esc="${esc//\"/\\\"}"
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$esc"
fi
